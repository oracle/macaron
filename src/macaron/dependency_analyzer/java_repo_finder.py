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
        logger.debug("Failed to retrieve pom from: %s, error code: %s", url, res.status_code)
        return ""

    logger.debug("Found artifact POM at: %s", url)

    return res.text


def _find_element(parent: typing.Optional[Element], target: str) -> typing.Optional[Element]:
    if not parent:
        return None

    # Attempt to match the target tag within the children of parent.
    for child in parent:
        # Account for raw tags, and tags accompanied by Maven metadata enclosed in curly braces. E.g. '{metadata}tag'
        if child.tag == target or child.tag.endswith(f"}}{target}"):
            return child
    return None


def find_parent(pom: Element) -> tuple[str, str, str]:
    """
    Extract parent information from passed POM.

    Parameters
    ----------
    pom : str
        The POM as a string.

    Returns
    -------
    tuple[str] :
        The GAV of the parent artefact.
    """
    element = _find_element(pom, "parent")
    if element is None:
        return "", "", ""
    group = _find_element(element, "groupId")
    artifact = _find_element(element, "artifactId")
    version = _find_element(element, "version")
    if (
        group is not None
        and group.text
        and artifact is not None
        and artifact.text
        and version is not None
        and version.text
    ):
        return group.text.strip(), artifact.text.strip(), version.text.strip()
    return "", "", ""


def find_scm(pom: Element, tags: list[str]) -> tuple[Iterator[str], int]:
    """
    Parse the passed pom and extract the passed tags.

    Parameters
    ----------
    pom : Element
        The parsed POM.
    tags : list[str]
        The list of tags to try extracting from the POM.

    Returns
    -------
    tuple[Iterator[str], int] :
        The extracted contents of any matches tags, and the number of matches, as a tuple.
    """
    results = []

    # Try to match each tag with the contents of the POM.
    for tag in tags:
        element: typing.Optional[Element] = pom
        tag_parts = tag.split(".")
        for index, tag_part in enumerate(tag_parts):
            element = _find_element(element, tag_part)
            if element is None:
                break
            if index == len(tag_parts) - 1 and element.text:
                # Add the contents of the final tag
                results.append(element.text.strip())

    return iter(results), len(results)


def parse_pom(pom: str) -> typing.Optional[Element]:
    """
    Parse the passed POM using defusedxml.

    Parameters
    ----------
    pom : str
        The contents of a POM file as a string.

    Returns
    -------
    Element :
        The parsed element representing the POM's XML hierarchy.
    """
    try:
        pom_element: Element = fromstring(pom)
        return pom_element
    except defusedxml.ElementTree.ParseError as error:
        logger.debug("Failed to parse XML: %s", error)
        return None


def find_repo(group: str, artifact: str, version: str, tags: list[str]) -> Iterator[str]:
    """
    Attempt to retrieve a repository URL that matches the passed GAV artifact.

    Parameters
    ----------
    group : str
        The group identifier of an artifact.
    artifact : str
        The artifact name of an artifact.
    version : str
        The version number of an artifact.
    tags : Iterator[str]
        The list of XML tags to look for, each in the format: tag1[.tag2 ... .tagN].

    Returns
    -------
    list[str] :
        The URLs found for the passed GAV.
    """
    repositories = defaults.get_list(
        "repofinder.java", "artifact_repositories", fallback=["https://repo.maven.apache.org/maven2"]
    )
    if len(tags) == 0 or not any(tags):
        logger.debug("No POM tags found for URL discovery.")
        return iter([])

    # Perform the following in a loop:
    # - Create URLs for the current artifact POM
    # - Parse the POM
    # - Try to extract SCM metadata and return URLs
    # - Try to extract parent information and change current artifact to it
    # - Repeat
    limit = defaults.getint("repofinder.java", "parent_limit", fallback=10)
    while group and artifact and version and limit > 0:
        # Create the URLs for retrieving the artifact's POM
        group = group.replace(".", "/")
        artifact = artifact.replace(".", "/")
        request_urls = create_urls(group, artifact, version, repositories)
        if not request_urls:
            # Abort if no URLs were created
            return iter([])

        # Try each POM URL in order, terminating early if a match is found
        with requests.Session() as session:
            pom = ""
            for request_url in request_urls:
                pom = retrieve_pom(session, request_url)
                if pom != "":
                    break

        if pom == "":
            # Abort if no POM was found
            return iter([])

        # Parse POM using defusedxml
        pom_element = parse_pom(pom)
        if pom_element is None:
            return iter([])

        # Attempt to extract SCM data and return URL
        urls, url_count = find_scm(pom_element, tags)

        if url_count > 0:
            return urls

        if defaults.getboolean("repofinder.java", "find_parents"):
            # Attempt to extract parent information from POM
            group, artifact, version = find_parent(pom_element)
        else:
            break

        limit = limit - 1

    # Nothing found
    return iter([])
