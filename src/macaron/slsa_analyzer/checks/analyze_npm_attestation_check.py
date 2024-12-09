# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the implementation of the VCS check."""


import logging

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from macaron.database.table_definitions import (
    BuildDefinition,
    CheckFacts,
    ExternalParameters,
    InternalParameters,
    Predicate,
    ProvenanceFacts,
    ProvenanceSubjectRaw,
    Statement,
    SubjectDigest,
    Workflow,
)
from macaron.json_tools import json_extract
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.base_check import BaseCheck, CheckResultType
from macaron.slsa_analyzer.checks.check_result import CheckResultData, Confidence
from macaron.slsa_analyzer.registry import registry
from macaron.slsa_analyzer.slsa_req import ReqName

logger: logging.Logger = logging.getLogger(__name__)


class NPMAttestationFacts(CheckFacts):
    """The ORM mapping for justifications in the npm attestation analysis check."""

    __tablename__ = "_npm_attestation_check"

    #: The primary key.
    id: Mapped[int] = mapped_column(ForeignKey("_check_facts.id"), primary_key=True)  # noqa: A003

    __mapper_args__ = {
        "polymorphic_identity": "_npm_attestation_check",
    }


class NPMAttestationCheck(BaseCheck):
    """This Check extracts attestation fields to be used by the policy engine."""

    def __init__(self) -> None:
        """Initialize instance."""
        check_id = "mcn_npm_attestation_validation_1"
        description = "Extract attestation fields to be used by the policy engine."
        depends_on: list[tuple[str, CheckResultType]] = []
        eval_reqs = [ReqName.PROV_AVAILABLE]
        super().__init__(check_id=check_id, description=description, depends_on=depends_on, eval_reqs=eval_reqs)

    def run_check(self, ctx: AnalyzeContext) -> CheckResultData:
        """Implement the check in this method.

        Parameters
        ----------
        ctx : AnalyzeContext
            The object containing processed data for the target repo.

        Returns
        -------
        CheckResultData
            The result of the check.
        """
        payload = ctx.dynamic_data["provenance"]
        if not payload or ctx.dynamic_data["is_inferred_prov"]:
            logger.debug("Unable to find a provenance for %s.", ctx.component.purl)
            return CheckResultData(result_tables=[], result_type=CheckResultType.FAILED)

        # Extract facts from the attestation to store in the database.
        prov_facts = ProvenanceFacts()
        stmt = payload.statement
        if stmt["predicate"] is None:
            logger.debug("Unable to validate provenance content for %s.", ctx.component.purl)
            return CheckResultData(result_tables=[], result_type=CheckResultType.FAILED)

        workflow_section = json_extract(stmt["predicate"], ["buildDefinition", "externalParameters", "workflow"], dict)

        if workflow_section is None:
            logger.debug("Unable to validate provenance content for %s.", ctx.component.purl)
            return CheckResultData(result_tables=[], result_type=CheckResultType.FAILED)

        ref = json_extract(workflow_section, ["ref"], str)
        repository = json_extract(workflow_section, ["repository"], str)
        path = json_extract(workflow_section, ["path"], str)

        if any(param is None for param in (ref, repository, path)):
            logger.debug("Unable to validate provenance content for %s.", ctx.component.purl)
            return CheckResultData(result_tables=[], result_type=CheckResultType.FAILED)

        workflow = Workflow(ref=ref, repository=repository, path=path)

        external_parameters = ExternalParameters(workflow=workflow)

        internal_params_gh = json_extract(stmt["predicate"], ["buildDefinition", "internalParameters", "github"], dict)

        if internal_params_gh is None:
            logger.debug("Unable to validate provenance content for %s.", ctx.component.purl)
            return CheckResultData(result_tables=[], result_type=CheckResultType.FAILED)

        event = json_extract(internal_params_gh, ["event_name"], str)
        repo_id = json_extract(internal_params_gh, ["repository_id"], str)
        repo_owner_id = json_extract(internal_params_gh, ["repository_owner_id"], str)

        if any(param is None for param in (event, repo_id, repo_owner_id)):
            logger.debug("Unable to validate provenance content for %s.", ctx.component.purl)
            return CheckResultData(result_tables=[], result_type=CheckResultType.FAILED)

        internal_parameters = InternalParameters(
            github_event_name=event, github_repository_id=repo_id, github_repository_owner_id=repo_owner_id
        )

        build_type = json_extract(stmt["predicate"], ["buildDefinition", "buildType"], str)
        if build_type != "https://slsa-framework.github.io/github-actions-buildtypes/workflow/v1":
            logger.debug("Unable to validate provenance content for %s.", ctx.component.purl)
            return CheckResultData(result_tables=[], result_type=CheckResultType.FAILED)

        predicate = Predicate(
            build_definition=BuildDefinition(
                build_type=build_type,
                external_parameters=external_parameters,
                internal_parameters=internal_parameters,
            )
        )

        subjects = []
        for sub in stmt["subject"]:
            if (name := sub["name"]) and (sha512 := json_extract(dict(sub), ["digest", "sha512"], str)):
                subjects.append(ProvenanceSubjectRaw(name=name, digest=SubjectDigest(sha512=sha512)))

        if not subjects:
            logger.debug("Unable to validate provenance content for %s.", ctx.component.purl)
            return CheckResultData(result_tables=[], result_type=CheckResultType.FAILED)

        prov_facts.statement = Statement(
            _type=stmt["_type"], predicate_type=stmt["predicateType"], subject=subjects, predicate=predicate
        )

        prov_facts.provenance_json = payload.statement["predicate"] or {}

        # Add the provenance facts to the software component provenance to persist the data in the database.
        prov_facts.component = ctx.component

        return CheckResultData(
            result_tables=[NPMAttestationFacts(confidence=Confidence.HIGH)],
            result_type=CheckResultType.PASSED,
        )


registry.register(NPMAttestationCheck())
