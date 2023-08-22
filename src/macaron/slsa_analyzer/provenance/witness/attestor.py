# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Witness Attestors."""

from typing import Protocol

from macaron.slsa_analyzer.provenance.intoto import InTotoPayload, InTotoV01Payload


class RepoAttestor(Protocol):
    """Interface for witness attestors that record repo URLs."""

    def extract_repo_url(self, payload: InTotoPayload) -> str | None:
        """Extract the repo URL from a witness provenance payload.

        Parameters
        ----------
        payload : InTotoStatement
            The witness provenance payload.

        Returns
        -------
        str | None
            The repo URL, or ``None`` if it cannot be located in the provenance payload.
        """


class GitLabWitnessAttestor:
    """Witness attestor for GitLab.

    In the payload of a witness provenance, each subject corresponds to an attestor.
    Docs: https://github.com/testifysec/witness/blob/main/docs/attestors/gitlab.md
    """

    def extract_repo_url(self, payload: InTotoPayload) -> str | None:
        """Extract the repo URL from a witness provenance payload.

        Parameters
        ----------
        payload : InTotoStatement
            The witness provenance payload.

        Returns
        -------
        str | None
            The repo URL, or ``None`` if it cannot be located in the provenance payload.
        """
        if isinstance(payload, InTotoV01Payload):
            return self.extract_repo_url_intoto_v01(payload)
        return None

    def extract_repo_url_intoto_v01(self, payload: InTotoV01Payload) -> str | None:
        """Extract the repo URL from a witness provenance payload following in-toto v0.1 schema.

        Note: the current implementation inspects the ``predicate`` field of the payload
        to locate the repo URL. The schema of this field is currently undocumented by witness.

        Parameters
        ----------
        payload : InTotoV01Statement
            The in-toto v0.1 payload.

        Returns
        -------
        str | None
            The repo URL, or ``None`` if it cannot be located in the provenance payload.
        """
        if payload.statement["predicate"] is None:
            return None

        attestations = payload.statement["predicate"].get("attestations", [])

        if attestations is None or not isinstance(attestations, list):
            return None

        for attestation_entry in attestations:
            if not isinstance(attestation_entry, dict):
                return None

            attestation_type = attestation_entry.get("type")
            if attestation_type != "https://witness.dev/attestations/gitlab/v0.1":
                continue

            attestation = attestation_entry.get("attestation")
            if attestation is None or not isinstance(attestation, dict):
                return None

            project_url = attestation.get("projecturl")
            if project_url is None or not isinstance(project_url, str):
                return None

            return project_url

        return None
