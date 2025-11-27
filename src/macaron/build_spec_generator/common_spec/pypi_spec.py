# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module includes build specification and helper classes for PyPI packages."""

import logging
import os
import re

import tomli
from packageurl import PackageURL
from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier
from packaging.utils import InvalidWheelFilename, parse_wheel_filename

from macaron.build_spec_generator.build_command_patcher import CLI_COMMAND_PATCHES, patch_commands
from macaron.build_spec_generator.common_spec.base_spec import BaseBuildSpec, BaseBuildSpecDict
from macaron.config.defaults import defaults
from macaron.errors import GenerateBuildSpecError, SourceCodeError
from macaron.json_tools import json_extract
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

    def get_default_build_commands(
        self,
        build_tool_names: list[str],
    ) -> list[list[str]]:
        """Return the default build commands for the build tools.

        Parameters
        ----------
        build_tool_names: list[str]
            The build tools to get the default build command.

        Returns
        -------
        list[list[str]]
            The build command as a list[list[str]].

        Raises
        ------
        GenerateBuildSpecError
            If there is no default build command available for the specified build tool.
        """
        default_build_commands = []

        for build_tool_name in build_tool_names:

            match build_tool_name:
                case "pip":
                    default_build_commands.append("python -m build".split())
                case "poetry":
                    default_build_commands.append("poetry build".split())
                case "flit":
                    default_build_commands.append("flit build".split())
                case "hatch":
                    default_build_commands.append("hatch build".split())
                case "conda":
                    default_build_commands.append("conda build".split())
                case _:
                    pass

        if not default_build_commands:
            logger.critical(
                "There is no default build command available for the build tools %s.",
                build_tool_names,
            )
            raise GenerateBuildSpecError("Unable to find a default build command.")

        return default_build_commands

    def resolve_fields(self, purl: PackageURL) -> None:
        """
        Resolve PyPI-specific fields in the build specification.

        Parameters
        ----------
        purl: str
            The target software component Package URL.
        """
        if purl.type != "pypi" or purl.version is None:
            return

        registry = pypi_registry.PyPIRegistry()
        registry.load_defaults()

        registry_info = PackageRegistryInfo(
            ecosystem="pypi",
            package_registry=registry,
            metadata=[],
        )

        pypi_package_json = pypi_registry.find_or_create_pypi_asset(purl.name, purl.version, registry_info)
        patched_build_commands: list[list[str]] = []
        build_requires_set: set[str] = set()
        build_backends_set: set[str] = set()
        parsed_build_requires: dict[str, str] = {}
        python_version_set: set[str] = set()
        wheel_name_python_version_list: list[str] = []
        wheel_name_platforms: set[str] = set()

        if pypi_package_json is not None:
            if pypi_package_json.package_json or pypi_package_json.download(dest=""):

                # Get the Python constraints from the PyPI JSON response.
                json_releases = pypi_package_json.get_releases()
                if json_releases:
                    releases = json_extract(json_releases, [purl.version], list) or []
                    for release in releases:
                        if py_version := json_extract(release, ["requires_python"], str):
                            python_version_set.add(py_version.replace(" ", ""))

                try:
                    with pypi_package_json.wheel():
                        logger.debug("Wheel at %s", pypi_package_json.wheel_path)
                        # Should only have .dist-info directory.
                        logger.debug("It has directories %s", ",".join(os.listdir(pypi_package_json.wheel_path)))
                        wheel_contents, metadata_contents = self.read_directory(pypi_package_json.wheel_path, purl)
                        generator, version = self.read_generator_line(wheel_contents)
                        if generator != "" and version != "":
                            parsed_build_requires[generator] = "==" + version.replace(" ", "")
                        # Apply METADATA heuristics to determine setuptools version.
                        elif "License-File" in metadata_contents:
                            parsed_build_requires["setuptools"] = "==" + defaults.get(
                                "heuristic.pypi", "setuptools_version_emitting_license"
                            )
                        elif "Platform: UNKNOWN" in metadata_contents:
                            parsed_build_requires["setuptools"] = "==" + defaults.get(
                                "heuristic.pypi", "setuptools_version_emitting_platform_unknown"
                            )
                except SourceCodeError:
                    logger.debug("Could not find pure wheel matching this PURL")

                logger.debug("From .dist_info:")
                logger.debug(parsed_build_requires)

                try:
                    with pypi_package_json.sourcecode():
                        try:
                            pyproject_content = pypi_package_json.get_sourcecode_file_contents("pyproject.toml")
                            content = tomli.loads(pyproject_content.decode("utf-8"))
                            requires = json_extract(content, ["build-system", "requires"], list)
                            if requires:
                                build_requires_set.update(elem.replace(" ", "") for elem in requires)
                            backend = json_extract(content, ["build-system", "build-backend"], str)
                            if backend:
                                build_backends_set.add(backend.replace(" ", ""))

                            python_version_constraint = json_extract(content, ["project", "requires-python"], str)
                            if python_version_constraint:
                                python_version_set.add(python_version_constraint.replace(" ", ""))
                            logger.debug(
                                "After analyzing pyproject.toml from the sdist: build-requires: %s, build_backend: %s",
                                build_requires_set,
                                build_backends_set,
                            )
                        except TypeError as error:
                            logger.debug(
                                "Found a type error while reading the pyproject.toml file from the sdist: %s", error
                            )
                        except tomli.TOMLDecodeError as error:
                            logger.debug("Failed to read the pyproject.toml file from the sdist: %s", error)
                        except SourceCodeError as error:
                            logger.debug("No pyproject.toml found: %s", error)
                except SourceCodeError as error:
                    logger.debug("No source distribution found: %s", error)

                # Merge in pyproject.toml information only when the wheel dist_info does not contain the same.
                # Hatch is an interesting example of this merge being required.
                for requirement in build_requires_set:
                    try:
                        parsed_requirement = Requirement(requirement)
                        if parsed_requirement.name not in parsed_build_requires:
                            parsed_build_requires[parsed_requirement.name] = str(parsed_requirement.specifier)
                    except (InvalidRequirement, InvalidSpecifier) as error:
                        logger.debug("Malformed requirement encountered %s : %s", requirement, error)

                try:
                    # Get information from the wheel file name.
                    logger.debug(pypi_package_json.wheel_filename)
                    _, _, _, tags = parse_wheel_filename(pypi_package_json.wheel_filename)
                    for tag in tags:
                        wheel_name_python_version_list.append(tag.interpreter)
                        wheel_name_platforms.add(tag.platform)
                    logger.debug(python_version_set)
                except InvalidWheelFilename:
                    logger.debug("Could not parse wheel file name to extract version")

                self.data["language_version"] = list(python_version_set) or wheel_name_python_version_list

                # Use the default build command for pure Python packages.
                if "any" in wheel_name_platforms:
                    patched_build_commands = self.get_default_build_commands(self.data["build_tools"])

        # If we were not able to find any build  and backends, use the default setuptools.
        if not parsed_build_requires:
            parsed_build_requires["setuptools"] = "==" + defaults.get("heuristic.pypi", "default_setuptools")
        if not build_backends_set:
            build_backends_set.add("setuptools.build_meta")

        logger.debug("Combined build-requires: %s", parsed_build_requires)
        self.data["build_requires"] = parsed_build_requires
        self.data["build_backends"] = list(build_backends_set)

        if not patched_build_commands:
            # Resolve and patch build commands.
            selected_build_commands = self.data["build_commands"] or self.get_default_build_commands(
                self.data["build_tools"]
            )

            patched_build_commands = (
                patch_commands(
                    cmds_sequence=selected_build_commands,
                    patches=CLI_COMMAND_PATCHES,
                )
                or []
            )
            if not patched_build_commands:
                raise GenerateBuildSpecError(f"Failed to patch command sequences {selected_build_commands}.")

        self.data["build_commands"] = patched_build_commands

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
                if len(split_line) > 2:
                    backend = split_line[1]
                    match backend:
                        case "bdist_wheel":
                            backend = "wheel"
                    version = self.parse_generator_version(split_line[2])
                    return backend, version
        return "", ""

    def parse_generator_version(self, literal_version_specification: str) -> str:
        """
        Parse the generator's version.

        Parameters
        ----------
        version_literal : str
            Version string corresponding to generator.

        Returns
        -------
        str
            Sanitized and standardized version specifier.

        Examples
        --------
        >>> spec = PyPIBuildSpec(None)
        >>> spec.parse_generator_version("(1.2.3)")
        '1.2.3'
        >>> spec.parse_generator_version("1.2.3")
        '1.2.3'
        >>> spec.parse_generator_version("10.2.3")
        '10.2.3'
        >>> spec.parse_generator_version("(10.2.3)")
        '10.2.3'
        >>> spec.parse_generator_version("a.b.c")
        ''
        >>> spec.parse_generator_version("1..2.3")
        ''
        >>> spec.parse_generator_version("(1..2.3)")
        ''
        """
        # Two patterns p1 and p2 rather than just one
        # (p1)|(p2) as the latter complicates the group to return
        pattern_plain = re.compile(r"^(\d+(\.(\d)+)*)$")
        plain_match = pattern_plain.match(literal_version_specification)
        pattern_parenthesis = re.compile(r"^\((\d+(\.(\d)+)*)\)$")
        parenthesis_match = pattern_parenthesis.match(literal_version_specification)
        if plain_match:
            return plain_match.group(1)
        if parenthesis_match:
            return parenthesis_match.group(1)
        return ""
