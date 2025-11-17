# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module provides analysis functions for a pyproject.toml file."""

import logging
import tomllib
from pathlib import Path
from typing import Any

from tomli import TOMLDecodeError

from macaron.json_tools import json_extract

logger: logging.Logger = logging.getLogger(__name__)


def get_content(pyproject_path: Path) -> dict[str, Any] | None:
    """
    Return the pyproject.toml content.

    Parameters
    ----------
    pyproject_path : Path
        The file path to the pyproject.toml file.

    Returns
    -------
    dict[str, Any] | None
        The [build-system] section as a dict, or None otherwise.
    """
    try:
        with open(pyproject_path, "rb") as toml_file:
            return tomllib.load(toml_file)
    except (FileNotFoundError, TypeError, TOMLDecodeError) as error:
        logger.debug("Failed to read the %s file: %s", pyproject_path, error)
        return None


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
    content = get_content(pyproject_path)
    if not content:
        return False

    # Check for the existence of a [tool.<tool_name>] section.
    tools = json_extract(content, ["tool"], dict)
    if tools and tool_name in tools:
        return True
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
    content = get_content(pyproject_path)
    if not content:
        return False

    # Check in 'build-backend'.
    backend = json_extract(content, ["build-system", "build-backend"], str)
    if backend and tool_name in backend:
        return True
    # Check in 'requires' list.
    requires = json_extract(content, ["build-system", "requires"], list)
    if requires and any(tool_name in req for req in requires):
        return True

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
    content = get_content(pyproject_path)
    if not content:
        return None

    return json_extract(content, ["build-system"], dict)
