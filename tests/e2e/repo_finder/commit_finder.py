# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module performs a regression test of the commit finder's tag matching functionality."""

import json
import logging
import os
import sys
from pathlib import Path

from packageurl import PackageURL

from macaron.repo_finder import commit_finder

logger: logging.Logger = logging.getLogger(__name__)

# Set logging debug level.
logger.setLevel(logging.DEBUG)

path = Path(__file__).parent.joinpath("resources", "java_tags.json")


def test_commit_finder() -> int:
    """Test the commit finder's tag matching functionality."""
    with open(path, encoding="utf-8") as tag_file:
        json_data = json.load(tag_file)
    fail_count = 0
    for item in json_data:
        artifacts = item["artifacts"]
        for artifact in artifacts:
            purl = PackageURL.from_string(artifact["purl"])
            matched_tags = commit_finder.match_tags(item["tags"], purl.name, purl.version or "")
            matched_tag = matched_tags[0] if matched_tags else ""
            expected = str(artifact["match"])
            if matched_tag != expected:
                logger.debug(
                    "Matched tag '%s' did not match expected value '%s' for artifact '%s'",
                    matched_tag,
                    expected,
                    artifact["purl"],
                )
                fail_count = fail_count + 1

    if fail_count:
        logger.debug("Tag match failure count: %s", fail_count)
        return os.EX_DATAERR

    return os.EX_OK


def update_commit_finder_results() -> None:
    """Run the commit finder with the current results file and update the match values (override the file)."""
    # pylint: disable=protected-access
    with open(path, encoding="utf-8") as tag_file:
        json_data = json.load(tag_file)
    for item in json_data:
        name = str(item["name"])
        name, version = name.split("@")
        matched_tags = commit_finder.match_tags(item["tags"], name, version)
        matched_tag = matched_tags[0] if matched_tags else ""
        item["match"] = matched_tag
    with open(path, "w", encoding="utf-8") as tag_file:
        json.dump(json_data, tag_file, indent=4)


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--update":
        update_commit_finder_results()
    else:
        sys.exit(test_commit_finder())
