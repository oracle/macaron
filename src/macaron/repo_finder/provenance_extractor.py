# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains methods for extracting repository and commit metadata from provenance files."""
import logging
import urllib.parse
from abc import ABC, abstractmethod

from packageurl import PackageURL
from pydriller import Git

from macaron.errors import ProvenanceError
from macaron.json_tools import JsonType, json_extract
from macaron.repo_finder.commit_finder import (
    AbstractPurlType,
    determine_abstract_purl_type,
    extract_commit_from_version,
)
from macaron.repo_finder.repo_finder import to_domain_from_known_purl_types
from macaron.slsa_analyzer.provenance.intoto import InTotoPayload, InTotoV1Payload, InTotoV01Payload
from macaron.slsa_analyzer.provenance.intoto.v01 import InTotoV01Statement
from macaron.slsa_analyzer.provenance.intoto.v1 import InTotoV1Statement

logger: logging.Logger = logging.getLogger(__name__)


SLSA_V01_DIGEST_SET_GIT_ALGORITHMS = ["sha1"]
SLSA_V02_DIGEST_SET_GIT_ALGORITHMS = ["sha1"]
SLSA_V1_DIGEST_SET_GIT_ALGORITHMS = ["sha1", "gitCommit"]


def extract_repo_and_commit_from_provenance(payload: InTotoPayload) -> tuple[str | None, str | None]:
    """Extract the repository and commit metadata from the passed provenance payload.

    Parameters
    ----------
    payload: InTotoPayload
        The payload to extract from.

    Returns
    -------
    tuple[str, str]
        The repository URL and commit hash if found, a pair of empty strings otherwise.

    Raises
    ------
    ProvenanceError
        If the extraction process fails for any reason.
    """
    predicate_type = payload.statement.get("predicateType")
    if isinstance(payload, InTotoV1Payload):
        if predicate_type == "https://slsa.dev/provenance/v1":
            return _extract_from_slsa_v1(payload)
    elif isinstance(payload, InTotoV01Payload):
        if predicate_type == "https://slsa.dev/provenance/v0.2":
            return _extract_from_slsa_v02(payload)
        if predicate_type == "https://slsa.dev/provenance/v0.1":
            return _extract_from_slsa_v01(payload)
        if predicate_type == "https://witness.testifysec.com/attestation-collection/v0.1":
            return _extract_from_witness_provenance(payload)

    msg = (
        f"Extraction from provenance not supported for versions: "
        f"predicate_type {predicate_type}, in-toto {str(type(payload))}."
    )
    logger.debug(msg)
    raise ProvenanceError(msg)


def _extract_from_slsa_v01(payload: InTotoV01Payload) -> tuple[str | None, str | None]:
    """Extract the repository and commit metadata from the slsa v01 provenance payload."""
    predicate: dict[str, JsonType] | None = payload.statement.get("predicate")
    if not predicate:
        return None, None

    # The repository URL and commit are stored inside an entry in the list of predicate -> materials.
    # In predicate -> recipe -> definedInMaterial we find the list index that points to the correct entry.
    list_index = json_extract(predicate, ["recipe", "definedInMaterial"], int)
    if not list_index:
        return None, None

    material = json_extract(predicate, ["materials", list_index], dict)
    if not material:
        logger.debug("Indexed material list entry is invalid.")
        return None, None

    repo = None
    uri = json_extract(material, ["uri"], str)
    if uri:
        repo = _clean_spdx(uri)

    digest_set = json_extract(material, ["digest"], dict)
    if not digest_set:
        return repo, None
    commit = _extract_commit_from_digest_set(digest_set, SLSA_V01_DIGEST_SET_GIT_ALGORITHMS)

    return repo, commit or None


