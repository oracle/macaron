# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the logic to generate a build spec in a generic format that can be transformed if needed."""

import logging
import pprint
import shlex
from collections.abc import Mapping, Sequence
from enum import Enum
from importlib import metadata as importlib_metadata
from pprint import pformat

import sqlalchemy.orm
from packageurl import PackageURL

from macaron.build_spec_generator.build_command_patcher import PatchCommandBuildTool, PatchValueType, patch_commands
from macaron.build_spec_generator.jdk_finder import find_jdk_version_from_central_maven_repo
from macaron.build_spec_generator.jdk_version_normalizer import normalize_jdk_version
from macaron.build_spec_generator.macaron_db_extractor import (
    GenericBuildCommandInfo,
    lookup_any_build_command,
    lookup_build_tools_check,
    lookup_latest_component,
)
from macaron.errors import QueryMacaronDatabaseError
from macaron.slsa_analyzer.checks.build_tool_check import BuildToolFacts

logger: logging.Logger = logging.getLogger(__name__)

from dataclasses import dataclass, field

@dataclass
class GenericBuildSpec:
    """
    Generic build specification supporting multiple languages and build tools.

    Parameters
    ----------
    language : str
        The programming language, e.g., 'java', 'python', 'javascript'.
    language_version : str
        The version of the programming language or runtime, e.g., '11' for JDK, '3.11' for Python.
    build_tool : str
        The build tool or package manager, e.g., 'maven', 'gradle', 'pip', 'poetry', 'npm', 'yarn'.
    dependencies : list[str]
        list of release dependencies.
    build_dependencies : list[str]
        list of build dependencies, which includes tests.        
    build_commands : list[str]
        list of shell commands to build the project.
    test_commands : list[str]
        list of shell commands to test the project.
    environment : dict of str to str
        Environment variables required during build or test.
    artifact_path : str | None
        Path or location of the build artifact/output.
    entry_point : str | None
        Entry point script, class, or binary for running the project.
    """
    language: str
    language_version: str
    build_tool: str
    dependencies: list[str] = field(default_factory=list)
    build_commands: list[str] = field(default_factory=list)
    test_commands: list[str] = field(default_factory=list)
    environment: dict[str, str] = field(default_factory=dict)
    artifact_path: str | None = None
    entry_point: str | None = None


class MacaronBuildToolName(str, Enum):
    """Represent the name of a build tool that Macaron stores in the database.

    This doesn't cover all build tools that Macaron supports, and ONLY includes the ones that we
    support generating build spec for.
    """

    MAVEN = "maven"
    GRADLE = "gradle"
    PIP = "pip"
    POETRY = "poetry"

def format_build_command_info(build_command_info: list[GenericBuildCommandInfo]) -> str:
    """Return the prettified str format for a list of `GenericBuildCommandInfo` instances.

    Parameters
    ----------
    build_command_info: GenericBuildCommandInfo
        A list of ``GenericBuildCommandInfo`` instances.

    Returns
    -------
    str
        The prettified output.
    """
    pretty_formatted_ouput = [pprint.pformat(build_command_info) for build_command_info in build_command_info]
    return "\n".join(pretty_formatted_ouput)


def remove_shell_quote(cmd: list[str]) -> list[str]:
    """Remove shell quotes from a shell command.

    Parameters
    ----------
    cmd: list[str]
        The shell command as list[str]ing.

    Returns
    -------
    list[str]
        The shell command with all quote removed.

    Examples
    --------
    >>> cmd = "mvn -f fit/core-reference/pom.xml verify '-Dit.test=RESTITCase' '-Dmodernizer.skip=true' '-Drat.skip=true'"
    >>> remove_shell_quote(cmd.split())
    ['mvn', '-f', 'fit/core-reference/pom.xml', 'verify', '-Dit.test=RESTITCase', '-Dmodernizer.skip=true', '-Drat.skip=true']
    """
    return shlex.split(" ".join(cmd))


def compose_shell_commands(cmds_sequence: list[list[str]]) -> str:
    """
    Combine a sequence of command fragments into a single shell command suitable for a build spec.

    Parameters
    ----------
    cmds_sequence : list[list[str]]
        The sequence of build command fragments.

    Returns
    -------
    str
        A shell command string to be used in the build specification's command field.
    """
    removed_shell_quote = [" ".join(remove_shell_quote(cmds)) for cmds in cmds_sequence]
    result = " && ".join(removed_shell_quote)
    return result


