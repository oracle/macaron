# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module includes build specification and helper classes for PyPI packages."""

import logging
import os
import re

import tomli
from packageurl import PackageURL
from packaging.requirements import InvalidRequirement, Requirement

from macaron.build_spec_generator.common_spec.base_spec import BaseBuildSpec, BaseBuildSpecDict
from macaron.config.defaults import defaults
from macaron.errors import SourceCodeError
from macaron.slsa_analyzer.package_registry import pypi_registry
from macaron.slsa_analyzer.specs.package_registry_spec import PackageRegistryInfo

logger: logging.Logger = logging.getLogger(__name__)


class PyPIBuildSpec(
    BaseBuildSpec,
):
    """This class implements build spec inferences for PyPI packages."""

    def __init__(self, data: BaseBuildSpecDict):
        """
        Initialize the object.

        Parameters
        ----------
        data : BaseBuildSpecDict
            The data object containing the build configuration fields.
        """
        self.data = data

    def resolve_fields(self, purl: PackageURL) -> None:
        """
        Resolve PyPI-specific fields in the build specification.

        Parameters
        ----------
        purl: str
            The target software component Package URL.
        """
        if purl.type != "pypi":
            return

        registry = pypi_registry.PyPIRegistry()
        registry.load_defaults()

        registry_info = PackageRegistryInfo(
            build_tool_name="pip",
            build_tool_purl_type="pypi",
            package_registry=registry,
            metadata=[],
        )

        pypi_package_json = pypi_registry.find_or_create_pypi_asset(purl.name, purl.version, registry_info)

        if pypi_package_json is not None:
            if pypi_package_json.package_json or pypi_package_json.download(dest=""):
                requires_array: list[str] = []
                build_backends: dict[str, str] = {}
                try:
                    with pypi_package_json.wheel():
                        logger.debug("Wheel at %s", pypi_package_json.wheel_path)
                        # Should only have .dist-info directory
                        logger.debug("It has directories %s", ",".join(os.listdir(pypi_package_json.wheel_path)))
                        # Make build-req array
                        wheel_contents, metadata_contents = self.read_directory(pypi_package_json.wheel_path, purl)
                        generator, version = self.read_generator_line(wheel_contents)
                        if generator != "":
                            build_backends[generator] = "==" + version
                        if generator != "setuptools":
                            # Apply METADATA heuristics to determine setuptools version
                            if "License-File" in metadata_contents:
                                build_backends["setuptools"] = "==" + defaults.get(
                                    "heuristic.pypi", "setuptools_version_emitting_license"
                                )
                            elif "Platform: UNKNOWN" in metadata_contents:
                                build_backends["setuptools"] = "==" + defaults.get(
                                    "heuristic.pypi", "setuptools_version_emitting_platform_unknown"
                                )
                            else:
                                build_backends["setuptools"] = "==" + defaults.get(
                                    "heuristic.pypi", "default_setuptools"
                                )
                except SourceCodeError:
                    logger.debug("Could not find pure wheel matching this PURL")

                logger.debug("From .dist_info:")
                logger.debug(build_backends)

                try:
                    with pypi_package_json.sourcecode():
                        try:
                            pyproject_content = pypi_package_json.get_sourcecode_file_contents("pyproject.toml")
                            content = tomli.loads(pyproject_content.decode("utf-8"))
                            build_system: dict[str, list[str]] = content.get("build-system", {})
                            requires_array = build_system.get("requires", [])
                            logger.debug("From pyproject.toml:")
                            logger.debug(requires_array)
                        except SourceCodeError:
                            logger.debug("No pyproject.toml found")
                except SourceCodeError:
                    logger.debug("No source distribution found")

                # Merge in pyproject.toml information only when the wheel dist_info does not contain the same
                # Hatch is an interesting example of this merge being required.
                for requirement in requires_array:
                    try:
                        parsed_requirement = Requirement(requirement)
                        if parsed_requirement.name not in build_backends:
                            build_backends[parsed_requirement.name] = str(parsed_requirement.specifier)
                    except InvalidRequirement:
                        logger.debug("Malformed requirement encountered:")
                        logger.debug(requirement)

                logger.debug("Combined:")
                logger.debug(build_backends)
                self.data["build_backends"] = build_backends

    def read_directory(self, wheel_path: str, purl: PackageURL) -> tuple[str, str]:
        """
        Read in the WHEEL and METADATA file from the .dist_info directory.

        Parameters
        ----------
        wheel_path : str
            Path to the temporary directory where the wheel was
            downloaded into.
        purl: PackageURL
            PURL corresponding to the package being analyzed.

        Returns
        -------
        tuple[str, str]
            Tuple where the first element is a string of the .dist-info/WHEEL
            contents and the second element is a string of the .dist-info/METADATA
            contents
        """
        # From https://peps.python.org/pep-0427/#escaping-and-unicode
        normalized_name = re.sub(r"[^\w\d.]+", "_", purl.name, re.UNICODE)
        dist_info = f"{normalized_name}-{purl.version}.dist-info"
        logger.debug(dist_info)

        dist_info_path = os.path.join(wheel_path, dist_info)

        if not os.path.isdir(dist_info_path):
            return "", ""

        wheel_path = os.path.join(dist_info_path, "WHEEL")
        metadata_path = os.path.join(dist_info_path, "METADATA")

        wheel_contents = ""
        metadata_contents = ""

        if os.path.exists(wheel_path):
            with open(wheel_path, encoding="utf-8") as wheel_file:
                wheel_contents = wheel_file.read()
        if os.path.exists(metadata_path):
            with open(metadata_path, encoding="utf-8") as metadata_file:
                metadata_contents = metadata_file.read()

        return wheel_contents, metadata_contents

    def read_generator_line(self, wheel_contents: str) -> tuple[str, str]:
        """
        Parse through the "Generator: {build backend} {version}" line of .dist_info/WHEEL.

        Parameters
        ----------
        wheel_contents : str
            String of the contents of the .dist_info/WHEEL file

        Returns
        -------
        tuple[str, str]
            Tuple where the first element is the generating build backend and
            the second element is its version.
        """
        for line in wheel_contents.splitlines():
            if line.startswith("Generator:"):
                split_line = line.split(" ")
                return split_line[1], split_line[2]
        return "", ""
