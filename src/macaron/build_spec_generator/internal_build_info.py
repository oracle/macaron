# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the representation of all build related information obtained from the database."""

from collections.abc import Sequence
from dataclasses import dataclass

from packageurl import PackageURL

from macaron.build_spec_generator.macaron_db_extractor import GenericBuildCommandInfo
from macaron.database.table_definitions import Repository
from macaron.slsa_analyzer.checks.build_tool_check import BuildToolFacts


@dataclass
class InternalBuildInfo:
    """An internal representation of the information obtained from the database for a PURL.

    This is only used for generating build spec in different supported format.
    """

    purl: PackageURL
    repository: Repository
    generic_build_command_facts: Sequence[GenericBuildCommandInfo] | None
    latest_component_id: int
    build_tool_facts: Sequence[BuildToolFacts]
