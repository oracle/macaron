# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
ORM Table definitions used by macaron internally.

For tables associated with checks see base_check.py.
"""

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String
from sqlalchemy.orm import declarative_mixin, declared_attr

from macaron.database.database_manager import ORMBase

################################################################################
# Analyzer
#   - Tables corresponding to an invocation of "macaron analyze"
################################################################################


class SLSARequirement(ORMBase):
    """Table storing the SLSA requirements a repository satisfies."""

    __tablename__ = "_slsa_requirement"
    repository = Column(Integer, ForeignKey("_repository.id"), primary_key=True)
    requirement = Column(String, primary_key=True)
    requirement_name = Column(String, primary_key=False)
    feedback = Column(String, nullable=True)


class RepositoryDependency(ORMBase):
    """Identifies dependencies between repositories."""

    __tablename__ = "_dependency"
    dependent_repository = Column(Integer, ForeignKey("_repository.id"), primary_key=True)
    dependency_repository = Column(Integer, ForeignKey("_repository.id"), primary_key=True)


class AnalysisTable(ORMBase):
    """
    ORM Class for the analysis information.

    This information pertains to a single invocation of the macaron tool.
    """

    __tablename__ = "_analysis"
    id = Column(Integer, primary_key=True, autoincrement=True)  # noqa: A003
    analysis_time = Column(String, nullable=False)
    repository = Column(Integer, ForeignKey("_repository.id"), nullable=False)
    macaron_version = Column(String, nullable=False)


class RepositoryAnalysis(ORMBase):
    """Relates repositories to the analysis in which they were scanned."""

    __tablename__ = "_repository_analysis"
    analysis_id = Column(Integer, ForeignKey("_analysis.id"), nullable=False, primary_key=True)
    repository_id = Column(Integer, ForeignKey("_repository.id"), nullable=False, primary_key=True)


################################################################################
# AnalyzeContext
#    - Tables pertaining to a specific analysis target
################################################################################
class RepositoryTable(ORMBase):
    """ORM Class for a repository."""

    __tablename__ = "_repository"
    id = Column(Integer, primary_key=True, autoincrement=True)  # noqa: A003
    full_name = Column(String, nullable=False)
    remote_path = Column(String, nullable=True)
    branch_name = Column(String, nullable=False)
    release_tag = Column(String, nullable=True)
    commit_sha = Column(String, nullable=False)
    commit_date = Column(String, nullable=False)


class SLSALevelTable(ORMBase):
    """Table to store the slsa level of a repository."""

    __tablename__ = "_slsa_level"
    repository = Column(Integer, ForeignKey("_repository.id"), primary_key=True)
    slsa_level = Column(Integer, nullable=False)
    reached = Column(Boolean, nullable=False)


class CheckResultTable(ORMBase):
    """Table to store the result of a check, is automatically added for each check."""

    __tablename__ = "_check_result"
    id = Column(Integer, primary_key=True, autoincrement=True)  # noqa: A003 # pylint: disable=invalid-name
    check_id = Column(String, nullable=False)
    repository = Column(Integer, ForeignKey("_repository.id"), nullable=False)
    passed = Column(Boolean, nullable=False)
    skipped = Column(Boolean, nullable=False)


@declarative_mixin
class CheckFactsTable:
    """
    Declarative mixin for check results.

    All tables for check results must inherit this class, these fields are automatically filled in by the analyzer.
    """

    # pylint: disable=no-member

    @declared_attr  # type: ignore
    def id(self) -> Column:  # noqa: A003 # pylint: disable=invalid-name
        """Check result id."""
        return Column(Integer, primary_key=True, autoincrement=True)

    @declared_attr  # type: ignore
    def check_result(self) -> Column:
        """Store the id of the repository to which the analysis pertains."""
        return Column(Integer, ForeignKey("_check_result.id"), nullable=False)

    @declared_attr  # type: ignore
    def repository(self) -> Column:
        """Store the id of the repository to which the analysis pertains."""
        return Column(Integer, ForeignKey("_repository.id"), nullable=False)


class PolicyTable(CheckFactsTable, ORMBase):
    """ORM Class for a Policy."""

    # TODO: policy_check should store the policy, its evaluation result, and which PROVENANCE it was applied to
    #       rather than only linking to the repository

    __tablename__ = "_policy"
    id = Column(Integer, primary_key=True, autoincrement=True)  # noqa: A003
    policy_id = Column(String, nullable=False)
    description = Column(String, nullable=True)
    policy_type = Column(String, nullable=False)
    sha = Column(String, nullable=False)
    text = Column(String, nullable=False)
