# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains helper functions to process CycloneDX SBOM."""

import json
import logging
import os
import subprocess  # nosec B404
from abc import ABC, abstractmethod
from collections.abc import Iterable
from enum import Enum
from pathlib import Path
from typing import Any, TypedDict

from cyclonedx.exception import MissingOptionalDependencyException
from cyclonedx.model.bom import Bom
from cyclonedx.model.component import Component as CDXComponent
from cyclonedx.model.component import ExternalReference as CDXExternalReference
from cyclonedx.model.dependency import Dependency as CDXDependency
from cyclonedx.schema import SchemaVersion
from cyclonedx.validation.json import JsonStrictValidator
from packageurl import PackageURL
from packaging import version

from macaron.config.defaults import defaults
from macaron.config.global_config import global_config
from macaron.config.target_config import Configuration
from macaron.database.table_definitions import Component
from macaron.errors import CycloneDXParserError, DependencyAnalyzerError
from macaron.output_reporter.scm import SCMStatus
from macaron.repo_finder.repo_finder import find_repo
from macaron.repo_finder.repo_validator import find_valid_repository_url

logger: logging.Logger = logging.getLogger(__name__)


def deserialize_bom_json(file_path: Path) -> Bom:
    """Deserialize the bom.json file.

    Parameters
    ----------
    file_path : str
        Path to the bom.json file.

    Returns
    -------
    Bom
        The CycloneDX Bom object.

    Raises
    ------
    CycloneDXParserError
        If the bom.json file cannot be located or deserialized.
    """
    if not os.path.exists(file_path):
        raise CycloneDXParserError(f"Unable to locate any BOM files at: {str(file_path.parent)}.")

    # We use the `cyclonedx-python-library` library for deserialization following the example here:
    # https://cyclonedx-python-library.readthedocs.io/en/v7.3.4/examples.html
    with open(file_path, encoding="utf8") as file:
        json_data = file.read()
        if defaults.getboolean("dependency.resolver", "validate", fallback=True):
            schema_version = defaults.get("dependency.resolver", "schema", fallback="1.6")
            try:
                my_json_validator = JsonStrictValidator(SchemaVersion.from_version(schema_version))
            except ValueError as error:
                raise CycloneDXParserError(f"Unable to find schema validator for {schema_version}: {error}") from error
            try:
                validation_errors = my_json_validator.validate_str(json_data)
            except MissingOptionalDependencyException as error:
                # Allow MissingOptionalDependencyException.
                logger.debug("JSON-validation was skipped due to %s", error)
            except json.JSONDecodeError as error:
                raise CycloneDXParserError(f"BOM file is invalid: {error}") from error

            if validation_errors:
                logger.debug("BOM file is invalid: %s", repr(validation_errors))
                raise CycloneDXParserError(f"BOM file is invalid: {repr(validation_errors)}")

            logger.debug("Successfully validated the BOM file at %s", file_path)

        try:
            # Mypy complains that `"type[Bom]" has no attribute "from_json"`.
            # Based on the example provided by cyclonedx-python-lib this type issue needs to be suppressed.
            # This method is injected into the Bom class that is annotated by ``serializable`` but mypy is not
            # able to detect that.
            bom_from_json = Bom.from_json(json.loads(json_data))  # type: ignore[attr-defined]
        except (ValueError, AttributeError, json.JSONDecodeError) as error:
            raise CycloneDXParserError(f"Could not process the dependencies at {file_path}: {error}") from None

        if isinstance(bom_from_json, Bom):
            logger.debug("Successfully deserialized the BOM file: %s", repr(bom_from_json))
            return bom_from_json

        raise CycloneDXParserError(f"Could not process the dependencies at {file_path}")


class DependencyTools(str, Enum):
    """Dependency resolvers supported by Macaron."""

    CYCLONEDX_MAVEN = "cyclonedx-maven"
    CYCLONEDX_GRADLE = "cyclonedx-gradle"
    CYCLONEDX_PYTHON = "cyclonedx_py"


