# Copyright (c) 2023 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the commit finder."""
import logging
import os
import re
import shutil
from typing import Any

import hypothesis
import pytest
from hypothesis import given, settings
from hypothesis.strategies import DataObject, data, text
from packageurl import PackageURL
from pydriller.git import Git

from macaron.repo_finder import commit_finder
from macaron.repo_finder.commit_finder import AbstractPurlType, determine_optional_suffix_index
from macaron.repo_finder.repo_finder_enums import CommitFinderInfo
from macaron.repo_finder.repo_utils import get_repo_tags
from tests.slsa_analyzer.mock_git_utils import commit_files, initiate_repo

logger: logging.Logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.join(BASE_DIR, "mock_repos", "commit_finder", "sample_repo")
UNICODE_VERSION = "雪"  # The Japanese character for "snow".
TAG_VERSION = "2.3.4"
TAG_VERSION_2 = "4.5.2"


@pytest.fixture(name="tag_list")
def tag_list_() -> list[str]:
    """Return a list of tags."""
    return ["test-name-v1.0.1-A", "v1.0.3+test", "v_1.0.5", "50_0_2", "r78rv109", "1.0.5-JRE"]


@pytest.mark.parametrize(
    ("version", "name", "tag_list_index"),
    [
        ("1.0.1-A", "test-name-1", 0),
        ("1.0.3+test", "test-name-2", 1),
        ("1.0.5", "test-name-3", 2),
        ("50.0.2", "test-name-4", 3),
        ("78.109", "test-name-5", 4),
        ("1.0.5-JRE", "test-name-6", 5),
    ],
)
def test_get_commit_from_version(version: str, name: str, tag_list_index: int, tag_list: list[str]) -> None:
    """Test resolving commits from version tags."""
    matched_tags, outcome = commit_finder.match_tags(tag_list, name, version)
    assert matched_tags
    assert matched_tags[0] == tag_list[tag_list_index]
    assert outcome == CommitFinderInfo.MATCHED


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


@pytest.fixture(name="mocked_repo")
def mocked_repo_() -> Git:
    """Create a mocked repository."""
    if os.path.exists(REPO_DIR):
        shutil.rmtree(REPO_DIR)
    git_obj = initiate_repo(
        REPO_DIR,
        git_init_options={
            "initial_branch": "master",
        },
    )
    # Disable gpg signing of tags for this repository to prevent input prompt hang.
    with git_obj.repo.config_writer() as git_config:
        git_config.set_value("tag", "gpgsign", "false")

    # Create a commit from a newly created file.
    with open(os.path.join(REPO_DIR, "file_1"), "w", encoding="utf-8") as file:
        file.write("A")
    commit_files(git_obj, ["file_1"])

    return git_obj


@pytest.fixture(name="mocked_repo_commit")
def mocked_repo_commit_(mocked_repo: Git) -> Any:
    """Add a commit to the mocked repository."""
    return mocked_repo.repo.index.commit(message="Commit_0")


@pytest.fixture(name="mocked_repo_empty_commit")
def mocked_repo_empty_commit_(mocked_repo: Git) -> Any:
    """Add an empty commit to the mocked repository."""
    return mocked_repo.repo.index.commit(message="Empty_Commit")


@pytest.fixture(name="mocked_repo_expanded")
def mocked_repo_expanded_(mocked_repo: Git, mocked_repo_commit: Any, mocked_repo_empty_commit: Any) -> Any:
    """Add tags to the mocked repository."""
    mocked_repo.repo.create_tag("4.5", mocked_repo_commit.hexsha)

    # Create a tag from a tree.
    mocked_repo.repo.create_tag("1.0", ref=mocked_repo.repo.heads.master.commit.tree)

    # Add a tag with unicode version.
    mocked_repo.repo.create_tag(UNICODE_VERSION, mocked_repo_commit.hexsha)

    # Create a more typical tag on the same commit.
    mocked_repo.repo.create_tag(TAG_VERSION, mocked_repo_commit.hexsha)

    # Add more tags.
    mocked_repo.repo.create_tag(f"{TAG_VERSION_2}-DEV", ref=mocked_repo_empty_commit.hexsha)
    mocked_repo.repo.create_tag(f"{TAG_VERSION_2}_DEV_RC1_RELEASE", ref=mocked_repo_empty_commit.hexsha)
    mocked_repo.repo.create_tag(f"rel/prefix_name-{TAG_VERSION}", ref=mocked_repo_empty_commit.hexsha)

    return mocked_repo


@pytest.mark.parametrize(
    ("purl_string", "expected_outcome"),
    [
        # No version in PURL.
        ("pkg:maven/apache/maven", CommitFinderInfo.NO_VERSION_PROVIDED),
        # Unsupported PURL type.
        ("pkg:gem/ruby-artifact@1", CommitFinderInfo.UNSUPPORTED_PURL_TYPE),
        # Hash not present in repository.
        ("pkg:github/apache/maven@ab4ce3e", CommitFinderInfo.REPO_PURL_FAILURE),
        # Valid PURL but repository has no tags yet.
        ("pkg:maven/apache/maven@1.0", CommitFinderInfo.NO_TAGS),
    ],
)
def test_commit_finder_tagless_failure(mocked_repo: Git, purl_string: str, expected_outcome: CommitFinderInfo) -> None:
    """Test commit finder using mocked repository with no tags."""
    match, outcome = commit_finder.find_commit(mocked_repo, PackageURL.from_string(purl_string))
    assert not match
    assert outcome == expected_outcome


