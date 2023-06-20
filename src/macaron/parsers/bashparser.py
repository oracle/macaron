# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module is a Python wrapper for the compiled bashparser binary.

The bashparser Go module is based on the ``github.com/mvdan/sh`` Go module and is distributed
together with Macaron as a compiled binary.

See Also https://github.com/mvdan/sh.
"""

import json
import logging
import os
import subprocess  # nosec B404
from collections.abc import Iterable
from typing import TypedDict

from macaron.config.defaults import defaults
from macaron.config.global_config import global_config

logger: logging.Logger = logging.getLogger(__name__)


class BashCommands(TypedDict):
    """This dictionary stores the data for parsed bash commands."""

    caller_path: str
    """The relative path to the file that calls the bash command."""
    CI_path: str
    """The relative path to the root CI file that triggers the bash command."""
    CI_type: str
    """CI service type."""
    commands: list[list[str]]
    """Parsed bash commands."""
    workflow_info: dict


def parse_file(file_path: str, macaron_path: str = "") -> dict:
    """Parse a bash script file.

    Parameters
    ----------
    file_path : str
        Bash script file path.
    macaron_path : str
        Macaron's root path (optional).

    Returns
    -------
    dict
        The parsed bash script in JSON (dict) format.
    """
    if not macaron_path:
        macaron_path = global_config.macaron_path
    try:
        with open(file_path, encoding="utf8") as file:
            logger.info("Parsing %s.", file_path)
            return parse(file.read(), macaron_path)
    except OSError as error:
        logger.error("Could not load the bash script %s: %s.", file_path, error)
        return {}


def parse(bash_content: str, macaron_path: str = "") -> dict:
    """Parse a bash script's content.

    Parameters
    ----------
    bash_content : str
        Bash script content
    macaron_path : str
        Macaron's root path (optional).

    Returns
    -------
    dict
        The parsed bash script in JSON (dict) format.
    """
    if not macaron_path:
        macaron_path = global_config.macaron_path
    cmd = [
        os.path.join(macaron_path, "bin", "bashparser"),
        "-input",
        bash_content,
    ]

    try:
        result = subprocess.run(  # nosec B603
            cmd,
            capture_output=True,
            check=True,
            cwd=macaron_path,
            timeout=defaults.getint("bashparser", "timeout", fallback=30),
        )
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
    ) as error:
        logger.error("Error while parsing bash script: %s", error)
        return {}

    try:
        if result.returncode == 0:
            return dict(json.loads(result.stdout.decode("utf-8")))

        logger.error("Bash script parser failed: %s", result.stderr)
        return {}
    except json.JSONDecodeError as error:
        logger.error("Error while loading the parsed bash script: %s", error)
        return {}


def extract_bash_from_ci(
    bash_content: str,
    ci_file: str,
    ci_type: str,
    workflow_info: dict,
    macaron_path: str = "",
    recursive: bool = False,
    repo_path: str = "",
    working_dir: str = "",
) -> Iterable[BashCommands]:
    """Parse the bash scripts triggered from CI.

    Parameters
    ----------
    bash_content : str
        Bash script content.
    ci_file : str
        The relative path to the entry point CI workflow.
    ci_type : str
        The CI service.
    macaron_path : str
        Macaron's root path (optional).
    recursive : bool
        Recursively parse bash scripts with depth 1.
        Should specify repo_path too if set to True.
    repo_path : str
        The path to the target repo.
    working_dir : str
        The working directory from which the bash script has run.
        Empty value is considered as the root of the repo.

    Yields
    ------
    BashCommands
        The parsed bash script objects.
    """
    if not macaron_path:
        macaron_path = global_config.macaron_path

    parsed_parent = parse(bash_content)
    caller_commands = parsed_parent.get("commands", [])
    if caller_commands:
        yield BashCommands(
            caller_path=ci_file, CI_path=ci_file, CI_type=ci_type, commands=caller_commands, workflow_info=workflow_info
        )

    # Parse the bash script files called from the current script.
    if recursive and repo_path:
        for cmd in caller_commands:

            # Parse the scripts that end with `.sh`.
            # We only parse recursively at depth 1, so don't set the recursive argument in parse_file().
            # TODO: parse Makefiles for bash commands.
            if cmd[0] and cmd[0].endswith(".sh") and os.path.exists(os.path.join(repo_path, cmd[0])):
                callee_commands = parse_file(os.path.join(repo_path, cmd[0])).get("commands", [])
                if not callee_commands:
                    continue

                yield BashCommands(
                    caller_path=os.path.join(working_dir, cmd[0]),
                    CI_path=ci_file,
                    CI_type=ci_type,
                    commands=callee_commands,
                    workflow_info=workflow_info,
                )
