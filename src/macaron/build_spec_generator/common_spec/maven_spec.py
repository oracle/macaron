# Copyright (c) 2025 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module includes build specification and helper classes for Maven packages."""


import logging
import os

from packageurl import PackageURL

from macaron.build_spec_generator.build_command_patcher import CLI_COMMAND_PATCHES, patch_commands
from macaron.build_spec_generator.common_spec.base_spec import BaseBuildSpec, BaseBuildSpecDict
from macaron.build_spec_generator.common_spec.jdk_finder import find_jdk_version_from_central_maven_repo
from macaron.build_spec_generator.common_spec.jdk_version_normalizer import normalize_jdk_version
from macaron.parsers.pomparser import parse_pom_string
from macaron.slsa_analyzer.build_tool import BUILD_TOOLS
from macaron.slsa_analyzer.build_tool.base_build_tool import file_exists
from macaron.slsa_analyzer.build_tool.maven import Maven

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
        """
        default_build_commands = []

        for build_tool_name in build_tool_names:

            match build_tool_name:
                case "maven":
                    default_build_commands.append("mvn clean package".split())
                case "gradle":
                    default_build_commands.append("./gradlew clean assemble publishToMavenLocal".split())
                case _:
                    pass

        if not default_build_commands:
            logger.debug(
                "There is no default build command available for the build tools %s.",
                build_tool_names,
            )

        return default_build_commands

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
        selected_build_commands = self.data["build_commands"] or self.get_default_build_commands(
            self.data["build_tools"]
        )
        patched_build_commands = patch_commands(
            cmds_sequence=selected_build_commands,
            patches=CLI_COMMAND_PATCHES,
        )
        if not patched_build_commands:
            logger.debug("Failed to patch build command sequences %s", selected_build_commands)
            self.data["build_commands"] = []
            return

        for build_tool in BUILD_TOOLS:
            match build_tool:
                case Maven() as maven_tool:
                    pom_path = file_exists(self.data["fs_path"], "pom.xml", filters=maven_tool.path_filters)
                    if pom_path:
                        if (disable_test_compile := disable_maven_test_skip(pom_path)):
                            logger.debug(f"SHOULD SKIP TEST COMPILATION ?????? {disable_test_compile}")
                            # Add -Dmaven.test.skip for Maven builds.
                            # TODO: Use the build tool associated with the build command once
                            # https://github.com/oracle/macaron/issues/1300 is closed.
                            patched_build_commands = [
                                cmd[:1] + ["-Dmaven.test.skip=true"] + cmd[1:] if "mvn" in cmd[0] else cmd
                                for cmd in patched_build_commands
                            ]                        
                            break

        self.data["build_commands"] = patched_build_commands

POM_NS = "{http://maven.apache.org/POM/4.0.0}"

def read_pom_as_string(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def get_text(element, tag):
    el = element.find(f"./{POM_NS}{tag}")
    if el is not None:
        return el.text
    parent = element.find(f"./{POM_NS}parent/{POM_NS}{tag}")
    if parent is not None:
        return parent.text
    return None

def find_reactor_modules(parent_pom_path):
    pstring = read_pom_as_string(parent_pom_path)
    root = parse_pom_string(pstring)
    if root is None:
        return []
    modules_section = root.find(f"./{POM_NS}modules")
    return [module.text.strip() for module in modules_section.findall(f"{POM_NS}module")] if modules_section is not None else []

def parse_pom(path):
    pstring = read_pom_as_string(path)
    root = parse_pom_string(pstring)
    if root is None:
        return None, None, None
    group_id = get_text(root, "groupId")
    artifact_id = get_text(root, "artifactId")
    return group_id, artifact_id, root

def find_test_scope_reactor_deps(module_root, reactor_ga_set):
    deps = module_root.find(f"./{POM_NS}dependencies")
    if deps is None:
        return []
    harmful = []
    for dep in deps.findall(f"{POM_NS}dependency"):
        g = dep.find(f"{POM_NS}groupId")
        a = dep.find(f"{POM_NS}artifactId")
        scope = dep.find(f"{POM_NS}scope")
        typ = dep.find(f"{POM_NS}type")
        # Defaults
        scope = scope.text.strip() if scope is not None else "compile"
        typ = typ.text.strip() if typ is not None else "jar"
        ga = (g.text.strip(), a.text.strip())
        if scope == "test" and ga in reactor_ga_set:
            harmful.append({
                'groupId': g.text.strip(),
                'artifactId': a.text.strip(),
                'type': typ,
            })
    return harmful

def disable_maven_test_skip(parent_pom_path) -> bool:
    modules = find_reactor_modules(parent_pom_path)
    project_dir = os.path.dirname(parent_pom_path)
    reactor_ga_set = set()
    module_poms = {}
    for module in modules:
        module_pom = os.path.join(project_dir, module, "pom.xml")
        group_id, artifact_id, root = parse_pom(module_pom)
        ga = (group_id, artifact_id)
        reactor_ga_set.add(ga)
        module_poms[module] = (module_pom, root)

    for module, (module_pom, root) in module_poms.items():
        if root is None:
            logger.debug(f"Module '{module}' could not be parsed and will be skipped.")
            continue
        harmful = find_test_scope_reactor_deps(root, reactor_ga_set)
        if harmful:
            logger.debug(f"Module '{module}' depends (test scope) on these reactor sibling artifacts:")
            for dep in harmful:
                logger.debug(f"  - {dep['groupId']}:{dep['artifactId']} (type: {dep['type']})")
            logger.debug("=> Skipping test compilation is NOT safe.\n")
            return False
        else:
            logger.debug(f"Module '{module}' has NO test-scope dependencies on other reactor modules.")
            logger.debug("=> Skipping test compilation is safe.\n")
    
    return True
