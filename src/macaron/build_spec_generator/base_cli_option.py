# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contain the base class for all cli options."""

import argparse
from abc import abstractmethod
from dataclasses import dataclass
from typing import Any, Generic, TypeGuard, TypeVar

T = TypeVar("T")


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
