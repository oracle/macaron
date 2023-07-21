# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
ORM Table definitions used by macaron internally.

The current ERD of Macaron is shown below:

.. figure:: /assets/er-diagram.svg

For table associated with a check see the check module.
"""
import hashlib
import logging
import os
import string
from datetime import datetime
from pathlib import Path
from typing import Optional, Self

from packageurl import PackageURL
from sqlalchemy import Boolean, Column, Enum, ForeignKey, Integer, String, Table, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from macaron.database.database_manager import ORMBase
from macaron.database.rfc3339_datetime import RFC3339DateTime
from macaron.errors import CUEExpectationError, CUERuntimeError
from macaron.slsa_analyzer.provenance.expectations.cue import cue_validator
from macaron.slsa_analyzer.provenance.expectations.expectation import Expectation
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
    """The SQLAlchemy mixin for Package URLs (PURL)."""

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
    version: Mapped[str] = mapped_column(String(100), nullable=True, comment="Version of the package.")

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

    def __init__(self, purl: str, analysis: Analysis, repository: Optional["Repository"]):
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
        """
        purl_parts = PackageURL.from_string(purl)
        purl_kwargs = purl_parts.to_dict()
        super().__init__(purl=purl, analysis=analysis, repository=repository, **purl_kwargs)

    @property
    def report_file_name(self) -> str:
        """Set the report file name using the name.

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
        """Set the report file name for this component using the PURL string.

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
        """Set the report directory name for this component using the PURL string.

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
    branch_name: Mapped[str] = mapped_column(String, nullable=False)

    #: The release tag.
    release_tag: Mapped[str] = mapped_column(String, nullable=True)

    #: The commit sha.
    commit_sha: Mapped[str] = mapped_column(String, nullable=False)

    #: The commit date.
    commit_date: Mapped[str] = mapped_column(String, nullable=False)

    #: The path to the repo on the file system.
    fs_path: Mapped[str] = mapped_column(String, nullable=False)

    def __init__(self, *args, files: list[str] | None = None, **kwargs):  # type: ignore[no-untyped-def]
        """Instantiate the repository and set files.

        Parameters
        ----------
        files: list[str] | None
            The files extracted for this repository.
        """
        super().__init__(*args, **kwargs)

        # We populate the PURL type, namespace, and name columns using the complete_name.
        # Because locally cloned repositories may miss the namespace, we need to check the length.
        # Note that the length of parts is already checked and should be either 2 or 3.
        parts = [str(p) for p in Path(self.complete_name).parts]

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

        self.files = [str(f) for f in files] if files else []


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
    # of the same name.
    __table_args__ = (UniqueConstraint("component_id", "requirement_name", name="uq__requirement_name_component_id"),)

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
    This class allows SQLAlchemy to load elements polymorphically, using single table inheritance.

    All tables for checks must inherit this class, these fields are automatically filled in by the analyzer.
    """

    __tablename__ = "_check_facts"

    #: The primary key.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # noqa: A003

    #: The foreign key to the software component.
    component_id: Mapped[int] = mapped_column(Integer, ForeignKey("_component.id"), nullable=False)

    #: A many-to-one relationship with software components.
    component: Mapped["Component"] = relationship(back_populates="checkfacts")

    #: The foreign key to the check result.
    check_result_id: Mapped[int] = mapped_column(String, ForeignKey("_check_result.id"), nullable=False)

    #: The column used as a mapper argument for distinguishing checks in polymorphic inheritance.
    check_type: Mapped[str]

    #: A many-to-one relationship with check results.
    checkresult: Mapped["MappedCheckResult"] = relationship(back_populates="checkfacts")

    #: The polymorphic inheritance configuration.
    __mapper_args__ = {
        "polymorphic_identity": "CheckFacts",
        "polymorphic_on": "check_type",
    }


class CUEExpectation(Expectation, CheckFacts):
    """ORM Class for an expectation."""

    # TODO: provenance content check should store the expectation, its evaluation result,
    # and which PROVENANCE it was applied to rather than only linking to the repository.

    __tablename__ = "_expectation"

    #: The primary key, which is also a foreign key to the base check table.
    id: Mapped[int] = mapped_column(ForeignKey("_check_facts.id"), primary_key=True)  # noqa: A003

    #: The polymorphic inheritance configuration.
    __mapper_args__ = {
        "polymorphic_identity": "_expectation",
    }

    @classmethod
    def make_expectation(cls, expectation_path: str) -> Self | None:
        """Construct a CUE expectation from a CUE file.

        Note: we require the CUE expectation file to have a "target" field.

        Parameters
        ----------
        expectation_path: str
            The path to the expectation file.

        Returns
        -------
        Self
            The instantiated expectation object.
        """
        logger.info("Generating an expectation from file %s", expectation_path)
        expectation: CUEExpectation = CUEExpectation(
            description="CUE expectation",
            path=expectation_path,
            target="",
            expectation_type="CUE",
        )

        try:
            with open(expectation_path, encoding="utf-8") as expectation_file:
                expectation.text = expectation_file.read()
                expectation.sha = str(hashlib.sha256(expectation.text.encode("utf-8")).hexdigest())
                expectation.target = cue_validator.get_target(expectation.text)
                expectation._validator = (  # pylint: disable=protected-access
                    lambda provenance: cue_validator.validate_expectation(expectation.text, provenance)
                )
        except (OSError, CUERuntimeError, CUEExpectationError) as error:
            logger.error("CUE expectation error: %s", error)
            return None

        # TODO remove type ignore once mypy adds support for Self.
        return expectation  # type: ignore


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
    version: Mapped[str] = mapped_column(String, nullable=False)

    #: The release tag commit sha.
    release_commit_sha: Mapped[str] = mapped_column(String, nullable=True)

    #: The release tag.
    release_tag: Mapped[str] = mapped_column(String, nullable=True)

    #: The provenance payload content in JSON format.
    provenance_json: Mapped[str] = mapped_column(String, nullable=False)

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
