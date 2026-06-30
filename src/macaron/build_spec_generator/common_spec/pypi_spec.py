# Copyright (c) 2025 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module includes build specification and helper classes for PyPI packages."""

import logging
import os
import re
from typing import Any

import tomli
from packageurl import PackageURL
from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier
from packaging.utils import InvalidWheelFilename, parse_wheel_filename

from macaron.build_spec_generator.common_spec.base_spec import (
    BaseBuildSpec,
    BaseBuildSpecDict,
    SpecBuildCommandDict,
    SpecBuildRequirementDict,
)
from macaron.config.defaults import defaults
from macaron.errors import SourceCodeError, WheelTagError
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

    def set_default_build_commands(
        self,
        build_cmd_spec: SpecBuildCommandDict,
    ) -> None:
        """Return the default build commands for the build tools.

        Parameters
        ----------
        build_cmd_spec: SpecBuildCommandDict
            The build command and related information.
        """
        match build_cmd_spec["build_tool"]:
            case "pip":
                build_cmd_spec["command"] = ["python", "-m", "build", "--wheel", "-n"]
            case "poetry":
                build_cmd_spec["command"] = ["poetry", "build"]
            case "uv":
                build_cmd_spec["command"] = ["uv", "build"]
            case "flit":
                # We might also want to deal with existence flit.ini, we can do so via
                # "python -m flit.tomlify"
                build_cmd_spec["command"] = ["flit", "build"]
            case "hatch":
                build_cmd_spec["command"] = ["hatch", "build"]
            case "maturin":
                build_cmd_spec["command"] = ["maturin", "build", "--release"]
            case _:
                logger.debug(
                    "There is no default build command available for the build tools %s.",
                    build_cmd_spec["build_tool"],
                )

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

        upstream_artifacts: dict[str, list[str]] = {}
        pypi_package_json = pypi_registry.find_or_create_pypi_asset(purl.name, purl.version, registry_info)
        build_backends_set: set[str] = set()
        parsed_build_requires: dict[str, SpecBuildRequirementDict] = {}
        sdist_build_requires: dict[str, SpecBuildRequirementDict] = {}
        python_version_set: set[str] = set()
        wheel_name_python_version_set: set[str] = set()
        dependency_python_version_set: set[str] = set()
        # Precautionary fallback to default version
        chronologically_likeliest_version: str = defaults.get("heuristic.pypi", "default_setuptools")

        if pypi_package_json is not None:
            if pypi_package_json.package_json or pypi_package_json.download(dest=""):
                # Get the Python constraints from the PyPI JSON response.
                json_releases = pypi_package_json.get_releases()
                if json_releases:
                    releases = json_extract(json_releases, [purl.version], list) or []
                    for release in releases:
                        if py_version := json_extract(release, ["requires_python"], str):
                            python_version_set.add(py_version.replace(" ", ""))

                logger.debug("From package JSON inferred Python constraints: %s", python_version_set)

                self.data["has_binaries"] = pypi_package_json.has_non_pure_wheel()

                if self.data["has_binaries"]:
                    logger.debug("Can not find a pure wheel")
                else:
                    logger.debug("Found pure wheel matching this PURL")

                try:
                    # The wheel function handles downloading binaries in the case that we cannot find a pure wheel.
                    with pypi_package_json.wheel(download_binaries=self.data["has_binaries"]):
                        upstream_artifacts["wheels"] = pypi_package_json.wheel_urls
                        logger.debug("Wheel at %s", pypi_package_json.wheel_path)
                        # Should only have .dist-info directory.
                        logger.debug("It has directories %s", ",".join(os.listdir(pypi_package_json.wheel_path)))
                        wheel_contents, metadata_contents = self.read_directory(pypi_package_json.wheel_path, purl)
                        generator, version = self.read_generator_line(wheel_contents)
                        if generator != "" and version != "":
                            self.add_to_build_requires(
                                parsed_build_requires, generator, "pip", "==" + version.replace(" ", "")
                            )
                        # Apply METADATA heuristics to determine setuptools version.
                        elif "License-File" in metadata_contents:
                            self.add_to_build_requires(
                                parsed_build_requires,
                                "setuptools",
                                "pip",
                                "==" + defaults.get("heuristic.pypi", "setuptools_version_emitting_license"),
                            )
                        elif "Platform: UNKNOWN" in metadata_contents:
                            self.add_to_build_requires(
                                parsed_build_requires,
                                "setuptools",
                                "pip",
                                "==" + defaults.get("heuristic.pypi", "setuptools_version_emitting_platform_unknown"),
                            )
                        chronologically_likeliest_version = (
                            pypi_package_json.get_chronologically_suitable_setuptools_version()
                        )
                        try:
                            # Get information from the wheel file name.
                            logger.debug(pypi_package_json.wheel_filename)
                            _, _, _, tags = parse_wheel_filename(pypi_package_json.wheel_filename)
                            for tag in tags:
                                wheel_name_python_version_set.add(tag.interpreter)
                            if wheel_name_python_version_set:
                                logger.debug(
                                    "From wheel name inferred Python constraints: %s", wheel_name_python_version_set
                                )
                                python_version_set.update(wheel_name_python_version_set)
                        except InvalidWheelFilename:
                            logger.debug("Could not parse wheel file name to extract version")
                except WheelTagError:
                    logger.debug("Can not analyze non-pure wheels")
                except SourceCodeError:
                    logger.debug("Could not download wheel matching this PURL")

                logger.debug("From .dist_info build-requires: %s", parsed_build_requires)

                try:
                    with pypi_package_json.sourcecode():
                        upstream_artifacts["sdist"] = [pypi_package_json.sdist_url]
                        logger.debug("sdist url at %s", upstream_artifacts["sdist"])

                        has_maturin = False
                        cargo_toml_exists = pypi_package_json.file_exists("Cargo.toml")
                        cargo_toml_content: dict[str, Any] = {}
                        cargo_lock_content: dict[str, Any] = {}

                        try:
                            cargo_text_bytes = pypi_package_json.get_sourcecode_file_contents("Cargo.toml")
                            cargo_toml_content = tomli.loads(cargo_text_bytes.decode("utf-8"))
                        except (SourceCodeError, UnicodeDecodeError, tomli.TOMLDecodeError):
                            logger.debug("No Cargo.toml found")

                        try:
                            cargo_lock_bytes = pypi_package_json.get_sourcecode_file_contents("Cargo.lock")
                            cargo_lock_content = tomli.loads(cargo_lock_bytes.decode("utf-8"))
                        except (SourceCodeError, UnicodeDecodeError, tomli.TOMLDecodeError):
                            logger.debug("No Cargo.lock found")

                        try:
                            # Get the build time requirements from ["build-system", "requires"]
                            pyproject_content = pypi_package_json.get_sourcecode_file_contents("pyproject.toml")
                            content = tomli.loads(pyproject_content.decode("utf-8"))
                            requires = json_extract(content, ["build-system", "requires"], list)
                            if requires:
                                for requirement in requires:
                                    if parsed_requirement := self.add_parsed_python_requirement(
                                        sdist_build_requires, requirement
                                    ):
                                        if parsed_requirement.name.lower() == "maturin":
                                            has_maturin = True
                            # If we cannot find `requires` in `[build-system]`, we lean on the fact that setuptools
                            # was the de-facto build tool, and infer a setuptools version to include.
                            else:
                                self.add_parsed_python_requirement(
                                    sdist_build_requires, f"setuptools=={chronologically_likeliest_version}"
                                )
                            backend = json_extract(content, ["build-system", "build-backend"], str)
                            if backend:
                                build_backends_set.add(backend.replace(" ", ""))
                            python_version_constraint = json_extract(content, ["project", "requires-python"], str)
                            if python_version_constraint:
                                python_version_set.add(python_version_constraint.replace(" ", ""))
                            self.apply_tool_specific_inferences(sdist_build_requires, python_version_set, content)
                            logger.debug(
                                "After analyzing pyproject.toml from the sdist: build-requires: %s, build_backend: %s",
                                sdist_build_requires,
                                build_backends_set,
                            )
                            # Here we have successfully analyzed the pyproject.toml file. Now, if we have a setup.py/cfg,
                            # we also need to infer a setuptools version to infer.
                            if pypi_package_json.file_exists("setup.py") or pypi_package_json.file_exists("setup.cfg"):
                                self.add_parsed_python_requirement(
                                    sdist_build_requires, f"setuptools=={chronologically_likeliest_version}"
                                )
                        except TypeError as error:
                            logger.debug(
                                "Found a type error while reading the pyproject.toml file from the sdist: %s", error
                            )
                        except tomli.TOMLDecodeError as error:
                            logger.debug("Failed to read the pyproject.toml file from the sdist: %s", error)
                        except SourceCodeError as error:
                            logger.debug("No pyproject.toml found: %s", error)
                            # Here we do not have a pyproject.toml file. Instead, we lean on the fact that setuptools
                            # was the de-facto build tool, and infer a setuptools version to include.
                            self.add_parsed_python_requirement(
                                sdist_build_requires, f"setuptools=={chronologically_likeliest_version}"
                            )

                        if self.is_rust_backed_package(build_backends_set, has_maturin, cargo_toml_exists):
                            self.add_to_build_requires(sdist_build_requires, "rustup", "bootstrap")

                            rust_requirement = self.infer_rust_requirement(
                                pypi_package_json,
                                cargo_toml_content,
                            )

                            self.add_to_build_requires(
                                sdist_build_requires,
                                rust_requirement["name"],
                                rust_requirement["installer"],
                                rust_requirement.get("version"),
                            )
                            # Look through Cargo.lock first for resolved versions.
                            cargo_packages = json_extract(cargo_lock_content, ["package"], list)
                            if cargo_packages:
                                for package in cargo_packages:
                                    cargo_dependency_name = json_extract(package, ["name"], str)
                                    cargo_dependency_version = json_extract(package, ["version"], str)
                                    if not cargo_dependency_name:
                                        continue
                                    cargo_dependency_version_constraint = (
                                        f"=={cargo_dependency_version}" if cargo_dependency_version else None
                                    )
                                    self.add_to_build_requires(
                                        sdist_build_requires,
                                        cargo_dependency_name,
                                        "cargo",
                                        cargo_dependency_version_constraint,
                                    )
                            else:
                                # As a fallback, look through Cargo.toml dependency tables.
                                for table_name in ["build-dependencies", "dependencies"]:
                                    cargo_dependencies = json_extract(cargo_toml_content, [table_name], dict)
                                    if not cargo_dependencies:
                                        continue
                                    for cargo_dependency_name, cargo_dependency_spec in cargo_dependencies.items():
                                        cargo_dependency_version_constraint = None
                                        if isinstance(cargo_dependency_spec, str):
                                            cargo_dependency_version_constraint = cargo_dependency_spec
                                        elif isinstance(cargo_dependency_spec, dict):
                                            cargo_dependency_version_constraint = json_extract(
                                                cargo_dependency_spec, ["version"], str
                                            )

                                        self.add_to_build_requires(
                                            sdist_build_requires,
                                            cargo_dependency_name,
                                            "cargo",
                                            cargo_dependency_version_constraint,
                                        )

                except SourceCodeError as error:
                    logger.debug("No source distribution found: %s", error)

                logger.debug("After complete analysis of the sdist:")
                logger.debug(sdist_build_requires)

                # Merge in pyproject.toml information only when the wheel dist_info does not contain the same.
                # Hatch is an interesting example of this merge being required.
                for requirement in sdist_build_requires.values():
                    self.add_to_build_requires(
                        parsed_build_requires,
                        requirement["name"],
                        requirement["installer"],
                        requirement.get("version"),
                    )

        # If we were not able to find any build and backends, use the default setuptools.
        if not parsed_build_requires:
            self.add_to_build_requires(
                parsed_build_requires,
                "setuptools",
                "pip",
                "==" + defaults.get("heuristic.pypi", "default_setuptools"),
            )
        if not build_backends_set:
            build_backends_set.add("setuptools.build_meta")

        build_requires = sorted(parsed_build_requires.values(), key=lambda requirement: requirement["name"])

        logger.debug("Combined build-requires: %s", build_requires)

        for requirement in build_requires:
            if requirement["installer"] != "pip":
                continue
            package_requirement = requirement["name"] + requirement.get("version", "")
            python_version_constraints = registry.get_python_requires_for_package_requirement(package_requirement)
            if python_version_constraints:
                dependency_python_version_set.add(python_version_constraints)

        # We will prefer to use Python version constraints from the package's
        # dependencies. In the case that such inference was unsuccessful, we default
        # to the Python version constraints inferred from other sources.
        if dependency_python_version_set:
            self.data["language_version"] = sorted(dependency_python_version_set)
        else:
            self.data["language_version"] = sorted(python_version_set)

        self.data["build_requires"] = build_requires
        self.data["build_backends"] = sorted(build_backends_set)
        for build_cmd_spec in self.data["build_commands"]:
            self.set_default_build_commands(build_cmd_spec)
        self.data["upstream_artifacts"] = upstream_artifacts

    def add_to_build_requires(
        self,
        build_requirements: dict[str, SpecBuildRequirementDict],
        name: str,
        installer: str,
        version: str | None = None,
    ) -> None:
        """
        Add requirement to build_requirements with version handling.

        Parameters
        ----------
        build_requirements: dict[str, SpecBuildRequirementDict]
            Dictionary of build requirements to populate.
        name: str
            Name of dependency.
        installer: str
            Installer used for the dependency.
        version: str | None
            Version specifier for the build requirement, if it exists
        """
        if build_requirements.get(name):
            # If we do not have version, but current invocation has inferred version, use that version.
            if ("version" not in build_requirements[name]) and version:
                build_requirements[name]["version"] = version
            return

        requirement: SpecBuildRequirementDict = {
            "name": name,
            "installer": installer,
        }
        if version:
            requirement["version"] = version
        build_requirements[name] = requirement

    def add_parsed_python_requirement(
        self,
        build_requirements: dict[str, SpecBuildRequirementDict],
        requirement: str,
    ) -> Requirement | None:
        """
        Parse a requirement string and add it to build_requirements, doing appropriate error handling.

        Parameters
        ----------
        build_requirements: dict[str, SpecBuildRequirementDict]
            Dictionary of build requirements to populate.
        requirement: str
            Requirement string to parse.
        """
        try:
            parsed_requirement = Requirement(requirement)
            self.add_to_build_requires(
                build_requirements,
                parsed_requirement.name,
                "pip",
                str(parsed_requirement.specifier),
            )
            return parsed_requirement
        except (InvalidRequirement, InvalidSpecifier) as error:
            logger.debug("Malformed requirement encountered %s : %s", requirement, error)
            return None

    def is_rust_backed_package(
        self,
        build_backends_set: set[str],
        has_maturin: bool,
        cargo_toml_exists: bool,
    ) -> bool:
        """
        Determine if the artifact packages Rust binaries.

        Parameters
        ----------
        build_backends_set: set[str]
            Inferred set of build backends
        has_maturin: bool
            Whether maturin is a build requirement of the package
        cargo_toml_exists: bool
            Whether Cargo.toml exists in the sdist.

        Returns
        -------
        bool
            True if Rust signal was detected.
        """
        return "maturin" in build_backends_set or has_maturin or cargo_toml_exists

    def infer_rust_requirement(
        self,
        pypi_package_json: pypi_registry.PyPIPackageJsonAsset,
        cargo_toml_content: dict[str, Any],
    ) -> SpecBuildRequirementDict:
        """
        Infer Rust requirement object.

        Parameters
        ----------
        pypi_package_json: pypi_registry.PyPIPackageJsonAsset
            The PyPI package JSON asset object.
        cargo_toml_content: dict[str, Any]
            Parsed Cargo.toml data.

        Returns
        -------
        SpecBuildRequirementDict
            Rust requirement dictionary.
        """
        version = self.read_rust_toolchain_version(pypi_package_json)
        if version:
            return {
                "name": "rust",
                "version": version,
                "installer": "rustup",
            }

        cargo_rust_version = json_extract(cargo_toml_content, ["package", "rust-version"], str)
        if not cargo_rust_version:
            cargo_rust_version = json_extract(cargo_toml_content, ["workspace", "package", "rust-version"], str)
        if cargo_rust_version:
            return {
                "name": "rust",
                "version": f">={cargo_rust_version.strip()}",
                "installer": "rustup",
            }

        return {
            "name": "rust",
            "installer": "rustup",
        }

    def read_rust_toolchain_version(self, pypi_package_json: pypi_registry.PyPIPackageJsonAsset) -> str | None:
        """
        Infer Rust toolchain version.

        Parameters
        ----------
        pypi_package_json: pypi_registry.PyPIPackageJsonAsset
            The PyPI package JSON asset object.

        Returns
        -------
        str | None
            The inferred Rust toolchain version, or None if unavailable.
        """
        for file in ["rust-toolchain.toml", "rust-toolchain"]:
            if not pypi_package_json.file_exists(file):
                continue
            try:
                content = pypi_package_json.get_sourcecode_file_contents(file).decode("utf-8")
            except (SourceCodeError, UnicodeDecodeError):
                continue

            version = self.extract_rust_toolchain_version(content)
            if version:
                return version
        return None

    def extract_rust_toolchain_version(self, content: str) -> str | None:
        """
        Extract the Rust toolchain version from rust-toolchain content.

        Parameters
        ----------
        content: str
            Contents of a rust-toolchain.toml or rust-toolchain file.

        Returns
        -------
        str | None
            The inferred Rust toolchain version, or None if unavailable.
        """
        stripped = content.strip()
        if not stripped:
            return None

        try:
            parsed = tomli.loads(content)
            toolchain_version = json_extract(parsed, ["toolchain", "channel"], str)
            if toolchain_version:
                return toolchain_version.strip()
        except tomli.TOMLDecodeError:
            pass

        for line in stripped.splitlines():
            sanitized = line.strip().strip('"').strip("'")
            if not sanitized or sanitized.startswith("#"):
                continue
            return sanitized
        return None

    def apply_tool_specific_inferences(
        self,
        build_requirements: dict[str, SpecBuildRequirementDict],
        python_version_set: set[str],
        pyproject_contents: dict[str, Any],
    ) -> None:
        """
        Based on build tools inferred, look into the pyproject.toml for related additional dependencies.

        Parameters
        ----------
        build_requirements: dict[str, SpecBuildRequirementDict]
            Dictionary of build requirements to populate.
        python_version_set: set[str]
            Set of compatible interpreter versions to populate.
        pyproject_contents: dict[str, Any]
            Parsed contents of the pyproject.toml file.
        """
        # If we have hatch as a build_tool, we will examine [tool.hatch.build.hooks.*] to
        # look for any additional build dependencies declared there.
        if "hatch" in self.data["build_tools"]:
            # Look for [tool.hatch.build.hooks.*]
            hatch_build_hooks = json_extract(pyproject_contents, ["tool", "hatch", "build", "hooks"], dict)
            if hatch_build_hooks:
                for _, section in hatch_build_hooks.items():
                    dependencies = section.get("dependencies")
                    if dependencies:
                        for requirement in dependencies:
                            self.add_parsed_python_requirement(build_requirements, requirement)
        # If we have flit as a build_tool, we will check if the legacy header [tool.flit.metadata] exists,
        # and if so, check to see if we can use its "requires-python".
        if "flit" in self.data["build_tools"]:
            flit_python_version_constraint = json_extract(
                pyproject_contents, ["tool", "flit", "metadata", "requires-python"], str
            )
            if flit_python_version_constraint:
                python_version_set.add(flit_python_version_constraint.replace(" ", ""))

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
        normalized_name = re.sub(r"[^\w\d.]+", "_", purl.name, flags=re.UNICODE)
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
