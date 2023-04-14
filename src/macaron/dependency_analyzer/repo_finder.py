# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tries to find urls of repositories that match artifacts passed in 'group:artifact:version' form."""

import re
import typing

import requests
from defusedxml.ElementTree import fromstring

from macaron.config.global_config import global_config, logger


def create_urls(group: str, artifact: str, version: str) -> list[str]:
    """
    Create the urls to search for the pom relating to the passed GAV.

    Parameters
    ----------
    group : str
        The group ID.
    artifact: str
        The artifact ID.
    version: str
        The version of the artifact.

    Returns
    -------
    list[str]
        The list of created URLs.
    """
    urls = []

    version_pruned = ""
    if "-" in version:
        # Create a pruned version to fix some strangely labeled artifacts
        version_pruned = re.sub("-[a-zA-Z]+", "", version)

    # Create URLs using all configured repositories
    for repo in global_config.artifact_repositories:
        urls.append(f"{repo}/{group}/{artifact}/{version}/{artifact}-{version}.pom")
        if version_pruned != "":
            urls.append(f"{repo}/{group}/{artifact}/{version_pruned}/{artifact}-{version_pruned}.pom")

    return urls


def parse_gav(gav: str) -> list[str]:
    """
    Parse the passed GAV string, splitting it into its constituent parts.

    Parameters
    ----------
    gav : str
        An artifact represented as a GAV (group, artifact, version) in the format: G:A:V.

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
    logger.info("Found artifact POM at: %s", url)
    return res.text


def _find_element(parent: typing.Any, target: str) -> typing.Any:
    # Attempt to match the target tag within the children of parent.
    for child in parent:
        # Account for raw tags and tags accompanied by Maven metadata enclosed in curly braces. E.g. '{metadata}tag'
        if child.tag == target or child.tag.endswith("}" + target):
            return child
    return None


def parse_pom(pom: str, tags: list[str]) -> list[str]:
    """
    Parse the passed pom and extract the passed tags.

    Parameters
    ----------
    pom : str
        The POM as a string
    tags : list[str]
        The list of tags to try extracting from the POM

    Returns
    -------
    list[str] :
        The extracted contents of any matches tags
    """
    xml = fromstring(pom)
    results = []

    # Try to match each tag with the contents of the POM
    for tag in tags:
        element = xml
        tag_parts = tag.split(".")
        for index, tag_part in enumerate(tag_parts):
            element = _find_element(element, tag_part)
            if element is None:
                break
            if index == len(tag_parts) - 1:
                # Add the contents of the final tag
                results.append(element.text)

    return results


def find_repo(gav: str, tags: list[str]) -> list[str]:
    """
    Attempt to retrieve a repository URL that matches the passed GAV artifact.

    Parameters
    ----------
    gav : str
        An artifact represented as a GAV (group, artifact, version) in the format: G:A:V.
    tags : list[str]
        The list of XML tags to look for, each in the format: tag1[.tag2 ... .tagN]

    Returns
    -------
    list[str] :
        The URLs found for the passed GAV.
    """
    if len(global_config.artifact_repositories) == 0:
        logger.warning("No repositories set in config artifact_repositories parameter for repo finder.")
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

    # Parse XML data and return URL
    return parse_pom(pom, tags)
