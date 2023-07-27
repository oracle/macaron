# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This check examines a witness provenance (https://github.com/testifysec/witness)."""

import logging
from typing import NamedTuple, TypeGuard

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from macaron.config.defaults import defaults
from macaron.database.database_manager import ORMBase
from macaron.database.table_definitions import CheckFacts
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import CheckResult, CheckResultType
from macaron.slsa_analyzer.package_registry import JFrogMavenAsset, JFrogMavenRegistry
from macaron.slsa_analyzer.registry import registry
from macaron.slsa_analyzer.slsa_req import ReqName
from macaron.slsa_analyzer.specs.package_registry_data import PackageRegistryData
from macaron.util import JsonType

logger: logging.Logger = logging.getLogger(__name__)


class WitnessProvenanceSubject(NamedTuple):
    """A helper class to store elements of the ``subject`` list in the provenances.

    Attributes
    ----------
    subject_name : str
        The ``"name"`` field of each ``subject``.
    sha256 : str
        The SHA256 digest of the corresponding asset to the subject.
    """

    subject_name: str
    sha256_digest: str

    @property
    def artifact_name(self) -> str:
        """Get the artifact name, which should be the last part of the subject."""
        _, _, artifact_name = self.subject_name.rpartition("/")
        return artifact_name


class WitnessVerifierConfig(NamedTuple):
    """Configuration for verifying witness provenances.

    Attributes
    ----------
    predicate_types: set[str]
        A provenance payload is recognized by Macaron to be a witness provenance if its
        ``predicateType`` value is present within this set.
    artifact_extensions : set[str]
        A set of artifact extensions to verify. Artifacts having an extension outside this list
        are not verified.
    """

    predicate_types: set[str]
    artifact_extensions: set[str]


def load_witness_verifier_config() -> WitnessVerifierConfig:
    """Load configuration for verifying witness provenances.

    Returns
    -------
    WitnessVerifierConfig
        Configuration for verifying witness provenance.
    """
    return WitnessVerifierConfig(
        predicate_types=set(
            defaults.get_list(
                "provenance.witness",
                "predicate_types",
                fallback=[],
            )
        ),
        artifact_extensions=set(
            defaults.get_list(
                "provenance.witness",
                "artifact_extensions",
                fallback=[],
            )
        ),
    )


def is_witness_provenance_payload(
    payload: JsonType,
    predicate_types: set[str],
) -> TypeGuard[dict[str, JsonType]]:
    """Check if the given provenance payload is a witness provenance payload.

    Parameters
    ----------
    payload : JsonType
        The provenance payload.
    predicate_types : set[str]
        The allowed values for the ``"predicateType"`` field of the provenance payload.

    Returns
    -------
    TypeGuard[dict[str, JsonType]]
        ``True`` if the payload is a witness provenance payload, ``False`` otherwise.
        If ``True`` is returned, the type of ``payload`` is narrowed to be a JSON object,
        or ``dict[str, JsonType]`` in Python type.
    """
    if not isinstance(payload, dict):
        logger.debug("Malformed provenance payload: expected a JSON object.")
        return False
    predicate_type = payload.get("predicateType")
    if predicate_type is None:
        logger.debug("Malformed provenance payload: missing the 'predicateType' field.")
        return False
    return predicate_type in predicate_types


def extract_witness_provenance_subjects(witness_payload: dict[str, JsonType]) -> list[WitnessProvenanceSubject]:
    """Read the ``"subjects"`` field of the provenance to obtain the hash digests of each subject.

    Parameters
    ----------
    witness_payload : dict[str, JsonType]
        The witness provenance payload.
    extensions : list[str]
        The allowed extensions of the subjects.
        All subjects with names not ending in these extensions are ignored.

    Returns
    -------
    dict[str, str]
        A dictionary in which each key is a subject name and each value is the corresponding SHA256 digest.
    """
    subjects = witness_payload.get("subject")
    if subjects is None:
        logger.debug("Could not find the 'subject' field in the witness provenance payload.")
        return []

    if not isinstance(subjects, list):
        logger.debug(
            "Got unexpected value type for the 'subject' field in the witness provenance payload. Expected a list."
        )
        return []

    subject_digests = []

    for subject in subjects:
        if not isinstance(subject, dict):
            logger.debug("Got unexpected value type for an element in the 'subject' list. Expected a JSON object.")
            continue

        name = subject.get("name")
        if not name or not isinstance(name, str):
            continue

        digest = subject.get("digest")
        if not digest or not isinstance(digest, dict):
            continue
        sha256 = digest.get("sha256")
        if not sha256 or not isinstance(sha256, str):
            continue

        subject_digests.append(
            WitnessProvenanceSubject(
                subject_name=name,
                sha256_digest=sha256,
            )
        )

    return subject_digests


def verify_artifact_assets(
    artifact_assets: list[JFrogMavenAsset],
    subjects: list[WitnessProvenanceSubject],
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
    """Result table for provenenance l3 check."""

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

    def run_check(self, ctx: AnalyzeContext, check_result: CheckResult) -> CheckResultType:
        """Implement the check in this method.

        Parameters
        ----------
        ctx : AnalyzeContext
            The object containing processed data for the target repo.
        check_result : CheckResult
            The object containing result data of a check.

        Returns
        -------
        CheckResultType
            The result type of the check (e.g. PASSED).
        """
        witness_verifier_config = load_witness_verifier_config()
        verified_artifact_assets = []

        for package_registry_data_entry in ctx.dynamic_data["package_registries"]:
            match package_registry_data_entry:
                case PackageRegistryData(
                    package_registry=JFrogMavenRegistry() as jfrog_registry,
                    provenances=provenances,
                    provenance_assets=provenance_assets,
                ):
                    for provenance_url, payload in provenances.items():
                        provenance_asset = next(
                            (asset for asset in provenance_assets if asset.url == provenance_url),
                            None,
                        )
                        if not provenance_asset or not isinstance(provenance_asset, JFrogMavenAsset):
                            continue
                        if not is_witness_provenance_payload(
                            payload=payload,
                            predicate_types=witness_verifier_config.predicate_types,
                        ):
                            continue

                        artifact_assets = jfrog_registry.fetch_assets(
                            group_id=provenance_asset.group_id,
                            artifact_id=provenance_asset.artifact_id,
                            version=provenance_asset.version,
                            extensions=witness_verifier_config.artifact_extensions,
                        )
                        subjects = extract_witness_provenance_subjects(payload)
                        failure_justification = verify_artifact_assets(artifact_assets, subjects)

                        if failure_justification:
                            check_result["justification"].extend(failure_justification)
                            return CheckResultType.FAILED

                        verified_artifact_assets.extend(artifact_assets)

        check_result["justification"].append("Successfully verified the following artifacts:")
        for asset in verified_artifact_assets:
            check_result["justification"].append(f"* {asset.url}")

        check_result["result_tables"].append(ProvenanceWitnessL1Table())
        return CheckResultType.PASSED


registry.register(ProvenanceWitnessL1Check())
