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


# SELECT
#     analysis.analysis_time, analysis.id, component.id
# FROM
#     component
# INNER JOIN
#     analysis
# ON
#     analysis.id = component.analysis_id
# WHERE
#     component.purl = ?
def get_sql_stmt_latest_component_for_purl(purl_string: str) -> Select[tuple[Component]]:
    """Return an SQLAlchemy SELECT statement to query the latest Component.

    Parameters
    ----------
    purl_string : str
        The PackageURL string to find the Component instance.

    Returns
    -------
    Select[tuple[Component, Analysis]]
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
    """Return None if the value is not available in the database."""
    latest_component_id_stmt = get_sql_stmt_latest_component_for_purl(purl_string)
    logger.debug("Latest Analysis and Component query \n %s", compile_sqlite_select_statement(latest_component_id_stmt))

    component = session.execute(latest_component_id_stmt).scalars().first()

    if not component:
        return None

    return component.id


# SELECT
#     build_tool_check.build_tool_name,
#     build_tool_check.language
# FROM
#     component
# INNER JOIN
#     check_result
# ON
#     component.id = check_result.component_id
# INNER JOIN
#     check_facts
# ON
#     check_result.id = check_facts.check_result_id
# INNER JOIN
#     build_tool_check
# ON
#     check_facts.id = build_tool_check.id
# WHERE
#     component.id = ?
# ORDER BY
#     check_facts.confidence DESC, build_tool_check.id ASC
def get_sql_stmt_build_tools(component_id: int) -> Select[tuple[BuildToolFacts]]:
    """WIP."""
    # https://docs.sqlalchemy.org/en/20/errors.html#an-alias-is-being-generated-automatically-due-to-overlapping-tables
    # TODO: explain why we need this.
    build_tool_facts_alias = aliased(BuildToolFacts, flat=True)

    # There are 2 ways we can perform the join, on the table or on a relationship
    # I decide to join on the table, with explicit ON clause.
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
    """WIP."""
    build_tools_statement = get_sql_stmt_build_tools(component_id)
    logger.debug(
        "Build Tools Check Facts for component %d \n %s",
        component_id,
        compile_sqlite_select_statement(build_tools_statement),
    )

    sql_results = session.execute(build_tools_statement).scalars().all()

    return sql_results or None


# SELECT
#     build_as_code_check.deploy_command,
#     build_as_code_check.build_tool_name,
#     build_as_code_check.language,
#     build_as_code_check.language_distributions,
#     build_as_code_check.language_versions
# FROM
#     component
# INNER JOIN
#     check_result
# ON
#     component.id = check_result.component_id
# INNER JOIN
#     check_facts
# ON
#     check_result.id = check_facts.check_result_id
# INNER JOIN
#     build_as_code_check
# ON
#     check_facts.id = build_as_code_check.id
# WHERE
#     component.id = ? AND build_as_code_check.deploy_command IS NOT NULL
# ORDER BY
#     check_facts.confidence DESC, build_as_code_check.id ASC
def get_sql_stmt_build_as_code_check(component_id: int) -> Select[tuple[BuildAsCodeFacts]]:
    """WIP."""
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
    """WIP."""
    build_as_code_statement = get_sql_stmt_build_as_code_check(component_id)
    logger.debug(
        "Build As Code Check Fact for component %d \n %s",
        component_id,
        compile_sqlite_select_statement(build_as_code_statement),
    )

    sql_results = session.execute(build_as_code_statement).scalars().all()

    return sql_results or None


# SELECT
#     build_service_check.build_command,
#     build_service_check.build_tool_name,
#     build_service_check.language,
#     build_service_check.language_distributions,
#     build_service_check.language_versions
# FROM
#     component
# INNER JOIN
#     check_result
# ON
#     component.id = check_result.component_id
# INNER JOIN
#     check_facts
# ON
#     check_result.id = check_facts.check_result_id
# INNER JOIN
#     build_service_check
# ON
#     check_facts.id = build_service_check.id
# WHERE
#     component.id = ? AND build_service_check.build_command IS NOT NULL
# ORDER BY
#     check_facts.confidence DESC, build_service_check.id ASC
def get_sql_stmt_build_service_check(component_id: int) -> Select[tuple[BuildServiceFacts]]:
    """WIP."""
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
    """WIP."""
    build_service_statement = get_sql_stmt_build_service_check(component_id)
    logger.debug(
        "Build Service Check Fact for component %d \n %s",
        component_id,
        compile_sqlite_select_statement(build_service_statement),
    )

    sql_results = session.execute(build_service_statement).scalars().all()

    return sql_results or None


# SELECT
#     build_script_check.build_tool_command,
#     build_script_check.build_tool_name,
#     build_script_check.language,
#     build_script_check.language_distributions,
#     build_script_check.language_versions
# FROM
#     component
# INNER JOIN
#     check_result
# ON
#     component.id = check_result.component_id
# INNER JOIN
#     check_facts
# ON
#     check_result.id = check_facts.check_result_id
# INNER JOIN
#     build_script_check
# ON
#     check_facts.id = build_script_check.id
# WHERE
#     component.id = ? AND build_script_check.build_tool_command IS NOT NULL
# ORDER BY
#     check_facts.confidence DESC, build_script_check.id ASC
def get_sql_stmt_build_script_check(component_id: int) -> Select[tuple[BuildScriptFacts]]:
    """WIP."""
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
    """WIP."""
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
    """WIP."""
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
    """WIP."""
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