def _extract_from_slsa_v02(payload: InTotoV01Payload) -> tuple[str | None, str | None]:
    """Extract the repository and commit metadata from the slsa v02 provenance payload."""
    predicate: dict[str, JsonType] | None = payload.statement.get("predicate")
    if not predicate:
        logger.debug("No predicate in payload statement.")
        return None, None

    # The repository URL and commit are stored within the predicate -> invocation -> configSource object.
    # See https://slsa.dev/spec/v0.2/provenance
    repo = None
    uri = json_extract(predicate, ["invocation", "configSource", "uri"], str)
    if uri:
        repo = _clean_spdx(uri)

    digest_set = json_extract(predicate, ["invocation", "configSource", "digest"], dict)
    if not digest_set:
        return repo, None
    commit = _extract_commit_from_digest_set(digest_set, SLSA_V02_DIGEST_SET_GIT_ALGORITHMS)

    return repo, commit or None


def _extract_from_slsa_v1(payload: InTotoV1Payload) -> tuple[str | None, str | None]:
    """Extract the repository and commit metadata from the slsa v1 provenance payload."""
    predicate: dict[str, JsonType] | None = payload.statement.get("predicate")
    if not predicate:
        logger.debug("No predicate in payload statement.")
        return None, None

    build_def = json_extract(predicate, ["buildDefinition"], dict)
    if not build_def:
        return None, None

    build_type = json_extract(build_def, ["buildType"], str)
    if not build_type:
        return None, None

    # Extract the repository URL.
    match build_type:
        case "https://slsa-framework.github.io/gcb-buildtypes/triggered-build/v1":
            repo = json_extract(build_def, ["externalParameters", "sourceToBuild", "repository"], str)
            if not repo:
                repo = json_extract(build_def, ["externalParameters", "configSource", "repository"], str)
        case "https://slsa-framework.github.io/github-actions-buildtypes/workflow/v1":
            repo = json_extract(build_def, ["externalParameters", "workflow", "repository"], str)
        case "https://github.com/oracle/macaron/tree/main/src/macaron/resources/provenance-buildtypes/oci/v1":
            repo = json_extract(build_def, ["externalParameters", "source"], str)
        case _:
            logger.debug("Unsupported build type for SLSA v1: %s", build_type)
            return None, None

    if not repo:
        logger.debug("Repo URL not found in SLSA v1 payload.")
        return None, None

    # Extract the commit hash.
    commit = None
    if build_type == "https://github.com/oracle/macaron/tree/main/src/macaron/resources/provenance-buildtypes/oci/v1":
        commit = json_extract(build_def, ["internalParameters", "buildEnvVar", "BLD_COMMIT_HASH"], str)
    else:
        deps = json_extract(build_def, ["resolvedDependencies"], list)
        if not deps:
            return repo, None
        for dep in deps:
            if not isinstance(dep, dict):
                continue
            uri = json_extract(dep, ["uri"], str)
            if not uri:
                continue
            url = _clean_spdx(uri)
            if url != repo:
                continue
            digest_set = json_extract(dep, ["digest"], dict)
            if not digest_set:
                continue
            commit = _extract_commit_from_digest_set(digest_set, SLSA_V1_DIGEST_SET_GIT_ALGORITHMS)

    return repo, commit or None


def _extract_from_witness_provenance(payload: InTotoV01Payload) -> tuple[str | None, str | None]:
    """Extract the repository and commit metadata from the witness provenance file found at the passed path.

    To successfully return the commit and repository URL, the payload must respectively contain a Git attestation, and
    either a GitHub or GitLab attestation.

    Parameters
    ----------
    payload: InTotoPayload
        The payload to extract from.

    Returns
    -------
    tuple[str, str]
        The repository URL and commit hash if found, a pair of empty strings otherwise.
    """
    predicate: dict[str, JsonType] | None = payload.statement.get("predicate")
    if not predicate:
        logger.debug("No predicate in payload statement.")
        return None, None

    attestations = json_extract(predicate, ["attestations"], list)
    if not attestations:
        return None, None

    repo = None
    commit = None
    for entry in attestations:
        if not isinstance(entry, dict):
            continue
        entry_type = entry.get("type")
        if not entry_type:
            continue
        if entry_type.startswith("https://witness.dev/attestations/git/"):
            commit = json_extract(entry, ["attestation", "commithash"], str)
        elif entry_type.startswith("https://witness.dev/attestations/gitlab/") or entry_type.startswith(
            "https://witness.dev/attestations/github/"
        ):
            repo = json_extract(entry, ["attestation", "projecturl"], str)

    return repo or None, commit or None


