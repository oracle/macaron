# Copyright (c) 2023 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
ORM Table definitions used by macaron internally.

The current ERD of Macaron is shown below:

.. figure:: /assets/er-diagram.svg

For table associated with a check see the check module.
"""
import logging
import os
import string
from datetime import datetime
from pathlib import Path
from typing import Any, Self

from packageurl import PackageURL
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from macaron.artifact.maven import MavenSubjectPURLMatcher
from macaron.database.database_manager import ORMBase
from macaron.database.db_custom_types import ProvenancePayload, RFC3339DateTime
from macaron.errors import InvalidPURLError
from macaron.repo_finder.repo_finder_enums import CommitFinderInfo, RepoFinderInfo
from macaron.slsa_analyzer.provenance.intoto import InTotoPayload, ProvenanceSubjectPURLMatcher
from macaron.slsa_analyzer.slsa_req import ReqName

logger: logging.Logger = logging.getLogger(__name__)

# TODO: Use UUIDs as primary keys rather than incremental

################################################################################
# Analysis
#   - Table corresponding to an invocation of "macaron analyze"
################################################################################


class Analysis(ORMBase):
    """
    ORM Class for the analysis information.

    This information pertains to a single invocation of Macaron.
    """

    __tablename__ = "_analysis"

    #: The primary key.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # noqa: A003

    #: The analysis start time.
    analysis_time: Mapped[datetime] = mapped_column(RFC3339DateTime, nullable=False)

    #: The current version of Macaron.
    macaron_version: Mapped[str] = mapped_column(String, nullable=False)

    #: The one-to-many relationship with software components.
    component: Mapped[list["Component"]] = relationship(back_populates="analysis")


class PackageURLMixin:
    """The SQLAlchemy mixin for Package URLs (PURL).

    See https://github.com/package-url/purl-spec

    TODO: Use the PackageURLMixin from https://github.com/package-url/packageurl-python
    once it makes a new release (> 0.11.1).
    """

    #: A short code to identify the type of the package.
    type: Mapped[str] = mapped_column(  # noqa: A003
        String(16),
        nullable=False,
        comment=(
            "A short code to identify the type of this package. "
            "For example: gem for a Rubygem, docker for a container, "
            "pypi for a Python Wheel or Egg, maven for a Maven Jar, "
            "deb for a Debian package, etc."
        ),
    )

    #: Package name prefix, such as Maven groupid.
    namespace: Mapped[str] = mapped_column(
        String(255),
        nullable=True,
        comment=("Package name prefix, such as Maven groupid, Docker image owner, GitHub user or organization, etc."),
    )

    #: Name of the package.
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="Name of the package.")

    #: Version of the package.
    version: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="Version of the package.")

    #: Extra qualifying data for a package such as the name of an OS.
    qualifiers: Mapped[str] = mapped_column(
        String(1024),
        nullable=True,
        comment=("Extra qualifying data for a package such as the name of an OS, " "architecture, distro, etc."),
    )

    #: Extra subpath within a package, relative to the package root.
    subpath: Mapped[str] = mapped_column(
        String(200), nullable=True, comment="Extra subpath within a package, relative to the package root."
    )


# An association table that identifies the many-to-many dependency relationship between components."""
components_association_table = Table(
    "_dependency",
    ORMBase.metadata,
    Column("parent_component", ForeignKey("_component.id"), primary_key=True),
    Column("child_component", ForeignKey("_component.id"), primary_key=True),
)


