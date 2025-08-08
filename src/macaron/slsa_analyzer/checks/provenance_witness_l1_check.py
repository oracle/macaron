# Copyright (c) 2023 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This check examines a witness provenance (https://github.com/testifysec/witness)."""

import logging

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from macaron.database.table_definitions import CheckFacts
from macaron.errors import MacaronError
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import CheckResultData, CheckResultType, Confidence, JustificationType
from macaron.slsa_analyzer.package_registry import JFrogMavenRegistry
from macaron.slsa_analyzer.package_registry.jfrog_maven_registry import JFrogMavenAsset
from macaron.slsa_analyzer.provenance.intoto.v01 import InTotoV01Subject
from macaron.slsa_analyzer.provenance.witness import (
    extract_build_artifacts_from_witness_subjects,
    is_witness_provenance_payload,
    load_witness_verifier_config,
)
from macaron.slsa_analyzer.registry import registry
from macaron.slsa_analyzer.slsa_req import ReqName
from macaron.slsa_analyzer.specs.package_registry_spec import PackageRegistryInfo

logger: logging.Logger = logging.getLogger(__name__)


class WitnessProvenanceException(MacaronError):
    """When there is an error while processing a Witness provenance."""


class WitnessProvenanceAvailableFacts(CheckFacts):
    """The ORM mapping for justifications in provenance l3 check."""

    __tablename__ = "_provenance_witness_l1_check"

    #: The primary key.
    id: Mapped[int] = mapped_column(ForeignKey("_check_facts.id"), primary_key=True)  # noqa: A003

    #: The provenance asset name.
    provenance_name: Mapped[str] = mapped_column(String, nullable=False, info={"justification": JustificationType.TEXT})

    #: The URL for the provenance asset.
    provenance_url: Mapped[str] = mapped_column(String, nullable=True, info={"justification": JustificationType.HREF})

    #: The URL for the artifact asset.
    artifact_url: Mapped[str] = mapped_column(String, nullable=True, info={"justification": JustificationType.HREF})

    __mapper_args__ = {
        "polymorphic_identity": "_provenance_witness_l1_check",
    }


def verify_artifact_assets(
    artifact_assets: list[JFrogMavenAsset],
    subjects: list[InTotoV01Subject],
) -> bool:
    """Verify artifact assets against subjects in the witness provenance payload.

    Parameters
    ----------
    artifact_assets : list[JFrogMavenAsset]
        List of artifact assets to verify.
    subjects : list[InTotoV01Subject]
        List of subjects extracted from the in the witness provenance.

    Returns
    -------
    bool
        True if verification succeeds and False otherwise.

    Raises
    ------
    WitnessProvenanceException
        If a subject is not a file attested by the Witness product attestor.
    """
    # A look-up table to verify:
    # 1. if the name of the artifact appears in any subject of the witness provenance, then
    # 2. if the digest of the artifact could be found.
    look_up: dict[str, dict[str, InTotoV01Subject]] = {}

    for subject in subjects:
        if not subject["name"].startswith("https://witness.dev/attestations/product/v0.1/file:"):
            raise WitnessProvenanceException(
                f"{subject['name']} is not a file attested by the Witness product attestor."
            )

        # Get the artifact name, which should be the last part of the artifact subject value.
        _, _, artifact_filename = subject["name"].rpartition("/")
        if artifact_filename not in look_up:
            look_up[artifact_filename] = {}
        look_up[artifact_filename][subject["digest"]["sha256"]] = subject

    for asset in artifact_assets:
        if asset.name not in look_up:
            message = f"Could not find subject for asset {asset.name} in the provenance."
            logger.info(message)
            return False

        if asset.sha256_digest not in look_up[asset.name]:
            message = f"Failed to verify the SHA256 digest of the asset '{asset.name}' in the provenance."
            logger.info(message)
            return False

        subject = look_up[asset.name][asset.sha256_digest]

        logger.info(
            "Successfully verified asset '%s' against the subject '%s' in the provenance.",
            asset.name,
            subject["name"],
        )

    return True


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

        result_tables: list[CheckFacts] = []

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
                        subjects = extract_build_artifacts_from_witness_subjects(provenance.payload)

                        try:
                            verify_status = verify_artifact_assets(artifact_assets, subjects)
                        except WitnessProvenanceException as err:
                            logger.error(err)
                            return CheckResultData(
                                result_tables=result_tables,
                                result_type=CheckResultType.UNKNOWN,
                            )

                        if not verify_status:
                            return CheckResultData(
                                result_tables=result_tables,
                                result_type=CheckResultType.FAILED,
                            )

                        verified_artifact_assets.extend(artifact_assets)
                        verified_provenances.append(provenance)
                        for artifact in verified_artifact_assets:
                            result_tables.append(
                                WitnessProvenanceAvailableFacts(
                                    provenance_name=provenance.asset.name,
                                    provenance_url=provenance.asset.url,
                                    artifact_url=artifact.url,
                                    confidence=Confidence.HIGH,
                                )
                            )

        # When this check passes, it means: "the project produces verifiable witness provenances".
        # Therefore, If Macaron cannot discover any witness provenance, we "fail" the check.
        if len(verified_provenances) > 0:
            return CheckResultData(result_tables=result_tables, result_type=CheckResultType.PASSED)

        return CheckResultData(
            result_tables=result_tables,
            result_type=CheckResultType.FAILED,
        )


registry.register(ProvenanceWitnessL1Check())
