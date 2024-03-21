# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module provides utility functions for JSON data."""

from typing import TypeVar

from macaron.errors import JsonError
from macaron.util import JsonType

T = TypeVar("T", bound=JsonType)


def json_extract(entry: JsonType, keys: list[str], type_: type[T]) -> T:
    """Return the value found by following the list of depth-sequential keys inside the passed JSON dictionary.

    The value must be of the passed type.

    Parameters
    ----------
    entry: JsonType
        An entry point into a JSON structure.
    keys: list[str]
        The list of depth-sequential keys within the JSON.
    type: type[T]
        The type to check the value against and return it as.

    Returns
    -------
    T:
        The found value as the type of the type parameter.

    Raises
    ------
    JsonError
        Raised if an error occurs while searching for or validating the value.
    """
    target = entry

    for index, key in enumerate(keys):
        if not isinstance(target, dict):
            raise JsonError(f"Expect the value .{'.'.join(keys[:index])} to be a dict.")
        if key not in target:
            raise JsonError(f"JSON key '{key}' not found in .{'.'.join(keys[:index])}.")
        target = target[key]

    if isinstance(target, type_):
        return target

    raise JsonError(f"Expect the value .{'.'.join(keys)} to be of type '{type_}'.")