class Component(PackageURLMixin, ORMBase):
    """ORM class for a software component."""

    __tablename__ = "_component"

    #: The primary key.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # noqa: A003

    # TODO: The unique constraint on PURL is set to False for now and we be turned on in future.
    #: The PURL column is for the benefit of Souffle to make it easy to query based on a PURL string.
    purl: Mapped[str] = mapped_column(String, nullable=False, unique=False)

    #: The foreign key to the analysis table.
    analysis_id: Mapped[int] = mapped_column(Integer, ForeignKey("_analysis.id"), nullable=False)

    #: The many-to-one relationship with an analysis.
    analysis: Mapped["Analysis"] = relationship(back_populates="component", lazy="immediate")

    #: The one-to-one relationship with a repository.
    repository: Mapped["Repository"] = relationship(uselist=False, back_populates="component", lazy="immediate")

    #: The one-to-one relationship with a SLSA level.
    slsalevel: Mapped["SLSALevel"] = relationship(back_populates="component", lazy="immediate")

    #: The one-to-many relationship with SLSA requirements.
    slsarequirement: Mapped[list["SLSARequirement"]] = relationship(back_populates="component", lazy="immediate")

    #: The one-to-many relationship with the result table.
    checkresult: Mapped[list["MappedCheckResult"]] = relationship(back_populates="component", lazy="immediate")

    #: The one-to-many relationship with checks.
    checkfacts: Mapped[list["CheckFacts"]] = relationship(back_populates="component", lazy="immediate")

    #: The one-to-many relationship with provenances.
    provenance: Mapped[list["Provenance"]] = relationship(back_populates="component", lazy="immediate")

    #: The bidirectional many-to-many relationship for component dependencies.
    dependencies: Mapped[list["Component"]] = relationship(
        secondary=components_association_table,
        primaryjoin=components_association_table.c.parent_component == id,
        secondaryjoin=components_association_table.c.child_component == id,
    )

    #: The optional one-to-one relationship with a provenance subject in case this
    #: component represents a subject in a provenance.
    provenance_subject: Mapped["ProvenanceSubject | None"] = relationship(
        back_populates="component",
        lazy="immediate",
    )

    #: The one-to-one relationship with Repo Finder metadata.
    repo_finder_metadata: Mapped["RepoFinderMetadata"] = relationship(back_populates="component", lazy="immediate")

    def __init__(
        self, purl: str, analysis: Analysis, repository: "Repository | None", repo_finder_metadata: "RepoFinderMetadata"
    ):
        """
        Instantiate the software component using PURL identifier.

        Parameters
        ----------
        purl: str
            The Package URL identifier.
        analysis: Analysis
            The corresponding analysis.
        repository: Repository | None
            The corresponding repository.

        Raises
        ------
        InvalidPURLError
            If the PURL provided from the user is invalid.
        """
        try:
            purl_parts = PackageURL.from_string(purl)
        except ValueError as error:
            raise InvalidPURLError(f"The package url {purl} is not valid.") from error

        # We set ``encode=True`` to encode qualifiers as a normalized string because SQLite doesn't support ``dict`` type.
        # TODO: Explore the ``dbm`` or ``shelve`` packages to support dict type, which are part of the Python standard library.
        purl_kwargs = purl_parts.to_dict(encode=True)

        super().__init__(
            purl=purl,
            analysis=analysis,
            repository=repository,
            repo_finder_metadata=repo_finder_metadata,
            **purl_kwargs,
        )

    @property
    def report_file_name(self) -> str:
        """Return the report file name using the PURL string's name attribute.

        Return
        ------
        str
            The report file name.
        """
        # Sanitize the file name.
        allowed_chars = string.ascii_letters + string.digits + "-"
        return "".join(c if c in allowed_chars else "_" for c in self.name)

    @property
    def report_file_purl(self) -> str:
        """Return the report file name for this component using the PURL string.

        Return
        ------
        str
            The report file name.
        """
        # Sanitize the path and make sure it's a valid file name.
        # A purl string is an ASCII URL string that can allow uppercase letters for
        # certain parts. So we shouldn't change uppercase letters with lower case
        # to avoid merging results for two distinct PURL strings.
        allowed_chars = string.ascii_letters + string.digits + "-"
        return "".join(c if c in allowed_chars else "_" for c in self.purl)

    @property
    def report_dir_name(self) -> str:
        """Return the report directory name for this component using the PURL string.

        Return
        ------
        str
            The report directory name.
        """
        # Sanitize the path and make sure it's a valid file name.
        # A purl string is an ASCII URL string that can allow uppercase letters for
        # certain parts. So we shouldn't change uppercase letters with lower case
        # to avoid merging results for two distinct PURL strings.
        allowed_chars = string.ascii_letters + string.digits + "-"
        p_type = "".join(c if c in allowed_chars else "_" for c in self.type)
        p_namespace = "".join(c if c in allowed_chars else "_" for c in self.namespace) if self.namespace else ""
        p_name = "".join(c if c in allowed_chars else "_" for c in self.name)
        return os.path.join(p_type, p_namespace, p_name)


