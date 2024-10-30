# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the JSON template for repo finder/commit finder standalone reports."""
import json
import logging
import os
import string

from packageurl import PackageURL

logger: logging.Logger = logging.getLogger(__name__)


def create_report(purl: str, commit: str, repo: str) -> str:
    """Create and return the JSON report containing the input and output information.

    Parameters
    ----------
    purl: str
        The PackageURL of the target artifact, as a string.
    commit: str
        The commit hash to report.
    repo: str
        The repository to report.

    Returns
    -------
    str
        The JSON report as a string.
    """
    data = {"purl": purl, "commit": commit, "repo": repo}
    if "github.com" in repo:
        data["url"] = f"{repo}/commit/{commit}"
    return json.dumps(data, indent=4)


def create_filename(purl: PackageURL) -> str:
    """Create the filename of the report based on the PURL.

    Parameters
    ----------
    purl: PackageURL
        The PackageURL of the artifact.

    Returns
    -------
    str
        The filename to save the report under.
    """

    def convert_to_path(text: str) -> str:
        """Convert a PackageURL component to a path safe form."""
        allowed_chars = string.ascii_letters + string.digits + "-"
        return "".join(c if c in allowed_chars else "_" for c in text)

    filename = f"{convert_to_path(purl.type)}"
    if purl.namespace:
        filename = filename + f"/{convert_to_path(purl.namespace)}"
    filename = filename + f"/{convert_to_path(purl.name)}/{convert_to_path(purl.name)}.source.json"
    return filename


def generate_report(purl: str, commit: str, repo: str, target_dir: str) -> bool:
    """Create the report and save it to the passed directory.

    Parameters
    ----------
    purl: str
        The PackageURL of the target artifact, as a string.
    commit: str
        The commit hash to report.
    repo: str
        The repository to report.
    target_dir: str
        The path of the directory where the report will be saved.

    Returns
    -------
    bool
        True if the report was created. False otherwise.
    """
    report_json = create_report(purl, commit, repo)

    try:
        purl_object = PackageURL.from_string(purl)
    except ValueError as error:
        logger.debug("Failed to parse purl string as PURL: %s", error)
        return False

    filename = create_filename(purl_object)
    fullpath = f"{target_dir}/{filename}"

    os.makedirs(os.path.dirname(fullpath), exist_ok=True)
    logger.info("Writing report to: %s", fullpath)

    try:
        with open(fullpath, "w", encoding="utf-8") as file:
            file.write(report_json)
    except OSError as error:
        logger.debug("Failed to write report to file: %s", error)
        return False

    logger.info("Report written to: %s", fullpath)

    return True
