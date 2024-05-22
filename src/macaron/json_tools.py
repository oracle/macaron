# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module provides utility functions for JSON data."""
import logging
from collections.abc import Sequence
from typing import TypeVar

JsonType = int | float | str | None | bool | list["JsonType"] | dict[str, "JsonType"]
T = TypeVar("T", bound=JsonType)

logger: logging.Logger = logging.getLogger(__name__)


def json_extract(entry: dict | list, keys: Sequence[str | int], type_: type[T]) -> T | None:
    """Return the value found by following the list of depth-sequential keys inside the passed JSON dictionary.

    The value must be of the passed type.

    Parameters
    ----------
    entry: dict | list
        An entry point into a JSON structure.
    keys: Sequence[str | int]
        The sequence of depth-sequential keys within the JSON. Can be dict keys or list indices.
    type: type[T]
        The type to check the value against and return it as.

    Returns
    -------
    T | None:
        The found value as the type of the type parameter.
    """
    target: JsonType = entry
    for key in keys:
        if isinstance(target, dict) and isinstance(key, str):
            if key not in target:
                logger.debug("JSON key '%s' not found in dict target.", key)
                return None
        elif isinstance(target, list) and isinstance(key, int):
            if key < 0 or key >= len(target):
                logger.debug("JSON list index '%s' is outside of list bounds %s.", key, len(target))
                return None
        else:
            logger.debug("Cannot index '%s' (type: %s) in target (type: %s).", key, type(key), type(target))
            return None

        # If statement required for mypy to not complain. The else case can never happen because of the above if block.
        if isinstance(target, dict) and isinstance(key, str):
            target = target[key]
        elif isinstance(target, list) and isinstance(key, int):
            target = target[key]

    if isinstance(target, type_):
        return target

    logger.debug("Found value of incorrect type: %s instead of %s.", type(target), type(type_))
    return None
