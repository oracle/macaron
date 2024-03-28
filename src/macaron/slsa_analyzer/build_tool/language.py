# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains abstractions for build languages."""

from enum import Enum
from typing import Protocol, runtime_checkable


class BuildLanguage(str, Enum):
    """The supported build languages."""

    JAVA = "java"
    PYTHON = "python"
    GO = "go"
    JAVASCRIPT = "javascript"
    DOCKER = "docker"


@runtime_checkable
class Language(Protocol):
    """Interface of a language."""

    @property
    def lang_name(self) -> str:
        """Get the name of the language."""

    @property
    def lang_versions(self) -> list[str] | None:
        """Get the possible versions of the language."""

    @property
    def lang_distributions(self) -> list[str] | None:
        """Get the possible distributions of the language."""

    @property
    def lang_url(self) -> str | None:
        """Get the URL that provides information about the language distributions and versions."""
