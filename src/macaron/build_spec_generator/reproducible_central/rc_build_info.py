# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the representation of information needed for Reproducible Central Buildspec generation."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from packageurl import PackageURL
from sqlalchemy.orm import Session

from macaron.build_spec_generator.macaron_db_extractor import (
    GenericBuildCommandInfo,
    lookup_any_build_command,
    lookup_build_tools_check,
    lookup_latest_component_id,
    lookup_repository,
)
from macaron.database.table_definitions import Repository
from macaron.errors import QueryMacaronDatabaseError
from macaron.slsa_analyzer.checks.build_tool_check import BuildToolFacts

logger: logging.Logger = logging.getLogger(__name__)


@dataclass
class RcInternalBuildInfo:
    """An internal representation of the information obtained from the database for a PURL.

    This is only used for generating the Reproducible Central build spec.
    """

    purl: PackageURL
    repository: Repository
    generic_build_command_facts: Sequence[GenericBuildCommandInfo] | None
    latest_component_id: int
    build_tool_facts: Sequence[BuildToolFacts]


def get_rc_internal_build_info(
    purl: PackageURL,
    session: Session,
) -> RcInternalBuildInfo | None:
    """Return an ``RcInternalBuildInfo`` instance that captures the build related information for a PackageURL.

    Parameters
    ----------
    purl: PackageURL
        The PackageURL to extract information about.
    session: Session
        The SQLAlchemy Session for the Macaron database.

    Returns
    -------
    RcInternalBuildInfo | None
        An instance of ``RcInternalBuildInfo`` or None if there was an error.
    """
    try:
        latest_component_id = lookup_latest_component_id(
            purl=purl,
            session=session,
        )
    except QueryMacaronDatabaseError as lookup_component_error:
        logger.error(
            "Unexpected result from querying latest component id for %s. Error: %s",
            purl.to_string(),
            lookup_component_error,
        )
        return None
    if not latest_component_id:
        logger.error(
            "Cannot find an analysis result for PackageURL %s in the database. "
            + "Please check if an analysis for it exists in the database.",
            purl.to_string(),
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
            purl.to_string(),
            lookup_build_tools_error,
        )
        return None
    if not build_tool_facts:
        logger.error(
            "Cannot find any build tool for PackageURL %s in the database.",
            purl.to_string(),
        )
        return None
    logger.debug("Build tools discovered from the %s table: %s", BuildToolFacts.__tablename__, build_tool_facts)

    try:
        lookup_component_repository = lookup_repository(latest_component_id, session)
    except QueryMacaronDatabaseError as lookup_repository_error:
        logger.error(
            "Unexpected result from querying repository information for %s. Error: %s",
            purl.to_string(),
            lookup_repository_error,
        )
        return None
    if not lookup_component_repository:
        logger.error(
            "Cannot find any repository information for %s in the database.",
            purl.to_string(),
        )
        return None

    try:
        lookup_build_facts = lookup_any_build_command(latest_component_id, session)
    except QueryMacaronDatabaseError as lookup_build_command_error:
        logger.error(
            "Unexpected result from querying all build command information for %s. Error: %s",
            purl.to_string(),
            lookup_build_command_error,
        )
        return None

    return RcInternalBuildInfo(
        purl=purl,
        repository=lookup_component_repository,
        latest_component_id=latest_component_id,
        build_tool_facts=build_tool_facts,
        generic_build_command_facts=lookup_build_facts,
    )
