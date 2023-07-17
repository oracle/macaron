# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains classes that represent the result of the Macaron analysis."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Generic, Optional, TypedDict, TypeVar

from macaron.config.target_config import Configuration
from macaron.output_reporter.scm import SCMStatus
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.check_result import CheckResultType
from macaron.slsa_analyzer.levels import SLSALevels
from macaron.slsa_analyzer.registry import registry
from macaron.slsa_analyzer.slsa_req import ReqName


class DepSummary(TypedDict):
    """The summary of the dependency analysis."""

    analyzed_deps: int
    """The total number of dependencies analyzed."""
    unique_dep_repos: int
    """The number of unique repos analyzed for all dependencies."""
    checks_summary: list[dict]
    """This list contains mapping between each check ID and how many deps PASSED this check.

    Examples
    --------
    >>> dep_summary["checks_summary"]
    [
        {
            "Check A": 3
        },
        {
            "Check B": 4
        }
    ]
    """
    dep_status: list[dict]
    """This list contains the summaries for all dependency ``Record``.

    See Also
    --------
    Record.get_summary() : Get the summary status for a ``Record`` instance.
    """


RecordNode = TypeVar("RecordNode", bound="Record")
# The documentation below for `TypeVar` is commented out due to a breaking
# change in Sphinx version (^=6.1.0).
# Reported at: https://github.com/oracle/macaron/issues/58.
# """This binds type ``RecordNode`` to ``Record`` and any of its subclasses."""


@dataclass
class Record(Generic[RecordNode]):
    """This class contains the analysis status and data of a repo.

    Parameters
    ----------
    record_id : str
        The id of the record.
    description : str
        The description for this record.
    pre_config : Configuration
        The ``Configuration`` instance used to start the analysis of this repo.
    status : SCMStatus
        The SCM status of this repo.
    context : AnalyzeContext or None
        The context instance for this repo.
    dependencies : list[RecordNode]
        The list of Records for the analyzed dependencies of this repo.

    See Also
    --------
    SCMStatus
    macaron.config.configuration.Configuration
    macaron.slsa_analyzer.analyze_context.AnalyzeContext
    """

    record_id: str
    description: str
    pre_config: Configuration
    status: SCMStatus
    context: AnalyzeContext | None = field(default=None)
    dependencies: list[RecordNode] = field(default_factory=list)

    def get_summary(self) -> dict:
        """Get a dictionary that summarizes the status of this record.

        Returns
        -------
        dict
            The summary of this record.

        Examples
        --------
        >>> record.get_summary()
        {'id': 'apache/maven', 'description': 'Analysis completed', 'report': 'apache.html', 'status': 'AVAILABLE'}
        """
        return {
            "id": self.record_id,
            "description": self.description,
            "report": f"{self.context.component.report_file_name}.html" if self.context else "",
            "status": self.status,
        }

    def get_dict(self) -> dict:
        """Get the dictionary representation of the Record instance.

        Returns
        -------
        dict
            The dictionary representation of this record.
        """
        result = {
            "metadata": {
                "timestamps": datetime.now().isoformat(sep=" ", timespec="seconds"),
            },
            "target": self.context.get_dict() if self.context else {},
            "dependencies": self.get_dep_summary(),
        }
        return result

    def get_dep_summary(self) -> DepSummary:
        """Get the dependency analysis summary data.

        Returns
        -------
        DepSummary
            The dependency analysis summary data.
        """
        result = DepSummary(
            analyzed_deps=0,
            unique_dep_repos=0,
            checks_summary=[
                {"check_id": check_id, "num_deps_pass": 0} for check_id in registry.get_all_checks_mapping()
            ],
            dep_status=[dep.get_summary() for dep in self.dependencies],
        )
        for dep_record in self.dependencies:
            match dep_record.status:
                case SCMStatus.AVAILABLE:
                    result["analyzed_deps"] += 1
                    result["unique_dep_repos"] += 1
                    if dep_record.context:
                        for check_result in dep_record.context.check_results.values():
                            if check_result["result_type"] == CheckResultType.PASSED:
                                for entry in result["checks_summary"]:
                                    if entry["check_id"] == check_result["check_id"]:
                                        entry["num_deps_pass"] += 1
                case SCMStatus.DUPLICATED_SCM:
                    result["analyzed_deps"] += 1

        return result


