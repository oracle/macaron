# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the logic to extract build relation information for a PURL from the Macaron database."""

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypeVar

from packageurl import PackageURL
from sqlalchemy import Select, and_, select
from sqlalchemy.dialects import sqlite
from sqlalchemy.exc import MultipleResultsFound, SQLAlchemyError
from sqlalchemy.orm import Session, aliased

from macaron.database.table_definitions import Analysis, CheckFacts, Component, MappedCheckResult, Repository
from macaron.errors import QueryMacaronDatabaseError
from macaron.slsa_analyzer.checks.build_as_code_check import BuildAsCodeFacts
from macaron.slsa_analyzer.checks.build_script_check import BuildScriptFacts
from macaron.slsa_analyzer.checks.build_service_check import BuildServiceFacts
from macaron.slsa_analyzer.checks.build_tool_check import BuildToolFacts

logger: logging.Logger = logging.getLogger(__name__)


@dataclass
class GenericBuildCommandInfo:
    """Contains the build command information extracted from build related check facts."""

    command: list[str]
    language: str
    language_versions: list[str]
    build_tool_name: str


T = TypeVar("T")


def lookup_multiple(
    select_statement: Select[tuple[T]],
    session: Session,
) -> Sequence[T]:
    """Perform an SELECT statement and return all scalar results.

    Parameters
    ----------
    select_statement : Select[tuple[T]]
        The SQLAlchemy SELECT statement to execute.
    session : Session
        The SQLAlchemy session to the database we are querying from.

    Returns
    -------
    Sequence[T]
        The result of executing the SELECT statement as scalar values.

    Raises
    ------
    QueryMacaronDatabaseError
        If the SELECT statement isn't executed successfully.
        For example, if the schema of the target database doesn't match the statement.
    """
    try:
        sql_results = session.execute(select_statement)
    except SQLAlchemyError as generic_exec_error:
        raise QueryMacaronDatabaseError(
            f"Critical: unexpected error when execute query {compile_sqlite_select_statement(select_statement)}."
        ) from generic_exec_error

    return sql_results.scalars().all()


def lookup_one_or_none(
    select_statement: Select[tuple[T]],
    session: Session,
) -> T | None:
    """Perform an SELECT statement and return at most one scalar result.

    Parameters
    ----------
    select_statement : Select[tuple[T]]
        The SQLAlchemy SELECT statement to execute
    session : Session
        The SQLAlchemy session to the database we are querying from.

    Returns
    -------
    T | None
        The result of executing the SELECT statement as one scalar value or None
        if there isn't any available.

    Raises
    ------
    QueryMacaronDatabaseError
        If the SELECT statement isn't executed successfully.
        For example, if the schema of the target database doesn't match the statement.
        Of if there are more than one result obtained from the SELECT statement.
    """
    compiled_select_statement = compile_sqlite_select_statement(select_statement)
    try:
        query_scalar_results = session.execute(select_statement).scalars()
    except SQLAlchemyError as generic_exec_error:
        raise QueryMacaronDatabaseError(
            f"Critical: unexpected error when execute query {compiled_select_statement}."
        ) from generic_exec_error

    try:
        result = query_scalar_results.one_or_none()
    except MultipleResultsFound as error:
        raise QueryMacaronDatabaseError(
            f"Expect at most one result, found multiple results for query {compiled_select_statement}."
        ) from error

    return result


def compile_sqlite_select_statement(select_statment: Select) -> str:
    """Return the equivalent SQLite SELECT statement from an SQLAlchemy SELECT statement.

    This function also introduces additional cosmetic details so that it can be easily
    read from the log.

    Parameters
    ----------
    select_statement : Select
        The SQLAlchemy Select statement.

    Returns
    -------
    str
        The equivalent SQLite SELECT statement as a string.
    """
    compiled_sqlite = select_statment.compile(
        dialect=sqlite.dialect(),  # type: ignore
        compile_kwargs={"literal_binds": True},
    )
    return f"\n----- Begin SQLite query \n{str(compiled_sqlite)}\n----- End SQLite query\n"


