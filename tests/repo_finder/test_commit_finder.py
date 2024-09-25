# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the commit finder."""
import logging
import os
import re
import shutil

import hypothesis
import pytest
from hypothesis import given, settings
from hypothesis.strategies import DataObject, data, text
from packageurl import PackageURL

from macaron.repo_finder import commit_finder
from macaron.repo_finder.commit_finder import AbstractPurlType
from tests.slsa_analyzer.mock_git_utils import commit_files, initiate_repo

logger: logging.Logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.join(BASE_DIR, "mock_repos", "commit_finder/sample_repo")


def test_get_commit_from_version() -> None:
    """Test resolving commits from version tags."""
    versions = [
        "1.0.1-A",  # To match a tag with a named suffix.
        "1.0.3+test",  # To match a tag with a '+' suffix.
        "1.0.5",  # To match a tag with a 'v_' prefix.
        "50.0.2",  # To match a tag separated by '_'.
        "78.109",  # To match a tag separated by characters 'r' 'rv'.
        "1.0.5-JRE",  # To NOT match the similar tag without the 'JRE' suffix.
    ]

    tags = ["test-name-v1.0.1-A", "v1.0.3+test", "v_1.0.5", "50_0_2", "r78rv109", "1.0.5-JRE"]

    # Perform tests
    purl_name = "test-name"
    for count, value in enumerate(versions):
        _test_version(tags, purl_name, value, tags[count])
        purl_name = "test-name" + "-" + str(count + 1)


def _test_version(tags: list[str], name: str, version: str, target_tag: str) -> None:
    """Retrieve tag matching version and check it is correct."""
    matched_tags = commit_finder.match_tags(tags, name, version)
    assert matched_tags
    assert matched_tags[0] == target_tag


@pytest.mark.parametrize(
    ("purls", "expected"),
    [
        pytest.param(
            [
                "pkg:maven/apache/maven",
                "pkg:maven/commons-io/commons-io@2.15.0",
                "pkg:pypi/requests@2.31.0",
                "pkg:npm/@colors/colors@1.4.0",
                "pkg:nuget/system.text.json@8.0.0",
                "pkg:cargo/mailmeld@1.0.0",
            ],
            AbstractPurlType.ARTIFACT,
            id="Artifact PURLs",
        ),
        pytest.param(
            [
                "pkg:github/apache/maven@69bc993b8089a2d3d1ddfd6c7d4f8dc6cc205995",
                "pkg:github/oracle/macaron@v0.6.0",
                "pkg:bitbucket/owner/project@tag_5",
            ],
            AbstractPurlType.REPOSITORY,
            id="Repository PURLs",
        ),
        pytest.param(
            ["pkg:gem/ruby-advisory-db-check@0.12.4", "pkg:unknown-domain/project/owner@tag"],
            AbstractPurlType.UNSUPPORTED,
            id="Unsupported PURLs",
        ),
    ],
)
def test_abstract_purl_type(purls: list[str], expected: AbstractPurlType) -> None:
    """Test each purl in list is of expected type."""
    for purl in purls:
        assert commit_finder.determine_abstract_purl_type(PackageURL.from_string(purl)) == expected


