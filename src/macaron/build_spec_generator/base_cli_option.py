# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contain the base class for all cli options."""

import argparse
from abc import abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Generic, TypeGuard, TypeVar

T = TypeVar("T")


def is_list_of_strs(value: Any) -> TypeGuard[list[str]]:
    """Type guard for a list of strings."""
    return isinstance(value, list) and all(isinstance(ele, str) for ele in value)


def is_dict_of_str_to_str(value: Any) -> TypeGuard[list[str]]:
    """Type guard for a dictionary with keys are string and values are strings."""
    return isinstance(value, dict) and all(isinstance(key, str) and isinstance(val, str) for key, val in value.items())


def patch_mapping(
    original: Mapping[str, str],
    patch: Mapping[str, str | None],
) -> dict[str, str]:
    """Patch a mapping.

    A key with value in patch set to None will be removed from the original.

    Parameters
    ----------
    original: Mapping[str, str]
        The original mapping.
    patch: Mapping[str, str | None]
        The patch.

    Returns
    -------
    dict[str, str]:
        The new dictionary after applying the patch.
    """
    patch_result = dict(original)

    for name, value in patch.items():
        if value is None:
            patch_result.pop(name, None)
        else:
            patch_result[name] = value

    return patch_result


@dataclass
class Option(Generic[T]):
    """This class represent a type of option for the CLI command.

    The generic type T is how we store the value parsed for this option internally.
    """

    # e.g. `--long-option-name`
    # We always require the long name as we use it as the unique identifier in the parser.
    long_name: str

    @abstractmethod
    def is_valid_patch_option(self, patch: Any) -> TypeGuard[T]:
        """Return True if the provide patch value is compatible with the internal type of this option."""
        raise NotImplementedError()

    @abstractmethod
    def add_itself_to_arg_parser(self, arg_parse: argparse.ArgumentParser) -> None:
        """Add a new argument to argparser.ArgumentParser representing this option."""
        raise NotImplementedError()

    @abstractmethod
    def get_patch_type_str(self) -> str:
        """Return the expected type for the patch value as string."""
        raise NotImplementedError()
