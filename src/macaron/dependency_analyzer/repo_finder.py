# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tries to find urls of repositories that match artefacts passed in 'group:artefact:version' form."""

import re

import requests

from macaron.config.global_config import global_config, logger
from macaron.parsers.limited_xmlparser import extract_tags


def create_urls(group: str, artefact: str, version: str) -> list[str]:
    """
    Create the urls to search for the pom relating to the passed GAV.

    Parameters
    ----------
    group : str
        The group ID.
    artefact: str
        The artefact ID.
    version: str
        The version of the artefact.

    Returns
    -------
    list[str]
        The list of created URLs.
    """
    urls = []

    version_pruned = ""
    if "-" in version:
        # Create a pruned version to fix some strangely labeled artefacts
        version_pruned = re.sub("-[a-zA-Z]+", "", version)

    # Create URLs using all configured repositories
    for repo in global_config.artefact_repositories:
        urls.append(f"{repo}/{group}/{artefact}/{version}/{artefact}-{version}.pom")
        if version_pruned != "":
            urls.append(f"{repo}/{group}/{artefact}/{version_pruned}/{artefact}-{version_pruned}.pom")

    return urls


def parse_gav(gav: str) -> list[str]:
    """
    Parse the passed GAV string, splitting it into its constituent parts.

    Parameters
    ----------
    gav : str
        An artefact represented as a GAV (group, artefact, version) in the format: G:A:V.

    Returns
    -------
    list[str]
        The list of URLs created for the GAV by the create_urls trailing function call.
    """
    split = gav.split(":")
    if len(split) < 3:
        logger.error("Could not parse GAV: %s", gav)
        return []

    group = split[0]
    artifact = split[1]
    version = split[2]
    group_url = group.replace(".", "/")

    print(f"gav: {group_url}, {artifact}, {version}")

    return create_urls(group_url, artifact, version)


def retrieve_pom(session: requests.Session, url: str) -> str:
    """
    Attempt to retrieve the file located at the passed URL using the passed Session.

    Parameters
    ----------
    session : requests.Session
        The HTTP session to use for attempting the GET request.
    url : str
        The URL for the GET request.

    Returns
    -------
    str :
        The retrieved file data or an empty string.
    """
    if not url.endswith(".pom"):
        return ""
    res = session.get(url)
    if not res.ok:
        logger.warning("Failed to retrieve pom from: %s, error code: %s", url, res.status_code)
        return ""
    logger.info("Found artefact POM at: %s", url)
    return res.text


def find_repo(gav: str) -> list[str]:
    """
    Attempt to retrieve a repository URL that matches the passed GAV artefact.

    Parameters
    ----------
    gav : str
        An artefact represented as a GAV (group, artefact, version) in the format: G:A:V.

    Returns
    -------
    list[str]:
        A list of URLs found for the passed GAV.
    """
    if len(global_config.artefact_repositories) == 0:
        logger.warning("No repositories set in config artefact_repositories parameter for repo finder.")
        return []

    # Parse the GAV and create the URLs for its POM
    request_urls = parse_gav(gav)
    if len(request_urls) == 0:
        return []

    # Try each POM URL in order, terminating early if a match is found
    session = requests.Session()
    pom = ""
    for request_url in request_urls:
        pom = retrieve_pom(session, request_url)
        if pom != "":
            break

    if pom == "":
        return []

    # Trailing call to extract SCM URLs from the POM and return them
    return extract_tags(pom, {"project.scm.url"})
