# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the functions used for generating build specs from the Macaron database."""

import logging
import os
from collections.abc import Mapping
from enum import Enum

from packageurl import PackageURL
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from macaron.build_spec_generator.build_command_patcher import PatchCommandBuildTool, PatchValueType
from macaron.build_spec_generator.reproducible_central.reproducible_central import gen_reproducible_central_build_spec
from macaron.path_utils.purl_based_path import get_purl_based_dir

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


def gen_build_spec_for_purl(
    purl: PackageURL,
    database_path: str,
    build_spec_format: BuildSpecFormat,
    output_path: str,
) -> int:
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
    int
        The exit code for this function. ``os.EX_OK`` if everything is fine, ``os.EX_OSERR`` if the
        buildspec file cannot be created in the local filesystem, ``os.EX_DATAERR`` if there was an
        error in generate the content for the buildspec file.
    """
    db_engine = create_engine(f"sqlite+pysqlite:///{database_path}", echo=False)

    with Session(db_engine) as session, session.begin():
        build_spec_content = None
        match build_spec_format:
            case BuildSpecFormat.REPRODUCIBLE_CENTRAL:
                build_spec_content = gen_reproducible_central_build_spec(
                    purl=purl,
                    session=session,
                    patches=CLI_COMMAND_PATCHES,
                )

        if not build_spec_content:
            logger.error("Error while generate reproducible central build spec.")
            return os.EX_DATAERR

        logger.debug("Build spec content: \n%s", build_spec_content)

        build_spec_filepath = os.path.join(
            output_path,
            "buildspec",
            get_purl_based_dir(
                purl_name=purl.name,
                purl_namespace=purl.namespace,
                purl_type=purl.type,
            ),
            "macaron.buildspec",
        )

        os.makedirs(
            name=os.path.dirname(build_spec_filepath),
            exist_ok=True,
        )

        try:
            with open(build_spec_filepath, mode="w", encoding="utf-8") as file:
                logger.info(
                    "Generating the %s format build spec to %s.",
                    build_spec_format.value,
                    os.path.relpath(build_spec_filepath, os.getcwd()),
                )
                file.write(build_spec_content)
        except OSError as error:
            logger.error(
                "Could not generate the Buildspec to %s. Error: %s",
                os.path.relpath(build_spec_filepath, os.getcwd()),
                error,
            )
            return os.EX_OSERR

        return os.EX_OK
