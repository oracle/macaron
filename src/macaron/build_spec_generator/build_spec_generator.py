# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the functions used for generating build specs from the Macaron database."""

import logging
from enum import Enum

from packageurl import PackageURL
from sqlalchemy.engine import create_engine
from sqlalchemy.orm import Session

from macaron.build_spec_generator.macaron_db_extractor import (
    lookup_any_build_command,
    lookup_build_tools_check,
    lookup_latest_component_id,
    lookup_repository,
)
from macaron.errors import InvalidPURLError
from macaron.slsa_analyzer.checks.build_tool_check import BuildToolFacts

logger: logging.Logger = logging.getLogger(__name__)


class BuildSpecGenerationError(Exception):
    """Happens when there is unexpected error during the build spec generation."""


class BuildSpecFormat(str, Enum):
    """The build spec format that we supports."""

    REPRODUCIBLE_CENTRAL = "rc-buildspec"


def gen_build_spec_from_database(
    purl_string: str,
    database_path: str,
    build_spec_format: str,
) -> str:
    """Generate a build spec for a given PURL string from the database.

    Parameters
    ----------
    purl_string : str
        The PackageURL as string to generate the build spec for.
    database_path: str
        The path to the Macaron database where we extract the information.
    build_spec_format : str
        The format of the output build spec file.

    Returns
    -------
    str
        The build spec file content as a string.
    """
    if build_spec_format not in [ele.value for ele in BuildSpecFormat]:
        raise BuildSpecGenerationError(f"The output format {build_spec_format} is not supported")

    db_engine = create_engine(f"sqlite+pysqlite:///{database_path}", echo=False)

    with Session(db_engine) as session, session.begin():
        latest_component_id = lookup_latest_component_id(purl_string, session)
        if not latest_component_id:
            raise BuildSpecGenerationError(f"Cannot find an analysis result for PackageURL {purl_string}.")
        logger.debug("Latest component ID: %d", latest_component_id)

        build_tool_facts = lookup_build_tools_check(latest_component_id, session)
        if not build_tool_facts:
            raise BuildSpecGenerationError(
                f"Cannot find any build tool in the {BuildToolFacts.__tablename__} table for PackageURL {purl_string}."
            )
        logger.debug("Build tools discovered from the %s table: %s", BuildToolFacts.__tablename__, build_tool_facts)

        # The build tool from the build tool check table is found by checking the build configs.
        # We use this as the default build tool if we cannot find any build commands from the build-related checks.
        default_build_tool_name = None
        for fact in build_tool_facts:
            if fact.build_tool_name in {"gradle", "maven"} and fact.language in {"java"}:
                default_build_tool_name = fact.build_tool_name
        if not default_build_tool_name:
            raise BuildSpecGenerationError(f"The PackageURL {purl_string} doesn't have any build tool that we support.")

        lookup_build_facts = lookup_any_build_command(latest_component_id, session)
        if not lookup_build_facts:
            logger.info(
                "Cannot find any build facts for component %d. " + "Use the default build command for %s.",
                latest_component_id,
                default_build_tool_name,
            )
            # lookup_build_facts = ...

        lookup_component_repository = lookup_repository(latest_component_id, session)
        if not lookup_component_repository:
            raise BuildSpecGenerationError(f"The PackageURL {purl_string} doesn't have any repository information.")

        print(lookup_component_repository.remote_path)
        print(lookup_component_repository.commit_sha)

    return ""


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


# def gen_build_spec_rc(
#     purl_string: str,
#     session: Session,
# ) -> str:
#     """Generate the build spec in Reproducible Central format.

#     WIP.
#     """
#     try:
#         rc_purl = parse_rc_purl(purl_string)
#     except InvalidPURLError as error:
#         raise BuildSpecGenerationError(
#             f"The purl string {purl_string} is not sufficient for Reproducible-Central build spec generation"
#         ) from error

#     return ""
