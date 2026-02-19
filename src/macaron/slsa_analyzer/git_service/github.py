# Copyright (c) 2022 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the spec for the GitHub service."""
import logging

from pydriller.git import Git

from macaron.config.global_config import global_config
from macaron.errors import ConfigurationError, RepoCheckOutError
from macaron.json_tools import json_extract
from macaron.provenance import ProvenanceAsset
from macaron.slsa_analyzer import git_url
from macaron.slsa_analyzer.git_service.api_client import GhAPIClient, get_default_gh_client
from macaron.slsa_analyzer.git_service.base_git_service import BaseGitService
from macaron.slsa_analyzer.provenance.intoto import ValidateInTotoPayloadError, validate_intoto_payload
from macaron.slsa_analyzer.provenance.loader import decode_provenance

logger: logging.Logger = logging.getLogger(__name__)


class GitHub(BaseGitService):
    """This class contains the spec of the GitHub service."""

    def __init__(self) -> None:
        """Initialize instance."""
        super().__init__("github")
        self._api_client: GhAPIClient | None = None

    def load_defaults(self) -> None:
        """Load the values for this git service from the ini configuration and environment variables.

        Raises
        ------
        ConfigurationError
            If there is an error loading the configuration.
        """
        try:
            self.hostname = self.load_hostname(section_name="git_service.github")
        except ConfigurationError as error:
            raise error

    @property
    def api_client(self) -> GhAPIClient:
        """Return the API client used for querying GitHub API.

        This API is used to check if a GitHub repo can be cloned.
        """
        if not self._api_client:
            self._api_client = get_default_gh_client(global_config.gh_token)

        return self._api_client

    def clone_repo(self, clone_dir: str, url: str) -> None:
        """Clone a GitHub repository.

        clone_dir: str
            The name of the directory to clone into.
            This is equivalent to the <directory> argument of ``git clone``.
            The url to the repository.

        Raises
        ------
        CloneError
            If there is an error cloning the repo.
        """
        git_url.clone_remote_repo(clone_dir, url)

    def check_out_repo(self, git_obj: Git, branch: str, digest: str, offline_mode: bool) -> Git:
        """Checkout the branch and commit specified by the user of a repository.

        Parameters
        ----------
        git_obj : Git
            The Git object for the repository to check out.
        branch : str
            The branch to check out.
        digest : str
            The sha of the commit to check out.
        offline_mode: bool
            If true, no fetching is performed.

        Returns
        -------
        Git
            The same Git object from the input.

        Raises
        ------
        RepoError
            If there is error while checkout the specific branch and digest.
        """
        if not git_url.check_out_repo_target(git_obj, branch, digest, offline_mode):
            raise RepoCheckOutError(
                f"Failed to check out branch {branch} and commit {digest} for repo {git_obj.project_name}."
            )

        return git_obj

    def get_attestation(self, repository_name: str, artifact_hash: str) -> ProvenanceAsset | None:
        """Get the GitHub attestation associated with the given PURL, or None if it cannot be found.

        The schema of GitHub attestation can be found on the API page:
        https://docs.github.com/en/rest/repos/repos?apiVersion=2022-11-28#list-attestations

        Parameters
        ----------
        repository_name: str
            The name of the repository to retrieve attestation from.
        artifact_hash: str
            The hash of the related artifact.

        Returns
        -------
        ProvenanceAsset | None
            The provenance asset, if found.
        """
        attestation_url, git_attestation_dict = self.api_client.get_attestation(repository_name, artifact_hash)

        if not attestation_url or not git_attestation_dict:
            return None

        git_attestation_list = json_extract(git_attestation_dict, ["attestations"], list)
        if not git_attestation_list:
            return None

        payload = decode_provenance(git_attestation_list[0])
        validated_payload = None
        try:
            validated_payload = validate_intoto_payload(payload)
        except ValidateInTotoPayloadError as error:
            logger.debug("Invalid attestation payload: %s", error)
            return None
        if not validated_payload:
            return None

        return ProvenanceAsset(validated_payload, artifact_hash, attestation_url)
