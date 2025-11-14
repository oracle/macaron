# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module provides analysis functions for a pyproject.toml file."""

import logging
import tomllib
from pathlib import Path

logger: logging.Logger = logging.getLogger(__name__)


def contains_build_tool(tool_name: str, pyproject_path: Path) -> bool:
    """
    Check if a given build tool is present in the [tool] section of a pyproject.toml file.

    Parameters
    ----------
    tool_name : str
        The name of the build tool to search for (e.g., 'poetry', 'flit').
    pyproject_path : Path
        The file path to the pyproject.toml file.

    Returns
    -------
    bool
        True if the build tool is found in the [tool] section, False otherwise.
    """
    try:
        # Parse the pyproject.toml file.
        with open(pyproject_path, "rb") as toml_file:
            try:
                data = tomllib.load(toml_file)
                # Check for the existence of a [tool.<tool_name>] section.
                if ("tool" in data) and (tool_name in data["tool"]):
                    return True
            except tomllib.TOMLDecodeError:
                logger.debug("Failed to read the %s file: invalid toml file.", pyproject_path)
                return False
        return False
    except FileNotFoundError:
        logger.debug("Failed to read the %s file.", pyproject_path)
        return False


def build_system_contains_tool(tool_name: str, pyproject_path: Path) -> bool:
    """
    Check if the [build-system] section lists the specified tool in 'build-backend' or 'requires' in pyproject.toml.

    Parameters
    ----------
    tool_name : str
        The tool or backend name to search for (e.g., 'setuptools', 'poetry.masonry.api', 'flit_core.buildapi').
    pyproject_path : Path
        The file path to the pyproject.toml file.

    Returns
    -------
    bool
        True if the tool is found in either the 'build-backend' or 'requires' of the [build-system] section, False otherwise.
    """
    try:
        with open(pyproject_path, "rb") as toml_file:
            try:
                data = tomllib.load(toml_file)
                build_system = data.get("build-system", {})
                backend = build_system.get("build-backend", "")
                requires = build_system.get("requires", [])
                # Check in 'build-backend'.
                if tool_name in backend:
                    return True
                # Check in 'requires' list.
                if any(tool_name in req for req in requires):
                    return True
            except tomllib.TOMLDecodeError:
                logger.debug("Failed to read the %s file: invalid toml file.", pyproject_path)
                return False
        return False
    except FileNotFoundError:
        logger.debug("Failed to read the %s file.", pyproject_path)
        return False


def get_build_system(pyproject_path: Path) -> dict[str, str] | None:
    """
    Return the [build-system] section in pyproject.toml if it exists.

    Parameters
    ----------
    pyproject_path : Path
        The file path to the pyproject.toml file.

    Returns
    -------
    dict[str, str] | None
        The [build-system] section as a dict, or None otherwise.
    """
    try:
        with open(pyproject_path, "rb") as toml_file:
            try:
                data = tomllib.load(toml_file)
                return data.get("build-system", {}) or None
            except tomllib.TOMLDecodeError:
                logger.debug("Failed to read the %s file: invalid toml file.", pyproject_path)
                return None
    except FileNotFoundError:
        logger.debug("Failed to read the %s file.", pyproject_path)
        return None