class Repository(ORMBase):
    """ORM Class for a repository."""

    __tablename__ = "_repository"

    #: The primary key.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # noqa: A003

    # Because component is the parent table, we should define the foreign key here in the child table.
    #: The foreign key to the software component.
    component_id: Mapped[int] = mapped_column(Integer, ForeignKey("_component.id"))

    #: The one-to-one relationship with the software component for this repository.
    component: Mapped["Component"] = relationship(back_populates="repository", uselist=False, lazy="immediate")

    # :Repository name in ``<git-service>/<owner>/<repo_name>`` format.
    complete_name: Mapped[str] = mapped_column(String, nullable=False)

    # :Repository name in ``<owner>/<repo_name>`` format.
    full_name: Mapped[str] = mapped_column(String, nullable=False)

    #: The PURL type.
    type: Mapped[str] = mapped_column(String, nullable=False)  # noqa: A003

    # TODO: for locally cloned repos, do we have both type and owner, or can they be null?
    #: The PURL namespace, which is the owner in pkg:github.com/owner/name@commit-sha.
    owner: Mapped[str] = mapped_column(String, nullable=True)

    #: The PURL name.
    name: Mapped[str] = mapped_column(String, nullable=False)

    #: The remote URL path to the repo.
    remote_path: Mapped[str] = mapped_column(String, nullable=False)

    #: The branch name.
    branch_name: Mapped[str | None] = mapped_column(String, nullable=True)

    #: The release tag.
    release_tag: Mapped[str] = mapped_column(String, nullable=True)

    #: The commit sha.
    commit_sha: Mapped[str] = mapped_column(String, nullable=False)

    #: The commit date.
    commit_date: Mapped[str] = mapped_column(String, nullable=False)

    #: The path to the repo on the file system.
    fs_path: Mapped[str] = mapped_column(String, nullable=False)

    def __init__(self, files: list[str] | None = None, **kwargs: Any):
        """Instantiate the repository and set files.

        Parameters
        ----------
        files: list[str] | None
            The files extracted for this repository.
        """
        super().__init__(**kwargs)

        # We populate the PURL type, namespace, and name columns using the complete_name.
        # Because locally cloned repositories may miss the namespace, we need to check the length.
        # Note that the length of parts is already checked and should be either 2 or 3.
        parts = Path(self.complete_name).parts

        # TODO: check if we need to trim ".com" from the netloc following the examples in
        # https://github.com/package-url/purl-spec/blob/master/PURL-SPECIFICATION.rst
        self.type = parts[0]

        # Set PURL namespace and name based on the type of repository, i.e., remote or locally clones.
        if (length := len(parts)) == 3:
            # It is a remote repository.
            self.owner, self.name = parts[1:3]
        elif length == 2:
            # It is a locally cloned repository.
            self.name = parts[1]

        self.files = files or []


class SLSALevel(ORMBase):
    """ORM class for the slsa level of a repository."""

    __tablename__ = "_slsa_level"

    #: The primary key.
    component_id: Mapped[int] = mapped_column(Integer, ForeignKey("_component.id"), primary_key=True)

    #: An integer value showing the SLSA level.
    slsa_level: Mapped[int] = mapped_column(Integer, nullable=False)

    #: A boolean that shows whether the SLSA level has reached or not.
    reached: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # TODO: investigate of this relationship is really one-to-one.
    #: A one-to-one relationship with software components.
    component: Mapped["Component"] = relationship(back_populates="slsalevel", lazy="immediate")


