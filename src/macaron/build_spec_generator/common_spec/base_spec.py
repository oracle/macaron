# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module includes base build specification and helper classes."""

from abc import ABC, abstractmethod
from typing import NotRequired, Required, TypedDict

from packageurl import PackageURL


class BaseBuildSpecDict(TypedDict, total=False):
    """
    Initialize base build specification.

    It supports multiple languages, build tools, and additional metadata for enhanced traceability.
    """

    #: The package ecosystem.
    ecosystem: Required[str]

    #: The package identifier.
    purl: Required[str]

    #: The programming language, e.g., 'java', 'python', 'javascript'.
    language: Required[str]

    #: The build tool or package manager, e.g., 'maven', 'gradle', 'pip', 'poetry', 'npm', 'yarn'.
    build_tool: Required[str]

    #: The version of Macaron used for generating the spec.
    macaron_version: Required[str]

    #: The group identifier for the project/component.
    group_id: NotRequired[str | None]

    #: The artifact identifier for the project/component.
    artifact_id: Required[str]

    #: The version of the package or component.
    version: Required[str]

    #: The remote path or URL of the git repository.
    git_repo: NotRequired[str]

    #: The commit SHA or tag in the VCS repository.
    git_tag: NotRequired[str]

    #: The type of line endings used (e.g., 'lf', 'crlf').
    newline: NotRequired[str]

    #: The version of the programming language or runtime, e.g., '11' for JDK, '3.11' for Python.
    language_version: Required[list[str]]

    #: List of release dependencies.
    dependencies: NotRequired[list[str]]

    #: List of build dependencies, which includes tests.
    build_dependencies: NotRequired[list[str]]

    #: List of shell commands to build the project.
    build_commands: NotRequired[list[list[str]]]

    #: List of shell commands to test the project.
    test_commands: NotRequired[list[str]]

    #: Environment variables required during build or test.
    environment: NotRequired[dict[str, str]]

    #: Path or location of the build artifact/output.
    artifact_path: NotRequired[str | None]

    #: Entry point script, class, or binary for running the project.
    entry_point: NotRequired[str | None]

    #: A "back end" is tool that a "front end" (such as pip/build) would call to
    #: package the source distribution into the wheel format. build_backends would
    #: be a list of these that were used in building the wheel alongside their version.
    build_backends: NotRequired[dict[str, str]]


class BaseBuildSpec(ABC):
    """Abstract base class for build specification behavior and field resolution."""

    @abstractmethod
    def resolve_fields(self, purl: PackageURL) -> None:
        """
        Resolve fields that require special logic for a specific build ecosystem.

        Notes
        -----
        This method should be implemented by subclasses to handle
        logic specific to a given package ecosystem, such as Maven or PyPI.
        """
