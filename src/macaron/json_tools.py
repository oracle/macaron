# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module provides utility functions for JSON data."""
import logging
from typing import TypeVar

JsonType = int | float | str | None | bool | list["JsonType"] | dict[str, "JsonType"]
T = TypeVar("T", bound=JsonType)

logger: logging.Logger = logging.getLogger(__name__)


def json_extract(entry: JsonType, keys: list, type_: type[T]) -> T | None:
    """Return the value found by following the list of depth-sequential keys inside the passed JSON dictionary.

    The value must be of the passed type.

    Parameters
    ----------
    entry: JsonType
        An entry point into a JSON structure.
    keys: list
        The list of depth-sequential keys within the JSON. Can be dict keys or list indices.
    type: type[T]
        The type to check the value against and return it as.

    Returns
    -------
    T | None:
        The found value as the type of the type parameter.
    """
    target = entry

    for index, key in enumerate(keys):
        if isinstance(target, dict):
            if key not in target:
                logger.debug("JSON key '%s' not found in .%s", key, ".".join(keys[:index]))
                return None
        elif isinstance(target, list):
            if isinstance(key, str):
                logger.debug("JSON key '%s' of type 'str' cannot extract from list.", key)
                return None

            if key < 0 or key >= len(target):
                logger.debug("JSON key '%s' is outside of list bounds %s.", key, len(target))
                return None
        else:
            logger.debug("Expect the value .%s to be a dict or list.", ".".join(keys[:index]))
            return None

        target = target[key]

    if isinstance(target, type_):
        return target

    logger.debug("Expect the value .%s to be of type %s", ".".join(keys), type_)
    return None
