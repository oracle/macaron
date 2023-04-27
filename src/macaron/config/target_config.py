# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the Configuration class for the target analyzed repository."""

import logging
import os
from dataclasses import dataclass, field

import yamale
from yamale.schema import Schema

from macaron.output_reporter.scm import SCMStatus

logger: logging.Logger = logging.getLogger(__name__)

_SCHEMA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "target_config_schema.yaml")

TARGET_CONFIG_SCHEMA: Schema = yamale.make_schema(_SCHEMA_DIR)
"""The schema for the target configuration yaml file."""


@dataclass
class Configuration:
    """This class contains the configuration for an analyzed repo in Macaron."""

    target_id: str
    path: str
    branch: str = ""
    digest: str = ""
    note: str = ""
    available: SCMStatus = SCMStatus.UNKNOWN
    dependencies: list["Configuration"] = field(default_factory=list)

    @classmethod
    def from_single_config(cls, config: dict) -> "Configuration":
        """WIP."""
        target_id = config.get("id", "")
        path = config.get("path", "")
        branch = config.get("branch", "")
        digest = config.get("digest", "")
        return Configuration(target_id=target_id, path=path, branch=branch, digest=digest)

    @classmethod
    def from_user_config(cls, config: dict):
        """WIP."""
        main_target = Configuration.from_single_config(config.get("target", {}))
        main_target.dependencies = [Configuration.from_single_config(dep) for dep in config.get("dependencies", [])]
        return main_target

    def get_dict(self) -> dict:
        """WIP."""
        return {
            "id": self.target_id,
            "path": self.path,
            "branch": self.branch,
            "digest": self.digest,
            "note": self.note,
            "available": self.available,
            "dependencies": [dep.get_dict() for dep in self.dependencies],
        }
