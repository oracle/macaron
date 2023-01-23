# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the Jinja2 extension filters and tests.

All tests will have ``j2_test_`` as a prefix. The rest of the name will
be the name of that test in the Jinja2 Environment.

All filters will have ``j2_filter_`` as a prefix. The rest of the name will
be the name of that filter in the Jinja2 Environment.

References
----------
    - https://jinja.palletsprojects.com/en/3.1.x/api/#custom-filters
    - https://jinja.palletsprojects.com/en/3.1.x/api/#custom-tests
"""

from enum import Enum
from typing import Any

from jinja2 import TemplateRuntimeError

from macaron.output_reporter.scm import SCMStatus
from macaron.slsa_analyzer.checks.check_result import CheckResultType


def j2_test_list(obj: Any) -> bool:
    """Return True if the object is a list.

    Parameters
    ----------
    obj : Any
        The object to check.

    Returns
    -------
    bool
    """
    return isinstance(obj, list)


def j2_test_python_enum(obj: Any) -> bool:
    """Return True if the object is an Enum.

    Parameters
    ----------
    obj : Any
        The object to check.

    Returns
    -------
    bool
    """
    return isinstance(obj, Enum)


def j2_filter_get_headers(val_list: list[dict]) -> list[str]:
    """Return the list of headers to form a table from a list of dictionaries.

    The list of headers will be the set contains all unique keys from all
    dictionaries in the list.

    Parameters
    ----------
    val_list : list[dict]
        The list of all dictionaries.

    Returns
    -------
    list[str]
        The list of header names.

    Raises
    ------
    TemplateRuntimeError
        If trying to extract headers from a non-dict object.
    """
    headers: list[str] = []

    for ele in val_list:
        if not isinstance(ele, dict):
            raise TemplateRuntimeError("Cannot get the headers from a non-dict object.")

        for key in ele:
            if key not in headers:
                headers.append(key)

    return headers


def j2_filter_get_flatten_dict(data: Any, has_key: bool = False) -> dict | Any:
    """Flatten a dictionary to only contain dict and primitives values.

    This method removes all list from a nested dictionary by replacing it with a
    dictionary that maps from the index number (in the original list) to each element
    of that list.

    For values that are not in primitive types, we try to return a string representation
    of that object.

    If ``has_key`` is True, this method will return the primitive values as is (i.e. the returned value
    will be put in a mapping of the previous level dictionary.). If ``has_key`` is False OR the data is
    not a dict, list or of primitive types, this method will
    return a simple mapping ``{"0": str(data)}``

    Parameters
    ----------
    data : Any
        The dictionary that we want to flatten out.
    has_key : bool
        True if data has a key associated with it.

    Returns
    -------
    dict
        The result dictionary.

    Examples
    --------
    >>> j2_filter_get_flatten_dict(
        {
            "A": [1,2,3],
            "B": {
                "C": ["blah", "bar", "foo"]
            }
        }
    )
    {'A': {'0': 1, '1': 2, '2': 3}, 'B': {'C': {'0': 'blah', '1': 'bar', '2': 'foo'}}}
    """
    if isinstance(data, (str, int, bool, float)):
        if has_key:
            return data
        return {"0": data}

    if isinstance(data, dict):
        for key, item in data.items():
            data[key] = j2_filter_get_flatten_dict(item, has_key=True)
        return data

    if isinstance(data, list):
        converted = {}
        for index, item in enumerate(data):
            converted[index] = j2_filter_get_flatten_dict(item, has_key=True)
        return converted

    # For non-supported types.
    return {"0": str(data)}


def j2_filter_get_dep_status_color(dep_status: str) -> str:
    """Return the html class name for the color of the dep status.

    Parameters
    ----------
    dep_status : str
        The dep status as string.

    Returns
    -------
    str
        The css class name with the corresponding color or an empty string if the status is not recognized.
    """
    try:
        scm_status = SCMStatus(dep_status)
        match scm_status:
            case SCMStatus.AVAILABLE:
                return "green_bg"
            case SCMStatus.DUPLICATED_SCM:
                return "lightgreen_bg"
            case SCMStatus.MISSING_SCM:
                return "grey_bg"
            case SCMStatus.ANALYSIS_FAILED:
                return "red_bg"
    except ValueError:
        return ""


def j2_filter_get_check_result_color(result_type: str) -> str:
    """Return the html class name for the color of the check result.

    Parameters
    ----------
    result_type : str
        The result type as string.

    Returns
    -------
    str
        The css class name with the corresponding color or empty string if the result type is not recognized.
    """
    try:
        check_result_type = CheckResultType(result_type)
        match check_result_type:
            case CheckResultType.PASSED:
                return "green_bg"
            case CheckResultType.FAILED:
                return "red_bg"
            case CheckResultType.SKIPPED:
                return "lightgreen_bg"
            case CheckResultType.UNKNOWN:
                return "grey_bg"
            case CheckResultType.DISABLED:
                return "black_bg"
    except ValueError:
        return ""


filter_extensions: dict[str, str] = {
    filter_str.replace("j2_filter_", ""): filter_str for filter_str in dir() if filter_str.startswith("j2_filter_")
}
"""The mappings between the name of a filter and its function's name as defined in this module."""

test_extensions: dict[str, str] = {test.replace("j2_test_", ""): test for test in dir() if test.startswith("j2_test_")}
"""The mappings between the name of a test and its function's name as defined in this module."""
