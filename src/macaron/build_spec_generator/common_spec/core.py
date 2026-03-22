# Copyright (c) 2025 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the logic to generate a build spec in a generic format that can be transformed if needed."""

import logging
import pprint
import shlex
from collections.abc import Sequence
from enum import Enum
from importlib import metadata as importlib_metadata

import sqlalchemy.orm
from packageurl import PackageURL

from macaron.build_spec_generator.common_spec.base_spec import BaseBuildSpecDict, SpecBuildCommandDict
from macaron.build_spec_generator.common_spec.maven_spec import MavenBuildSpec
from macaron.build_spec_generator.common_spec.pypi_spec import PyPIBuildSpec
from macaron.build_spec_generator.macaron_db_extractor import (
    GenericBuildCommandInfo,
    lookup_any_build_command,
    lookup_build_tools_check,
    lookup_latest_component,
)
from macaron.errors import GenerateBuildSpecError, QueryMacaronDatabaseError
from macaron.json_tools import json_extract
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
    FLIT = "flit"
    HATCH = "hatch"
    CONDA = "conda"


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
    pretty_formatted_output = [pprint.pformat(build_command_info) for build_command_info in build_command_info]
    return "\n".join(pretty_formatted_output)


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


def get_macaron_build_tools(
    build_tool_facts: Sequence[BuildToolFacts], target_language: str
) -> dict[str, dict[str, float | str | None]] | None:
    """
    Retrieve the Macaron build tool names for supported projects from the database facts.

    Iterates over the provided build tool facts and returns the list of valid `MacaronBuildToolName`
    for a supported language.

    Parameters
    ----------
    build_tool_facts : Sequence[BuildToolFacts]
        A sequence of build tool fact records to be searched.
    target_language: str
        The target build language.

    Returns
    -------
    dict[str, dict[str, float, str | None]]| None:
        The corresponding Macaron build tool name, config_path, confidence score, optional build tool version,
        and optional root config path if present.
    """
    build_tools: dict[str, dict[str, float | str | None]] = {}
    for fact in build_tool_facts:
        if fact.language.lower() == target_language:
            try:
                tool_name = MacaronBuildToolName(fact.build_tool_name).value
                current_confidence: float = float(fact.confidence)
                build_tool_info: dict[str, float | str | None] = {
                    "build_config_path": fact.build_config_path,
                    "confidence_score": current_confidence,
                    "build_tool_version": fact.build_tool_version,
                    "root_build_config_path": fact.root_build_config_path,
                }
                existing_build_tool_info = build_tools.get(tool_name)
                existing_confidence = (
                    existing_build_tool_info.get("confidence_score") if existing_build_tool_info is not None else None
                )
                if (
                    existing_build_tool_info is None
                    or not isinstance(existing_confidence, float)
                    or current_confidence > existing_confidence
                ):
                    build_tools[tool_name] = build_tool_info
            except ValueError:
                continue
    return build_tools or None


def get_build_tools(
    component_id: int, session: sqlalchemy.orm.Session, target_language: str
) -> dict[str, dict[str, float | str | None]] | None:
    """Retrieve the Macaron build tool names for a given component.

    Queries the database for build tool facts associated with the specified component ID.
    It returns the corresponding list of `MacaronBuildToolName` if found.

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
    dict[str, dict[str, float, str | None]]| None:
        The corresponding Macaron build tool name, config_path, confidence score, optional build tool version,
        and optional root config path if present.
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
        [
            (
                fact.build_tool_name,
                fact.language,
                fact.build_config_path,
                fact.root_build_config_path,
                fact.build_tool_version,
            )
            for fact in build_tool_facts
        ],
    )

    return get_macaron_build_tools(build_tool_facts, target_language)


def get_build_command_info(
    component_id: int,
    session: sqlalchemy.orm.Session,
) -> list[GenericBuildCommandInfo]:
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
    list[GenericBuildCommandInfo]
        The list of GenericBuildCommandInfo objects with the highest confidence build command as the first element;
        or [] if there was an error, or no build command is found from the database.
    """
    try:
        lookup_build_command_info = lookup_any_build_command(component_id, session)
    except QueryMacaronDatabaseError as lookup_build_command_error:
        logger.error(
            "Unexpected result from querying all build command information for component id %s. Error: %s",
            component_id,
            lookup_build_command_error,
        )
        return []
    logger.debug(
        "Build command information discovered\n%s",
        format_build_command_info(lookup_build_command_info),
    )

    return lookup_build_command_info or []


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