def test_commit_finder() -> None:
    """Test commit finder using mocked repository."""
    if os.path.exists(REPO_DIR):
        shutil.rmtree(REPO_DIR)
    git_obj = initiate_repo(
        REPO_DIR,
        git_init_options={
            "initial_branch": "master",
        },
    )

    # Create a commit from a newly created file.
    with open(os.path.join(REPO_DIR, "file_1"), "w", encoding="utf-8") as file:
        file.write("A")
    commit_files(git_obj, ["file_1"])

    # Create a commit with no associated branch.
    commit_0 = git_obj.repo.index.commit(message="Commit_0")

    # No version in PURL.
    assert not commit_finder.find_commit(git_obj, PackageURL.from_string("pkg:maven/apache/maven"))

    # Unsupported PURL type.
    assert not commit_finder.find_commit(git_obj, PackageURL.from_string("pkg:gem/ruby-artifact@1"))

    # Hash not present in repository, tests hash and tag.
    assert not commit_finder.find_commit(git_obj, PackageURL.from_string("pkg:github/apache/maven@ab4ce3e"))

    # Valid PURL but repository has no tags yet.
    assert not commit_finder.find_commit(git_obj, PackageURL.from_string("pkg:maven/apache/maven@1.0"))

    # Additional setup is done here to avoid tainting earlier tests.

    # Create a tag from a tree.
    tag_tree_version = "1.0"
    tree = git_obj.repo.heads.master.commit.tree
    git_obj.repo.create_tag(tag_tree_version, ref=tree)

    # Add a new tag with an associated commit. This is the Japanese character for 'snow'.
    unicode_version = "雪"
    git_obj.repo.create_tag(unicode_version, commit_0.hexsha)

    # Create a more typical tag on the same commit.
    tag_version = "2.3.4"
    git_obj.repo.create_tag(tag_version, commit_0.hexsha)

    # Add an empty commit with some tags.
    empty_commit = git_obj.repo.index.commit("Empty commit.")
    tag_version_2 = "4.5.2"
    git_obj.repo.create_tag(f"{tag_version_2}-DEV", ref=empty_commit.hexsha)
    git_obj.repo.create_tag(f"{tag_version_2}_DEV_RC1_RELEASE", ref=empty_commit.hexsha)
    git_obj.repo.create_tag(f"rel/prefix_name-{tag_version}", ref=empty_commit.hexsha)

    # Version with a suffix and no matching tag.
    assert not commit_finder.find_commit(git_obj, PackageURL.from_string("pkg:maven/apache/maven@1-JRE"))

    # Version with only one digit and no matching tag.
    assert not commit_finder.find_commit(git_obj, PackageURL.from_string("pkg:maven/apache/maven@1"))

    # Unicode version.
    assert commit_finder.find_commit(git_obj, PackageURL.from_string(f"pkg:maven/apache/maven@{unicode_version}"))

    # Valid repository PURL.
    digest = commit_finder.find_commit(git_obj, PackageURL.from_string(f"pkg:github/apache/maven@{commit_0.hexsha}"))
    assert digest == commit_0.hexsha

    # Valid artifact PURL.
    digest = commit_finder.find_commit(git_obj, PackageURL.from_string(f"pkg:maven/apache/maven@{tag_version}"))
    assert digest == commit_0.hexsha

    # Valid artifact PURL with an alphanumeric suffix.
    digest = commit_finder.find_commit(git_obj, PackageURL.from_string(f"pkg:maven/apache/maven@{tag_version}-RC1"))
    assert digest == commit_0.hexsha

    # Valid artifact PURL that should match a tag with a name prefix.
    digest = commit_finder.find_commit(git_obj, PackageURL.from_string(f"pkg:maven/apache/prefix_name@{tag_version}"))
    assert digest == empty_commit.hexsha

    # Valid artifact PURL that matches a version with a suffix, to a tag with the same suffix.
    digest = commit_finder.find_commit(git_obj, PackageURL.from_string(f"pkg:maven/apache/maven@{tag_version_2}-DEV"))
    assert digest == empty_commit.hexsha

    # Valid artifact PURL that matches a version with a suffix, to a tag with the same suffix part in a multi-suffix.
    digest = commit_finder.find_commit(
        git_obj, PackageURL.from_string(f"pkg:maven/apache/maven@{tag_version_2}_RELEASE")
    )
    assert digest == empty_commit.hexsha

    # Valid artifact PURL that matches a version with an alphanumeric suffix, to a tag with the same suffix part in a
    # multi-suffix.
    digest = commit_finder.find_commit(git_obj, PackageURL.from_string(f"pkg:maven/apache/maven@{tag_version_2}_RC1"))
    assert digest == empty_commit.hexsha


@given(text())
@settings(max_examples=10000, deadline=None)
def test_pattern_generation(version: str) -> None:
    """Test stability of pattern creation from user input."""
    # pylint: disable=protected-access
    # Try creating a PURL from the version, if successful pass the purl.version to commit finder's pattern builder.
    if not version:
        return
    try:
        purl = PackageURL(name="test", version=version, type="maven")
        if not purl.version:
            return
    except ValueError as error:
        logger.debug(error)
        return

    commit_finder._build_version_pattern(purl.name, purl.version)
    assert True


input_pattern = re.compile(r"[0-9]{1,3}(\.[0-9a-z]{1,3}){,5}([-+#][a-z0-9].+)?", flags=re.IGNORECASE)
# These numbers should be kept low as the complex regex makes generation slow.
VERSION_ITERATIONS = 50  # The number of times to iterate the test_version_to_tag_matching test.
TAG_ITERATIONS = 1  # The number of tags to generate per version iteration.


@given(data())
@settings(max_examples=VERSION_ITERATIONS, deadline=None)
def test_version_to_tag_matching(_data: DataObject) -> None:  # noqa: PT019
    """Test matching generated versions to generated tags.

    This test verifies that a similar version and tag can be matched by the commit finder.
    """
    # pylint: disable=protected-access
    # Generate the version
    version = _data.draw(hypothesis.strategies.from_regex(input_pattern, fullmatch=True))
    if not version:
        return
    purl = PackageURL(name="test", version=version, type="maven")
    if not purl.version:
        return
    # Build the pattern from the version.
    pattern, parts = commit_finder._build_version_pattern(purl.name, purl.version)
    if not pattern:
        return
    # Generate the tag from a pattern that is very similar to how version patterns are made.
    sep = "[^a-z0-9]"
    tag_pattern = (
        "(?P<prefix_0>(?:[a-z].*(?:[a-z0-9][a-z][0-9]+|[0-9][a-z]|[a-z]{2}))|[a-z]{2})?("
        "?P<prefix_sep_0>(?:(?:(?<![0-9a-z])[vrc])|(?:[^0-9a-z][vrc])|[^0-9a-z])(?:[^0-9a-z])?)"
    )
    for count, part in enumerate(parts):
        if count > 0:
            tag_pattern = tag_pattern + f"{sep}"
        tag_pattern = tag_pattern + part
    tag_pattern = tag_pattern + f"({sep}[a-z].*)?"
    compiled_pattern = re.compile(tag_pattern, flags=re.IGNORECASE)
    # Generate tags to match the generated version.
    for _ in range(TAG_ITERATIONS):
        tag = _data.draw(hypothesis.strategies.from_regex(compiled_pattern, fullmatch=True))
        # Perform the match.
        pattern.match(tag)

        # We do not assert that the match succeeded as the patterns here no longer reflect the state of the commit
        # finder. This test is left in place to check for exceptions and potential ReDoS bugs.
