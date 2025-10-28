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
from macaron.build_spec_generator.common_spec.base_spec import BaseBuildSpecDict
from macaron.build_spec_generator.common_spec.maven_spec import MavenBuildSpec
from macaron.build_spec_generator.common_spec.pypi_spec import PyPIBuildSpec
from macaron.build_spec_generator.macaron_db_extractor import (
    GenericBuildCommandInfo,
    lookup_any_build_command,
    lookup_build_tools_check,
    lookup_latest_component,
)
from macaron.errors import GenerateBuildSpecError, QueryMacaronDatabaseError
from macaron.slsa_analyzer.checks.build_tool_check import BuildToolFacts

logger: logging.Logger = logging.getLogger(__name__)


class ECOSYSTEMS(Enum):
    """This Enum provides implementation mappings for supported ecosystems."""

    #: The Maven build specification.
    MAVEN = MavenBuildSpec
    #: The PyPI build specification.
    PYPI = PyPIBuildSpec


class LANGUAGES(Enum):
    """This Enum provides mappings for supported languages."""

    #: The language used in the Maven build ecosystem.
    MAVEN = "java"
    #: The language used in the PyPI build ecosystem.
    PYPI = "python"


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


def get_macaron_build_tool_name(
    build_tool_facts: Sequence[BuildToolFacts], target_language: str
) -> MacaronBuildToolName | None:
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
    target_language: str
        The target build language.

    Returns
    -------
    MacaronBuildToolName or None
        The corresponding Macaron build tool name if found, otherwise None.
    """
    for fact in build_tool_facts:
        if fact.language.lower() == target_language:
            try:
                macaron_build_tool_name = MacaronBuildToolName(fact.build_tool_name)
            except ValueError:
                continue

            # TODO: What happen if we report multiple build tools in the database?
            return macaron_build_tool_name

    return None


def get_build_tool_name(
    component_id: int, session: sqlalchemy.orm.Session, target_language: str
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
    target_language: str
        The target build language.

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

    return get_macaron_build_tool_name(build_tool_facts, target_language)


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
) -> BaseBuildSpecDict:
    """
    Generate and return the Buildspec file.

    Parameters
    ----------
    purl : PackageURL
        The PackageURL to generate build spec for.
    session : sqlalchemy.orm.Session
        The SQLAlchemy Session opened for the database to extract build information.
    patches : Mapping[PatchCommandBuildTool, Mapping[str, PatchValueType | None]]
        The patches to apply to the build commands in ``build_info`` before being populated in
        the output Buildspec.

    Returns
    -------
    BaseBuildSpecDict
        The generated build spec.

    Raises
    ------
    GenerateBuildSpecError
        Raised if generation of the build spec fails due to any of the following reasons:
        1. The input PURL is invalid.
        2. There is no supported build tool for this PURL.
        3. Failed to patch the build commands using the provided ``patches``.
        4. The database from ``session`` doesn't contain enough information.

    """
    if purl.type not in [e.name.lower() for e in ECOSYSTEMS]:
        raise GenerateBuildSpecError(
            f"PURL type '{purl.type}' is not supported. Supported: {[e.name.lower() for e in ECOSYSTEMS]}"
        )

    logger.debug(
        "Generating build spec for %s with command patches:\n%s",
        purl,
        pformat(patches),
    )

    target_language = LANGUAGES[purl.type.upper()].value
    group = purl.namespace
    artifact = purl.name
    version = purl.version
    if version is None:
        raise GenerateBuildSpecError(f"Missing version for purl {purl}.")

    try:
        latest_component = lookup_latest_component(
            purl=purl,
            session=session,
        )
    except QueryMacaronDatabaseError as lookup_component_error:
        raise GenerateBuildSpecError(
            f"Unexpected result from querying latest component for {purl}. "
        ) from lookup_component_error
    if not latest_component:
        raise GenerateBuildSpecError(
            f"Cannot find an analysis result for PackageURL {purl} in the database. "
            "Please check if an analysis for it exists in the database."
        )

    latest_component_repository = latest_component.repository
    if not latest_component_repository:
        raise GenerateBuildSpecError(f"Cannot find any repository information for {purl} in the database.")

    logger.info(
        "Repository information for purl %s: url %s, commit %s",
        purl,
        latest_component_repository.remote_path,
        latest_component_repository.commit_sha,
    )

    build_tool_name = get_build_tool_name(
        component_id=latest_component.id, session=session, target_language=target_language
    )
    if not build_tool_name:
        raise GenerateBuildSpecError(f"Failed to determine build tool for {purl}.")

    build_command_info = get_build_command_info(
        component_id=latest_component.id,
        session=session,
    )
    logger.info(
        "Attempted to find build command from the database. Result: %s",
        build_command_info or "Cannot find any.",
    )

    selected_build_command = (
        build_command_info.command
        if build_command_info
        else get_default_build_command(
            build_tool_name,
        )
    )
    if not selected_build_command:
        raise GenerateBuildSpecError(f"Failed to get a build command for {purl}.")

    patched_build_commands = patch_commands(
        cmds_sequence=[selected_build_command],
        patches=patches,
    )
    if not patched_build_commands:
        raise GenerateBuildSpecError(f"Failed to patch command sequences {selected_build_command}.")

    lang_version = get_language_version(build_command_info) if build_command_info else ""

    base_build_spec_dict = BaseBuildSpecDict(
        {
            "macaron_version": importlib_metadata.version("macaron"),
            "group_id": group,
            "artifact_id": artifact,
            "version": version,
            "git_repo": latest_component_repository.remote_path,
            "git_tag": latest_component_repository.commit_sha,
            "newline": "lf",
            "language_version": lang_version or "",
            "ecosystem": purl.type,
            "purl": str(purl),
            "language": target_language,
            "build_tool": build_tool_name.value,
            "build_commands": patched_build_commands,
        }
    )
    ECOSYSTEMS[purl.type.upper()].value(base_build_spec_dict).resolve_fields(purl)
    return base_build_spec_dict