def _extract_commit_from_digest_set(digest_set: dict[str, JsonType], valid_algorithms: list[str]) -> str:
    """Extract the commit from the passed DigestSet.

    The DigestSet is an in-toto object that maps algorithm types to commit hashes (digests).
    """
    if len(digest_set.keys()) > 1:
        logger.debug("DigestSet contains multiple algorithms: %s", digest_set.keys())

    for key in digest_set:
        if key in valid_algorithms:
            value = digest_set.get(key)
            if isinstance(value, str):
                return value
    logger.debug("No valid digest in digest set: %s not in %s", digest_set.keys(), valid_algorithms)
    return ""


def _clean_spdx(uri: str) -> str:
    """Clean the passed SPDX URI and return the normalised URL it represents.

    A SPDX URI has the form: git+https://example.com@refs/heads/main
    """
    url, _, _ = uri.lstrip("git+").rpartition("@")
    return url


def check_if_input_repo_provenance_conflict(
    repo_path_input: str | None,
    provenance_repo_url: str | None,
) -> bool:
    """Test if the input repo and commit match the contents of the provenance.

    Parameters
    ----------
    repo_path_input: str | None
        The repo URL from input.
    provenance_repo_url: str | None
        The repo URL from provenance.

    Returns
    -------
    bool
        True if there is a conflict between the inputs, False otherwise, or if the comparison cannot be performed.
    """
    # Check the provenance repo against the input repo.
    if repo_path_input and provenance_repo_url and repo_path_input != provenance_repo_url:
        logger.debug(
            "The repository URL from input does not match what exists in the provenance. "
            "Input Repo: %s, Provenance Repo: %s.",
            repo_path_input,
            provenance_repo_url,
        )
        return True

    return False


def check_if_input_purl_provenance_conflict(
    git_obj: Git,
    repo_path_input: bool,
    digest_input: bool,
    provenance_repo_url: str | None,
    provenance_commit_digest: str | None,
    purl: PackageURL,
) -> bool:
    """Test if the input repository type PURL's repo and commit match the contents of the provenance.

    Parameters
    ----------
    git_obj: Git
        The Git object.
    repo_path_input: bool
        True if there is a repo as input.
    digest_input: str
        True if there is a commit as input.
    provenance_repo_url: str | None
        The repo url from provenance.
    provenance_commit_digest: str | None
        The commit digest from provenance.
    purl: PackageURL
        The input repository PURL.

    Returns
    -------
    bool
        True if there is a conflict between the inputs, False otherwise, or if the comparison cannot be performed.
    """
    if determine_abstract_purl_type(purl) != AbstractPurlType.REPOSITORY:
        return False

    # Check the PURL repo against the provenance.
    if not repo_path_input and provenance_repo_url:
        if not check_if_repository_purl_and_url_match(provenance_repo_url, purl):
            logger.debug(
                "The repo url passed via purl input does not match what exists in the provenance. "
                "Purl: %s, Provenance: %s.",
                purl,
                provenance_repo_url,
            )
            return True

    # Check the PURL commit against the provenance.
    if not digest_input and provenance_commit_digest and purl.version:
        purl_commit = extract_commit_from_version(git_obj, purl.version)
        if purl_commit and purl_commit != provenance_commit_digest:
            logger.debug(
                "The commit digest passed via purl input does not match what exists in the "
                "provenance. Purl Commit: %s, Provenance Commit: %s.",
                purl_commit,
                provenance_commit_digest,
            )
            return True

    return False


