# Copyright (c) 2022 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains helper functions for reporting."""

import logging
import os
from pathlib import Path

from macaron.config.global_config import global_config

logger: logging.Logger = logging.getLogger(__name__)


def find_report_output_path(file_name: str, host_output_path: str | None = None) -> str:
    """
    Determine the output path for a report file.

    If ``host_output_path`` is empty or None, returns the file path relative
    to the current working directory. Otherwise, prefixes the path (stripping
    the first directory component) with the provided container host output path.
    Returns empty string if path has no parts to strip.

    Parameters
    ----------
    file_name : str
        Path to the input file (absolute or relative).
    host_output_path : str | None
        Base output directory path.

    Returns
    -------
    str
        Output path as string.

    Examples
    --------
    >>> find_report_output_path("output/reports/maven/foo/bar", host_output_path=None)
    'output/reports/maven/foo/bar'
    >>> find_report_output_path("output/reports/maven/foo/bar", host_output_path="output_dir")
    'output_dir/reports/maven/foo/bar'
    >>> find_report_output_path("foo", host_output_path="output")
    'output/'
    >>> find_report_output_path("", host_output_path="output")
    ''
    """
    if not file_name:
        return ""
    if host_output_path is None:
        host_output_path = global_config.host_output_path
    try:
        file_path = Path(os.path.relpath(file_name, os.getcwd()))
    except (ValueError, OSError) as error:
        logger.debug("Failed to create path for %s: %s", file_name, error)
        return ""
    if not host_output_path:
        return str(file_path)

    return os.path.join(host_output_path, file_path.relative_to(file_path.parts[0])).rstrip(".")