def get_sql_stmt_latest_component_for_purl(purl: PackageURL) -> Select[tuple[Component]]:
    """Return an SQLAlchemy SELECT statement to query the latest Component.

    Parameters
    ----------
    purl : PackageURL
        The PackageURL object to find the Component instance.

    Returns
    -------
    Select[tuple[Component]]
        The SQLAlchemy SELECT statement to query the latest analyzed Component instance
        corresponding to the PackageURL.
    """
    return (
        select(
            Component,
        )
        .select_from(Component)
        .join(
            Analysis,
            onclause=Component.analysis_id == Analysis.id,
        )
        .where(Component.purl == purl.to_string())
        .order_by(
            Analysis.analysis_time.desc(),
            Analysis.id.desc(),
        )
    )


def get_sql_stmt_build_tools(component_id: int) -> Select[tuple[BuildToolFacts]]:
    """Return an SQLAlchemy SELECT statement to query the BuildToolFacts for a given PackageURL.

    Parameters
    ----------
    purl_string : str
        The PackageURL string to find the BuildToolFacts.

    Returns
    -------
    Select[tuple[BuildAsCodeFacts]]
        The SQLAlchemy SELECT statement.
    """
    # Because BuildToolFacts inherit from CheckFacts, SQLAlchemy had to perform implicit alias
    # when performing a join between them. This pattern is not recommended, hence a warning is raised
    # https://docs.sqlalchemy.org/en/20/errors.html#an-alias-is-being-generated-automatically-due-to-overlapping-tables.
    # To resolve this, we need to create an SQLAlchemy alias and use it in the SELECT statement.
    build_tool_facts_alias = aliased(BuildToolFacts, flat=True)

    return (
        select(build_tool_facts_alias)
        .select_from(Component)
        .join(
            MappedCheckResult,
            onclause=Component.id == MappedCheckResult.component_id,
        )
        .join(
            CheckFacts,
            onclause=MappedCheckResult.id == CheckFacts.check_result_id,
        )
        .join(
            build_tool_facts_alias,
            onclause=CheckFacts.id == build_tool_facts_alias.id,
        )
        .where(Component.id == component_id)
        .order_by(
            build_tool_facts_alias.confidence.desc(),
            build_tool_facts_alias.id.asc(),
        )
    )


def get_sql_stmt_build_as_code_check(component_id: int) -> Select[tuple[BuildAsCodeFacts]]:
    """Return an SQLAlchemy SELECT statement to query the BuildAsCodeFacts for a given PackageURL.

    Parameters
    ----------
    purl_string : str
        The PackageURL string to find the BuildToolFacts.

    Returns
    -------
    Select[tuple[BuildAsCodeFacts]]
        The SQLAlchemy SELECT statement.
    """
    # Because BuildAsCodeFacts inherit from CheckFacts, SQLAlchemy had to perform implicit alias
    # when performing a join between them. This pattern is not recommended, hence a warning is raised
    # https://docs.sqlalchemy.org/en/20/errors.html#an-alias-is-being-generated-automatically-due-to-overlapping-tables.
    # To resolve this, we need to create an SQLAlchemy alias and use it in the SELECT statement.
    build_as_code_facts_alias = aliased(BuildAsCodeFacts, flat=True)

    return (
        select(build_as_code_facts_alias)
        .select_from(Component)
        .join(
            MappedCheckResult,
            onclause=MappedCheckResult.id == Component.id,
        )
        .join(
            CheckFacts,
            onclause=MappedCheckResult.id == CheckFacts.check_result_id,
        )
        .join(
            build_as_code_facts_alias,
            onclause=CheckFacts.id == build_as_code_facts_alias.id,
        )
        .where(
            and_(
                Component.id == component_id,
                build_as_code_facts_alias.deploy_command.is_not(None),
            )
        )
        .order_by(
            build_as_code_facts_alias.confidence.desc(),
            build_as_code_facts_alias.id.asc(),
        )
    )


def get_sql_stmt_build_service_check(component_id: int) -> Select[tuple[BuildServiceFacts]]:
    """Return an SQLAlchemy SELECT statement to query the BuildServiceFacts for a given PackageURL.

    Parameters
    ----------
    purl_string : str
        The PackageURL string to find the BuildServiceFacts.

    Returns
    -------
    Select[tuple[BuildServiceFacts]]
        The SQLAlchemy SELECT statement.
    """
    # Because BuildServiceFacts inherit from CheckFacts, SQLAlchemy had to perform implicit alias
    # when performing a join between them. This pattern is not recommended, hence a warning is raised
    # https://docs.sqlalchemy.org/en/20/errors.html#an-alias-is-being-generated-automatically-due-to-overlapping-tables.
    # To resolve this, we need to create an SQLAlchemy alias and use it in the SELECT statement.
    build_service_facts_alias = aliased(BuildServiceFacts, flat=True)

    return (
        select(build_service_facts_alias)
        .select_from(Component)
        .join(
            MappedCheckResult,
            onclause=MappedCheckResult.component_id == Component.id,
        )
        .join(
            CheckFacts,
            onclause=MappedCheckResult.id == CheckFacts.check_result_id,
        )
        .join(
            build_service_facts_alias,
            onclause=CheckFacts.id == build_service_facts_alias.id,
        )
        .where(
            and_(
                Component.id == component_id,
                build_service_facts_alias.build_command.is_not(None),
            )
        )
        .order_by(
            build_service_facts_alias.confidence.desc(),
            build_service_facts_alias.id.asc(),
        )
    )


