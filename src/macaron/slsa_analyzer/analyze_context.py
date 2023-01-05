# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the Analyze Context class.

The AnalyzeContext is used to store the data of the repository being analyzed.
"""

import logging
import os
from typing import TypedDict

from pydriller.git import Git
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Table

from macaron.database.database_manager import ORMBase
from macaron.policy_engine.policy import Policy
from macaron.slsa_analyzer.build_tool.base_build_tool import NoneBuildTool
from macaron.slsa_analyzer.checks.check_result import CheckResult, CheckResultType
from macaron.slsa_analyzer.git_service import BaseGitService
from macaron.slsa_analyzer.git_service.base_git_service import NoneGitService
from macaron.slsa_analyzer.levels import SLSALevels
from macaron.slsa_analyzer.slsa_req import ReqName, SLSAReq, get_requirements_dict
from macaron.slsa_analyzer.specs.build_spec import BuildSpec
from macaron.slsa_analyzer.specs.ci_spec import CIInfo

logger: logging.Logger = logging.getLogger(__name__)


class RepositoryTable(ORMBase):
    """ORM Class for a repository."""

    __tablename__ = "_repository"
    id = Column(Integer, primary_key=True, autoincrement=True)
    full_name = Column(String, nullable=False)
    remote_path = Column(String, nullable=True)
    branch_name = Column(String, nullable=False)
    release_tag = Column(String, nullable=True)
    commit_sha = Column(String, nullable=False)
    commit_date = Column(String, nullable=False)


class ChecksOutputs(TypedDict):
    """Data computed at runtime by checks."""

    git_service: BaseGitService
    """The git service information for this repository."""
    build_spec: BuildSpec
    """The build spec inferred for this repository."""
    ci_services: list[CIInfo]
    """The CI services information for this repository."""
    is_inferred_prov: bool
    """True if we cannot find the provenance and Macaron need to infer the provenance."""
    policy: Policy | None
    """The policy to verify the provenance for this repository."""


class AnalyzeContext:
    """This class contains data of the current analyzed repository."""

    def __init__(
        self,
        full_name: str,
        repo_path: str,
        git_obj: Git,
        branch_name: str = "",
        commit_sha: str = "",
        commit_date: str = "",
        macaron_path: str = "",
        output_dir: str = "",
        remote_path: str = "",
        current_date: str = "",
    ):
        """Initialize instance.

        Parameters
        ----------
        full_name : str
            Repository name in ``<owner>/<repo_name>`` format.
        repo_path : str
            Target repository path.
        git_obj : Git
            The Git object for the target path.
        branch_name : str
            The target branch.
        commit_sha : str
            The commit sha of the target repo.
        commit_date : str
            The commit date of the target repo.
        macaron_path : str
            The Macaron's root path.
        output_dir : str
            The output dir.
        remote_path : str
            The remote path for the target repo.
        """
        # <owner>/<repo_name>
        self.repo_full_name = full_name

        # <repo_name>
        if full_name.rfind("/") != -1:
            self.repo_name = self.repo_full_name.split("/")[1]
        else:
            self.repo_name = full_name

        self.repo_path = repo_path
        self.ctx_data: dict[ReqName, SLSAReq] = get_requirements_dict()
        self.git_obj = git_obj
        self.file_list = git_obj.files()

        self.slsa_level = SLSALevels.LEVEL0
        # Indicate whether this repo fully reach a level or
        # it's just compliant for a SLSA level
        self.is_full_reach = False

        self.branch_name = branch_name
        self.commit_sha = commit_sha
        self.commit_date = commit_date
        self.current_date = current_date
        self.remote_path = remote_path

        # The Macaron root path where the wrapper files exist.
        self.macaron_path = macaron_path

        # The output dir to store all files
        self.output_dir = output_dir

        # The check results from the analysis
        self.check_results: dict[str, CheckResult] = {}

        # Add the data computed at runtime to the dynamic_data attribute.
        self.dynamic_data: ChecksOutputs = ChecksOutputs(
            git_service=NoneGitService(),
            build_spec=BuildSpec(tool=NoneBuildTool()),
            ci_services=[],
            is_inferred_prov=True,
            policy=None,
        )

    @property
    def provenances(self) -> dict:
        """Return the provenances data as a dictionary.

        Returns
        -------
        dict
        """
        try:
            ci_services = self.dynamic_data["ci_services"]
            result = {}
            for ci_info in ci_services:
                result[ci_info["service"].name] = ci_info["provenances"]
            return result
        except KeyError:
            return {}

    # TODO: refactor as this information is related to the reporter not analyze context
    @property
    def is_inferred_provenance(self) -> bool:
        """Return True if the provenance for this repo is an inferred one.

        Returns
        -------
        bool
        """
        return self.dynamic_data["is_inferred_prov"]

    def update_req_status(self, req_name: ReqName, status: bool, feedback: str) -> None:
        """Update the status of a single requirement.

        Parameters
        ----------
        req_name : ReqName
            The requirement to update.
        status : bool
            True if the requirement passes, else False.
        feedback: str
            The feedback to the requirement.
        """
        req = self.ctx_data.get(req_name)
        if req:
            logger.debug(
                "Update requirement %s: set to %s (%s)",
                req_name.value,
                status,
                feedback,
            )
            self.ctx_data[req_name].set_status(status, feedback)
        else:
            logger.debug("Trying to update non-existing requirement, ignoring ...")

    def bulk_update_req_status(self, req_list: list, status: bool, feedback: str) -> None:
        """Update the status of a requirements in ``req_list``.

        Parameters
        ----------
        req_list : list[ReqName]
            The list of requirement to update.
        status : bool
            True if the requirement passes, else False.
        feedback : str
            The feedback to the requirement.
        """
        for req in req_list:
            self.update_req_status(req, status, feedback)

    @staticmethod
    def get_analysis_result_table(table_name: str) -> Table:
        """Get the table definition to store an analysis result.

        Parameters
        ----------
        table_name: str
            Name of the table to create.
        """
        return Table(
            table_name,
            ORMBase.metadata,
            Column("analysis_id", Integer, ForeignKey("_analysis.id"), primary_key=True),
            Column("full_name", String, unique=False),
            Column("branch_name", String),
            Column("commit_sha", String),
            Column("commit_date", String),
            Column("slsa_level", String),
            Column("is_full_reach", Boolean),
            *(Column(key.name, Boolean) for key in get_requirements_dict()),
        )

    def get_repository_data(self) -> dict:
        """Get the data for the repository table."""
        return {
            "full_name": self.repo_full_name,
            "commit_date": self.commit_date,
            "branch_name": self.branch_name,
            "commit_sha": self.commit_sha,
            "remote_path": self.remote_path,
        }

    def get_analysis_result_data(self) -> dict:
        """Get the dictionary of all the necessary data to be inserted into the database."""
        return {
            "full_name": self.repo_full_name,
            "branch_name": self.branch_name,
            "commit_sha": self.commit_sha,
            "commit_date": self.commit_date,
            "slsa_level": str(self.slsa_level.value),
            "is_full_reach": self.is_full_reach,
            **{key.name: value.is_pass for key, value in self.ctx_data.items()},
        }

    def get_dict(self) -> dict:
        """Return the dictionary representation of the AnalyzeContext instance."""
        rel_local_clone_path = os.path.relpath(self.repo_path, self.output_dir)
        sorted_on_id = sorted(self.check_results.values(), key=lambda item: item["check_id"])
        sorted_results = sorted(sorted_on_id, key=lambda item: item["result_type"], reverse=True)
        check_summary = {
            result_type.value: len(result_list) for result_type, result_list in self.get_check_summary().items()
        }
        check_summary_sorted = dict(sorted(check_summary.items()))
        result = {
            "info": {
                "full_name": self.repo_full_name,
                "local_cloned_path": rel_local_clone_path,
                "remote_path": self.remote_path,
                "branch": self.branch_name,
                "commit_hash": self.commit_sha,
                "commit_date": self.commit_date,
            },
            "provenances": {
                "is_inferred": self.is_inferred_provenance,
                "content": self.provenances,
            },
            "checks": {"summary": check_summary_sorted, "results": sorted_results},
        }
        return result

    def get_check_summary(self) -> dict[CheckResultType, list[CheckResult]]:
        """Return the summary of all checks results for the target repository.

        Returns
        -------
        dict[CheckResultType, list[CheckResult]]
            The mapping of the check result type and the related check results.
        """
        result: dict[CheckResultType, list[CheckResult]] = {result_type: [] for result_type in CheckResultType}

        for check_result in self.check_results.values():
            match check_result["result_type"]:
                case CheckResultType.PASSED:
                    result[CheckResultType.PASSED].append(check_result)
                case CheckResultType.SKIPPED:
                    result[CheckResultType.SKIPPED].append(check_result)
                case CheckResultType.FAILED:
                    result[CheckResultType.FAILED].append(check_result)
                case CheckResultType.DISABLED:
                    result[CheckResultType.DISABLED].append(check_result)

        return result

    def __str__(self) -> str:
        """Return the string representation of the AnalyzeContext instance."""
        output = ""

        check_summary = self.get_check_summary()

        for check_result in self.check_results.values():
            output = "".join(
                [
                    output,
                    f"Check {check_result['check_id']}: {check_result['check_description']}\n",
                    f"\t{check_result['result_type'].value}\n",
                ]
            )

        for result_type, result_list in check_summary.items():
            output = "".join([output, f"{len(result_list)} checks {result_type.value}\n"])

        return output
