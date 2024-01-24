# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This check examines a witness provenance (https://github.com/testifysec/witness)."""

import logging

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from macaron.database.database_manager import ORMBase
from macaron.database.table_definitions import CheckFacts
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import CheckResultData, CheckResultType, Justification, ResultTables
from macaron.slsa_analyzer.package_registry import JFrogMavenRegistry
from macaron.slsa_analyzer.package_registry.jfrog_maven_registry import JFrogMavenAsset
from macaron.slsa_analyzer.provenance.witness import (
    WitnessProvenanceSubject,
    extract_witness_provenance_subjects,
    is_witness_provenance_payload,
    load_witness_verifier_config,
)
from macaron.slsa_analyzer.registry import registry
from macaron.slsa_analyzer.slsa_req import ReqName
from macaron.slsa_analyzer.specs.package_registry_spec import PackageRegistryInfo

logger: logging.Logger = logging.getLogger(__name__)


def verify_artifact_assets(
    artifact_assets: list[JFrogMavenAsset],
    subjects: set[WitnessProvenanceSubject],
) -> list[str]:
    """Verify artifact assets against subjects in the witness provenance payload.

    Parameters
    ----------
    artifact_assets : list[JFrogMavenAsset]
        List of artifact assets to verify.
    subjects : list[WitnessProvenanceSubject]
        List of subjects extracted from the in the witness provenance.

    Returns
    -------
    list[str]
        A list of justifications if the verification fails.
        If the verification is successful, an empty list is returned.
    """
    fail_justifications = []

    # A look-up table to verify:
    # 1. if the name of the artifact appears in any subject of the witness provenance, then
    # 2. if the digest of the artifact could be found
    look_up: dict[str, dict[str, WitnessProvenanceSubject]] = {}

    for subject in subjects:
        if subject.artifact_name not in look_up:
            look_up[subject.artifact_name] = {}
        look_up[subject.artifact_name][subject.sha256_digest] = subject

    for asset in artifact_assets:
        if asset.name not in look_up:
            message = f"Could not find subject with name {asset.name} in the provenance."
            logger.info(message)
            fail_justifications.append(message)

        if asset.sha256_digest not in look_up[asset.name]:
            message = f"Failed to verify the SHA256 digest of the asset '{asset.name}' in the provenance."
            logger.info(message)
            fail_justifications.append(message)

        subject = look_up[asset.name][asset.sha256_digest]

        logger.info(
            "Successfully verified asset '%s' against the subject '%s' in the provenance.",
            asset.name,
            subject.subject_name,
        )

    return fail_justifications


class ProvenanceWitnessL1Table(CheckFacts, ORMBase):
    """Result table for provenance l3 check."""

    __tablename__ = "_provenance_witness_l1_check"

    # The primary key.
    id: Mapped[int] = mapped_column(ForeignKey("_check_facts.id"), primary_key=True)  # noqa: A003

    __mapper_args__ = {
        "polymorphic_identity": "_provenance_witness_l1_check",
    }


class ProvenanceWitnessL1Check(BaseCheck):
    """This check examines a Witness provenance (https://github.com/testifysec/witness).

    At the moment, we are only checking the actual digests of the artifacts
    against the digests in the provenance.
    """

    def __init__(self) -> None:
        """Initialize a check instance."""
        check_id = "mcn_provenance_witness_level_one_1"
        description = "Check whether the target has a level-1 witness provenance."
        depends_on: list[tuple[str, CheckResultType]] = [
            ("mcn_provenance_available_1", CheckResultType.PASSED),
        ]
        eval_reqs = [
            ReqName.PROV_AVAILABLE,
            ReqName.PROV_CONT_BUILD_INS,
            ReqName.PROV_CONT_ARTI,
            ReqName.PROV_CONT_BUILDER,
        ]
        super().__init__(
            check_id=check_id,
            description=description,
            depends_on=depends_on,
            eval_reqs=eval_reqs,
            result_on_skip=CheckResultType.FAILED,
        )

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
        witness_verifier_config = load_witness_verifier_config()
        verified_provenances = []
        verified_artifact_assets = []

        justification: Justification = []
        result_tables: ResultTables = []

        for package_registry_info_entry in ctx.dynamic_data["package_registries"]:
            match package_registry_info_entry:
                case PackageRegistryInfo(
                    package_registry=JFrogMavenRegistry() as jfrog_registry,
                    provenances=provenances,
                ):
                    for provenance in provenances:
                        if not isinstance(provenance.asset, JFrogMavenAsset):
                            continue
                        if not is_witness_provenance_payload(
                            payload=provenance.payload,
                            predicate_types=witness_verifier_config.predicate_types,
                        ):
                            continue

                        artifact_assets = jfrog_registry.fetch_assets(
                            group_id=provenance.asset.group_id,
                            artifact_id=provenance.asset.artifact_id,
                            version=provenance.asset.version,
                            extensions=witness_verifier_config.artifact_extensions,
                        )
                        subjects = extract_witness_provenance_subjects(provenance.payload)
                        failure_justification = verify_artifact_assets(artifact_assets, subjects)

                        if failure_justification:
                            justification.extend(failure_justification)
                            return CheckResultData(
                                justification=justification,
                                result_tables=result_tables,
                                result_type=CheckResultType.FAILED,
                            )

                        verified_artifact_assets.extend(artifact_assets)
                        verified_provenances.append(provenance)

        # When this check passes, it means: "the project produces verifiable witness provenances".
        # Therefore, If Macaron cannot discover any witness provenance, we "fail" the check.
        if len(verified_provenances) > 0:
            justification.append("Successfully verified the following artifacts:")
            for asset in verified_artifact_assets:
                justification.append(f"* {asset.url}")
            result_tables.append(ProvenanceWitnessL1Table())
            return CheckResultData(
                justification=justification, result_tables=result_tables, result_type=CheckResultType.PASSED
            )

        justification.append("Failed to discover any witness provenance.")
        return CheckResultData(
            justification=justification, result_tables=result_tables, result_type=CheckResultType.FAILED
        )


registry.register(ProvenanceWitnessL1Check())