def get_sql_stmt_build_script_check(component_id: int) -> Select[tuple[BuildScriptFacts]]:
    """Return an SQLAlchemy SELECT statement to query the BuildScriptFacts for a given PackageURL.

    Parameters
    ----------
    purl_string : str
        The PackageURL string to find the BuildScriptFacts.

    Returns
    -------
    Select[tuple[BuildScriptFacts]]
        The SQLAlchemy SELECT statement.
    """
    # Because BuildScriptFacts inherit from CheckFacts, SQLAlchemy had to perform implicit alias
    # when performing a join between them. This pattern is not recommended, hence a warning is raised
    # https://docs.sqlalchemy.org/en/20/errors.html#an-alias-is-being-generated-automatically-due-to-overlapping-tables.
    # To resolve this, we need to create an SQLAlchemy alias and use it in the SELECT statement.
    build_script_facts_alias = aliased(BuildScriptFacts, flat=True)

    return (
        select(build_script_facts_alias)
        .select_from(Component)
        .join(
            MappedCheckResult,
            onclause=MappedCheckResult.component_id == Component.id,
        )
        .join(
            CheckFacts,
            onclause=MappedCheckResult.id == CheckFacts.check_result_id,
        )
        .join(
            build_script_facts_alias,
            onclause=CheckFacts.id == build_script_facts_alias.id,
        )
        .where(
            and_(
                Component.id == component_id,
                build_script_facts_alias.build_tool_command.is_not(None),
            )
        )
        .order_by(
            build_script_facts_alias.confidence.desc(),
            build_script_facts_alias.id.asc(),
        )
    )


def get_sql_stmt_repository(component_id: int) -> Select[tuple[Repository]]:
    """Return an SQLAlchemy SELECT statement to query the Repository for a given PackageURL.

    Parameters
    ----------
    purl_string : str
        The PackageURL string to find the Repository.

    Returns
    -------
    Select[tuple[Repository]]
        The SQLAlchemy SELECT statement.
    """
    return (
        select(Repository)
        .select_from(Component)
        .join(
            Repository,
            onclause=Component.id == Repository.component_id,
        )
        .where(Component.id == component_id)
    )


def lookup_latest_component_id(purl: PackageURL, session: Session) -> int | None:
    """Return the component id of the latest analysis that matches a given PackageURL string.

    Parameters
    ----------
    purl : PackageURL
        The PackageURL object to look for the latest component id.
    session : Session
        The SQLAlcemy Session that connects to the Macaron database.

    Returns
    -------
    int | None
        The latest component id or None if there isn't one available in the database.

    Raises
    ------
    QueryMacaronDatabaseError
        If there is an unexpected error when executing the SQLAlchemy query.
    """
    latest_component_id_stmt = get_sql_stmt_latest_component_for_purl(purl)
    logger.debug("Latest Analysis and Component query \n %s", compile_sqlite_select_statement(latest_component_id_stmt))

    try:
        component_results = session.execute(latest_component_id_stmt)
    except SQLAlchemyError as generic_exec_error:
        raise QueryMacaronDatabaseError(
            f"Critical: unexpected error when execute query {compile_sqlite_select_statement(latest_component_id_stmt)}."
        ) from generic_exec_error

    latest_component = component_results.scalars().first()
    if not latest_component:
        return None

    return latest_component.id


