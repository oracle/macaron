# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contain the base classes cli command parsers related."""

import argparse
from abc import abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Generic, Protocol, TypeGuard, TypeVar


def is_list_of_strs(value: Any) -> TypeGuard[list[str]]:
    """Type guard for a list of strings."""
    return isinstance(value, list) and all(isinstance(ele, str) for ele in value)


def is_dict_of_str_to_str_or_none(value: Any) -> TypeGuard[dict[str, str | None]]:
    """Type guard for a dictionary where the keys are string and values are strings or None."""
    if not isinstance(value, dict):
        return False

    for key, val in value.items():
        if not isinstance(key, str):
            return False

        if not (val is None or isinstance(val, str)):
            return False

    return True


def patch_mapping(
    original: Mapping[str, str],
    patch: Mapping[str, str | None],
) -> dict[str, str]:
    """Patch a mapping.

    A key with a value in the patch set to None will be removed from the original.

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


P = TypeVar("P")


@dataclass
class OptionDef(Generic[P]):
    """This class represents a definition of a CLI option for argparse.ArgumentParser.

    This class also contains the information for validating a patch value.
    The generic type P is the patch expected type (if it's not None).
    """

    # e.g. `--long-option-name`
    # We always require the long name as we use it as the unique identifier in the parser.
    long_name: str

    @abstractmethod
    def is_valid_patch_option(self, patch: Any) -> TypeGuard[P]:
        """Return True if the provided patch value is compatible with the internal type of this option."""
        raise NotImplementedError()

    @abstractmethod
    def add_to_arg_parser(self, arg_parse: argparse.ArgumentParser) -> None:
        """Add a new argument to argparser.ArgumentParser representing this option."""
        raise NotImplementedError()

    @abstractmethod
    def get_patch_type_str(self) -> str:
        """Return the expected type for the patch value as string."""
        raise NotImplementedError()


class PatchCommandBuildTool(str, Enum):
    """Build tool supported for CLICommand patching."""

    MAVEN = "maven"
    GRADLE = "gradle"


class CLIOptions(Protocol):
    """Interface of the options part of a CLICommand."""

    def to_option_cmds(self) -> list[str]:
        """Return the options as a list of strings."""


class CLICommand(Protocol):
    """Interface of a CLI Command."""

    def to_cmds(self) -> list[str]:
        """Return the CLI Command as a list of strings."""


# T is a generic type variable restricted to subclasses of CLICommand.
# It ensures that only derived types of CLICommand can be used with
# generic classes or functions parameterized by T.
T = TypeVar("T", bound="CLICommand")

# Y_contra is a contravariant type variable intended for CLI argument
# patch values. Using contravariance allows generic classes or functions
# to accept supertypes of the specified type parameter, making it easier
# to support broader value types when implementing patching for different
# build tools.
Y_contra = TypeVar("Y_contra", contravariant=True)


class CLICommandParser(Protocol[T, Y_contra]):
    """Interface of a CLI Command Parser."""

    @property
    def build_tool(self) -> PatchCommandBuildTool:
        """Return the ``BuildTool`` enum corresponding to this CLICommand."""

    def parse(self, cmd_list: list[str]) -> CLICommand:
        """Parse the CLI Command.

        Parameters
        ----------
        cmd_list: list[str]
            The CLI Command as list of strings.

        Returns
        -------
        CLICommand
            The CLICommand instance.

        Raises
        ------
        CommandLineParseError
            If an error happens when parsing the CLI Command.
        """

    def is_build_tool(self, executable_path: str) -> bool:
        """Return True if ``executable_path`` ends the accepted executable for this build tool.

        Parameters
        ----------
        executable_path: str
            The executable component of a CLI command.

        Returns
        -------
        bool
        """

    def apply_patch(
        self,
        cli_command: T,
        patch_options: Mapping[str, Y_contra | None],
    ) -> T:
        """Return a new CLICommand object with its option patched, while persisting the executable path."""