def get_default_build_command(
    build_tool_name: MacaronBuildToolName,
) -> list[str] | None:
    """Return a default build command for the build tool.

    Parameters
    ----------
    build_tool_name: MacaronBuildToolName
        The type of build tool to get the default build command.

    Returns
    -------
    list[str] | None
        The build command as a list[str] or None if we cannot get one for this tool.
    """
    default_build_command = None

    match build_tool_name:
        case MacaronBuildToolName.MAVEN:
            default_build_command = "mvn clean package".split()
        case MacaronBuildToolName.GRADLE:
            default_build_command = "./gradlew clean assemble publishToMavenLocal".split()
        case MacaronBuildToolName.PIP:
            default_build_command = "python -m build".split()
        case MacaronBuildToolName.POETRY:
            default_build_command = "poetry build".split()                        
        case _:
            pass

    if not default_build_command:
        logger.critical(
            "There is no default build command available for the build tool %s.",
            build_tool_name,
        )
        return None

    return default_build_command


def get_macaron_build_tool_name(build_tool_facts: Sequence[BuildToolFacts]) -> MacaronBuildToolName | None:
    """
    Retrieve the Macaron build tool name for supported projects from the database facts.

    Iterates over the provided build tool facts and returns the first valid `MacaronBuildToolName` 
    for a supported language. If no valid build tool name is found, returns None.

    .. note::
        If multiple build tools are present in the database, only the first valid one encountered
        in the sequence is returned.

    Parameters
    ----------
    build_tool_facts : Sequence[BuildToolFacts]
        A sequence of build tool fact records to be searched.

    Returns
    -------
    MacaronBuildToolName or None
        The corresponding Macaron build tool name if found, otherwise None.
    """
    for fact in build_tool_facts:
        if fact.language in {"java", "python"}:
            try:
                macaron_build_tool_name = MacaronBuildToolName(fact.build_tool_name)
            except ValueError:
                continue

            # TODO: What happen if we report multiple build tools in the database?
            return macaron_build_tool_name

    return None


def get_build_tool_name(
    component_id: int,
    session: sqlalchemy.orm.Session,
) -> MacaronBuildToolName | None:
    """
    Retrieve the Macaron build tool name for a given component.

    Queries the database for build tool facts associated with the specified component ID 
    and returns the corresponding `MacaronBuildToolName` if found. If no valid build tool 
    information is available or an error occurs during the query, returns None.

    Parameters
    ----------
    component_id : int
        The ID of the component for which to retrieve the build tool name.
    session : sqlalchemy.orm.Session
        The SQLAlchemy session used to access the database.

    Returns
    -------
    MacaronBuildToolName or None
        The corresponding build tool name for the component if available, otherwise None.
    """
    try:
        build_tool_facts = lookup_build_tools_check(
            component_id=component_id,
            session=session,
        )
    except QueryMacaronDatabaseError as lookup_build_tools_error:
        logger.error(
            "Unexpected result from querying build tools for component id %s. Error: %s",
            component_id,
            lookup_build_tools_error,
        )
        return None
    if not build_tool_facts:
        logger.error(
            "Cannot find any build tool for component id %s in the database.",
            component_id,
        )
        return None
    logger.info(
        "Build tools discovered from the %s table: %s",
        BuildToolFacts.__tablename__,
        [(fact.build_tool_name, fact.language) for fact in build_tool_facts],
    )

    return get_macaron_build_tool_name(build_tool_facts)


def get_build_command_info(
    component_id: int,
    session: sqlalchemy.orm.Session,
) -> GenericBuildCommandInfo | None:
    """Return the highest confidence build command information from the database for a component.

    The build command is found by looking up CheckFacts for build-related checks.

    Parameters
    ----------
    component_id: int
        The id of the component we are finding the build command for.
    session: sqlalchemy.orm.Session
        The SQLAlchemy Session opened for the database to extract build information.

    Returns
    -------
    GenericBuildCommandInfo | None
        The GenericBuildCommandInfo object for the highest confidence build command; or None if there was
        an error, or no build command is found from the database.
    """
    try:
        lookup_build_command_info = lookup_any_build_command(component_id, session)
    except QueryMacaronDatabaseError as lookup_build_command_error:
        logger.error(
            "Unexpected result from querying all build command information for component id %s. Error: %s",
            component_id,
            lookup_build_command_error,
        )
        return None
    logger.debug(
        "Build command information discovered\n%s",
        format_build_command_info(lookup_build_command_info),
    )

    return lookup_build_command_info[0] if lookup_build_command_info else None


def get_language_version(
    build_command_info: GenericBuildCommandInfo,
) -> str | None:
    """Retrieve the language version from a GenericBuildCommandInfo object.

    If available, returns a language version from the `language_versions` list associated with 
    the provided GenericBuildCommandInfo object. Currently, this function returns the last
    element in the list. If the list is empty, returns None.

    Notes
    -----
    The selection of the last element from `language_versions` is a temporary strategy,
    as more robust selection logic may be implemented in the future depending on 
    requirements for specific language/runtime versions (e.g., multiple JDK versions).

    Parameters
    ----------
    build_command_info : GenericBuildCommandInfo
        The object containing language version information.

    Returns
    -------
    str | None
        The selected language version as a string, or None if not available.
    """
    if build_command_info.language_versions:
        # There isn't a concrete reason why we select the last element.
        # We just use this at this point because we haven't looked into
        # a better way to select the jdk version obtained from the database.
        return build_command_info.language_versions.pop()

    return None