def lookup_build_tools_check(component_id: int, session: Session) -> Sequence[BuildToolFacts]:
    """Return the sequence of BuildToolFacts instances for given PackageURL string.

    Parameters
    ----------
    purl_string : str
        The PackageURL string to look for the BuildToolFacts.
    session : Session
        The SQLAlcemy Session that connects to the Macaron database.

    Returns
    -------
    Sequence[BuildToolFacts]
        The sequence of BuildToolFacts instances obtained from querying the database.

    Raises
    ------
    QueryMacaronDatabaseError
        If there is an unexpected error when executing the SQLAlchemy query.
    """
    build_tools_statement = get_sql_stmt_build_tools(component_id)
    logger.debug(
        "Build Tools Check Facts for component %d \n %s",
        component_id,
        compile_sqlite_select_statement(build_tools_statement),
    )

    build_tool_facts = lookup_multiple(
        select_statement=build_tools_statement,
        session=session,
    )

    return build_tool_facts


def lookup_build_as_code_check(component_id: int, session: Session) -> Sequence[BuildAsCodeFacts]:
    """Return the sequence of BuildAsCodeFacts instances for given PackageURL string.

    Parameters
    ----------
    purl_string : str
        The PackageURL string to look for the BuildAsCodeFacts.
    session : Session
        The SQLAlcemy Session that connects to the Macaron database.

    Returns
    -------
    Sequence[BuildAsCodeFacts]
        The sequence of BuildAsCodeFacts instances obtained from querying the database.

    Raises
    ------
    QueryMacaronDatabaseError
        If there is an unexpected error when executing the SQLAlchemy query.
    """
    build_as_code_select_statement = get_sql_stmt_build_as_code_check(component_id)
    logger.debug(
        "Build As Code Check Fact for component %d \n %s",
        component_id,
        compile_sqlite_select_statement(build_as_code_select_statement),
    )

    build_as_code_check_facts = lookup_multiple(
        select_statement=build_as_code_select_statement,
        session=session,
    )

    return build_as_code_check_facts


def lookup_build_service_check(component_id: int, session: Session) -> Sequence[BuildServiceFacts]:
    """Return the sequence of BuildServiceFacts instances for given PackageURL string.

    Parameters
    ----------
    purl_string : str
        The PackageURL string to look for the BuildServiceFacts.
    session : Session
        The SQLAlcemy Session that connects to the Macaron database.

    Returns
    -------
    Sequence[BuildServiceFacts]
        The sequence of BuildServiceFacts instances obtained from querying the database.

    Raises
    ------
    QueryMacaronDatabaseError
        If there is an unexpected error when executing the SQLAlchemy query.
    """
    build_service_select_statement = get_sql_stmt_build_service_check(component_id)
    logger.debug(
        "Build Service Check Fact for component %d \n %s",
        component_id,
        compile_sqlite_select_statement(build_service_select_statement),
    )

    build_service_check_facts = lookup_multiple(
        select_statement=build_service_select_statement,
        session=session,
    )

    return build_service_check_facts


def lookup_build_script_check(component_id: int, session: Session) -> Sequence[BuildScriptFacts]:
    """Return the sequence of BuildScriptFacts instances for given PackageURL string.

    Parameters
    ----------
    purl_string : str
        The PackageURL string to look for the BuildScriptFacts.
    session : Session
        The SQLAlcemy Session that connects to the Macaron database.

    Returns
    -------
    Sequence[BuildScriptFacts]
        The sequence of BuildScriptFacts instances obtained from querying the database.

    Raises
    ------
    QueryMacaronDatabaseError
        If there is an unexpected error when executing the SQLAlchemy query.
    """
    build_script_select_statment = get_sql_stmt_build_script_check(component_id)
    logger.debug(
        "Build Script Check Fact for component %d \n %s",
        component_id,
        compile_sqlite_select_statement(build_script_select_statment),
    )

    build_script_check_facts = lookup_multiple(
        select_statement=build_script_select_statment,
        session=session,
    )

    return build_script_check_facts


