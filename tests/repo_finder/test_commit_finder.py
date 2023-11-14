# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the commit finder."""
import logging
import re

import hypothesis
from hypothesis import given, settings
from hypothesis.strategies import DataObject, data
from packageurl import PackageURL

from macaron.repo_finder import commit_finder

logger: logging.Logger = logging.getLogger(__name__)


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


input_pattern = re.compile(r"[0-9]{1,3}(\.[0-9a-z]{1,3}){,5}([-+#][a-z0-9].+)?", flags=re.IGNORECASE)


@given(hypothesis.strategies.text())
@settings(max_examples=1000)
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
        commit_finder._build_version_pattern(purl.version)
        assert True
    except ValueError as error:
        logger.debug(error)


# These numbers should be kept low as the complex regex makes generation slow.
VERSION_ITERATIONS = 50  # The number of times to iterate the test_version_to_tag_matching test.
TAG_ITERATIONS = 10  # The number of tags to generate per version iteration.


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
    try:
        purl = PackageURL(name="test", version=version, type="maven")
        if not purl.version:
            return
        # Build the pattern from the version.
        pattern, parts, _ = commit_finder._build_version_pattern(purl.version)
        if not pattern:
            return
        # Generate the tag from a pattern that is very similar to how version patterns are made.
        sep = "[^a-z0-9]"
        tag_pattern = (
            "(?P<prefix_0>(?:[a-z].*(?:[a-z0-9][a-z][0-9]+|[0-9][a-z]|[a-z]{2}))|[a-z]{2})?("
            "?P<prefix_sep_0>(?:(?:(?<![0-9a-z])[vrc])|(?:[^0-9a-z][vrc])|[^0-9a-z])(?:[^0-9a-z])?)?"
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
            match = pattern.match(tag)
            assert match
    except ValueError as error:
        logger.debug(error)
