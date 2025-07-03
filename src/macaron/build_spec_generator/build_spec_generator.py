# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the functions used for generating build specs from the Macaron database."""

import logging
from collections.abc import Mapping
from enum import Enum

from packageurl import PackageURL
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from macaron.build_spec_generator.build_command_patcher import PatchCommandBuildTool, PatchValueType
from macaron.build_spec_generator.internal_build_info import InternalBuildInfo
from macaron.build_spec_generator.macaron_db_extractor import (
    lookup_any_build_command,
    lookup_build_tools_check,
    lookup_latest_component_id,
    lookup_repository,
)
from macaron.build_spec_generator.reproducible_central import gen_reproducible_central_build_spec
from macaron.errors import QueryMacaronDatabaseError
from macaron.slsa_analyzer.checks.build_tool_check import BuildToolFacts

logger: logging.Logger = logging.getLogger(__name__)


class BuildSpecFormat(str, Enum):
    """The build spec format that we supports."""

    REPRODUCIBLE_CENTRAL = "rc-buildspec"


CLI_COMMAND_PATCHES: dict[
    PatchCommandBuildTool,
    Mapping[str, PatchValueType | None],
] = {
    PatchCommandBuildTool.MAVEN: {
        "goals": ["clean", "package"],
        "--batch-mode": False,
        "--quiet": False,
        "--no-transfer-progress": False,
        # Example pkg:maven/io.liftwizard/liftwizard-servlet-logging-mdc@1.0.1
        # https://github.com/liftwizard/liftwizard/blob/
        # 4ea841ffc9335b22a28a7a19f9156e8ba5820027/.github/workflows/build-and-test.yml#L23
        "--threads": None,
        # For cases such as
        # pkg:maven/org.apache.isis.valuetypes/isis-valuetypes-prism-resources@2.0.0-M7
        "--version": False,
        "--define": {
            # pkg:maven/org.owasp/dependency-check-utils@7.3.2
            # To remove "-Dgpg.passphrase=$MACARON_UNKNOWN"
            "gpg.passphrase": None,
            "skipTests": "true",
            "maven.test.skip": "true",
            "maven.site.skip": "true",
            "rat.skip": "true",
            "maven.javadoc.skip": "true",
        },
    },
    PatchCommandBuildTool.GRADLE: {
        "tasks": ["clean", "assemble"],
        "--console": "plain",
        "--exclude-task": ["test"],
        "--project-prop": {
            "skip.signing": "",
            "skipSigning": "",
            "gnupg.skip": "",
        },
    },
}


def gen_build_spec_str(
    purl: PackageURL,
    database_path: str,
    build_spec_format: BuildSpecFormat,
) -> str | None:
    """Return the content of a build spec file from a given PURL.

    Parameters
    ----------
    purl: PackageURL
        The package URL to generate build spec for.
    database_path: str
        The path to the Macaron database.
    build_spec_format: BuildSpecFormat
        The format of the final build spec content.

    Returns
    -------
    str | None
        The build spec content as a string, or None if there is an error.
    """
    db_engine = create_engine(f"sqlite+pysqlite:///{database_path}", echo=False)

    with Session(db_engine) as session, session.begin():
        internal_build_info = get_internal_build_info(
            purl=purl,
            session=session,
        )

        if not internal_build_info:
            logger.error(
                "Failed to obtain necessary data for purl %s from the database %s",
                purl,
                database_path,
            )
            return None

        match build_spec_format:
            case BuildSpecFormat.REPRODUCIBLE_CENTRAL:
                build_spec_content = gen_reproducible_central_build_spec(
                    build_info=internal_build_info,
                    # TODO: update this later
                    patches=CLI_COMMAND_PATCHES,
                )

                return build_spec_content


def get_internal_build_info(
    purl: PackageURL,
    session: Session,
) -> InternalBuildInfo | None:
    """Return an ``InternalBuildInfo`` instance that captures the build related information for a PackageURL.

    Parameters
    ----------
    purl: PackageURL
        The PackageURL to extract information about.
    session: Session
        The SQLAlchemy Session for the Macaron database.

    Returns
    -------
    InternalBuildInfo | None
        An instance of ``InternalBuildInfo`` or None if there was an error.
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

    return InternalBuildInfo(
        purl=purl,
        repository=lookup_component_repository,
        latest_component_id=latest_component_id,
        build_tool_facts=build_tool_facts,
        generic_build_command_facts=lookup_build_facts,
    )
