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
from typing import Any, cast

from macaron.code_analyzer.call_graph import BaseNode
from macaron.config.defaults import defaults
from macaron.config.global_config import global_config
from macaron.errors import CallGraphError, ParseError
from macaron.parsers.actionparser import get_run_step
from macaron.parsers.bashparser_model import File
from macaron.parsers.github_workflow_model import Step

logger: logging.Logger = logging.getLogger(__name__)


class BashScriptType(Enum):
    """This class is used for different bash script types."""

    NONE = "None"
    INLINE = "inline"  # Inline bash script.
    FILE = "file"  # Bash script file.


class BashNode(BaseNode):
    """This class represents a callgraph node for bash commands."""

    def __init__(
        self,
        name: str,
        node_type: BashScriptType,
        source_path: str,
        parsed_step_obj: Step | None,
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
        parsed_step_obj : Step | None
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

    Raises
    ------
    ParseError
        When parsing fails with errors.
    """
    if not macaron_path:
        macaron_path = global_config.macaron_path
    try:
        with open(file_path, encoding="utf8") as file:
            logger.info("Parsing %s.", file_path)
            return parse(file.read(), macaron_path)
    except OSError as error:
        raise ParseError(f"Could not load the bash script file: {file_path}.") from error
    except ParseError as error:
        raise error


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

    Raises
    ------
    ParseError
        When parsing fails with errors.
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
        raise ParseError("Error while parsing bash script.") from error

    try:
        if result.returncode == 0:
            return dict(json.loads(result.stdout.decode("utf-8")))

        raise ParseError(f"Bash script parser failed: {result.stderr.decode('utf-8')}")

    except json.JSONDecodeError as error:
        raise ParseError("Error while loading the parsed bash script.") from error


def parse_raw(bash_content: str, macaron_path: str | None = None) -> File:
    """Parse a bash script's content.

    Parameters
    ----------
    bash_content : str
        Bash script content
    macaron_path : str | None
        Macaron's root path (optional).

    Returns
    -------
    bashparser_model.File
        The parsed bash script AST in typed JSON (dict) format.

    Raises
    ------
    ParseError
        When parsing fails with errors.
    """
    if not macaron_path:
        macaron_path = global_config.macaron_path
    cmd = [
        os.path.join(macaron_path, "bin", "bashparser"),
        "-input",
        bash_content,
        "-raw",
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
        raise ParseError("Error while parsing bash script.") from error

    try:
        if result.returncode == 0:
            return cast(File, json.loads(result.stdout.decode("utf-8")))

        raise ParseError(f"Bash script parser failed: {result.stderr.decode('utf-8')}")

    except json.JSONDecodeError as error:
        raise ParseError("Error while loading the parsed bash script.") from error


def create_bash_node(
    name: str,
    node_id: str | None,
    node_type: BashScriptType,
    source_path: str,
    ci_step_ast: Step | None,
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
    ci_step_ast: Step | None
        The AST of the CI step that runs a bash script.
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
    parsed_bash_script = {}
    working_dir = None
    match node_type:
        case BashScriptType.INLINE:
            if ci_step_ast is None:
                raise CallGraphError(f"Unable to find the parsed AST for the CI step at {source_path}.")
            working_dir = ci_step_ast.get("working-directory")
            run_script = get_run_step(ci_step_ast)
            if run_script is None:
                raise CallGraphError(f"Invalid run step at {source_path}.")
            try:
                parsed_bash_script = parse(run_script, macaron_path=macaron_path)
            except ParseError as error:
                logger.debug(error)
        case BashScriptType.FILE:
            try:
                parsed_bash_script = parse_file(source_path, macaron_path=macaron_path)
            except ParseError as error:
                logger.debug(error)
    bash_node = BashNode(
        name,
        node_type,
        source_path,
        parsed_step_obj=ci_step_ast,
        parsed_bash_obj=parsed_bash_script,
        node_id=node_id,
        caller=caller,
    )
    caller_commands = parsed_bash_script.get("commands", [])

    # Parse the bash script files called from the current script.
    if caller_commands and repo_path:
        for cmd in caller_commands:
            # Parse the scripts that end with `.sh`.
            # TODO: parse Makefiles for bash commands.
            if not cmd or not cmd[0] or not cmd[0].endswith(".sh"):
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
                        ci_step_ast=None,
                        repo_path=repo_path,
                        caller=bash_node,
                        recursion_depth=recursion_depth + 1,
                        macaron_path=macaron_path,
                    )
                except CallGraphError as error:
                    raise error
                bash_node.add_callee(callee)
    return bash_node