def check_if_repository_purl_and_url_match(url: str, repo_purl: PackageURL) -> bool:
    """Compare a repository PURL and URL for equality.

    Parameters
    ----------
    url: str
        The URL.
    repo_purl: PackageURL
        A PURL that is of the repository abstract type. E.g. GitHub.

    Returns
    -------
    bool
        True if the two inputs match in terms of URL netloc/domain and path.
    """
    expanded_purl_type = to_domain_from_known_purl_types(repo_purl.type)
    parsed_url = urllib.parse.urlparse(url)
    purl_path = repo_purl.name
    if repo_purl.namespace:
        purl_path = f"{repo_purl.namespace}/{purl_path}"
    # Note that the urllib method includes the "/" before path while the PURL method does not.
    return f"{parsed_url.hostname}{parsed_url.path}".lower() == f"{expanded_purl_type or repo_purl.type}/{purl_path}"


class ProvenanceBuildDefinition(ABC):
    """Abstract base class for representing provenance build definitions.

    This class serves as a blueprint for various types of build definitions
    in provenance data. It outlines the methods and properties that derived
    classes must implement to handle specific build definition types.
    """

    #: Determines the expected ``buildType`` field in the provenance predicate.
    expected_build_type: str

    @abstractmethod
    def get_build_invocation(self, statement: InTotoV01Statement | InTotoV1Statement) -> tuple[str | None, str | None]:
        """Retrieve the build invocation information from the given statement.

        This method is intended to be implemented by subclasses to extract
        specific invocation details from a provenance statement.

        Parameters
        ----------
        statement : InTotoV1Statement | InTotoV01Statement
            The provenance statement from which to extract the build invocation
            details. This statement contains the metadata about the build process
            and its associated artifacts.

        Returns
        -------
        tuple[str | None, str | None]
            A tuple containing two elements:
            - The first element is the build invocation entry point (e.g., workflow name), or None if not found.
            - The second element is the invocation URL or identifier (e.g., job URL), or None if not found.

        Raises
        ------
        NotImplementedError
            If the method is called directly without being overridden in a subclass.
        """


class SLSAGithubGenericBuildDefinitionV01(ProvenanceBuildDefinition):
    """Class representing the SLSA GitHub Generic Build Definition (v0.1).

    This class implements the abstract methods defined in `ProvenanceBuildDefinition`
    to extract build invocation details specific to the GitHub provenance generator's generic build type.
    """

    #: Determines the expected ``buildType`` field in the provenance predicate.
    expected_build_type = "https://github.com/slsa-framework/slsa-github-generator/generic@v1"

    def get_build_invocation(self, statement: InTotoV01Statement | InTotoV1Statement) -> tuple[str | None, str | None]:
        """Retrieve the build invocation information from the given statement.

        This method is intended to be implemented by subclasses to extract
        specific invocation details from a provenance statement.

        Parameters
        ----------
        statement : InTotoV1Statement | InTotoV01Statement
            The provenance statement from which to extract the build invocation
            details. This statement contains the metadata about the build process
            and its associated artifacts.

        Returns
        -------
        tuple[str | None, str | None]
            A tuple containing two elements:
            - The first element is the build invocation entry point (e.g., workflow name), or None if not found.
            - The second element is the invocation URL or identifier (e.g., job URL), or None if not found.
        """
        if statement["predicate"] is None:
            return None, None
        gha_workflow = json_extract(statement["predicate"], ["invocation", "configSource", "entryPoint"], str)
        gh_run_id = json_extract(statement["predicate"], ["invocation", "environment", "github_run_id"], str)
        repo_uri = json_extract(statement["predicate"], ["invocation", "configSource", "uri"], str)
        repo = None
        if repo_uri:
            repo = _clean_spdx(repo_uri)
        if repo is None:
            return gha_workflow, repo
        invocation_url = f"{repo}/" f"actions/runs/{gh_run_id}"
        return gha_workflow, invocation_url


