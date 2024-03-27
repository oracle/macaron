# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module declares types and utilities for Maven artifacts."""

import re
from dataclasses import dataclass
from enum import Enum
from typing import NamedTuple, Self

from packageurl import PackageURL

from macaron.slsa_analyzer.provenance.intoto import InTotoPayload
from macaron.slsa_analyzer.provenance.intoto.v01 import InTotoV01Subject
from macaron.slsa_analyzer.provenance.intoto.v1 import InTotoV1ResourceDescriptor
from macaron.slsa_analyzer.provenance.witness import (
    extract_build_artifacts_from_witness_subjects,
    is_witness_provenance_payload,
    load_witness_verifier_config,
)


class _MavenArtifactType(NamedTuple):
    filename_pattern: str
    purl_qualifiers: dict[str, str]


class MavenArtifactType(_MavenArtifactType, Enum):
    """Maven artifact types that Macaron supports.

    For reference, see:
    - https://maven.apache.org/ref/3.9.6/maven-core/artifact-handlers.html
    - https://github.com/package-url/purl-spec/blob/master/PURL-TYPES.rst#maven

    Note: For the time being, we are only supporting the ``"type"`` qualifier, although the
    Maven section in the PackageURL docs also mention the ``"classifier"`` qualifier.
    This is because not all artifact types has a unique value of ``"classifier"`` according
    to the Artifact Handlers table in the Maven Core reference. In addition, not supporting
    the ``"classifier"`` qualifier at the moment simplifies the implementation for PURL
    decoding and generation until there is a concrete use case for this additional qualifier.
    """

    # Enum with custom value type.
    # See https://docs.python.org/3.10/library/enum.html#others.
    JAR = _MavenArtifactType(
        filename_pattern="{artifact_id}-{version}.jar",
        purl_qualifiers={"type": "jar"},
    )
    POM = _MavenArtifactType(
        filename_pattern="{artifact_id}-{version}.pom",
        purl_qualifiers={"type": "pom"},
    )
    JAVADOC = _MavenArtifactType(
        filename_pattern="{artifact_id}-{version}-javadoc.jar",
        purl_qualifiers={"type": "javadoc"},
    )
    JAVA_SOURCE = _MavenArtifactType(
        filename_pattern="{artifact_id}-{version}-sources.jar",
        purl_qualifiers={"type": "java-source"},
    )


@dataclass
class MavenArtifact:
    """A Maven artifact."""

    group_id: str
    artifact_id: str
    version: str
    artifact_type: MavenArtifactType

    @property
    def package_url(self) -> PackageURL:
        """Get the PackageURL of this Maven artifact."""
        return PackageURL(
            type="maven",
            namespace=self.group_id,
            name=self.artifact_id,
            version=self.version,
            qualifiers=self.artifact_type.purl_qualifiers,
        )

    @classmethod
    def from_package_url(cls, package_url: PackageURL) -> Self | None:
        """Create a Maven artifact from a PackageURL.

        Parameters
        ----------
        package_url : PackageURL
            The PackageURL identifying a Maven artifact.

        Returns
        -------
        Self | None
            A Maven artifact, or ``None`` if the PURL is not a valid Maven artifact PURL, or if
            the artifact type is not supported.
            For supported artifact types, see :class:`MavenArtifactType`.
        """
        if not package_url.namespace:
            return None
        if not package_url.version:
            return None
        if package_url.type != "maven":
            return None
        maven_artifact_type = None
        for artifact_type in MavenArtifactType:
            if artifact_type.purl_qualifiers == package_url.qualifiers:
                maven_artifact_type = artifact_type
                break
        if not maven_artifact_type:
            return None
        return cls(
            group_id=package_url.namespace,
            artifact_id=package_url.name,
            version=package_url.version,
            artifact_type=maven_artifact_type,
        )

    @classmethod
    def from_artifact_name(
        cls,
        artifact_name: str,
        group_id: str,
        version: str,
    ) -> Self | None:
        """Create a Maven artifact given an artifact name.

        The artifact type is determined based on the naming pattern of the artifact.

        Parameters
        ----------
        artifact_name : str
            The artifact name.
        group_id : str
            The group id.
        version : str
            The version

        Returns
        -------
        Self | None
            A Maven artifact, or ``None`` if the PURL is not a valid Maven artifact PURL, or if
            the artifact type is not supported.
            For supported artifact types, see :class:`MavenArtifactType`.
        """
        for maven_artifact_type in MavenArtifactType:
            pattern = maven_artifact_type.filename_pattern.format(
                artifact_id="(.*)",
                version=version,
            )
            match_result = re.search(pattern, artifact_name)
            if not match_result:
                continue
            artifact_id = match_result.group(1)
            return cls(
                group_id=group_id,
                artifact_id=artifact_id,
                version=version,
                artifact_type=maven_artifact_type,
            )
        return None


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
        if (maven_artifact := MavenArtifact.from_package_url(purl)) and is_witness_provenance_payload(
            payload=provenance_payload,
            predicate_types=load_witness_verifier_config().predicate_types,
        ):
            artifact_subjects = extract_build_artifacts_from_witness_subjects(provenance_payload)

            maven_artifact_subject_pairs = []
            for subject in artifact_subjects:
                _, _, artifact_name = subject["name"].rpartition("/")
                artifact = MavenArtifact.from_artifact_name(
                    artifact_name=artifact_name,
                    group_id=maven_artifact.group_id,
                    version=maven_artifact.version,
                )
                if artifact is None:
                    continue
                maven_artifact_subject_pairs.append((artifact, subject))

            for artifact, subject in maven_artifact_subject_pairs:
                if artifact.package_url == purl:
                    return subject

        return None