class Report:
    """This class contains the report content of an analysis."""

    def __init__(self, root_record: Record) -> None:
        """Initialize instance.

        Parameters
        ----------
        root_record : Record
            The record of the main target repository.
        """
        # The record of the target repo in the analysis.
        self.root_record: Record = root_record
        self.record_mapping: dict[str, Record] = {}
        if root_record.context:
            self.record_mapping[root_record.record_id] = root_record

    def get_records(self) -> Iterable[Record]:
        """Get the generator for all records in the report.

        Yields
        ------
        Record
            The record within this report instance.
        """
        yield self.root_record
        yield from self.root_record.dependencies

    def add_dep_record(self, dep_record: Record) -> None:
        """Add a dependency record into the report.

        Parameters
        ----------
        dep_record : Record
            The record of the dependency.
        """
        # Do not add a dependency if it's a duplicate.
        if dep_record.record_id not in self.record_mapping:
            self.root_record.dependencies.append(dep_record)
            if dep_record.context:
                self.record_mapping[dep_record.record_id] = dep_record

    def get_serialized_configs(self) -> Iterable[dict]:
        """Get the generator for the configs content of all dependencies.

        These dependency configurations are determined by the dependency analyzer.
        Note that the status of the configuration might change in the follow up analyses,
        e.g., if a repository is already analyzed, the status changes from "AVAILABLE" to "DUPLICATED".

        Yields
        ------
        dict
            The configs dict of a dependency.
        """
        for record in self.root_record.dependencies:
            yield record.pre_config.options

    def get_ctxs(self) -> Iterable[AnalyzeContext]:
        """Get the generator for all AnalyzeContext instances.

        Yields
        ------
        AnalyzeContext
            The AnalyzeContext instance of a repository.
        """
        if self.root_record.context:
            yield self.root_record.context
        for record in self.root_record.dependencies:
            if record.context:
                yield record.context

    def get_dependencies(self, root_record: Optional[Record] = None) -> Iterable[tuple[AnalyzeContext, AnalyzeContext]]:
        """Get the generator for the dependency relations between repositories.

        Parameters
        ----------
        root_record: Optional[Record]
            The root record to find the dependencies of, if none is provided self.root_record is used.

        Yields
        ------
        Tuple[AnalyzeContext, AnalyzeContext]
            The tuple containing first the parent context followed by the child context.
        """
        if root_record is None:
            root_record = self.root_record
        if root_record.context:
            for record in root_record.dependencies:
                if record.context:
                    yield root_record.context, record.context

    def find_ctx(self, record_id: str) -> AnalyzeContext | None:
        """Find the context instance using the configuration ID.

        Parameters
        ----------
        record_id : str
            The ID to look for the analyze context.

        Returns
        -------
        AnalyzeContext
            The analyze context for the given record ID or None if cannot find.
        """
        record = self.record_mapping.get(record_id, None)
        if record:
            return record.context or None

        return None

    def __str__(self) -> str:
        """Return the string representation of the Report instance."""
        ctx_list = list(self.get_ctxs())
        main_ctx: AnalyzeContext = ctx_list.pop(0)

        output = "".join(
            [
                f"\n{main_ctx.component.purl} ANALYSIS RESULT:\n\n",
                "\nCHECK RESULTS:\n\n",
                str(main_ctx),
                "\nSLSA REQUIREMENT RESULTS:\n",
            ]
        )

        slsa_req_mesg: dict[SLSALevels, list[str]] = {level: [] for level in SLSALevels if level != SLSALevels.LEVEL0}
        for req in main_ctx.ctx_data.values():
            if req.min_level_required != SLSALevels.LEVEL0 and req.is_addressed:
                message = f"{req.name.capitalize()}: " + ("PASSED" if req.is_pass else "FAILED")

                if ctx_list:
                    # Get the fail count for dependencies.
                    fail_count = 0
                    for dep in ctx_list:
                        dep_req = dep.ctx_data.get(ReqName(req.name))
                        if dep_req and not dep_req.is_pass:
                            fail_count += 1
                    message = "".join([message, f" (and {fail_count}/{len(ctx_list)} dependencies FAILED)"])

                slsa_req_mesg[req.min_level_required].append(message)

        for level, mesg_list in slsa_req_mesg.items():
            output = "".join([output, f"\n{level.value}:\n"])
            for mesg in mesg_list:
                output = "".join([output, f"- {mesg}\n"])

        for record in self.get_records():
            if not record.context:
                continue

        return output