def extract_generic_build_command_info(
    check_facts: Sequence[BuildAsCodeFacts] | Sequence[BuildServiceFacts] | Sequence[BuildScriptFacts],
) -> list[GenericBuildCommandInfo]:
    """Return the list of GenericBuildCommandInfo instances from a list of Build related Check Facts.

    The following information are captured for each Check Facts

    - ``command``: the build command, but this information is located in different attribute depending on the
      type of Build Check Fact (e.g. in `BuildAsCodeFacts` it is stored in `deploy_command`). It's stored
      in the database as a serialized JSON object so we need to use json.loads to turn it into a list of strings.

    - ``language`` and ``build_tool_name`` are attributes of all Build Check Fact instances

    - ``language_versions`` is an attribute of all Build Check Fact instances. It's stored
      in the database as a serialized JSON object so we need to use json.loads to turn it into a list of strings.

    Parameters
    ----------
    check_facts : Sequence[BuildAsCodeFacts] | Sequence[BuildServiceFacts] | Sequence[BuildScriptFacts]
        The sequence of check facts obtained from the database.

    Returns
    -------
    list[GenericBuildCommandInfo]
        The list of GenericBuildCommandInfo instances that store build command information
        representing by the Build Check Facts.

    Raises
    ------
    json.decoder.JSONDecodeError
        If we failed to decode the JSON-serialized values stored in the Build*Facts instances.
    """
    result = []
    for fact in check_facts:
        match fact:
            case BuildAsCodeFacts():
                result.append(
                    GenericBuildCommandInfo(
                        command=json.loads(fact.deploy_command),
                        language=fact.language,
                        language_versions=json.loads(fact.language_versions) if fact.language_versions else [],
                        build_tool_name=fact.build_tool_name,
                    )
                )
            case BuildServiceFacts():
                result.append(
                    GenericBuildCommandInfo(
                        command=json.loads(fact.build_command),
                        language=fact.language,
                        language_versions=json.loads(fact.language_versions) if fact.language_versions else [],
                        build_tool_name=fact.build_tool_name,
                    )
                )
            case BuildScriptFacts():
                result.append(
                    GenericBuildCommandInfo(
                        command=json.loads(fact.build_tool_command),
                        language=fact.language,
                        language_versions=json.loads(fact.language_versions) if fact.language_versions else [],
                        build_tool_name=fact.build_tool_name,
                    )
                )

    return result


def lookup_any_build_command(component_id: int, session: Session) -> list[GenericBuildCommandInfo]:
    """Return a list of ``GenericBuildCommandInfo`` instances from looking up any available build command.

    We will look for available build command from build-related check facts.

    Parameters
    ----------
    component_id: int
        The component id to lookup the build command.
    session: Session
        The SQLAlchemy session to the database for the lookup.

    Returns
    -------
    list[GenericBuildCommandInfo]
        This list will be empty if there is no available build command for this component.

    Raises
    ------
    QueryMacaronDatabaseError
        If there is an unexpected error when executing the SQLAlchemy query for looking up the build commands.
        Raised by "lookup_*_check" functions
    """
    build_as_code_check_facts = lookup_build_as_code_check(
        component_id=component_id,
        session=session,
    )
    if build_as_code_check_facts:
        try:
            return extract_generic_build_command_info(build_as_code_check_facts)
        except json.decoder.JSONDecodeError as error:
            logger.debug(
                "Failed to extract generic build command info for build as code check facts for component id %s. "
                + "Error %s. Continue",
                component_id,
                error,
            )

    build_service_check_facts = lookup_build_service_check(
        component_id=component_id,
        session=session,
    )
    if build_service_check_facts:
        try:
            return extract_generic_build_command_info(build_service_check_facts)
        except json.decoder.JSONDecodeError as error:
            logger.debug(
                "Failed to extract generic build command info for build servoce check facts for component id %s. "
                + "Error %s. Continue",
                component_id,
                error,
            )

    build_script_check_facts = lookup_build_script_check(
        component_id=component_id,
        session=session,
    )
    try:
        return extract_generic_build_command_info(build_script_check_facts)
    except json.decoder.JSONDecodeError as error:
        logger.debug(
            "Failed to extract generic build command info for build as code check facts for component id %s. "
            + "Error %s. Continue",
            component_id,
            error,
        )
        return []


def lookup_repository(component_id: int, session: Session) -> Repository | None:
    """Return the Repository instance for given PackageURL string.

    Parameters
    ----------
    component_id : int
        The component id to look for the Repository.
    session : Session
        The SQLAlcemy Session that connects to the Macaron database.

    Returns
    -------
    Repository
        The Repository instances obtained from querying the database.

    Raises
    ------
    QueryMacaronDatabaseError
        If the query result from the database contains more than one Repository instance,
        or there is an unexpected error when executing the SQLAlchemy query.
    """
    repository_select_statement = get_sql_stmt_repository(component_id)
    logger.debug(
        "Repository for component %d \n %s.", component_id, compile_sqlite_select_statement(repository_select_statement)
    )

    repository_result = lookup_one_or_none(
        select_statement=repository_select_statement,
        session=session,
    )

    return repository_result
