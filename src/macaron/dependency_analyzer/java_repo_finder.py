# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tries to find urls of repositories that match artifacts passed in 'group:artifact:version' form."""
import logging
import re
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


def _find_element(parent: Element | None, target: str) -> Element | None:
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
        The GAV of the parent artifact.
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


def find_scm(pom: Element, tags: list[str], resolve_properties: bool = True) -> tuple[Iterator[str], int]:
    """
    Parse the passed pom and extract the passed tags.

    Parameters
    ----------
    pom : Element
        The parsed POM.
    tags : list[str]
        The list of tags to try extracting from the POM.
    resolve_properties: bool
        Whether to attempt resolution of Maven properties within the POM.

    Returns
    -------
    tuple[Iterator[str], int] :
        The extracted contents of any matches tags, and the number of matches, as a tuple.
    """
    results = []

    # Try to match each tag with the contents of the POM.
    for tag in tags:
        element: Element | None = pom

        if tag.startswith("properties."):
            # Tags under properties are often "." separated
            # These can be safely split into two resulting tags as nested tags are not allowed here
            tag_parts = ["properties", tag[11:]]
        else:
            # Other tags can be split into distinct elements via "."
            tag_parts = tag.split(".")

        for index, tag_part in enumerate(tag_parts):
            element = _find_element(element, tag_part)
            if element is None:
                break
            if index == len(tag_parts) - 1 and element.text:
                # Add the contents of the final tag
                results.append(element.text.strip())

    # Resolve any Maven properties within the results
    if resolve_properties:
        results = _resolve_properties(pom, results)

    return iter(results), len(results)


def _resolve_properties(pom: Element, values: list[str]) -> list[str]:
    """Resolve any Maven properties found within the passed list of values.

    Maven POM files have five different use cases for properties (see https://maven.apache.org/pom.html).
    Only the two that relate to contents found elsewhere within the same POM file are considered here.
    That is: ${project.x} where x can be a child tag at any depth, or ${x} where x is found at project.properties.x.
    Entries with unresolved properties are not included in the returned list. In the case of chained properties,
    only the top most property is evaluated.
    """
    resolved_values = []
    for value in values:
        replacements: list = []
        # Calculate replacements - matches any number of ${...} entries in the current value
        for match in re.finditer("\\$\\{[^}]+}", value):
            text = match.group().replace("$", "").replace("{", "").replace("}", "")
            if text.startswith("project."):
                text = text.replace("project.", "")
            else:
                text = f"properties.{text}"
            # Call find_scm with property resolution flag set to False to prevent the possibility of endless looping
            value_iterator, count = find_scm(pom, [text], False)
            if count == 0:
                break
            replacements.append([match.start(), next(value_iterator), match.end()])

        # Apply replacements in reverse order
        # E.g.
        # git@github.com:owner/project${javac.src.version}-${project.inceptionYear}.git
        # ->
        # git@github.com:owner/project${javac.src.version}-2023.git
        # ->
        # git@github.com:owner/project1.8-2023.git
        for replacement in reversed(replacements):
            value = f"{value[:replacement[0]]}{replacement[1]}{value[replacement[2]:]}"

        resolved_values.append(value)

    return resolved_values


def parse_pom(pom: str) -> Element | None:
    """
    Parse the passed POM using defusedxml.

    Parameters
    ----------
    pom : str
        The contents of a POM file as a string.

    Returns
    -------
    Element | None :
        The parsed element representing the POM's XML hierarchy.
    """
    try:
        pom_element: Element = fromstring(pom)
        return pom_element
    except defusedxml.ElementTree.ParseError as error:
        logger.debug("Failed to parse XML: %s", error)
        return None


def find_java_repo(group: str, artifact: str, version: str, tags: list[str]) -> Iterator[str]:
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

    Yields
    ------
    Iterator[str] :
        The URLs found for the passed GAV.
    """
    repositories = defaults.get_list(
        "repofinder.java", "artifact_repositories", fallback=["https://repo.maven.apache.org/maven2"]
    )
    if not any(tags):
        logger.debug("No POM tags found for URL discovery.")
        return

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
        request_urls = create_urls(group, artifact, version, repositories)
        if not request_urls:
            # Abort if no URLs were created
            return

        # Try each POM URL in order, terminating early if a match is found
        with requests.Session() as session:
            pom = ""
            for request_url in request_urls:
                pom = retrieve_pom(session, request_url)
                if pom != "":
                    break

        if pom == "":
            # Abort if no POM was found
            return

        # Parse POM using defusedxml
        pom_element = parse_pom(pom)
        if pom_element is None:
            return

        # Attempt to extract SCM data and return URL
        urls, url_count = find_scm(pom_element, tags)

        if url_count > 0:
            yield from urls

        if defaults.getboolean("repofinder.java", "find_parents"):
            # Attempt to extract parent information from POM
            group, artifact, version = find_parent(pom_element)
        else:
            break

        limit = limit - 1

    # Nothing found
    return