class DependencyInfo(TypedDict):
    """The information of a resolved dependency."""

    purl: PackageURL
    url: str
    note: str
    available: SCMStatus


class DependencyAnalyzer(ABC):
    """This abstract class is used to implement dependency analyzers."""

    def __init__(self, resources_path: str, file_name: str, tool_name: str, tool_version: str) -> None:
        """Initialize the dependency analyzer instance.

        Parameters
        ----------
        resources_path : str
            The path to the resources directory.
        file_name : str
            The name of dependency output file.
        tool_name: str
            The name of the dependency analyzer.
        tool_version : str
            The version of the dependency analyzer.
        """
        self.resources_path: str = resources_path
        self.file_name: str = file_name
        self.tool_name: str = tool_name
        self.tool_version: str = tool_version
        self.visited_deps: set = set()

    @abstractmethod
    def collect_dependencies(self, dir_path: str, target_component: Component) -> dict[str, DependencyInfo]:
        """Process the dependency JSON files and collect direct dependencies.

        Parameters
        ----------
        dir_path : str
            Local path to the target repo.
        target_component: Component
            The analyzed target software component.

        Returns
        -------
        dict
            A dictionary where artifacts are grouped based on "artifactId:groupId".
        """

    @abstractmethod
    def remove_sboms(self, dir_path: str) -> bool:
        """Remove all the SBOM files in the provided directory recursively.

        Parameters
        ----------
        dir_path : str
            Path to the repo.

        Returns
        -------
        bool
            Returns True if all the files are removed successfully.
        """

    @abstractmethod
    def get_cmd(self) -> list:
        """Return the CLI command to run the dependency analyzer.

        Returns
        -------
        list
            The command line arguments.
        """

    @abstractmethod
    def get_purl_from_cdx_component(self, component: CDXComponent) -> PackageURL:
        """Construct and return a PackageURL from a CycloneDX component.

        Parameters
        ----------
        component: CDXComponent

        Returns
        -------
        PackageURL
            The PackageURL object constructed from the CycloneDX component.
        """

    @staticmethod
    def add_latest_version(
        item: DependencyInfo,
        key: str,
        all_versions: dict[str, list[DependencyInfo]],
        latest_deps: dict[str, DependencyInfo],
        url_to_artifact: dict[str, set],
    ) -> None:
        """Find and add the unique URL for the latest version of the artifact.

        Parameters
        ----------
        item : DependencyInfo
            The dictionary containing info about the dependency to be added.
        key : str
            The ID of the artifact.
        all_versions: dict[str, str]
            Stores all the versions of dependencies for debugging.
        latest_deps: dict[str, DependencyInfo]
            Stores the latest version of dependencies.
        url_to_artifact: dict[str, set]
            Used to detect artifacts that have similar repos.
        """
        # Check if the URL is already seen for a different artifact.
        if item["url"] != "":
            artifacts = url_to_artifact.get(item["url"])
            if artifacts is None:
                url_to_artifact[item["url"]] = {key}
            else:
                item["note"] = f"{item['url']} is already analyzed."
                item["available"] = SCMStatus.DUPLICATED_SCM
                url_to_artifact[item["url"]].add(key)
                logger.debug(item["note"])
        else:
            logger.debug("Could not find SCM URL for %s. Skipping...", key)
            item["note"] = "Manual configuration required. Could not find SCM URL."
            item["available"] = SCMStatus.MISSING_SCM

        # For debugging purposes.
        value = all_versions.get(key)
        if not value:
            all_versions[key] = [item]
        else:
            value.append(item)

        # Only update the artifact if it has a newer version.
        latest_value = latest_deps.get(key)
        if not latest_value:
            latest_deps[key] = item
        else:
            try:
                # These are stored as variables so mypy does not complain about None values (union-attr)
                latest_value_purl = latest_value.get("purl")
                item_purl = item.get("purl")
                if (
                    latest_value_purl is not None
                    and item_purl is not None
                    and (latest_version := latest_value_purl.version)
                    and (item_version := item_purl.version)
                    and version.Version(latest_version) < version.Version(item_version)
                ):
                    latest_deps[key] = item
            except ValueError as error:
                logger.error("Could not parse dependency version number: %s", error)

    @staticmethod
    def to_configs(resolved_deps: dict[str, DependencyInfo]) -> list[Configuration]:
        """Convert the resolved dependencies into the format used by the Analyzer.

        Parameters
        ----------
        resolved_deps : dict[str, DependencyInfo]
            The automatically resolved dependencies.

        Returns
        -------
        list[Configuration]
            The dependencies list to be used by the Analyzer.
        """
        if not resolved_deps:
            return []

        config_list: list[Configuration] = []

        for key, value in resolved_deps.items():
            config_list.append(
                Configuration(
                    {
                        "id": key,
                        "purl": str(value.get("purl")),
                        "path": value.get("url"),
                        "branch": "",
                        "digest": "",
                        "note": value.get("note"),
                        "available": value.get("available"),
                    }
                )
            )

        return config_list

    @staticmethod
    def tool_valid(tool: str) -> bool:
        """Validate the dependency analyzer name.

        Parameters
        ----------
        tool : str
            The full name of the dependency analyzer, i.e., <name>:<version>.

        Returns
        -------
        bool
            Return True if the tool name is valid.
        """
        if ":" not in tool:
            return False
        items = tool.split(":")
        supported = False
        for element in DependencyTools:
            if items[0] == element.value:
                supported = True
                break
        if not supported:
            logger.error("Dependency tool %s is not supported.", items[0])
            return False
        try:
            if not version.Version(items[1].lower()):
                logger.error("Invalid dependency analyzer version: %s", items[1])
                return False
        except ValueError as error:
            logger.error("Dependency analyzer: %s.", error)
            return False
        return True

    @staticmethod
    def resolve_dependencies(main_ctx: Any, sbom_path: str) -> dict[str, DependencyInfo]:
        """Resolve the dependencies of the main target repo.

        Parameters
        ----------
        main_ctx : Any (AnalyzeContext)
            The context of object of the target repository.
        sbom_path: str
            The path to the SBOM.

        Returns
        -------
        dict[str, DependencyInfo]
            A dictionary where artifacts are grouped based on ``artifactId:groupId``.
        """
        deps_resolved: dict[str, DependencyInfo] = {}

        build_tools = main_ctx.dynamic_data["build_spec"]["tools"]
        if not build_tools:
            # If the repository is not available, we use the first build tool object that has
            # matched the software component's PackageURL type to allow a customized dependency resolution logic.
            if main_ctx.dynamic_data["build_spec"]["purl_tools"]:
                build_tools = [main_ctx.dynamic_data["build_spec"]["purl_tools"][0]]

            # Check if we cannot still find a matching build tool.
            if not build_tools:
                logger.info("Unable to find any valid build tools.")
                return {}

        # Grab dependencies for each build tool, collate all into the deps_resolved.
        for build_tool in build_tools:
            try:
                # We allow dependency analysis if SBOM is provided but no repository is found.
                dep_analyzer = build_tool.get_dep_analyzer()
            except DependencyAnalyzerError as error:
                logger.error("Unable to find a dependency analyzer for %s: %s", build_tool.name, error)
                return {}

            if isinstance(dep_analyzer, NoneDependencyAnalyzer):
                logger.info(
                    "Dependency analyzer is not available for %s",
                    build_tool.name,
                )
                continue

            if sbom_path:
                logger.info("Getting the dependencies from the SBOM defined at %s.", sbom_path)

                deps_resolved = dep_analyzer.get_deps_from_sbom(sbom_path, main_ctx.component)

                # Use repo finder to find more repositories to analyze.
                if defaults.getboolean("repofinder", "find_repos"):
                    DependencyAnalyzer._resolve_more_dependencies(deps_resolved)

                return deps_resolved

            if not main_ctx.component.repository:
                logger.info(
                    "Unable to find a repository and no SBOM is provided as input. Analyzing the dependencies will be skipped."
                )
                return {}

            # Start resolving dependencies.
            logger.info(
                "Running %s version %s dependency analyzer on %s",
                dep_analyzer.tool_name,
                dep_analyzer.tool_version,
                main_ctx.component.repository.fs_path,
            )

            log_path = os.path.join(
                global_config.build_log_path,
                f"{main_ctx.component.report_file_name}.{dep_analyzer.tool_name}.log",
            )

            # Clean up existing SBOM files.
            if not dep_analyzer.remove_sboms(main_ctx.component.repository.fs_path):
                logger.debug("Unable to remove intermediate files generated during the creation of SBOM.")

            commands = dep_analyzer.get_cmd()
            working_dirs: Iterable[Path] = build_tool.get_build_dirs(main_ctx.component.repository.fs_path)
            for working_dir in working_dirs:
                # Get the absolute path to use as the working dir in the subprocess.
                working_dir = Path(main_ctx.component.repository.fs_path).joinpath(working_dir)

                try:
                    # Suppressing Bandit's B603 report because the repo paths are validated.
                    analyzer_output = subprocess.run(  # nosec B603
                        commands,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        check=True,
                        cwd=str(working_dir),
                        timeout=defaults.getint("dependency.resolver", "timeout", fallback=1200),
                    )
                    with open(log_path, mode="a", encoding="utf-8") as log_file:
                        log_file.write(analyzer_output.stdout.decode("utf-8"))

                except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
                    logger.error(error)
                    with open(log_path, mode="a", encoding="utf-8") as log_file:
                        log_file.write(error.output.decode("utf-8"))
                except FileNotFoundError as error:
                    logger.error(error)

                # We collect the generated SBOM as a best effort, even if the build exits with errors.
                # TODO: add improvements to help the SBOM build succeed as much as possible.
                deps_resolved |= dep_analyzer.collect_dependencies(str(working_dir), main_ctx.component)

            logger.info("Stored dependency resolver log for %s to %s.", dep_analyzer.tool_name, log_path)

        # Use repo finder to find more repositories to analyze.
        if defaults.getboolean("repofinder", "find_repos"):
            DependencyAnalyzer._resolve_more_dependencies(deps_resolved)

        return deps_resolved

    @staticmethod
    def _resolve_more_dependencies(dependencies: dict[str, DependencyInfo]) -> None:
        """Utilise the Repo Finder to resolve the repositories of more dependencies."""
        for item in dependencies.values():
            if item["available"] != SCMStatus.MISSING_SCM:
                continue

            item["url"] = find_repo(item["purl"])
            if item["url"] == "":
                logger.debug("Failed to find url for purl: %s", item["purl"])
            else:
                # TODO decide how to handle possible duplicates here
                item["available"] = SCMStatus.AVAILABLE
                item["note"] = ""

    def get_root_component(self, root_bom_path: Path) -> CDXComponent | None:
        """Get the root dependency component.

        Parameters
        ----------
        root_bom_path : str
            Path to the root bom.json file.

        Returns
        -------
        CDXComponent | None
            The root CycloneDX component.
        """
        try:
            root_bom = deserialize_bom_json(root_bom_path)
        except CycloneDXParserError as error:
            logger.error(error)
            return None
        try:
            return root_bom.metadata.component
        except AttributeError as error:
            logger.error(error)

        return None

    def get_target_cdx_component(self, root_bom: Bom, target_component: Component) -> CDXComponent | None:
        """Get the CycloneDX component that matches the analyzed target software component.

        Parameters
        ----------
        root_bom: Bom
            The top-level BOM file.
        target_component: Component
            The analyzed target software component.

        Returns
        -------
        CDXComponent | None
            The CycloneDX component or None if it cannot be found.
        """

        def _is_target_cmp(cmp: CDXComponent | None) -> bool:
            if cmp is None:
                return False
            cmp_purl = self.get_purl_from_cdx_component(cmp)
            if str(cmp_purl) == target_component.purl:
                logger.debug("Found the target CycloneDX component: %s", cmp.bom_ref.value)
                return True
            return False

        for cmp in root_bom.components:
            if not isinstance(cmp, CDXComponent):
                continue
            if _is_target_cmp(cmp):
                return cmp

        if root_bom.metadata:
            if _is_target_cmp(root_bom.metadata.component):
                return root_bom.metadata.component
            if root_bom.metadata.component:
                logger.error(
                    (
                        "The analysis target %s and the metadata component %s in the BOM file do not match."
                        " Please fix the PURL input and try again."
                    ),
                    target_component.purl,
                    self.get_purl_from_cdx_component(root_bom.metadata.component),
                )
                return None

        logger.error(
            "Unable to find the analysis target %s in the BOM file. Please fix the PURL input and try again.",
            target_component.purl,
        )
        return None

    def get_dep_components(
        self,
        target_component: Component,
        root_bom_path: Path,
        child_bom_paths: list[Path] | None = None,
        recursive: bool = False,
    ) -> Iterable[CDXComponent]:
        """Get CycloneDX components that are dependencies of the analyzed target software component.

        Parameters
        ----------
        target_component: Component
            The analyzed target software component.
        root_bom_path : str
            Path to the root bom.json file.
        child_bom_paths: list[Path] | None
            The list of paths to sub-project bom.json files.
        recursive: bool
            Set to False to get the direct dependencies only (default).

        Yields
        ------
        CDXComponent
            The dependencies as CycloneDX components.
        """
        try:
            root_bom = deserialize_bom_json(root_bom_path)
        except CycloneDXParserError as error:
            logger.error(error)
            return

        if root_bom.components is None:
            logger.error("The BOM file at %s misses components.", str(root_bom_path))
            return

        dependencies: list[CDXDependency] = []

        # Find dependencies in the root BOM file.
        target_cdx_component = self.get_target_cdx_component(root_bom=root_bom, target_component=target_component)
        if target_cdx_component is None:
            return

        for node in root_bom.dependencies:
            if not isinstance(node, CDXDependency):
                continue
            if recursive or (target_cdx_component.bom_ref and node.ref == target_cdx_component.bom_ref):
                if dep_on := node.dependencies:
                    dependencies.extend(dep_on)

        # Find dependencies in child BOMs if they exist. Multi-module Java projects need this resolution.
        child_bom_objects: list[Bom] = []
        modules: set[str] = set()  # Stores all module dependencies.

        for child_path in child_bom_paths or []:
            try:
                child_bom_objects.append(deserialize_bom_json(child_path))
            except CycloneDXParserError as error:
                logger.error(error)
                continue

        for bom in child_bom_objects:
            if not bom.metadata or not bom.metadata.component:
                continue
            try:
                target_bom_ref = bom.metadata.component.bom_ref
                if target_bom_ref and target_bom_ref.value:
                    modules.add(target_bom_ref.value)
                for node in bom.dependencies:
                    if not isinstance(node, CDXDependency):
                        continue
                    if node.ref == target_bom_ref or recursive:
                        dependencies.extend(node.dependencies)
                        break
            except AttributeError as error:
                logger.debug(error)

        # Find the dependency components.
        for dependency in dependencies:
            if not dependency.ref.value:
                continue
            if dependency.ref.value in modules:
                continue
            for component in root_bom.components:
                try:
                    if not isinstance(component, CDXComponent):
                        continue
                    if dependency.ref == component.bom_ref:
                        yield component
                except AttributeError as error:
                    logger.debug(error)

    def convert_components_to_artifacts(
        self, components: Iterable[CDXComponent], root_component: CDXComponent | None = None
    ) -> dict[str, DependencyInfo]:
        """Convert CycloneDX components using internal artifact representation.

        Parameters
        ----------
        components : Iterable[CDXComponent]
            The dependency components.
        root_component: CDXComponent | None
            The root CycloneDX component.

        Returns
        -------
        dict
            A dictionary where dependency artifacts are grouped based on "groupId:artifactId".
        """
        all_versions: dict[str, list[DependencyInfo]] = {}  # Stores all the versions of dependencies for debugging.
        latest_deps: dict[str, DependencyInfo] = {}  # Stores the latest version of dependencies.
        url_to_artifact: dict[str, set] = {}  # Used to detect artifacts that have similar repos.
        for component in components:
            # try:
            # TODO make this function language agnostic when CycloneDX SBOM processing also is.
            # See https://github.com/oracle/macaron/issues/464
            key = f"{component.group}:{component.name}"
            purl = self.get_purl_from_cdx_component(component)

            # According to PEP-0589 all keys must be present in a TypedDict.
            # See https://peps.python.org/pep-0589/#totality
            item = DependencyInfo(
                purl=purl,
                url="",
                note="",
                available=SCMStatus.AVAILABLE,
            )
            # Some of the components might miss external references.
            if component.external_references is None:
                # In Java, development artifacts contain "SNAPSHOT" in the version.
                # If the SBOM generation completes with no build errors for submodules
                # the submodule would not be added as a dependency and we shouldn't reach here.
                # IN case of a build error, we use this as a heuristic to avoid analyzing
                # submodules that produce development artifacts in the same repo.
                if (
                    "snapshot" in (purl.version or "").lower()
                    # or "" is not necessary but mypy produces a FP otherwise.
                    and root_component
                    and purl.namespace == root_component.group
                ):
                    continue
                logger.debug(
                    "Could not find external references for %s. Skipping...",
                    component.bom_ref.value,
                )
            else:
                # Find a valid URL.
                item["url"] = find_valid_repository_url(
                    str(link.url) for link in component.external_references if isinstance(link, CDXExternalReference)
                )

            DependencyAnalyzer.add_latest_version(
                item=item, key=key, all_versions=all_versions, latest_deps=latest_deps, url_to_artifact=url_to_artifact
            )

        try:
            with open(os.path.join(global_config.output_path, "sbom_debug.json"), "w", encoding="utf8") as debug_file:
                debug_file.write(json.dumps(all_versions, indent=4))
        except OSError as error:
            logger.error(error)

        return latest_deps

    def get_deps_from_sbom(self, sbom_path: str | Path, target_component: Component) -> dict[str, DependencyInfo]:
        """Get the dependencies from a provided SBOM.

        Parameters
        ----------
        sbom_path : str | Path
            The path to the SBOM file.
        target_component: Component
            The analyzed target software component.

        Returns
        -------
            A dictionary where dependency artifacts are grouped based on "groupId:artifactId".
        """
        return self.convert_components_to_artifacts(
            self.get_dep_components(
                target_component=target_component,
                root_bom_path=Path(sbom_path),
                recursive=defaults.getboolean(
                    "dependency.resolver",
                    "recursive",
                    fallback=False,
                ),
            )
        )


