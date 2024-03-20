# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module is a Python wrapper for the compiled actionparser binary.

The actionparser Go module is based on the ``github.com/rhysd/actionlint`` Go module
and is distributed together with Macaron as a compiled binary.

See Also https://github.com/rhysd/actionlint.
"""

import json
import logging
import os
import subprocess  # nosec B404
from typing import Any, cast

from macaron.config.defaults import defaults
from macaron.config.global_config import global_config
from macaron.errors import ParseError

logger: logging.Logger = logging.getLogger(__name__)


def parse(workflow_path: str, macaron_path: str = "") -> dict:
    """Parse the GitHub Actions workflow YAML file.

    Parameters
    ----------
    workflow_path : str
        Path to the GitHub Actions.
    macaron_path : str
        Macaron's root path (optional).

    Returns
    -------
    dict
        The parsed workflow as a JSON (dict) object.

    Raises
    ------
    ParseError
        When parsing fails with errors.
    """
    if not macaron_path:
        macaron_path = global_config.macaron_path
    cmd = [
        os.path.join(macaron_path, "bin", "actionparser"),
        "-file",
        workflow_path,
    ]

    try:
        result = subprocess.run(  # nosec B603
            cmd,
            capture_output=True,
            check=True,
            cwd=macaron_path,
            timeout=defaults.getint("actionparser", "timeout", fallback=30),
        )
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
    ) as error:
        raise ParseError(f"Error while parsing GitHub Action workflow {workflow_path}") from error

    try:
        if result.returncode == 0:
            parsed_obj: dict = json.loads(result.stdout.decode("utf-8"))
            return parsed_obj
        raise ParseError(f"GitHub Actions parser failed: {result.stderr.decode('utf-8')}")
    except json.JSONDecodeError as error:
        raise ParseError("Error while loading the parsed Actions workflow") from error


def validate_step(step: dict[str, Any]) -> dict | None:
    """Validate the parsed GitHub Action step.

    Parameters
    ----------
    step: dict[str, Any]
        The parsed step object.

    Returns
    -------
    dict | None
        The Exec object in the parsed step object..
    """
    # This validation function can be extended over time based on our use cases.
    if "Exec" not in step:
        return None

    return cast(dict, step["Exec"])


def validate_run_step(step: dict[str, Any]) -> str | None:
    """Validate the parsed GitHub Action run step.

    Parameters
    ----------
    step: dict[str, Any]
        The parsed step object.

    Returns
    -------
    str | None
        The inlined run script.
    """
    if validate_step(step=step) is None:
        return None
    if step["Exec"].get("Run") is None:
        return None
    if step["Exec"]["Run"].get("Value") is None:
        return None

    return cast(str, step["Exec"]["Run"]["Value"])


def get_step_input(step: dict[str, Any], key: str) -> str | None:
    """Get an input value from a GitHub Action step.

    Parameters
    ----------
    step: dict[str, Any]
        The parsed step object.
    key: str
        The key to be looked up.

    Returns
    -------
    str | None
        The input value or None if it doesn't exist or the parsed object validation fails.
    """
    if validate_step(step=step) is None:
        return None
    if step["Exec"].get("Inputs") is None:
        return None
    if step["Exec"]["Inputs"].get(key) is None:
        return None
    if step["Exec"]["Inputs"][key].get("Value") is None:
        return None
    if (value := step["Exec"]["Inputs"][key]["Value"].get("Value")) is None:
        return None
    return cast(str, value)
