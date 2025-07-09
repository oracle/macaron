# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the class definition for a CLICommand that we don't support parsing for it."""

from macaron.build_spec_generator.cli_command_parser import dataclass


@dataclass
class UnparsedCLICommand:
    """This class represents a CLICommand that we don't support parsing.

    Therefore, it only stores the original command as is.
    """

    original_cmds: list[str]

    def to_cmds(self) -> list[str]:
        """Return the CLI Command as a list of strings."""
        return self.original_cmds
