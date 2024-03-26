# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
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
from enum import Enum
from typing import Any

from macaron.code_analyzer.call_graph import BaseNode
from macaron.config.defaults import defaults
from macaron.config.global_config import global_config
from macaron.errors import CallGraphError
from macaron.parsers.actionparser import validate_run_step, validate_step

logger: logging.Logger = logging.getLogger(__name__)


class BashScriptType(Enum):
    """This class is used for different bash script types."""

    NONE = "None"
    INLINE = "inline"  # Inline bash script.
    FILE = "file"  # Bash script file.


class BashNode(BaseNode):
    """This class is used to create a call graph node for bash commands."""

    def __init__(
        self,
        name: str,
        node_type: BashScriptType,
        source_path: str,
        parsed_step_obj: dict | None,
        parsed_bash_obj: dict,
        **kwargs: Any,
    ) -> None:
        """Initialize instance.

        Parameters
        ----------
        name : str
            Name of the bash script file or the step name if the script is inlined.
        node_type : BashScriptType
            The type of the script.
        source_path : str
            The path of the script.
        parsed_step_obj : dict | None
            The parsed step object.
        parsed_bash_obj : dict
            The parsed bash script object.
        """
        super().__init__(**kwargs)
        self.name = name
        self.node_type: BashScriptType = node_type
        self.source_path = source_path
        self.parsed_step_obj = parsed_step_obj
        self.parsed_bash_obj = parsed_bash_obj

    def __str__(self) -> str:
        return f"BashNode({self.name},{self.node_type})"


def parse_file(file_path: str, macaron_path: str | None = None) -> dict:
    """Parse a bash script file.

    Parameters
    ----------
    file_path : str
        Bash script file path.
    macaron_path : str | None
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


def parse(bash_content: str, macaron_path: str | None = None) -> dict:
    """Parse a bash script's content.

    Parameters
    ----------
    bash_content : str
        Bash script content
    macaron_path : str | None
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
        logger.error("Error while parsing script: %s", error)
        return {}

    try:
        if result.returncode == 0:
            return dict(json.loads(result.stdout.decode("utf-8")))

        logger.error("Bash script parser failed: %s", result.stderr)
        return {}
    except json.JSONDecodeError as error:
        logger.error("Error while loading the parsed bash script: %s", error)
        return {}


def create_bash_node(
    name: str,
    node_id: str | None,
    node_type: BashScriptType,
    source_path: str,
    parsed_obj: dict | None,
    repo_path: str,
    caller: BaseNode,
    recursion_depth: int,
    macaron_path: str | None = None,
) -> BashNode:
    """Create a callgraph node for a bash script.

    A bash node can have the following types:

      * :class:`BashScriptType.INLINE` when it is inlined in a CI workflow.
      * :class:`BashScriptType.FILE` when it is a bash script file.

    Parameters
    ----------
    name: str
        A name to be used as the identifier of the node.
    node_id: str | None
        The node ID if defined.
    node_type: BashScriptType
        The type of the node.
    source_path: str
        The file that contains the bash script.
    parsed_obj: dict | None
        The parsed bash script object.
    repo_path: str
        The path to the target repo.
    caller: BaseNode
        The caller node.
    recursion_depth: int
        The number of times this function is called recursively.
    macaron_path=None
        The path to the Macaron module.

    Returns
    -------
    BashNode
        A bash node object.

    Raises
    ------
    CallGraphError
        When unable to create a bash node.
    """
    if recursion_depth > defaults.getint("bashparser", "recursion_depth", fallback=3):
        raise CallGraphError(f"The analysis has reached maximum recursion depth {recursion_depth} at {source_path}.")
    parsed_content = {}
    working_dir = None
    match node_type:
        case BashScriptType.INLINE:
            if parsed_obj is None:
                raise CallGraphError(f"Unable to find the parsed AST for the CI step at {source_path}.")
            step_exec = validate_step(parsed_obj)
            if step_exec is None:
                raise CallGraphError(f"Unable to validate parsed AST for the CI step at {source_path}.")

            working_dir = step_exec.get("WorkingDirectory")
            run_script = validate_run_step(parsed_obj)
            if run_script is None:
                raise CallGraphError(f"Invalid run step at {source_path}.")
            parsed_content = parse(run_script, macaron_path=macaron_path)
        case BashScriptType.FILE:
            parsed_content = parse_file(source_path, macaron_path=macaron_path)
    bash_node = BashNode(
        name,
        node_type,
        source_path,
        parsed_step_obj=parsed_obj,
        parsed_bash_obj=parsed_content,
        node_id=node_id,
        caller=caller,
    )
    caller_commands = parsed_content.get("commands", [])

    # Parse the bash script files called from the current script.
    if caller_commands and repo_path:
        for cmd in caller_commands:
            # Parse the scripts that end with `.sh`.
            # TODO: parse Makefiles for bash commands.
            if not cmd[0] or not cmd[0].endswith(".sh"):
                continue

            # Check for path traversal patterns before analyzing a bash file.
            bash_file_path = os.path.realpath(os.path.join(repo_path, working_dir or "", cmd[0]))
            if os.path.exists(bash_file_path) and bash_file_path.startswith(repo_path):
                try:
                    callee = create_bash_node(
                        name=cmd[0],
                        node_id=node_id,
                        node_type=BashScriptType.FILE,
                        source_path=bash_file_path,
                        parsed_obj=None,
                        repo_path=repo_path,
                        caller=bash_node,
                        recursion_depth=recursion_depth + 1,
                        macaron_path=macaron_path,
                    )
                except CallGraphError as error:
                    raise error
                bash_node.add_callee(callee)
    return bash_node
