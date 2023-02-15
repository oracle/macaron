# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
ORM Table definitions used by macaron internally.

For tables associated with checks see base_check.py.
"""
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from macaron.database.database_manager import ORMBase
from macaron.database.rfc3339_datetime import RFC3339DateTime

# TODO: Use UUIDs as primary keys rather than incremental

################################################################################
# Analyzer
#   - Tables corresponding to an invocation of "macaron analyze"
################################################################################


class SLSARequirement(ORMBase):
    """Table storing the SLSA requirements a repository satisfies."""

    __tablename__ = "_slsa_requirement"
    repository: Mapped[int] = mapped_column(Integer, ForeignKey("_repository.id"), primary_key=True)
    requirement: Mapped[str] = mapped_column(String, primary_key=True)
    requirement_name: Mapped[str] = mapped_column(String, primary_key=False)
    feedback: Mapped[str] = mapped_column(String, nullable=True)


class RepositoryDependency(ORMBase):
    """Identifies dependencies between repositories."""

    __tablename__ = "_dependency"
    dependent_repository: Mapped[int] = mapped_column(Integer, ForeignKey("_repository.id"), primary_key=True)
    dependency_repository: Mapped[int] = mapped_column(Integer, ForeignKey("_repository.id"), primary_key=True)


class AnalysisTable(ORMBase):
    """
    ORM Class for the analysis information.

    This information pertains to a single invocation of the macaron tool.
    """

    __tablename__ = "_analysis"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # noqa: A003
    analysis_time: Mapped[datetime] = mapped_column(RFC3339DateTime, nullable=False)
    repository: Mapped[int] = mapped_column(Integer, ForeignKey("_repository.id"), nullable=False)
    macaron_version: Mapped[str] = mapped_column(String, nullable=False)


class RepositoryAnalysis(ORMBase):
    """Relates repositories to the analysis in which they were scanned."""

    __tablename__ = "_repository_analysis"
    analysis_id: Mapped[int] = mapped_column(Integer, ForeignKey("_analysis.id"), nullable=False, primary_key=True)
    repository_id: Mapped[int] = mapped_column(Integer, ForeignKey("_repository.id"), nullable=False, primary_key=True)


################################################################################
# AnalyzeContext
#    - Tables pertaining to a specific analysis target
################################################################################
class RepositoryTable(ORMBase):
    """ORM Class for a repository."""

    __tablename__ = "_repository"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # noqa: A003
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    remote_path: Mapped[str] = mapped_column(String, nullable=True)
    branch_name: Mapped[str] = mapped_column(String, nullable=False)
    release_tag: Mapped[str] = mapped_column(String, nullable=True)
    commit_sha: Mapped[str] = mapped_column(String, nullable=False)
    commit_date: Mapped[str] = mapped_column(String, nullable=False)


class SLSALevelTable(ORMBase):
    """Table to store the slsa level of a repository."""

    __tablename__ = "_slsa_level"
    repository: Mapped[int] = mapped_column(Integer, ForeignKey("_repository.id"), primary_key=True)
    slsa_level: Mapped[int] = mapped_column(Integer, nullable=False)
    reached: Mapped[bool] = mapped_column(Boolean, nullable=False)


class CheckResultTable(ORMBase):
    """Table to store the result of a check, is automatically added for each check."""

    __tablename__ = "_check_result"
    id: Mapped[int] = mapped_column(  # noqa: A003 # pylint: disable=invalid-name
        Integer, primary_key=True, autoincrement=True
    )
    check_id: Mapped[str] = mapped_column(String, nullable=False)
    repository: Mapped[int] = mapped_column(Integer, ForeignKey("_repository.id"), nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    skipped: Mapped[bool] = mapped_column(Boolean, nullable=False)


class CheckFactsTable:
    """
    Declarative mixin for check results.

    All tables for check results must inherit this class, these fields are automatically filled in by the analyzer.
    """

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # noqa: A003
    check_result: Mapped[int] = mapped_column(String, ForeignKey("_check_result.id"), nullable=False)
    repository: Mapped[int] = mapped_column(Integer, ForeignKey("_repository.id"), nullable=False)


class PolicyTable(CheckFactsTable, ORMBase):
    """ORM Class for a Policy."""

    # TODO: policy_check should store the policy, its evaluation result, and which PROVENANCE it was applied to
    #       rather than only linking to the repository

    __tablename__ = "_policy"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # noqa: A003
    policy_id: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=True)
    policy_type: Mapped[str] = mapped_column(String, nullable=False)
    sha: Mapped[str] = mapped_column(String, nullable=False)
    text: Mapped[str] = mapped_column(String, nullable=False)
