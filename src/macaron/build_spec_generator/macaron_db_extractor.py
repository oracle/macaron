# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the logic to extract build relation information for a PURL from the Macaron database."""

import logging
from collections.abc import Sequence

from sqlalchemy import Select, and_, select
from sqlalchemy.dialects import sqlite
from sqlalchemy.orm import Session, aliased

from macaron.database.table_definitions import Analysis, CheckFacts, Component, MappedCheckResult, Repository
from macaron.slsa_analyzer.checks.build_as_code_check import BuildAsCodeFacts
from macaron.slsa_analyzer.checks.build_script_check import BuildScriptFacts
from macaron.slsa_analyzer.checks.build_service_check import BuildServiceFacts
from macaron.slsa_analyzer.checks.build_tool_check import BuildToolFacts

logger: logging.Logger = logging.getLogger(__name__)


def compile_sqlite_select_statement(select_statment: Select) -> str:
    """Return the SQLite SELECT statement from an SQLAlchemy Select statement.

    Parameters
    ----------
    select_statement : Select
        The SQLAlchemy Select statement.

    Returns
    -------
    str
        The equivalent SQLite statement as a string.
    """
    sqlite_str = select_statment.compile(
        dialect=sqlite.dialect(),  # type: ignore
        compile_kwargs={"literal_binds": True},
    )
    return str(sqlite_str)


def get_sql_stmt_latest_component_for_purl(purl_string: str) -> Select[tuple[Component]]:
    """Return an SQLAlchemy SELECT statement to query the latest Component.

    Parameters
    ----------
    purl_string : str
        The PackageURL string to find the Component instance.

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
            onclause=Component.id == Analysis.id,
        )
        .where(Component.purl == purl_string)
        .order_by(
            Analysis.analysis_time.desc(),
            Analysis.id.desc(),
        )
    )


def lookup_latest_component_id(purl_string: str, session: Session) -> int | None:
    """Return the component id of the latest analysis that matches a given PackageURL string.

    Parameters
    ----------
    purl_string : str
        The PackageURL string to look for the latest component id.
    session : Session
        The SQLAlcemy Session that connects to the Macaron database.

    Returns
    -------
    int | None
        The latest component id or None if there isn't one available in the database.
    """
    latest_component_id_stmt = get_sql_stmt_latest_component_for_purl(purl_string)
    logger.debug("Latest Analysis and Component query \n %s", compile_sqlite_select_statement(latest_component_id_stmt))

    component = session.execute(latest_component_id_stmt).scalars().first()

    if not component:
        return None

    return component.id


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


def lookup_build_tools_check(component_id: int, session: Session) -> Sequence[BuildToolFacts] | None:
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
    """
    build_tools_statement = get_sql_stmt_build_tools(component_id)
    logger.debug(
        "Build Tools Check Facts for component %d \n %s",
        component_id,
        compile_sqlite_select_statement(build_tools_statement),
    )

    sql_results = session.execute(build_tools_statement).scalars().all()

    return sql_results or None


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
            onclause=MappedCheckResult.id == CheckFacts.id,
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


def lookup_build_as_code_check(component_id: int, session: Session) -> Sequence[BuildAsCodeFacts] | None:
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
    """
    build_as_code_statement = get_sql_stmt_build_as_code_check(component_id)
    logger.debug(
        "Build As Code Check Fact for component %d \n %s",
        component_id,
        compile_sqlite_select_statement(build_as_code_statement),
    )

    sql_results = session.execute(build_as_code_statement).scalars().all()

    return sql_results or None


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
            onclause=MappedCheckResult.id == CheckFacts.id,
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


def lookup_build_service_check(component_id: int, session: Session) -> Sequence[BuildServiceFacts] | None:
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
    """
    build_service_statement = get_sql_stmt_build_service_check(component_id)
    logger.debug(
        "Build Service Check Fact for component %d \n %s",
        component_id,
        compile_sqlite_select_statement(build_service_statement),
    )

    sql_results = session.execute(build_service_statement).scalars().all()

    return sql_results or None


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
            onclause=Component.id == MappedCheckResult.component_id,
        )
        .join(
            CheckFacts,
            onclause=MappedCheckResult.id == CheckFacts.id,
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


def lookup_build_script_check(component_id: int, session: Session) -> Sequence[BuildScriptFacts] | None:
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
    """
    build_script_statement = get_sql_stmt_build_script_check(component_id)
    logger.debug(
        "Build Script Check Fact for component %d \n %s",
        component_id,
        compile_sqlite_select_statement(build_script_statement),
    )

    sql_results = session.execute(build_script_statement).scalars().all()

    return sql_results or None


# TODO: think more about the return type of this function, should we proceed the CheckFacts instances
# or leave it to later.
def lookup_any_build_command(component_id: int, session: Session) -> Sequence[CheckFacts] | None:
    """WIP."""
    build_as_code_check_facts = lookup_build_as_code_check(component_id, session)
    if build_as_code_check_facts:
        return build_as_code_check_facts

    build_service_check_facts = lookup_build_service_check(component_id, session)
    if build_service_check_facts:
        return build_service_check_facts

    return lookup_build_script_check(component_id, session)


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
            onclause=Component.id == Repository.id,
        )
        .where(Component.id == component_id)
    )


def lookup_repository(component_id: int, session: Session) -> Repository | None:
    """Return the Repository instance for given PackageURL string.

    Parameters
    ----------
    purl_string : str
        The PackageURL string to look for the Repository.
    session : Session
        The SQLAlcemy Session that connects to the Macaron database.

    Returns
    -------
    Repository
        The Repository instances obtained from querying the database.
    """
    repository_statement = get_sql_stmt_repository(component_id)
    logger.debug(
        "Repository for component %d \n %s.", component_id, compile_sqlite_select_statement(repository_statement)
    )

    sql_results = session.execute(repository_statement).scalars().all()

    assert len(sql_results) == 1 or len(sql_results) == 0
    return sql_results[0] or None


# TODO: can we refactor the obtaining the sql statement and execute it
# so we don't repeat them ?
# Can we perform the execution of queries in build_spec_generator so that we can handle certain sqlalchemy
# ORM exceptions if needed in the future?
