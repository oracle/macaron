# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the Registry class for loading checks."""

import concurrent.futures
import fnmatch
import inspect
import logging
import queue
import re
import sys
from collections.abc import Callable
from copy import deepcopy
from graphlib import CycleError, TopologicalSorter
from typing import Any

from macaron.config.defaults import defaults
from macaron.errors import CheckRegistryError
from macaron.graph.graph import get_transitive_closure
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import (
    CheckInfo,
    CheckResult,
    CheckResultData,
    CheckResultType,
    SkippedInfo,
)
from macaron.slsa_analyzer.runner import Runner
from macaron.slsa_analyzer.slsa_req import ReqName

logger: logging.Logger = logging.getLogger(__name__)


CheckTree = dict[str, "CheckTree"]


class Registry:
    """This abstract class is used to store checks in Macaron."""

    _all_checks_mapping: dict[str, BaseCheck] = {}

    # Map between a check and any child checks that depend on it.
    _check_relationships_mapping: dict[str, dict[str, CheckResultType]] = {}

    # The format for check id
    _id_format = re.compile(r"^mcn_([a-z]+_)+([0-9]+)$")

    # The directed graph that represents the check relationships.
    # This graph is used to get the order in which checks are
    # executed. Each node of this graph is the id of a check.
    _graph: TopologicalSorter = TopologicalSorter()

    # True if we have already call Registry._graph.prepare
    # (which will then call TopologicalSorter.prepare).
    # This is because TopologicalSorter will raise an Exception
    # if we call TopologicalSorter.prepare multiple times.
    # Reference: https://docs.python.org/3/library/graphlib.html
    _is_graph_ready = False

    def __init__(self) -> None:
        """Initiate the Registry instance."""
        self.runners: list[Runner] = []
        self.runner_queue: queue.Queue = queue.Queue()

        # Use default values.
        self.runner_num = 1
        self.runner_timeout = 5

        self.checks_to_run: list[str] = []
        self.no_parent_checks: list[str] = []

        self.check_tree: CheckTree = {}

    def register(self, check: BaseCheck) -> None:
        """Register the check.

        This method will terminate the program if there is any error while registering the check.

        Parameters
        ----------
        check : BaseCheck
            The Check to be registered.
        """
        if not self._validate_check(check):
            logger.error("The check registered is invalid.")
            sys.exit(1)

        # Update the check relationship mapping. Even though a check might not depend on any other checks, other
        # checks can still depend on it, and therefore it might have been initialized and added to the mapping
        # already. So we need to check if it already exists in `_check_relationships_mapping`.
        if not check.depends_on:
            self.no_parent_checks.append(check.check_info.check_id)
            if check.check_info.check_id not in self._check_relationships_mapping:
                self._check_relationships_mapping[check.check_info.check_id] = {}
        else:
            for parent_relationship in check.depends_on:
                if not self._add_relationship_entry(check.check_info.check_id, parent_relationship):
                    logger.error("Cannot load relationships of check %s.", check.check_info.check_id)
                    sys.exit(1)

        if not self._add_node(check):
            logger.critical("Cannot add check %s to the directed graph.", check.check_info.check_id)
            sys.exit(1)

        self._all_checks_mapping[check.check_info.check_id] = check

    def _add_relationship_entry(self, check_id: str, relationship: tuple[str, CheckResultType]) -> bool:
        """Add the relationship of a check to a parent.

        Parameters
        ----------
        check_id : str
            The id of the check we are loading.
        relationship: tuple[str, CheckResultType]
            The tuple that contains the parent check id and the status this check depends on.

        Returns
        -------
        bool
            True if succeeded else False.
        """
        if not self._validate_check_relationship(relationship):
            logger.error(
                "Unknown relationship definition %s defined in check %s.",
                str(relationship),
                check_id,
            )
            return False

        parent_id = relationship[0]
        parent_status = relationship[1]

        if check_id == parent_id:
            logger.error("Check %s cannot depend on itself.", check_id)
            return False

        parent = self._check_relationships_mapping.get(parent_id)
        if not parent:
            logger.debug(
                "Creating new entry for parent check %s in the relationship mapping.",
                parent_id,
            )
            self._check_relationships_mapping[parent_id] = {}
        else:
            existed_label = parent.get(check_id)
            if existed_label:
                logger.error(
                    "The relationship between %s and parent %s has been defined with label %s.",
                    check_id,
                    parent_id,
                    existed_label,
                )
                return False

        self._check_relationships_mapping[parent_id][check_id] = parent_status
        return True

    @staticmethod
    def _validate_check(check: Any) -> bool:
        """Return True if a registered BaseCheck instance is valid.

        Parameters
        ----------
        check : BaseCheck
            The check to be validated.

        Returns
        -------
        bool
            True if check is valid, else False.
        """
        if not isinstance(check, BaseCheck):
            logger.error(
                "The registered Check is of type %s. Please register a child class of BaseCheck.",
                type(check).__name__,
            )
            return False

        # Try to get the path to the check module file
        check_module = inspect.getmodule(check)
        if not check_module:
            logger.critical("Cannot resolve the Check module.")
            return False
        try:
            check_file_abs_path = inspect.getsourcefile(check_module)
        except TypeError as err:
            # Shouldn't happen as we have checked for the type of the
            # registered Check.
            logger.critical("Cannot located the source file of the check. Error: %s.", str(err))
            return False

        if check_file_abs_path:
            if not (hasattr(check, "result_on_skip") and isinstance(check.result_on_skip, CheckResultType)):
                logger.error("The status_on_skipped in the Check at %s is invalid.", str(check.check_info.check_id))
                return False

            if not Registry._validate_check_id_format(check.check_info.check_id):
                logger.error(
                    "The check_id %s in the Check at %s has an invalid format.",
                    str(check.check_info.check_id),
                    check_file_abs_path,
                )
                return False

            if not Registry._validate_eval_reqs(check.check_info.eval_reqs):
                logger.error(
                    "The eval reqs defined for Check %s are invalid.",
                    str(check.check_info.check_id),
                )
                return False

            if Registry._all_checks_mapping.get(check.check_info.check_id):
                logger.error(
                    "The check_id %s in the Check at %s has already been registered. Please use a different ID.",
                    check.check_info.check_id,
                    check_file_abs_path,
                )
                return False
        else:
            logger.critical(
                "Cannot resolve the source file of %s even when it has been resolved.",
                check.check_info.check_id,
            )
            return False

        return True

    def _add_node(self, check: BaseCheck) -> bool:
        """Add this check to the directed graph along with its predecessors.

        This method only fails if Registry._graph.prepare() has already been called.

        References
        ----------
            - https://docs.python.org/3/library/graphlib.html#graphlib.TopologicalSorter.add

        Parameters
        ----------
        check : BaseCheck
            The check to be added.

        Returns
        -------
        bool
            True if added successfully, else False.
        """
        try:
            parent_ids = (parent[0] for parent in check.depends_on)

            # Add this check to the graph first.
            # The graphlib library supports adding duplicated nodes
            # or predecessors without breaking the graph.
            self._graph.add(check.check_info.check_id)

            # Add predecessors.
            for parent in parent_ids:
                self._graph.add(check.check_info.check_id, parent)

            return True
        except ValueError as err:
            logger.error(str(err))
            return False

    @staticmethod
    def _validate_eval_reqs(eval_reqs: list[Any]) -> bool:
        """Return True if the all evaluated requirements are valid.

        Parameters
        ----------
        eval_reqs : list[SLSAReq]
            The list of evaluated requirements in the check.

        Returns
        -------
        bool
            True if all evaluated requirements are valid, else False.
        """
        for req in eval_reqs:
            if not isinstance(req, ReqName):
                return False

        return True

    @staticmethod
    def _validate_check_id_format(check_id: Any) -> bool:
        """Return True if the check id is in the correct format.

        A valid check id must have the following properties:
            - The general format: ``mcn_<name>_<digits>``
            - In ``name``, only lowercase alphabetical letters are allowed. If ``name`` contains multiple \
            words, they must be separated by underscores.

        Parameters
        ----------
        check_id : str
            The id of the check we are registering.

        Returns
        -------
        bool
            True if the id is valid, else False.

        Examples
        --------
        >>> Registry._validate_check_id_format("mcn_the_check_name_123")
        True

        >>> Registry._validate_check_id_format("Some_Thing', '', '%(*$)")
        False
        """
        if (not isinstance(check_id, str)) or (not Registry._id_format.match(check_id)):
            return False

        return True

    @staticmethod
    def _validate_check_relationship(relationship: Any) -> bool:
        """Return True if the relationship is valid.

        A valid relationship tuple contains 2 elements:
            - The id of the parent check (str)
            - The status for the parent check (CheckResultType)

        Parameters
        ----------
        relationship : Any
            The relationship to validate.

        Returns
        -------
        bool
            True if valid, else False.
        """
        if (
            relationship
            and isinstance(relationship, tuple)
            and len(relationship) == 2
            and isinstance(relationship[0], str)
            and isinstance(relationship[1], CheckResultType)
        ):
            return True

        return False

    def get_parents(self, check_id: str) -> set[str]:
        """Return the ids of all direct parent checks.

        Parameters
        ----------
        check_id : str
            The check id we want to obtain the parents.

        Returns
        -------
        set[str]
            The set of ids for all parent checks.
        """
        check = self._all_checks_mapping.get(check_id)
        if not check:
            # It won't happen as we have validated the existence of check_id in registry.prepare().
            return set()

        return {relation[0] for relation in check.depends_on}

    def get_children(self, check_id: str) -> set[str]:
        """Return the ids of all direct children checks.

        Parameters
        ----------
        check_id : str
            The check id we want to obtain the children.

        Returns
        -------
        set[str]
            The set of ids for all children checks.
        """
        # If this check is not defined in the check relationships mapping, it means that it
        # doesn't have any children, hence the default empty dictionary.
        return set(self._check_relationships_mapping.get(check_id, {}))

    def get_final_checks(self, ex_pats: list[str], in_pats: list[str]) -> list[str]:
        """Return a set of the check ids to run from the exclude and include glob patterns.

        The exclude and include glob patterns are used to match against the id of registered checks.

        Including a check would effectively include all transitive parents of that check.
        Excluding a check would effectively exclude all transitive children of that check.

        The final list of checks to run would be the included checks minus the excluded checks.

        Parameters
        ----------
        ex_pats : list[str]
            The list of excluded glob patterns.
        in_pats : list[str]
            The list of included glob patterns.

        Returns
        -------
        list[str]
            The set of final checks to run

        Raises
        ------
        CheckRegistryError
            If there is an error while obtaining the final checks to run.
        """
        all_checks = self._all_checks_mapping.keys()

        if "*" in in_pats and not ex_pats:
            return list(all_checks)

        if "*" in ex_pats:
            return []

        exclude: set[str] = set()
        for ex_pat in set(ex_pats):
            exclude.update(fnmatch.filter(all_checks, ex_pat))

        transitive_ex: set[str] = set()
        for direct_ex in exclude:
            transitive_children = get_transitive_closure(
                node=direct_ex,
                get_successors=self.get_children,
            )

            transitive_ex.update(transitive_children)

        include: set[str] = set()
        for in_pat in set(in_pats):
            include.update(fnmatch.filter(all_checks, in_pat))

        transitive_in: set[str] = set()
        for direct_in in include:
            transitive_parents = get_transitive_closure(
                node=direct_in,
                get_successors=self.get_parents,
            )

            transitive_in.update(transitive_parents)

        include.update(transitive_in)
        exclude.update(transitive_ex)

        final = include.difference(exclude)
        return list(final)

    def scan(self, target: AnalyzeContext) -> dict[str, CheckResult]:
        """Run all checks on a target repo.

        Parameters
        ----------
        target : AnalyzeContext
            The object containing processed data for the target repo.
        skipped_checks : list[SkippedInfo]
            The list of skipped checks information.

        Returns
        -------
        dict[str, CheckResult]
            The mapping between the check id and its result.
        """
        all_checks = self._all_checks_mapping
        results: dict[str, CheckResult] = {}
        skipped_checks: list[SkippedInfo] = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.runner_num) as executor:
            # To allow the graph to be traversed again after this run.
            graph = deepcopy(self._graph)

            # This queue contains the futures instances returned from
            # submitting tasks to the ThreadPoolExecutor.
            futures_queue: queue.Queue = queue.Queue()

            # This queue contains the currently available Check instances
            # for the Runners to pickup and execute.
            check_queue: queue.Queue = queue.Queue()

            while graph.is_active():
                # Enqueue all checks that are available to be processed.
                # After a runner has completed a check, we call graph.done(check_id)
                # to signal the TopologicalSorter to proceed with more nodes.
                # These newly proceeded nodes are returned to us in the next call
                # to graph.get_ready().
                for check_id in graph.get_ready():
                    logger.debug("Check to run %s", check_id)
                    check = all_checks.get(check_id)

                    if not check:
                        message = f"Check {check_id} is not defined yet. Please add the implementation for {check_id}."
                        logger.error(message)
                        results[check_id] = CheckResult(
                            check=CheckInfo(
                                check_id=check_id,
                                check_description="",
                                eval_reqs=[],
                            ),
                            result=CheckResultData(
                                justification=[message],
                                result_type=CheckResultType.UNKNOWN,
                                result_tables=[],
                            ),
                        )
                        graph.done(check_id)
                    else:
                        check_queue.put(check)

                # If the runner_queue is empty, wait for a runner to become available.
                if self.runner_queue.empty():
                    while not futures_queue.empty():
                        current_runner, current_check_id, current_future = futures_queue.get()

                        try:
                            # Explicitly check and exit if the check has raised any exception.
                            if current_future.exception(timeout=self.runner_timeout):
                                logger.error("Exception in check %s: %s.", current_check_id, current_future.exception())
                                logger.info("Check %s has failed.", current_check_id)
                                current_future.cancel()
                                self.runner_queue.put(current_runner)
                                return results
                        except (
                            concurrent.futures.TimeoutError,
                            concurrent.futures.CancelledError,
                            concurrent.futures.InvalidStateError,
                            concurrent.futures.BrokenExecutor,
                        ):
                            # The check is still running, put the future back into the queue.
                            futures_queue.put((current_runner, current_check_id, current_future))

                            # Break out if a runner is available.
                            if not self.runner_queue.empty():
                                break

                        if current_future.done():
                            result = current_future.result()
                            results[current_check_id] = result
                            graph.done(current_check_id)

                # Run the check with the next available runner.
                if self.runner_queue.empty():
                    # We should not reach here.
                    logger.critical("Could not find any available runners. Stop the analysis...")
                    return results
                runner: Runner = self.runner_queue.get()

                if check_queue.empty():
                    # We should not reach here.
                    logger.error("Could not find any checks to run.")
                    return results
                next_check: BaseCheck = check_queue.get()

                # Don't run excluded checks
                if next_check.check_info.check_id not in self.checks_to_run:
                    logger.debug("Check %s is disabled by user configuration.", next_check.check_info.check_id)
                    graph.done(next_check.check_info.check_id)
                    self.runner_queue.put(runner)
                    continue

                # Look up check results to see if this check should be run based on its parent status
                skipped_info = self._should_skip_check(next_check, results)
                if skipped_info:
                    skipped_checks.append(skipped_info)

                # Submit check to run with specified runner.
                submitted_future = executor.submit(runner.run, target, next_check, skipped_checks)
                futures_queue.put(
                    (
                        runner,
                        next_check.check_info.check_id,
                        submitted_future,
                    )
                )

                # If the check queue is empty, wait for current check to complete.
                if check_queue.empty():
                    while not futures_queue.empty():
                        current_runner, current_check_id, current_future = futures_queue.get()

                        try:
                            # Explicitly check and exit if the check has raised any exception.
                            if current_future.exception(timeout=self.runner_timeout):
                                logger.error("Exception in check %s: %s.", current_check_id, current_future.exception())
                                logger.info("Check %s has failed.", current_check_id)
                                current_future.cancel()
                                return results
                        except concurrent.futures.TimeoutError:
                            # The check is still running, put the future back into the queue.
                            futures_queue.put((current_runner, current_check_id, current_future))

                            # Break out if more checks can be processed.
                            if not self.runner_queue.empty():
                                break

                        if current_future.done():
                            result = current_future.result()
                            results[current_check_id] = result
                            graph.done(current_check_id)

        return results

    def _init_runners(self) -> None:
        """Initiate runners from values in defaults.ini."""
        self.runner_num = defaults.getint("runner", "runner_num", fallback=1)
        self.runner_timeout = defaults.getint("runner", "timeout", fallback=5)
        if not self.runners:
            self.runners.extend([Runner(self, i) for i in range(self.runner_num)])

        for runner in self.runners:
            self.runner_queue.put(runner)

    def prepare(self) -> bool:
        """Prepare for the analysis.

        Return False if there are any errors that cause the analysis to not be able to begin.

        Returns
        -------
        bool
            True if there are no errors, else False.
        """
        self._init_runners()

        # Only support 1 runner at the moment.
        if not self.runners or len(self.runners) != 1:
            logger.critical("Invalid number of runners.")
            return False

        if not self._all_checks_mapping:
            logger.error("Cannot run because there is no check registered.")
            return False

        try:
            if not self._is_graph_ready:
                self._graph.prepare()
                self._is_graph_ready = True
        except CycleError as error:
            logger.error("Found circular dependencies in registered checks: %s", str(error))
            return False

        ex_pats = defaults.get_list(section="analysis.checks", item="exclude", fallback=[])
        in_pats = defaults.get_list(section="analysis.checks", item="include", fallback=["*"])
        try:
            checks_to_run = registry.get_final_checks(ex_pats, in_pats)
        except CheckRegistryError as error:
            logger.error(error)
            return False

        if len(checks_to_run) == 0:
            logger.info("There are no checks to run according to the exclude/include configuration.")
            return False
        self.checks_to_run = checks_to_run

        # Store the check tree as dictionary to be used in the HTML report.
        if not self.check_tree:
            self.check_tree = self._get_check_tree_as_dict()

        return True

    @staticmethod
    def get_all_checks_mapping() -> dict[str, BaseCheck]:
        """Return the dictionary that includes all registered checks.

        Returns
        -------
        dict[str, BaseCheck]
            The all checks mapping dictionary.
        """
        return Registry._all_checks_mapping

    @staticmethod
    def get_all_checks_relationships() -> dict[str, dict[str, CheckResultType]]:
        """Return the dictionary that includes all check relationship mappings.

        Returns
        -------
        dict[str, dict[CheckResultType, str]]
            The checks relationship mapping dictionary.
        """
        return Registry._check_relationships_mapping

    @staticmethod
    def _should_skip_check(check: BaseCheck, results: dict[str, CheckResult]) -> SkippedInfo | None:
        """Return a SkippedInfo instance if this check should be skipped.

        A check is only skipped if at least one of its parent relationships is not satisfied.

        Parameters
        ----------
        check : BaseCheck
            The next check to execute.
        results : dict[str, CheckResult]
            The dictionary that stores the results of finished checks.

        Returns
        -------
        SkippedInfo
            The SkippedInfo if this check should be skipped, else None.

        Examples
        --------
        A depends on B PASSED. When B FAILED, A will be skipped.
        """
        for parent in check.depends_on:
            parent_id: str = parent[0]
            expect_status: CheckResultType = parent[1]

            # Look up the result of this parent check
            parent_result = results[parent_id]
            got_status = parent_result.result.result_type

            if got_status != expect_status:
                suppress_comment = (
                    f"Check {check.check_info.check_id} is set to {check.result_on_skip.value} "
                    f"because {parent_id} {got_status.value}."
                )
                skipped_info = SkippedInfo(check_id=check.check_info.check_id, suppress_comment=suppress_comment)
                return skipped_info

        return None

    def _get_check_tree_as_dict(self) -> CheckTree:
        """Return a dictionary representation of the check relationships.

        Returns
        -------
        CheckTree
            A nested dictionary that represent the relationship between
            checks. For each mapping (K, V) in the returned dictionary, K is the check id and
            V is a dictionary that contains the children of that check.

        Examples
        --------
        Given the following checks and their relationships:

        .. code-block::

            mcn_provenance_available_1
            |-- mcn_provenance_level_three_1
                |-- mcn_provenance_expectation_1
            mcn_version_control_system_1
            |-- mcn_trusted_builder_level_three_1

        The resulting dictionary will be:

        .. code-block::

            {
                'mcn_provenance_available_1': {
                    'mcn_provenance_level_three_1': {
                        'mcn_provenance_expectation_1': {}
                    }
                },
                'mcn_version_control_system_1': {
                    'mcn_trusted_builder_level_three_1': {}
                },
            }
        """

        def _traverse(
            node: str,
            get_successors: Callable[[str], set[str]],
        ) -> CheckTree:
            """We assume that the data structure we are working with is a tree.

            Therefore, no cycle checking is needed.
            """
            result = {}
            successors = get_successors(node)
            for successor in successors:
                result[successor] = _traverse(successor, get_successors)

            return result

        result: CheckTree = {}
        for check in self.no_parent_checks:
            result[check] = _traverse(check, self.get_children)

        return result


registry = Registry()
