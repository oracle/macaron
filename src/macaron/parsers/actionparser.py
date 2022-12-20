# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
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

from macaron.config.defaults import defaults
from macaron.config.global_config import global_config

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
        logger.error("Error while parsing GitHub Action workflow %s: %s", workflow_path, error)
        return {}

    try:
        if result.returncode == 0:
            parsed_obj: dict = json.loads(result.stdout.decode("utf-8"))
            return parsed_obj
        logger.error("GitHub Actions parser failed: %s", result.stderr)
        return {}
    except json.JSONDecodeError as error:
        logger.error("Error while loading the parsed Actions workflow: %s", error)
        return {}
