# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains parsers for command line interfaces for commands relevant to analysis."""

from __future__ import annotations

import argparse


def parse_python_command_line(args: list[str]) -> argparse.Namespace:
    """Parse python command line.

    Parameters
    ----------
    args: list[str]
        Argument list to python command

    Returns
    -------
    argparse.Namespace
        Parsed python command args
    """
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-B", action="store_true")
    parser.add_argument("-b", action="count")
    parser.add_argument("--check-hash-based-pycs")
    parser.add_argument("-d", action="store_true")
    parser.add_argument("-E", action="store_true")
    parser.add_argument("-h", action="store_true")
    parser.add_argument("-?", action="store_true", dest="h")
    parser.add_argument("--help", action="store_true", dest="h")
    parser.add_argument("--help-env", action="store_true")
    parser.add_argument("--help-xoptions", action="store_true")
    parser.add_argument("--help-all", action="store_true")
    parser.add_argument("-i", action="store_true")
    parser.add_argument("-I", action="store_true")
    parser.add_argument("-o", action="count")
    parser.add_argument("-P", action="store_true")
    parser.add_argument("-q", action="store_true")
    parser.add_argument("-s", action="store_true")
    parser.add_argument("-S", action="store_true")
    parser.add_argument("-u", action="store_true")
    parser.add_argument("-v", action="count")
    parser.add_argument("-V", action="count")
    parser.add_argument("--version", action="count", dest="V")
    parser.add_argument("-w", action="store")
    parser.add_argument("-x", action="store")
    parser.add_argument("-m", nargs=argparse.REMAINDER)
    parser.add_argument("-c", nargs=argparse.REMAINDER)
    parser.add_argument("file", nargs=argparse.REMAINDER)

    parsed_args = parser.parse_args(args)

    if parsed_args.m is not None:
        parsed_args.subprocess_args = parsed_args.m[1:]
        parsed_args.m = parsed_args.m[0]
        parsed_args.file = None
    elif parsed_args.c is not None:
        parsed_args.subprocess_args = parsed_args.c[1:]
        parsed_args.c = parsed_args.c[0]
        parsed_args.file = None
    else:
        if len(parsed_args.file) > 0 and parsed_args.file[0] == "--":
            parsed_args.file = parsed_args.file[1:]
        if len(parsed_args.file) == 0:
            parsed_args.subprocess_args = []
            parsed_args.file = None
        else:
            parsed_args.subprocess_args = parsed_args.file[1:]
            parsed_args.file = parsed_args.file[0]

    return parsed_args


def main() -> None:
    """Test python command line parser."""
    print(str(parse_python_command_line(["-B", "-m", "pip", "install", "-U", "cibuildwheel"])))  # noqa: T201
    print(str(parse_python_command_line(["-B", "pip.py", "install", "-U", "cibuildwheel"])))  # noqa: T201
    print(str(parse_python_command_line(["-B", "--", "--pip.py", "install", "-U", "cibuildwheel"])))  # noqa: T201
    print(  # noqa: T201
        str(parse_python_command_line(["-B", "-c", "import sys; print(sys.argv[1:])", "install", "-U", "cibuildwheel"]))
    )
    print(str(parse_python_command_line(["-B"])))  # noqa: T201


if __name__ == "__main__":
    main()