def _build_spec_build_command(
    build_tools: dict[str, dict[str, float | str | None]],
    build_tool_name: str,
    command: list[str],
) -> SpecBuildCommandDict | None:
    """Build a single SpecBuildCommandDict entry for a given build tool."""
    build_config_path = json_extract(build_tools, [build_tool_name, "build_config_path"], str)
    # build_config_path is a required field.
    if build_config_path is None:
        return None

    root_build_config_path = json_extract(build_tools, [build_tool_name, "root_build_config_path"], str)
    build_tool_version = json_extract(build_tools, [build_tool_name, "build_tool_version"], str)
    confidence_score = json_extract(build_tools, [build_tool_name, "confidence_score"], float)
    if confidence_score is None:
        return None

    build_spec = SpecBuildCommandDict(
        build_tool=build_tool_name,
        command=command,
        build_config_path=build_config_path,
        confidence_score=confidence_score,
    )
    if root_build_config_path is not None:
        build_spec["root_build_config_path"] = root_build_config_path
    if build_tool_version is not None:
        build_spec["build_tool_version"] = build_tool_version
    return build_spec


def gen_generic_build_spec(
    purl: PackageURL,
    session: sqlalchemy.orm.Session,
) -> BaseBuildSpecDict:
    """
    Generate and return the Buildspec file.

    Parameters
    ----------
    purl : PackageURL
        The PackageURL to generate build spec for.
    session : sqlalchemy.orm.Session
        The SQLAlchemy Session opened for the database to extract build information.

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

    build_tool_names = []
    build_tools = get_build_tools(component_id=latest_component.id, session=session, target_language=target_language)
    if not build_tools:
        raise GenerateBuildSpecError(f"Failed to determine build tool for {purl}.")

    # This check is for Pylint, which is not able to iterate over build_tools, even though it cannot be None.
    if build_tools is not None:
        build_tool_names = list(build_tools.keys())

    db_build_command_info_list = get_build_command_info(
        component_id=latest_component.id,
        session=session,
    )

    lang_version = None
    spec_build_commad_info_list = []
    for db_build_command_info in db_build_command_info_list:
        logger.info(
            "Attempted to find build command from the database. Result: %s",
            db_build_command_info or "Cannot find any.",
        )
        lang_version = get_language_version(db_build_command_info) if db_build_command_info else ""
        build_spec_command = _build_spec_build_command(
            build_tools=build_tools,
            build_tool_name=db_build_command_info.build_tool_name,
            command=db_build_command_info.command,
        )
        if build_spec_command is not None:
            spec_build_commad_info_list.append(build_spec_command)

    # If no build commands were found from the analyze phase, add default commands for the identified build tools.
    if not db_build_command_info_list:
        for build_tool_name in build_tool_names:
            build_spec_command = _build_spec_build_command(
                build_tools=build_tools,
                build_tool_name=build_tool_name,
                command=[],
            )
            if build_spec_command is not None:
                spec_build_commad_info_list.append(build_spec_command)

    base_build_spec_dict = BaseBuildSpecDict(
        {
            "macaron_version": importlib_metadata.version("macaron"),
            "group_id": group,
            "artifact_id": artifact,
            "version": version,
            "git_repo": latest_component_repository.remote_path,
            "git_tag": latest_component_repository.commit_sha,
            "newline": "lf",
            "language_version": [lang_version] if lang_version else [],
            "ecosystem": purl.type,
            "purl": str(purl),
            "language": target_language,
            "build_tools": build_tool_names,
            "build_commands": spec_build_commad_info_list,
        }
    )

    ECOSYSTEMS[purl.type.upper()].value(base_build_spec_dict).resolve_fields(purl)
    return base_build_spec_dict
