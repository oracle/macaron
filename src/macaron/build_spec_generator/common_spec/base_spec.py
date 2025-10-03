from abc import ABC, abstractmethod
from typing import NotRequired, Required, TypedDict

class BaseBuildSpecDict(TypedDict):
    """
    Base build specification supporting multiple languages, build tools,
    and additional metadata for enhanced traceability.

    Parameters
    ----------
    ecosystem : str
        The package ecosystem.
    purl : str
        The package identifier.
    language : str
        The programming language, e.g., 'java', 'python', 'javascript'.
    build_tool : str
        The build tool or package manager, e.g., 'maven', 'gradle', 'pip', 'poetry', 'npm', 'yarn'.
    macaron_version : str
        The version of Macaron used for generating the spec.
    group_id : str, optional
        The group identifier for the project/component.
    artifact_id : str
        The artifact identifier for the project/component.
    version : str
        The version of the package or component.
    git_repo : str
        The remote path or URL of the git repository.
    git_tag : str
        The commit SHA or tag in the VCS repository.
    newline : str, optional
        The type of line endings used (e.g., 'lf', 'crlf').
    language_version : str, optional
        The version of the programming language or runtime, e.g., '11' for JDK, '3.11' for Python.
    dependencies : list of str, optional
        List of release dependencies.
    build_dependencies : list of str, optional
        List of build dependencies, which includes tests.
    build_commands : list of str, optional
        List of shell commands to build the project.
    test_commands : list of str, optional
        List of shell commands to test the project.
    environment : dict of str to str, optional
        Environment variables required during build or test.
    artifact_path : str or None, optional
        Path or location of the build artifact/output.
    entry_point : str or None, optional
        Entry point script, class, or binary for running the project.
    """
    ecosystem: Required[str]
    purl: Required[str]
    language: Required[str]
    build_tool: Required[str]
    macaron_version: Required[str]
    group_id: NotRequired[str]
    artifact_id: Required[str]
    version: Required[str]
    git_repo: Required[str]
    git_tag: Required[str]
    newline: NotRequired[str]    
    language_version: NotRequired[str]
    dependencies: NotRequired[list[str]]
    build_dependencies: NotRequired[list[str]]
    build_commands: NotRequired[list[str]]
    test_commands: NotRequired[list[str]]
    environment: NotRequired[dict[str, str]]
    artifact_path: NotRequired[str | None]
    entry_point: NotRequired[str | None]

class BaseBuildSpec(ABC):
    """
    Abstract base class for build specification behavior and field resolution.
    """

    @abstractmethod
    def resolve_fields(self) -> None:
        """
        Resolve fields that require special logic for a specific build ecosystem.

        Notes
        -----
        This method should be implemented by subclasses to handle
        logic specific to a given package ecosystem, such as Maven or PyPI.
        """
        pass