class SLSAGithubActionsBuildDefinitionV1(ProvenanceBuildDefinition):
    """Class representing the SLSA GitHub Actions Build Definition (v1).

    This class implements the abstract methods from the `ProvenanceBuildDefinition`
    to extract build invocation details specific to the GitHub Actions build type.
    """

    #: Determines the expected ``buildType`` field in the provenance predicate.
    expected_build_type = "https://slsa-framework.github.io/github-actions-buildtypes/workflow/v1"

    def get_build_invocation(self, statement: InTotoV01Statement | InTotoV1Statement) -> tuple[str | None, str | None]:
        """Retrieve the build invocation information from the given statement.

        This method is intended to be implemented by subclasses to extract
        specific invocation details from a provenance statement.

        Parameters
        ----------
        statement : InTotoV1Statement | InTotoV01Statement
            The provenance statement from which to extract the build invocation
            details. This statement contains the metadata about the build process
            and its associated artifacts.

        Returns
        -------
        tuple[str | None, str | None]
            A tuple containing two elements:
            - The first element is the build invocation entry point (e.g., workflow name), or None if not found.
            - The second element is the invocation URL or identifier (e.g., job URL), or None if not found.
        """
        if statement["predicate"] is None:
            return None, None

        gha_workflow = json_extract(
            statement["predicate"], ["buildDefinition", "externalParameters", "workflow", "path"], str
        )
        invocation_url = json_extract(statement["predicate"], ["runDetails", "metadata", "invocationId"], str)
        return gha_workflow, invocation_url


class SLSAGCBBuildDefinitionV1(ProvenanceBuildDefinition):
    """Class representing the SLSA Google Cloud Build (GCB) Build Definition (v1).

    This class implements the abstract methods from `ProvenanceBuildDefinition`
    to extract build invocation details specific to the Google Cloud Build (GCB).
    """

    #: Determines the expected ``buildType`` field in the provenance predicate.
    expected_build_type = "https://slsa-framework.github.io/gcb-buildtypes/triggered-build/v1"

    def get_build_invocation(self, statement: InTotoV01Statement | InTotoV1Statement) -> tuple[str | None, str | None]:
        """Retrieve the build invocation information from the given statement.

        This method is intended to be implemented by subclasses to extract
        specific invocation details from a provenance statement.

        Parameters
        ----------
        statement : InTotoV1Statement | InTotoV01Statement
            The provenance statement from which to extract the build invocation
            details. This statement contains the metadata about the build process
            and its associated artifacts.

        Returns
        -------
        tuple[str | None, str | None]
            A tuple containing two elements:
            - The first element is the build invocation entry point (e.g., workflow name), or None if not found.
            - The second element is the invocation URL or identifier (e.g., job URL), or None if not found.
        """
        # TODO implement this method.
        return None, None


class SLSAOCIBuildDefinitionV1(ProvenanceBuildDefinition):
    """Class representing the SLSA Oracle Cloud Infrastructure (OCI) Build Definition (v1).

    This class implements the abstract methods from `ProvenanceBuildDefinition`
    to extract build invocation details specific to OCI builds.
    """

    #: Determines the expected ``buildType`` field in the provenance predicate.
    expected_build_type = (
        "https://github.com/oracle/macaron/tree/main/src/macaron/resources/provenance-buildtypes/oci/v1"
    )

    def get_build_invocation(self, statement: InTotoV01Statement | InTotoV1Statement) -> tuple[str | None, str | None]:
        """Retrieve the build invocation information from the given statement.

        This method is intended to be implemented by subclasses to extract
        specific invocation details from a provenance statement.

        Parameters
        ----------
        statement : InTotoV1Statement | InTotoV01Statement
            The provenance statement from which to extract the build invocation
            details. This statement contains the metadata about the build process
            and its associated artifacts.

        Returns
        -------
        tuple[str | None, str | None]
            A tuple containing two elements:
            - The first element is the build invocation entry point (e.g., workflow name), or None if not found.
            - The second element is the invocation URL or identifier (e.g., job URL), or None if not found.
        """
        # TODO implement this method.
        return None, None