# TODO: Consider creating a table for requirements Enum where requirement_name is
# a primary key, and used in SLSARequirement as a foreign key.
class SLSARequirement(ORMBase):
    """ORM mapping for SLSA requirements a software component satisfies."""

    __tablename__ = "_slsa_requirement"

    # A unique constraint as defined below makes sure a component will have only one slsa requirement
    # of the same name. We follow Alembic's uq_%(table_name)s_%(column_0_name) naming convention.
    # See https://alembic.sqlalchemy.org/en/latest/naming.html
    __table_args__ = (UniqueConstraint("component_id", "requirement_name", name="uq__slsa_requirement_component_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # noqa: A003

    #: The software component ID.
    component_id: Mapped[int] = mapped_column(Integer, ForeignKey("_component.id"), nullable=False)

    #: The unique SLSA requirement name.
    requirement_name: Mapped[Enum] = mapped_column(
        Enum(*ReqName._member_names_), nullable=False  # pylint: disable=protected-access,no-member
    )

    #: The short description of the SLSA requirement.
    requirement_short_description: Mapped[str] = mapped_column(String, nullable=True)

    #: The justification in the check result for a particular requirement.
    feedback: Mapped[str] = mapped_column(String, nullable=True)

    #: The many-to-one relationship between SLSA requirements and software components.
    component: Mapped["Component"] = relationship(back_populates="slsarequirement", lazy="immediate")


# TODO: Rename this class to CheckResult once the `check_result.CheckResult` is removed.
class MappedCheckResult(ORMBase):
    """ORM class for the result of a check, is automatically added for each check."""

    __tablename__ = "_check_result"
    # A unique constraint as defined below makes sure a component will have only one result row
    # for a particular check. Note that this different from a column constraint (unique=True)
    # that ensures a check ID is unique.
    # See the naming convention for the declarative metadata (which we don't have currently!):
    # https://alembic.sqlalchemy.org/en/latest/naming.html#autogen-naming-conventions
    __table_args__ = (UniqueConstraint("component_id", "check_id", name="uq__check_result_component_id"),)

    #: The primary key.
    id: Mapped[int] = mapped_column(  # noqa: A003 # pylint: disable=invalid-name
        Integer, primary_key=True, autoincrement=True
    )

    #: The check identifier, e.g., mcn_build_as_code_1.
    check_id: Mapped[str] = mapped_column(String, nullable=False)

    #: Shows whether a check has passed or failed.
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)

    #: The foreign key to the software component.
    component_id: Mapped[int] = mapped_column(Integer, ForeignKey("_component.id"), nullable=False)

    #: A many-to-one relationship with software components.
    component: Mapped["Component"] = relationship(back_populates="checkresult")

    #: A one-to-many relationship with checks.
    checkfacts: Mapped[list["CheckFacts"]] = relationship(back_populates="checkresult", lazy="immediate")


class CheckFacts(ORMBase):
    """
    This class allows SQLAlchemy to load elements polymorphically, using joined table inheritance.

    All tables for checks must inherit this class, these fields are automatically filled in by the analyzer.

    See https://docs.sqlalchemy.org/en/20/orm/inheritance.html#joined-table-inheritance
    """

    __tablename__ = "_check_facts"

    #: The primary key.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # noqa: A003

    #: The confidence score to estimate the accuracy of the check fact. This value should be in the range [0.0, 1.0] with
    #: a lower value depicting a lower confidence. Because some analyses used in checks may use
    #: heuristics, the results can be inaccurate in certain cases.
    #: We use the confidence score to enable the check designer to assign a confidence estimate.
    #: This confidence is stored in the database to be used by the policy. This confidence score is
    #: also used to decide which evidence should be shown to the user in the HTML/JSON report.
    confidence: Mapped[float] = mapped_column(
        Float, CheckConstraint("confidence>=0.0 AND confidence<=1.0"), nullable=False
    )

    #: The foreign key to the software component.
    component_id: Mapped[int] = mapped_column(Integer, ForeignKey("_component.id"), nullable=False)

    #: A many-to-one relationship with software components.
    component: Mapped["Component"] = relationship(back_populates="checkfacts")

    #: The foreign key to the check result.
    check_result_id: Mapped[int] = mapped_column(Integer, ForeignKey("_check_result.id"), nullable=False)

    #: The column used as a mapper argument for distinguishing checks in polymorphic inheritance.
    check_type: Mapped[str]

    #: A many-to-one relationship with check results.
    checkresult: Mapped["MappedCheckResult"] = relationship(back_populates="checkfacts")

    #: The polymorphic inheritance configuration.
    __mapper_args__ = {
        "polymorphic_identity": "CheckFacts",
        "polymorphic_on": "check_type",
    }


class Provenance(ORMBase):
    """ORM class for a provenance document."""

    __tablename__ = "_provenance"

    #: The primary key.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # noqa: A003

    #: The foreign key to the software component.
    component_id: Mapped[int] = mapped_column(Integer, ForeignKey(Component.id), nullable=False)

    #: A many-to-one relationship with software components.
    component: Mapped["Component"] = relationship(back_populates="provenance")

    #: The SLSA version.
    slsa_version: Mapped[str] = mapped_column(String, nullable=True)

    #: The SLSA level.
    slsa_level: Mapped[int] = mapped_column(Integer, default=0)

    #: The release tag commit sha.
    release_commit_sha: Mapped[str] = mapped_column(String, nullable=True)

    #: The repository URL from the provenance.
    repository_url: Mapped[str] = mapped_column(String, nullable=True)

    #: The commit sha from the provenance.
    commit_sha: Mapped[str] = mapped_column(String, nullable=True)

    #: The provenance payload.
    provenance_payload: Mapped[InTotoPayload] = mapped_column(ProvenancePayload, nullable=False)

    #: The name of the provenance asset.
    provenance_asset_name: Mapped[str] = mapped_column(String, nullable=True)

    #: The URL of the provenance asset.
    provenance_asset_url: Mapped[str] = mapped_column(String, nullable=True)

    #: The verified status of the provenance.
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    #: A one-to-many relationship with the release artifacts.
    artifact: Mapped[list["ReleaseArtifact"]] = relationship(back_populates="provenance")


class ReleaseArtifact(ORMBase):
    """The ORM class for release artifacts."""

    __tablename__ = "_release_artifact"

    #: The primary key.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # noqa: A003

    #: The name of the artifact.
    name: Mapped[str] = mapped_column(String, nullable=False)

    #: The SLSA verification result.
    slsa_verified: Mapped[bool] = mapped_column(Boolean, nullable=True)

    #: The foreign key to the SLSA provenance.
    provenance_id: Mapped[int] = mapped_column(Integer, ForeignKey(Provenance.id), nullable=True)

    #: A many-to-one relationship with the SLSA provenance.
    provenance: Mapped["Provenance"] = relationship(back_populates="artifact")

    #: The one-to-many relationship with the hash digests for this artifact.
    digests: Mapped[list["HashDigest"]] = relationship(back_populates="artifact")


class HashDigest(ORMBase):
    """ORM class for artifact digests."""

    __tablename__ = "_hash_digest"

    #: The primary key.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # noqa: A003

    #: The hash digest value.
    digest: Mapped[str] = mapped_column(String, nullable=False)

    #: The hash digest algorithm.
    digest_algorithm: Mapped[str] = mapped_column(String, nullable=False)

    #: The foreign key to the release artifact.
    artifact_id: Mapped[int] = mapped_column(Integer, ForeignKey(ReleaseArtifact.id), nullable=False)

    #: The many-to-one relationship with artifacts.
    artifact: Mapped["ReleaseArtifact"] = relationship(back_populates="digests", lazy="immediate")


class ProvenanceSubject(ORMBase):
    """A subject in a provenance that matches the user-provided PackageURL.

    This subject may be later populated in VSAs during policy verification.
    """

    __tablename__ = "_provenance_subject"

    #: The primary key.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # noqa: A003

    #: The component id of the provenance subject.
    component_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("_component.id"),
        nullable=False,
    )

    #: The required one-to-one relationship with a component.
    component: Mapped[Component] = relationship(
        back_populates="provenance_subject",
        lazy="immediate",
    )

    #: The SHA256 hash of the subject.
    sha256: Mapped[str] = mapped_column(String, nullable=False)

    @classmethod
    def from_purl_and_provenance(
        cls,
        purl: PackageURL,
        provenance_payload: InTotoPayload,
    ) -> Self | None:
        """Create a ``ProvenanceSubject`` entry if there is a provenance subject matching the PURL.

        Parameters
        ----------
        purl : PackageURL
            The PackageURL identifying the software component being analyzed.
        provenance_payload : InTotoPayload
            The provenance payload.

        Returns
        -------
        Self | None
            A ``ProvenanceSubject`` entry with the SHA256 digest of the provenance subject
            matching the given PURL.
        """
        subject_artifact_types: list[ProvenanceSubjectPURLMatcher] = [MavenSubjectPURLMatcher]

        for subject_artifact_type in subject_artifact_types:
            subject = subject_artifact_type.get_subject_in_provenance_matching_purl(
                provenance_payload,
                purl,
            )
            if subject is None:
                return None
            digest = subject["digest"]
            if digest is None:
                return None
            sha256 = digest.get("sha256")
            if not sha256:
                return None
            return cls(sha256=sha256)

        return None


class RepoFinderMetadata(ORMBase):
    """Metadata from the Repo Finder and Commit Finder runs for an associated Component."""

    __tablename__ = "_repo_finder_metadata"

    #: The primary key.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # noqa: A003

    #: The foreign key to the software component.
    component_id: Mapped[int] = mapped_column(Integer, ForeignKey(Component.id), nullable=False)

    #: A one-to-one relationship with software components.
    component: Mapped["Component"] = relationship(back_populates="repo_finder_metadata")

    #: The outcome of the Repo Finder.
    repo_finder_outcome: Mapped[Enum] = mapped_column(
        Enum(RepoFinderInfo), nullable=False  # pylint: disable=protected-access,no-member
    )

    #: The outcome of the Commit Finder.
    commit_finder_outcome: Mapped[Enum] = mapped_column(
        Enum(CommitFinderInfo), nullable=False  # pylint: disable=protected-access,no-member
    )

    #: The URL found by the Repo Finder (if applicable).
    found_url: Mapped[str] = mapped_column(String)

    #: The commit of the tag matched by the Commit Finder.
    found_commit: Mapped[str] = mapped_column(String)
