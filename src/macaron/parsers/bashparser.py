# Copyright (c) 2022 - 2025, Oracle and/or its affiliates. All rights reserved.
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
from typing import cast

from macaron.config.defaults import defaults
from macaron.config.global_config import global_config
from macaron.errors import ParseError
from macaron.parsers.bashparser_model import File, Word

logger: logging.Logger = logging.getLogger(__name__)


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
            logger.info("Parsing %s.", os.path.relpath(file_path, os.getcwd()))
            return parse(file.read(), macaron_path)
    except OSError as error:
        raise ParseError(f"Could not load the bash script file: {os.path.relpath(file_path, os.getcwd())}.") from error
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


def parse_expr(bash_expr_content: str, macaron_path: str | None = None) -> list[Word]:
    """Parse a bash script's content.

    Parameters
    ----------
    bash_content : str
        Bash script content
    macaron_path : str | None
        Macaron's root path (optional).

    Returns
    -------
    list[bashparser_model.Word]
        The parsed bash expr AST in typed JSON (dict) format.

    Raises
    ------
    ParseError
        When parsing fails with errors.
    """
    if not macaron_path:
        macaron_path = global_config.macaron_path
    cmd = [
        os.path.join(macaron_path, "bin", "bashexprparser"),
        "-input",
        bash_expr_content,
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
        raise ParseError("Error while parsing bash expr.") from error

    try:
        if result.returncode == 0:
            return cast(list[Word], json.loads(result.stdout.decode("utf-8")))

        raise ParseError(f"Bash script parser failed: {result.stderr.decode('utf-8')}")

    except json.JSONDecodeError as error:
        raise ParseError("Error while loading the parsed bash script.") from error