class WitnessGitLabBuildDefinitionV01(ProvenanceBuildDefinition):
    """Class representing the Witness GitLab Build Definition (v0.1).

    This class implements the abstract methods from `ProvenanceBuildDefinition`
    to extract build invocation details specific to GitLab.
    """

    #: Determines the expected ``buildType`` field in the provenance predicate.
    expected_build_type = "https://witness.testifysec.com/attestation-collection/v0.1"

    #: Determines the expected ``attestations.type`` field in the Witness provenance predicate.
    expected_attestation_type = "https://witness.dev/attestations/gitlab/v0.1"

    def get_build_invocation(self, statement: InTotoV01Statement | InTotoV1Statement) -> tuple[str | None, str | None]:
        """Retrieve the build invocation information from the given statement.

        This method is intended to be implemented by subclasses to extract
        specific invocation details from a provenance statement.

        Parameters
        ----------
        statement : InTotoV1Statement | InTotoV01Statement
            The provenance statement from which to extract the build invocation
            details. This statement contains the metadata about the build process
            and its associated artifacts.

        Returns
        -------
        tuple[str | None, str | None]
            A tuple containing two elements:
            - The first element is the build invocation entry point (e.g., workflow name), or None if not found.
            - The second element is the invocation URL or identifier (e.g., job URL), or None if not found.
        """
        if statement["predicate"] is None:
            return None, None

        attestation_type = json_extract(statement["predicate"], ["attestations", "type"], str)
        if not self.expected_attestation_type == attestation_type:
            return None, None
        gl_workflow = json_extract(statement["predicate"], ["attestations", "attestation", "ciconfigpath"], str)
        gl_job_url = json_extract(statement["predicate"], ["attestations", "attestation", "joburl"], str)
        return gl_workflow, gl_job_url


class ProvenancePredicate:
    """Class providing utility methods for handling provenance predicates.

    This class contains static methods for extracting information from predicates in
    provenance statements related to various build definitions. It serves as a helper
    for identifying build types and finding the appropriate build definitions based on the extracted data.
    """

    @staticmethod
    def get_build_type(statement: InTotoV1Statement | InTotoV01Statement) -> str | None:
        """Extract the build type from the provided provenance statement.

        Parameters
        ----------
        statement : InTotoV1Statement | InTotoV01Statement
            The provenance statement from which to extract the build type.

        Returns
        -------
        str | None
            The build type if found; otherwise, None.
        """
        if statement["predicate"] is None:
            return None

        if build_type := json_extract(statement["predicate"], ["buildType"], str):
            return build_type

        return json_extract(statement["predicate"], ["buildDefinition", "buildType"], str)

    @staticmethod
    def find_build_def(statement: InTotoV01Statement | InTotoV1Statement) -> ProvenanceBuildDefinition:
        """Find the appropriate build definition class based on the extracted build type.

        This method checks the provided provenance statement for its build type
        and returns the corresponding `ProvenanceBuildDefinition` subclass.

        Parameters
        ----------
        statement : InTotoV01Statement | InTotoV1Statement
            The provenance statement containing the build type information.

        Returns
        -------
        ProvenanceBuildDefinition
            An instance of the appropriate build definition class that matches the
            extracted build type.

        Raises
        ------
        ProvenanceError
            Raised when the build definition cannot be found in the provenance statement.
        """
        build_type = ProvenancePredicate.get_build_type(statement)
        build_defs: list[ProvenanceBuildDefinition] = [
            SLSAGithubGenericBuildDefinitionV01(),
            SLSAGithubActionsBuildDefinitionV1(),
            SLSAGCBBuildDefinitionV1(),
            SLSAOCIBuildDefinitionV1(),
            WitnessGitLabBuildDefinitionV01(),
        ]

        for build_def in build_defs:
            if build_def.expected_build_type == build_type:
                return build_def

        raise ProvenanceError("Unable to find build definition in the provenance statement.")
