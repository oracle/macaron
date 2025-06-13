# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the functions used for generating build specs from the Macaron database."""

import logging
from enum import Enum

from packageurl import PackageURL
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from macaron.build_spec_generator.macaron_db_extractor import (
    QueryMacaronDatabaseError,
    lookup_any_build_command,
    lookup_build_tools_check,
    lookup_latest_component_id,
    lookup_repository,
)
from macaron.errors import InvalidPURLError
from macaron.slsa_analyzer.checks.build_tool_check import BuildToolFacts

logger: logging.Logger = logging.getLogger(__name__)


class BuildSpecFormat(str, Enum):
    """The build spec format that we supports."""

    REPRODUCIBLE_CENTRAL = "rc-buildspec"


# Possible refactor: move all of our purl parsing validation
# logic to a single module.
def parse_rc_purl(purl_string: str) -> PackageURL:
    """Parse and perform some validation on the input PURL string for Reproducible-Central build spec format.

    Returns
    -------
    PackageURL
        The packageurl.PackageURL instance created from the input PURL string.

    Raises
    ------
    InvalidPURLError
        If the purl string cannot be parsed, or if it's missing some information.
    """
    try:
        maven_purl = PackageURL.from_string(purl_string)
    except ValueError as error:
        raise InvalidPURLError(f"Cannot parse purl {purl_string}") from error

    if not maven_purl.type == "maven":
        raise InvalidPURLError(f"Expect 'maven' purl type for {purl_string}, got {maven_purl.type}")

    group = maven_purl.namespace
    version = maven_purl.version
    if group is None or version is None:
        raise InvalidPURLError(f"Missing group and/or version for purl {purl_string}")

    return maven_purl


def gen_rc_build_spec_from_database(
    purl_string: str,
    database_path: str,
) -> str | None:
    """Generate a Reproducible Central build spec for a given PURL string from the database.

    Parameters
    ----------
    purl_string : str
        The PackageURL as string to generate the build spec for.
    database_path: str
        The path to the Macaron database where we extract the information.

    Returns
    -------
    str | None
        The RC build spec content or None if there exists an error.
    """
    db_engine = create_engine(f"sqlite+pysqlite:///{database_path}", echo=False)

    with Session(db_engine) as session, session.begin():
        try:
            rc_purl = parse_rc_purl(purl_string)
        except InvalidPURLError as error:
            logger.error(
                "The purl string %s is not sufficient for Reproducible-Central build spec generation. Error: %s",
                purl_string,
                error,
            )
            return None

        try:
            latest_component_id = lookup_latest_component_id(
                purl=rc_purl,
                session=session,
            )
        except QueryMacaronDatabaseError as lookup_component_error:
            logger.error(
                "Unexpected result from querying latest component id for %s. Error: %s",
                purl_string,
                lookup_component_error,
            )
            return None
        if not latest_component_id:
            logger.error(
                "Cannot find an analysis result for PackageURL %s in the database. "
                + "Please check if an analysis for it exists in the database.",
                purl_string,
            )
            return None
        logger.debug("Latest component ID: %d", latest_component_id)

        try:
            build_tool_facts = lookup_build_tools_check(
                component_id=latest_component_id,
                session=session,
            )
        except QueryMacaronDatabaseError as lookup_build_tools_error:
            logger.error(
                "Unexpected result from querying build tools for %s. Error: %s",
                purl_string,
                lookup_build_tools_error,
            )
            return None
        if not build_tool_facts:
            logger.error(
                "Cannot find any build tool for PackageURL %s in the database.",
                purl_string,
            )
            return None
        logger.debug("Build tools discovered from the %s table: %s", BuildToolFacts.__tablename__, build_tool_facts)

        # The build tool from the build tool check table is found by checking the build configs.
        # We use this as the default build tool if we cannot find any build commands from the build-related checks.
        default_build_tool_name = None
        for fact in build_tool_facts:
            if fact.build_tool_name in {"gradle", "maven"} and fact.language in {"java"}:
                # TODO: think about what to do if many build tools are discovered for a single project.!!!
                default_build_tool_name = fact.build_tool_name
                break
        if not default_build_tool_name:
            logger.error(
                "The PackageURL %s doesn't have any build tool that we support. It has %s.",
                purl_string,
                [(fact.build_tool_name, fact.language) for fact in build_tool_facts],
            )
            return None

        try:
            lookup_component_repository = lookup_repository(latest_component_id, session)
        except QueryMacaronDatabaseError as lookup_repository_error:
            logger.error(
                "Unexpected result from querying repository information for %s. Error: %s",
                purl_string,
                lookup_repository_error,
            )
            return None
        if not lookup_component_repository:
            logger.error(
                "Cannot find any repository information for %s in the database.",
                purl_string,
            )
            return None

        print(lookup_component_repository.remote_path)
        print(lookup_component_repository.commit_sha)

        try:
            lookup_build_facts = lookup_any_build_command(latest_component_id, session)
        except QueryMacaronDatabaseError as lookup_build_command_error:
            logger.error(
                "Unexpected result from querying all build command information for %s. Error: %s",
                purl_string,
                lookup_build_command_error,
            )
            return None
        print(lookup_build_facts)

        return ""
