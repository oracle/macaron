# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the Analyze Context class.

The AnalyzeContext is used to store the data of the repository being analyzed.
"""

import logging
import os
from collections import defaultdict
from typing import Any, TypedDict

from macaron.database.table_definitions import Component, SLSALevel
from macaron.slsa_analyzer.checks.check_result import CheckResult, CheckResultType
from macaron.slsa_analyzer.ci_service.base_ci_service import BaseCIService
from macaron.slsa_analyzer.git_service import BaseGitService
from macaron.slsa_analyzer.git_service.base_git_service import NoneGitService
from macaron.slsa_analyzer.levels import SLSALevels
from macaron.slsa_analyzer.provenance.expectations.expectation import Expectation
from macaron.slsa_analyzer.provenance.intoto import InTotoPayload, InTotoV01Payload
from macaron.slsa_analyzer.provenance.intoto.v01 import InTotoV01Statement
from macaron.slsa_analyzer.provenance.intoto.v1 import InTotoV1Statement
from macaron.slsa_analyzer.slsa_req import ReqName, SLSAReqStatus, create_requirement_status_dict
from macaron.slsa_analyzer.specs.build_spec import BuildSpec
from macaron.slsa_analyzer.specs.ci_spec import CIInfo
from macaron.slsa_analyzer.specs.package_registry_spec import PackageRegistryInfo

logger: logging.Logger = logging.getLogger(__name__)


class ChecksOutputs(TypedDict):
    """Data computed at runtime by checks."""

    git_service: BaseGitService
    """The git service information for the target software component."""
    build_spec: BuildSpec
    """The build spec inferred for the target software component."""
    ci_services: list[CIInfo]
    """The CI services information for the target software component."""
    is_inferred_prov: bool
    """True if we cannot find the provenance and Macaron need to infer the provenance."""
    expectation: Expectation | None
    """The expectation to verify the provenance for the target software component."""
    package_registries: list[PackageRegistryInfo]
    """The package registries for the target software component."""
    provenance: InTotoPayload | None
    """The provenance payload for the target software component."""
    provenance_repo_url: str | None
    """The repository URL extracted from provenance, if applicable."""
    provenance_commit_digest: str | None
    """The commit digest extracted from provenance, if applicable."""
    provenance_verified: bool
    """True if the provenance exists and has been verified against a signed companion provenance."""


class AnalyzeContext:
    """This class contains data of the current analyzed repository."""

    def __init__(
        self,
        component: Component,
        macaron_path: str = "",
        output_dir: str = "",
    ):
        """Initialize instance.

        Parameters
        ----------
        component: Component
            The target software component.
        macaron_path : str
            The Macaron's root path.
        output_dir : str
            The output dir.
        """
        # The component attribute should be accessed via the `component` property.
        self._component = component

        self.ctx_data: dict[ReqName, SLSAReqStatus] = create_requirement_status_dict()

        self.slsa_level = SLSALevels.LEVEL0
        # Indicate whether this repo fully reach a level or
        # it's just compliant for a SLSA level
        self.is_full_reach = False

        # The Macaron root path where the wrapper files exist.
        self.macaron_path = macaron_path

        # The output dir to store all files
        self.output_dir = output_dir

        # The check results from the analysis
        self.check_results: dict[str, CheckResult] = {}

        # Add the data computed at runtime to the dynamic_data attribute.
        # This attribute should be accessed via the `dynamic_data` property.
        self._dynamic_data: ChecksOutputs = ChecksOutputs(
            git_service=NoneGitService(),
            build_spec=BuildSpec(tools=[], purl_tools=[]),
            ci_services=[],
            package_registries=[],
            is_inferred_prov=True,
            expectation=None,
            provenance=None,
            provenance_repo_url=None,
            provenance_commit_digest=None,
            provenance_verified=False,
        )

    @property
    def component(self) -> Component:
        """Return the object associated with a target software component.

        This property contains the information about a software component, such as it's
        corresponding repository and dependencies.


        Returns
        -------
        Component
        """
        return self._component

    @property
    def dynamic_data(self) -> ChecksOutputs:
        """Return the `dynamic_data` object that contains various intermediate representations.

        This object is used to pass various models and intermediate representations from the backend
        in Macaron to checks. A check can also store intermediate results in this object to be used
        by checks that depend on it. However, please avoid adding arbitrary attributes to this object!

        We recommend to take a look at the attributes in this object before writing a new check. Chances
        are that what you try to implement is already implemented and the results are available in the
        `dynamic_data` object.

        Returns
        -------
        ChecksOutputs
        """
        return self._dynamic_data

    @property
    def provenances(self) -> dict[str, list[InTotoV01Statement | InTotoV1Statement]]:
        """Return the provenances data as a dictionary.

        Returns
        -------
        dict[str, list[InTotoV01Statement | InTotoV1Statement] ]
            A dictionary in which each key is a CI service's name and each value is
            the corresponding provenance payload.
        """
        try:
            ci_services = self.dynamic_data["ci_services"]

            # By default, initialize every key with an empty list.
            result: dict[str, list[InTotoV01Statement | InTotoV1Statement]] = defaultdict(list)
            for ci_info in ci_services:
                result[ci_info["service"].name].extend(
                    provenance.payload.statement for provenance in ci_info["provenances"]
                )
            package_registry_entries = self.dynamic_data["package_registries"]
            for package_registry_entry in package_registry_entries:
                result[package_registry_entry.package_registry.name].extend(
                    provenance.payload.statement for provenance in package_registry_entry.provenances
                )
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
                "Update requirement %s: set to %s.",
                req_name.value,
                status,
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

    def get_slsa_level_table(self) -> SLSALevel:
        """Return filled ORM table storing the level for this component."""
        # TODO: right now `slsa_level` is always 0 and `is_full_reach` is False,
        # which needs to be handled properly.
        return SLSALevel(
            component=self.component,
            slsa_level=int(self.slsa_level),
            reached=self.is_full_reach,
        )

    def get_dict(self) -> dict:
        """Return the dictionary representation of the AnalyzeContext instance."""
        _sorted_on_id = sorted(self.check_results.values(), key=lambda item: item.check.check_id)
        # Remove result_tables since we don't have a good json representation for them.
        sorted_on_id = []
        for res in _sorted_on_id:
            # res is CheckResult
            res_dict: dict = dict(res.get_summary())
            res_dict.pop("result_tables")
            sorted_on_id.append(res_dict)
        sorted_results = sorted(sorted_on_id, key=lambda item: item["result_type"], reverse=True)
        check_summary = {
            result_type.value: len(result_list) for result_type, result_list in self.get_check_summary().items()
        }
        check_summary_sorted = dict(sorted(check_summary.items()))
        result = {
            "info": {
                "full_name": self.component.purl,
                "local_cloned_path": (
                    os.path.relpath(self.component.repository.fs_path, self.output_dir)
                    if self.component.repository
                    else "Unable to find a repository."
                ),
                "remote_path": self.component.repository.remote_path if self.component.repository else "",
                "branch": self.component.repository.branch_name if self.component.repository else "",
                "commit_hash": self.component.repository.commit_sha if self.component.repository else "",
                "commit_date": self.component.repository.commit_date if self.component.repository else "",
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
            match check_result.result.result_type:
                case CheckResultType.PASSED:
                    result[CheckResultType.PASSED].append(check_result)
                case CheckResultType.SKIPPED:
                    result[CheckResultType.SKIPPED].append(check_result)
                case CheckResultType.FAILED:
                    result[CheckResultType.FAILED].append(check_result)
                case CheckResultType.DISABLED:
                    result[CheckResultType.DISABLED].append(check_result)
                case CheckResultType.UNKNOWN:
                    result[CheckResultType.UNKNOWN].append(check_result)

        return result

    def __str__(self) -> str:
        """Return the string representation of the AnalyzeContext instance."""
        output = ""

        check_summary = self.get_check_summary()

        for check_result in self.check_results.values():
            output = "".join(
                [
                    output,
                    f"Check {check_result.check.check_id}: {check_result.check.check_description}\n",
                    f"\t{check_result.result.result_type.value}\n",
                ]
            )

        for result_type, result_list in check_summary.items():
            output = "".join([output, f"{len(result_list)} checks {result_type.value}\n"])

        return output


def store_inferred_build_info_results(
    ctx: AnalyzeContext,
    ci_info: CIInfo,
    ci_service: BaseCIService,
    trigger_link: str,
    job_id: str | None = None,
    step_id: str | None = None,
    step_name: str | None = None,
    callee_node_type: str | None = None,
) -> None:
    """Store the data related to the build.

    Parameters
    ----------
    ctx: AnalyzeContext
        The analyze context object.
    ci_info: CIInfo
        The CI data representation.
    ci_service: BaseCIService
        The CI service representation.
    trigger_link: str
        The link to the CI workflow.
    job_id: str | None
        The CI job ID.
    step_id: str | None
        The CI step ID.
    step_name: str | None
        The CI step name.
    callee_node_type: str | None
        The callee node type in the call graph.
    """
    # TODO: This data is potentially duplicated in the check result tables. Instead of storing the data
    # in the context object, retrieve it from the result tables and remove this function.
    if isinstance(ci_info["build_info_results"], InTotoV01Payload):
        predicate: Any = ci_info["build_info_results"].statement["predicate"]
        predicate["buildType"] = f"Custom {ci_service.name}"
        predicate["builder"]["id"] = trigger_link
        predicate["invocation"]["configSource"]["uri"] = (
            f"{ctx.component.repository.remote_path}" f"@refs/heads/{ctx.component.repository.branch_name}"
        )
        predicate["invocation"]["configSource"]["digest"]["sha1"] = ctx.component.repository.commit_sha
        predicate["invocation"]["configSource"]["entryPoint"] = trigger_link
        predicate["buildConfig"]["jobID"] = job_id or ""
        predicate["buildConfig"]["stepID"] = step_id or ""
        predicate["buildConfig"]["stepName"] = step_name or ""
        predicate["buildConfig"]["calleeType"] = callee_node_type
