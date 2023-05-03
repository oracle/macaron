# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tries to find urls of repositories that match artifacts passed in 'group:artifact:version' form."""
import logging
import typing
from collections.abc import Iterator
from xml.etree.ElementTree import Element  # nosec

import defusedxml.ElementTree
import requests
from defusedxml.ElementTree import fromstring

from macaron.config.defaults import defaults

logger: logging.Logger = logging.getLogger(__name__)


def create_urls(group: str, artifact: str, version: str, repositories: list[str]) -> list[str]:
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
    repositories: list[str]
        The list of repository URLs to use as the base for the new URLs.

    Returns
    -------
    list[str]
        The list of created URLs.
    """
    urls = []
    for repo in repositories:
        urls.append(f"{repo}/{group}/{artifact}/{version}/{artifact}-{version}.pom")
    return urls


def parse_gav(gav: str) -> tuple[str, str, str]:
    """
    Parse the passed GAV string, splitting it into its constituent parts.

    Parameters
    ----------
    gav : str
        An artifact represented as a GAV (group, artifact, version) in the format: G:A:V.

    Returns
    -------
    tuple[str, str, str]
        The tuple of separated GAV components.
    """
    split = gav.split(":")
    if len(split) < 3:
        logger.debug("Could not parse GAV: %s", gav)
        return "", "", ""

    group, artifact, version = split
    group = group.replace(".", "/")
    return group, artifact, version


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

    try:
        res = session.get(url)
    except (requests.RequestException, OSError) as error:
        logger.debug("Error during pom retrieval: %s", error)
        return ""

    if not res.ok:
        logger.warning("Failed to retrieve pom from: %s, error code: %s", url, res.status_code)
        return ""

    logger.debug("Found artifact POM at: %s", url)

    return res.text


def _find_element(parent: typing.Optional[Element], target: str) -> typing.Optional[Element]:
    if parent is None:
        return None

    # Attempt to match the target tag within the children of parent.
    for child in parent:
        # Account for raw tags, and tags accompanied by Maven metadata enclosed in curly braces. E.g. '{metadata}tag'
        if child.tag == target or child.tag.endswith("}" + target):
            return child
    return None


def parse_pom(pom: str, tags: list[str]) -> Iterator[str]:
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
    Iterator[str] :
        The extracted contents of any matches tags
    """
    try:
        xml: Element = fromstring(pom)
    except defusedxml.ElementTree.ParseError as error:
        logger.debug("Failed to parse XML: %s", error)
        return iter([])

    results = []

    # Try to match each tag with the contents of the POM.
    for tag in tags:
        element: typing.Optional[Element] = xml
        tag_parts = tag.split(".")
        for index, tag_part in enumerate(tag_parts):
            element = _find_element(element, tag_part)
            if element is None:
                break
            if index == len(tag_parts) - 1 and element.text is not None:
                # Add the contents of the final tag
                results.append(element.text.strip())

    return iter(results)


def find_repo(gav: str, tags: list[str]) -> Iterator[str]:
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
    Iterator[str] :
        The URLs found for the passed GAV.
    """
    repositories = defaults.get_list(
        "repofinder", "artifact_repositories", fallback=["https://repo.maven.apache.org/maven2"]
    )

    # Parse the GAV and create the URLs for its POM
    group, artifact, version = parse_gav(gav)
    if not group:
        return iter([])
    request_urls = create_urls(group, artifact, version, repositories)
    if not request_urls:
        return iter([])

    # Try each POM URL in order, terminating early if a match is found
    with requests.Session() as session:
        pom = ""
        for request_url in request_urls:
            pom = retrieve_pom(session, request_url)
            if pom != "":
                break

    if pom == "":
        return iter([])

    # Parse XML data and return URL
    return parse_pom(pom, tags)