@pytest.mark.parametrize(
    ("purl_string", "expected_outcome"),
    [
        # Invalid PURL.
        ("pkg:maven/[]@()", CommitFinderInfo.INVALID_VERSION),
        # Version with a suffix and no matching tag.
        ("pkg:maven/apache/maven@1-JRE", CommitFinderInfo.NO_TAGS_MATCHED),
        # Version with only one digit and no matching tag.
        ("pkg:maven/apache/maven@1", CommitFinderInfo.NO_TAGS_MATCHED),
    ],
)
def test_commit_finder_tag_failure(
    mocked_repo_expanded: Git, purl_string: str, expected_outcome: CommitFinderInfo
) -> None:
    """Test commit finder using mocked repository with tags."""
    match, outcome = commit_finder.find_commit(mocked_repo_expanded, PackageURL.from_string(purl_string))
    assert not match
    assert outcome == expected_outcome


@pytest.mark.parametrize(
    "purl_string",
    [
        f"pkg:maven/apache/maven@{UNICODE_VERSION}",
        f"pkg:maven/apache/maven@{TAG_VERSION}",
        f"pkg:maven/apache/maven@{TAG_VERSION}-RC1",
    ],
)
def test_commit_finder_success_commit(
    mocked_repo_expanded: Git,
    mocked_repo_commit: Any,
    purl_string: str,
) -> None:
    """Test Commit Finder on mocked repository that should match valid PURLs."""
    match, outcome = commit_finder.find_commit(mocked_repo_expanded, PackageURL.from_string(purl_string))
    assert match == mocked_repo_commit.hexsha
    assert outcome == CommitFinderInfo.MATCHED


@pytest.mark.parametrize(
    "purl_string",
    [
        # Match name prefix.
        f"pkg:maven/apache/prefix_name@{TAG_VERSION}",
        # Match suffix.
        f"pkg:maven/apache/maven@{TAG_VERSION_2}-DEV",
        # Match suffix in multi-suffix.
        f"pkg:maven/apache/maven@{TAG_VERSION_2}_RELEASE",
        # Match alphanumeric suffix in multi-suffix.
        f"pkg:maven/apache/maven@{TAG_VERSION_2}_RC1",
    ],
)
def test_commit_finder_success_empty_commit(
    mocked_repo_expanded: Git, mocked_repo_empty_commit: Any, purl_string: str
) -> None:
    """Test Commit Finder on mocked repository that should match value PURLs."""
    match, outcome = commit_finder.find_commit(mocked_repo_expanded, PackageURL.from_string(purl_string))
    assert match == mocked_repo_empty_commit.hexsha
    assert outcome == CommitFinderInfo.MATCHED


def test_commit_finder_repo_purl_success(mocked_repo_expanded: Git, mocked_repo_commit: Any) -> None:
    """Test Commit Finder on mocked repository using a repo type PURL."""
    match, outcome = commit_finder.find_commit(
        mocked_repo_expanded, PackageURL.from_string(f"pkg:github/apache/maven@{mocked_repo_commit.hexsha}")
    )
    assert match == mocked_repo_commit.hexsha
    assert outcome == CommitFinderInfo.MATCHED


@pytest.mark.parametrize(
    ("version", "parts", "expected"),
    [
        ("1.2.RELEASE", ["1", "2", "RELEASE"], 2),
        ("3.1.test.2.M5", ["3", "1", "test", "2", "M5"], 4),
        ("2.2-3", ["2", "2", "3"], 2),
        ("5.4.3_test.2.1", ["5", "4", "3", "test", "2", "1"], 3),
    ],
)
def test_commit_finder_optional_suffixes(version: str, parts: list, expected: int) -> None:
    """Test the optional suffix function."""
    assert determine_optional_suffix_index(version, parts) == expected


def test_get_repo_tags(mocked_repo_empty_commit: Any) -> None:
    """Test the get repo tags utils function."""
    # Create the repository object.
    repo = Git(os.path.join(REPO_DIR))

    # Create a non-utf8 tag in the packed references file.
    ref_file = os.path.join(REPO_DIR, ".git", "packed-refs")
    with open(ref_file, "w", encoding="ISO-8859-1") as file:
        file.write(f"{mocked_repo_empty_commit.hexsha} refs/tags/1.0\u00c3\n")

    # Using Pydriller to retrieve the tags fails.
    with pytest.raises(UnicodeDecodeError):
        _ = repo.repo.tags

    # Check the tags can still be retrieved using the corrected function.
    tags = get_repo_tags(repo)
    assert tags
    assert "1.0\u00c3" in tags


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
    # Generate the version.
    version = _data.draw(hypothesis.strategies.from_regex(input_pattern, fullmatch=True))
    if not version:
        return
    purl = PackageURL(name="test", version=version, type="maven")
    if not purl.version:
        return
    # Build the pattern from the version.
    pattern, parts, _ = commit_finder._build_version_pattern(purl.name, purl.version)
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