class NoneDependencyAnalyzer(DependencyAnalyzer):
    """This class is used to implement an empty dependency analyzers."""

    def __init__(self) -> None:
        """Initialize the dependency analyzer instance."""
        super().__init__(resources_path="", file_name="", tool_name="", tool_version="")

    def collect_dependencies(self, dir_path: str, target_component: Component) -> dict[str, DependencyInfo]:
        """Process the dependency JSON files and collect direct dependencies.

        Parameters
        ----------
        dir_path : str
            Local path to the target repo.
        target_component: Component
            The analyzed target software component.

        Returns
        -------
        dict
            A dictionary where artifacts are grouped based on "artifactId:groupId".
        """
        return {}

    def remove_sboms(self, dir_path: str) -> bool:
        """Remove all the SBOM files in the provided directory recursively.

        Parameters
        ----------
        dir_path : str
            Path to the repo.

        Returns
        -------
        bool
            Returns True if all the files are removed successfully.
        """
        return False

    def get_cmd(self) -> list:
        """Return the CLI command to run the dependency analyzer.

        Returns
        -------
        list
            The command line arguments.
        """
        return []

    def get_purl_from_cdx_component(self, component: CDXComponent) -> PackageURL:
        """Construct and return a PackageURL from a CycloneDX component.

        Parameters
        ----------
        component: CDXComponent

        Returns
        -------
        PackageURL
            The PackageURL object constructed from the CycloneDX component.
        """
        return component.purl or PackageURL(
            type="unknown",
            namespace=component.group,
            name=component.name,
            version=component.version or None,
        )
