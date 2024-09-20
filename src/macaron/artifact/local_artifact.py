# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module declares types and utilities for handling local artifacts."""

import os
from collections.abc import Mapping

from packageurl import PackageURL

from macaron.artifact.maven import construct_maven_repository_path
from macaron.config.global_config import global_config


def get_local_artifact_repo_mapper() -> Mapping[str, str]:
    """Get A."""
    local_artifact_mapper: dict[str, str] = {}

    if global_config.local_maven_repo:
        local_artifact_mapper["maven"] = global_config.local_maven_repo

    if global_config.python_venv_path:
        local_artifact_mapper["pypi"] = global_config.python_venv_path

    return local_artifact_mapper


def construct_local_artifact_path_from_purl(
    build_purl_type: str,
    component_purl: PackageURL,
    local_artifact_repo_mapper: Mapping[str, str],
) -> str | None:
    """Get B."""
    local_artifact_repo = local_artifact_repo_mapper.get(build_purl_type)
    if local_artifact_repo is None:
        return None

    artifact_path = None
    match build_purl_type:
        case "maven":
            group = component_purl.namespace
            artifact = component_purl.name
            version = component_purl.version

            if group is None or version is None:
                return None

            artifact_path = os.path.join(
                local_artifact_repo,
                "repository",
                construct_maven_repository_path(group, artifact, version),
            )
        case "pypi":
            # TODO: implement this.
            pass
        case _:
            return None

    return artifact_path


def get_local_artifact_paths(
    purl: PackageURL,
    build_tool_purl_types: list[str],
    local_artifact_repo_mapper: Mapping[str, str],
) -> dict[str, str]:
    """Get C."""
    result = {}

    for build_purl_type in build_tool_purl_types:
        local_artfiact_path = construct_local_artifact_path_from_purl(
            build_purl_type=build_purl_type,
            component_purl=purl,
            local_artifact_repo_mapper=local_artifact_repo_mapper,
        )

        if local_artfiact_path and os.path.isdir(local_artfiact_path):
            result[build_purl_type] = local_artfiact_path

    return result
