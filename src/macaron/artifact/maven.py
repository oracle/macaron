# Copyright (c) 2024 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module declares types and utilities for Maven artifacts."""
import re
from collections.abc import Sequence

from packageurl import PackageURL

from macaron.config.defaults import defaults
from macaron.slsa_analyzer.provenance.intoto import InTotoPayload
from macaron.slsa_analyzer.provenance.intoto.v01 import InTotoV01Subject
from macaron.slsa_analyzer.provenance.intoto.v1 import InTotoV1ResourceDescriptor
from macaron.slsa_analyzer.provenance.slsa import extract_build_artifacts_from_slsa_subjects, is_slsa_provenance_payload
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

        artifact_subjects: Sequence[InTotoV01Subject | InTotoV1ResourceDescriptor] = []
        if is_witness_provenance_payload(
            payload=provenance_payload,
            predicate_types=load_witness_verifier_config().predicate_types,
        ):
            artifact_subjects = extract_build_artifacts_from_witness_subjects(provenance_payload)
        elif is_slsa_provenance_payload(
            payload=provenance_payload,
            predicate_types=defaults.get_list(
                "slsa.verifier",
                "predicate_types",
                fallback=[],
            ),
        ):
            artifact_subjects = extract_build_artifacts_from_slsa_subjects(provenance_payload)
        else:
            return None

        for subject in artifact_subjects:
            subject_name = subject["name"]
            if not subject_name:
                continue
            _, _, artifact_filename = subject_name.rpartition("/")
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


def is_valid_maven_group_id(group_id: str) -> bool:
    """Check if the provided string is a valid maven group id.

    Parameters
    ----------
    group_id : str
        The group id to check.

    Returns
    -------
    bool
        True if the group id is valid, False otherwise
    """
    # Should match strings like org.example.foo, org.example-2.foo.bar_1.
    pattern = r"^[a-zA-Z][a-zA-Z0-9-]*\.([a-zA-Z][a-zA-Z0-9-]*\.)*[a-zA-Z][a-zA-Z0-9-]*[a-zA-Z0-9]$"
    return re.match(pattern, group_id) is not None


def construct_maven_repository_path(
    group_id: str,
    artifact_id: str | None = None,
    version: str | None = None,
    asset_name: str | None = None,
) -> str:
    """Construct a path to a folder or file on the registry, assuming Maven repository layout.

    For more details regarding Maven repository layout, see the following:
    - https://maven.apache.org/repository/layout.html
    - https://maven.apache.org/guides/mini/guide-naming-conventions.html

    Parameters
    ----------
    group_id : str
        The group id of a Maven package.
    artifact_id : str
        The artifact id of a Maven package.
    version : str
        The version of a Maven package.
    asset_name : str
        The asset name.

    Returns
    -------
    str
        The path to a folder or file on the registry.
    """
    path = group_id.replace(".", "/")
    if artifact_id:
        path = "/".join([path, artifact_id])
    if version:
        path = "/".join([path, version])
    if asset_name:
        path = "/".join([path, asset_name])
    return path


def construct_primary_jar_file_name(purl: PackageURL) -> str | None:
    """Return the name of the primary JAR for the passed PURL based on the Maven registry standard.

    Parameters
    ----------
    purl: PackageURL
        The PURL of the artifact.

    Returns
    -------
    str | None
        The artifact file name, or None if invalid.
    """
    if not purl.version:
        return None

    return purl.name + "-" + purl.version + ".jar"
