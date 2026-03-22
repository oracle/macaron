# Copyright (c) 2025 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module includes build specification and helper classes for Maven packages."""

import logging

from packageurl import PackageURL

from macaron.build_spec_generator.build_command_patcher import CLI_COMMAND_PATCHES, patch_command
from macaron.build_spec_generator.common_spec.base_spec import BaseBuildSpec, BaseBuildSpecDict, SpecBuildCommandDict
from macaron.build_spec_generator.common_spec.jdk_finder import find_jdk_version_from_central_maven_repo
from macaron.build_spec_generator.common_spec.jdk_version_normalizer import normalize_jdk_version

logger: logging.Logger = logging.getLogger(__name__)


class MavenBuildSpec(BaseBuildSpec):
    """This class implements build spec inferences for Maven packages."""

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
            case "maven":
                build_cmd_spec["command"] = "mvn clean package".split()

            case "gradle":
                build_cmd_spec["command"] = "./gradlew clean assemble publishToMavenLocal".split()
            case _:
                logger.debug(
                    "There is no default build command available for the build tools %s.",
                    build_cmd_spec["build_tool"],
                )

    def resolve_fields(self, purl: PackageURL) -> None:
        """
        Resolve Maven-specific fields in the build specification.

        Parameters
        ----------
        purl: str
            The target software component Package URL.
        """
        if purl.namespace is None or purl.version is None:
            missing_fields = []
            if purl.namespace is None:
                missing_fields.append("group ID (namespace)")
            if purl.version is None:
                missing_fields.append("version")
            logger.error("Purl %s is missing required field(s): %s.", purl, ", ".join(missing_fields))
            return

        # We always attempt to get the JDK version from maven central JAR for this GAV artifact.
        jdk_from_jar = find_jdk_version_from_central_maven_repo(
            group_id=purl.namespace,
            artifact_id=purl.name,
            version=purl.version,
        )
        logger.info(
            "Attempted to find JDK from Maven Central JAR. Result: %s",
            jdk_from_jar or "Cannot find any.",
        )

        existing = self.data["language_version"][0] if self.data["language_version"] else None

        # Select JDK from jar or another source, with a default of version 8.
        selected_jdk_version = jdk_from_jar or existing if existing else "8"

        major_jdk_version = normalize_jdk_version(selected_jdk_version)
        if not major_jdk_version:
            logger.error("Failed to obtain the major version of %s", selected_jdk_version)
            return

        self.data["language_version"] = [major_jdk_version]

        # Resolve and patch build commands.
        for build_cmd_spec in self.data["build_commands"]:
            if not build_cmd_spec["command"]:
                self.set_default_build_commands(build_cmd_spec)

        for build_command_info in self.data["build_commands"]:
            if build_command_info["command"] and (
                patched_cmd := patch_command(
                    cmd=build_command_info["command"],
                    patches=CLI_COMMAND_PATCHES,
                )
            ):
                build_command_info["command"] = patched_cmd
