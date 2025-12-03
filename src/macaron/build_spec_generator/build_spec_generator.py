# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the functions used for generating build specs from the Macaron database."""

import json
import logging
import os
from enum import Enum

from packageurl import PackageURL
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from macaron.build_spec_generator.common_spec.core import gen_generic_build_spec
from macaron.build_spec_generator.dockerfile.dockerfile_output import gen_dockerfile
from macaron.build_spec_generator.reproducible_central.reproducible_central import gen_reproducible_central_build_spec
from macaron.console import access_handler
from macaron.errors import GenerateBuildSpecError
from macaron.path_utils.purl_based_path import get_purl_based_dir

logger: logging.Logger = logging.getLogger(__name__)


class BuildSpecFormat(str, Enum):
    """The build spec formats that we support."""

    REPRODUCIBLE_CENTRAL = "rc-buildspec"

    DEFAULT = "default-buildspec"

    DOCKERFILE = "dockerfile"


def gen_build_spec_for_purl(
    purl: PackageURL,
    database_path: str,
    build_spec_format: BuildSpecFormat,
    output_path: str,
) -> int:
    """Generate the build spec file for the given PURL in the specified output directory.

    Parameters
    ----------
    purl: PackageURL
        The package URL to generate build spec for.
    database_path: str
        The path to the Macaron SQLite database file. This database will be accessed in read-only mode,
        ensuring that no modifications can be made during operations.
    build_spec_format: BuildSpecFormat
        The format of the final build spec content.
    output_path: str
        The path to the output directory.

    Returns
    -------
    int
        The exit code for this function. ``os.EX_OK`` if everything is fine, ``os.EX_OSERR`` if the
        buildspec file cannot be created in the local filesystem, ``os.EX_DATAERR`` if there was an
        error generating the content for the buildspec file.
    """
    db_engine = create_engine(f"sqlite+pysqlite:///file:{database_path}?mode=ro&uri=true", echo=False)
    build_spec_content = None

    build_spec_dir_path = os.path.join(
        output_path,
        "buildspec",
        get_purl_based_dir(
            purl_name=purl.name,
            purl_namespace=purl.namespace,
            purl_type=purl.type,
        ),
    )

    with Session(db_engine) as session, session.begin():
        try:
            build_spec = gen_generic_build_spec(purl=purl, session=session)
        except GenerateBuildSpecError as error:
            logger.error("Error while generating the build spec: %s.", error)
            return os.EX_DATAERR
        match build_spec_format:
            case BuildSpecFormat.REPRODUCIBLE_CENTRAL:
                try:
                    build_spec_content = gen_reproducible_central_build_spec(build_spec)
                except GenerateBuildSpecError as error:
                    logger.error("Error while generating the build spec: %s.", error)
                    return os.EX_DATAERR
                build_spec_file_path = os.path.join(build_spec_dir_path, "reproducible_central.buildspec")
            # Default build spec.
            case BuildSpecFormat.DEFAULT:
                try:
                    build_spec_content = json.dumps(build_spec, indent=4)
                except ValueError as error:
                    logger.error("Error while serializing the build spec: %s.", error)
                    return os.EX_DATAERR
                build_spec_file_path = os.path.join(build_spec_dir_path, "macaron.buildspec")
            case BuildSpecFormat.DOCKERFILE:
                try:
                    build_spec_content = gen_dockerfile(build_spec)
                except ValueError as error:
                    logger.error("Error while serializing the build spec: %s.", error)
                    return os.EX_DATAERR
                build_spec_file_path = os.path.join(build_spec_dir_path, "dockerfile.buildspec")

    if not build_spec_content:
        logger.error("Error while generating the build spec.")
        return os.EX_DATAERR

    logger.debug("Build spec content: \n%s", build_spec_content)

    try:
        os.makedirs(
            name=build_spec_dir_path,
            exist_ok=True,
        )
    except OSError as error:
        logger.error("Unable to create the output file: %s.", error)
        return os.EX_OSERR

    logger.info(
        "Generating the %s format build spec to %s",
        build_spec_format.value,
        os.path.relpath(build_spec_file_path, os.getcwd()),
    )
    rich_handler = access_handler.get_handler()
    rich_handler.update_gen_build_spec("Build Spec Path:", os.path.relpath(build_spec_file_path, os.getcwd()))
    try:
        with open(build_spec_file_path, mode="w", encoding="utf-8") as file:
            file.write(build_spec_content)
    except OSError as error:
        logger.error(
            "Could not create the build spec at %s. Error: %s",
            os.path.relpath(build_spec_file_path, os.getcwd()),
            error,
        )
        return os.EX_OSERR

    return os.EX_OK
