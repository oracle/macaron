# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module declares types and utilities for Maven artifacts."""

from packageurl import PackageURL

from macaron.slsa_analyzer.provenance.intoto import InTotoPayload
from macaron.slsa_analyzer.provenance.intoto.v01 import InTotoV01Subject
from macaron.slsa_analyzer.provenance.intoto.v1 import InTotoV1ResourceDescriptor
from macaron.slsa_analyzer.provenance.witness import (
    extract_build_artifacts_from_witness_subjects,
    is_witness_provenance_payload,
    load_witness_verifier_config,
)


class MavenSubjectPURLMatcher:
    """A matcher matching a PURL identifying a Maven artifact to a provenance subject."""

    @staticmethod
    def get_subject_in_provenance_matching_purl(
        provenance_payload: InTotoPayload, purl: PackageURL
    ) -> InTotoV01Subject | InTotoV1ResourceDescriptor | None:
        """Get the subject in the provenance matching the PURL.

        In this case where the provenance is assumed to be built from a Java project,
        the subject must be a Maven artifact.

        Parameters
        ----------
        provenance_payload : InTotoPayload
            The provenance payload.
        purl : PackageURL
            The PackageURL identifying the matching subject.

        Returns
        -------
        InTotoV01Subject | InTotoV1ResourceDescriptor | None
            The subject in the provenance matching the given PURL.
        """
        if not purl.namespace:
            return None
        if not purl.version:
            return None
        if purl.type != "maven":
            return None

        if not is_witness_provenance_payload(
            payload=provenance_payload,
            predicate_types=load_witness_verifier_config().predicate_types,
        ):
            return None
        artifact_subjects = extract_build_artifacts_from_witness_subjects(provenance_payload)

        for subject in artifact_subjects:
            _, _, artifact_filename = subject["name"].rpartition("/")
            subject_purl = create_maven_purl_from_artifact_filename(
                artifact_filename=artifact_filename,
                group_id=purl.namespace,
                version=purl.version,
            )
            if subject_purl == purl:
                return subject

        return None


def create_maven_purl_from_artifact_filename(
    artifact_filename: str,
    group_id: str,
    version: str,
) -> PackageURL | None:
    """Create a Maven PackageURL given an artifact filename, a group id, and a version.

    For reference, see:
    - https://maven.apache.org/ref/3.9.6/maven-core/artifact-handlers.html
    - https://github.com/package-url/purl-spec/blob/master/PURL-TYPES.rst#maven
    Notes:
    - For the time being, we are only supporting the ``"type"`` qualifier, although the
    Maven section in the PackageURL docs also mention the ``"classifier"`` qualifier.
    This is because not all artifact types has a unique value of ``"classifier"``
    according to the Artifact Handlers table in the Maven Core reference. In addition,
    not supporting the ``"classifier"`` qualifier at the moment simplifies the
    implementation for PURL decoding and generation until there is a concrete use
    case for this additional qualifier.
    - We are only supporting only 4 artifact types: jar, pom, javadoc, and java-source.

    Parameters
    ----------
    artifact_filename : str
        The filename of the artifact.
    group_id : str
        The group id of the artifact.
    version : str
        The version of the artifact.

    Returns
    -------
    PackageURL | None
        A Maven artifact PackageURL, or `None` if the filename does not follow any
        of the supported artifact name patters.
    """
    # Each artifact name should follow the pattern "<artifact-id>-<suffix>"
    # where "<suffix>" is one of the following.
    suffix_to_purl_qualifiers = {
        f"-{version}.jar": {"type": "jar"},
        f"-{version}.pom": {"type": "pom"},
        f"-{version}-javadoc.jar": {"type": "javadoc"},
        f"-{version}-sources.jar": {"type": "java-source"},
    }

    for suffix, purl_qualifiers in suffix_to_purl_qualifiers.items():
        if artifact_filename.endswith(suffix):
            artifact_id = artifact_filename[: -len(suffix)]
            return PackageURL(
                type="maven",
                namespace=group_id,
                name=artifact_id,
                version=version,
                qualifiers=purl_qualifiers,
            )

    return None