def gen_generic_build_spec(
    purl: PackageURL,
    session: sqlalchemy.orm.Session,
    patches: Mapping[
        PatchCommandBuildTool,
        Mapping[str, PatchValueType | None],
    ],
) -> GenericBuildSpec | None:
    """Return the content of a Reproducible Central Buildspec File.

    The Reproducible Central Buildspec File Format can be found here:
    https://github.com/jvm-repo-rebuild/reproducible-central/blob/e1708dd8dde3cdbe66b0cec9948812b601e90ba6/doc/BUILDSPEC.md#format

    Parameters
    ----------
    purl: PackageURL
        The PackageURL to generate build spec for.
    session: sqlalchemy.orm.Session
        The SQLAlchemy Session opened for the database to extract build information.
    patches: Mapping[PatchCommandBuildTool, Mapping[str, PatchValueType | None]]
        The patches to apply to the build commands in ``build_info`` before being populated in
        the output Buildspec.

    Returns
    -------
    str | None
        The content of the Buildspec as string or None if there is an error.
        The errors that can happen are: 1. The input PURL is invalid, 2. There is no supported build tool
        for this PURL, 3. Failed to patch the build commands using the provided ``patches``, 4. The database from
        ``session`` doesn't contain enough information.
    """
    logger.debug(
        "Generating build spec for %s with command patches:\n%s",
        purl,
        pformat(patches),
    )

    # Getting groupid, artifactid and version from PURL.
    group = purl.namespace
    artifact = purl.name
    version = purl.version
    if group is None or version is None:
        logger.error("Missing group and/or version for purl %s.", purl.to_string())
        return None

    try:
        latest_component = lookup_latest_component(
            purl=purl,
            session=session,
        )
    except QueryMacaronDatabaseError as lookup_component_error:
        logger.error(
            "Unexpected result from querying latest component for %s. Error: %s",
            purl.to_string(),
            lookup_component_error,
        )
        return None
    if not latest_component:
        logger.error(
            "Cannot find an analysis result for PackageURL %s in the database. "
            + "Please check if an analysis for it exists in the database.",
            purl.to_string(),
        )
        return None

    latest_component_repository = latest_component.repository
    if not latest_component_repository:
        logger.error(
            "Cannot find any repository information for %s in the database.",
            purl.to_string(),
        )
        return None
    logger.info(
        "Repository information for purl %s: url %s, commit %s",
        purl,
        latest_component_repository.remote_path,
        latest_component_repository.commit_sha,
    )

    # Getting the build tool name from the build tool check facts.
    build_tool_name = get_build_tool_name(
        component_id=latest_component.id,
        session=session,
    )
    if not build_tool_name:
        return None

    # We always attempt to get the JDK version from maven central JAR for this GAV artifact.
    jdk_from_jar = find_jdk_version_from_central_maven_repo(
        group_id=group,
        artifact_id=artifact,
        version=version,
    )
    logger.info(
        "Attempted to find JDK from Maven Central JAR. Result: %s",
        jdk_from_jar or "Cannot find any.",
    )

    # Obtain the highest confidence build command info from the database.
    build_command_info = get_build_command_info(
        component_id=latest_component.id,
        session=session,
    )
    logger.info(
        "Attempted to find build command from the database. Result: %s",
        build_command_info or "Cannot find any.",
    )

    # Select JDK from jar or another source, with a default of version 8.
    selected_jdk_version = (
        jdk_from_jar
        or (get_language_version(build_command_info) if build_command_info else None)
        or "8"
    )

    major_jdk_version = normalize_jdk_version(selected_jdk_version)
    if not major_jdk_version:
        logger.error("Failed to obtain the major version of %s", selected_jdk_version)
        return None

    # Select build commands from lookup or use a default one.
    selected_build_command = (
        build_command_info.command
        if build_command_info
        else get_default_build_command(
            build_tool_name,
        )
    )
    if not selected_build_command:
        logger.error("Failed to get a build command for %s.", purl.to_string())
        return None

    patched_build_commands = patch_commands(
        cmds_sequence=[selected_build_command],
        patches=patches,
    )
    if not patched_build_commands:
        logger.error(
            "Failed to patch command sequences %s.",
            [selected_build_command],
        )
        return None

    template_format_values: dict[str, str] = {
        "macaron_version": importlib_metadata.version("macaron"),
        "group_id": group,
        "artifact_id": artifact,
        "version": version,
        "git_repo": latest_component_repository.remote_path,
        "git_tag": latest_component_repository.commit_sha,
        "tool": build_tool_name.value,
        "newline": "lf",
        "buildinfo": f"target/{artifact}-{version}.buildinfo",
        "jdk": major_jdk_version,
        "command": compose_shell_commands(patched_build_commands),
    }

    return STRING_TEMPLATE.format_map(template_format_values)
