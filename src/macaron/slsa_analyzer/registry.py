# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the Registry class for loading checks."""

import fnmatch
import inspect
import logging
import re
import sys
import traceback
from collections.abc import Callable, Iterable
from graphlib import CycleError, TopologicalSorter
from typing import Any, TypeVar

from macaron.config.defaults import defaults
from macaron.errors import CheckRegistryError
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import (
    CheckInfo,
    CheckResult,
    CheckResultData,
    CheckResultType,
    SkippedInfo,
)
from macaron.slsa_analyzer.slsa_req import ReqName

logger: logging.Logger = logging.getLogger(__name__)


CheckTree = dict[str, "CheckTree"]
T = TypeVar("T")


class Registry:
    """This abstract class is used to store checks in Macaron."""

    _all_checks_mapping: dict[str, BaseCheck] = {}

    # Map between a check and any child checks that depend on it.
    _check_relationships_mapping: dict[str, dict[str, CheckResultType]] = {}

    # The format for check id
    _id_format = re.compile(r"^mcn_([a-z]+_)+([0-9]+)$")

    def __init__(self) -> None:
        """Initiate the Registry instance."""
        self.checks_to_run: list[str] = []
        self.no_parent_checks: list[str] = []

        self.check_tree: CheckTree = {}
        self.execution_order: list[str] = []

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
            class_name = check.__name__ if isinstance(check, type) else type(check).__name__
            logger.error(
                "The registered Check %s is not a valid instance of BaseCheck.",
                class_name,
            )

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
        return all(isinstance(req, ReqName) for req in eval_reqs)

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

    @staticmethod
    def get_reachable_nodes(
        node: T,
        get_successors: Callable[[T], Iterable[T]],
    ) -> Iterable[T]:
        """Return the set that contains `node` and nodes that can be transitively reached from it.

        This method obtains the successors of a node from `get_successors`. This `get_successors` function takes
        a node as input and returns a Collection of successors of that node.

        Parameters
        ----------
        node : T
            The start node to find the transitive successors.
        get_successors : Callable[[T], Iterable[T]]
            The function to obtain successors of every node.

        Returns
        -------
        Iterable[T]
            Contains `node` and its transitive successors.
        """
        visited = []
        stack = [node]

        while stack:
            current_node = stack[-1]

            if current_node not in visited:
                visited.append(current_node)

                for successor in get_successors(current_node):
                    if successor not in visited:
                        stack.append(successor)

            else:
                stack.pop()

        return visited

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
            transitive_children = self.get_reachable_nodes(
                node=direct_ex,
                get_successors=self.get_children,
            )

            transitive_ex.update(transitive_children)

        include: set[str] = set()
        for in_pat in set(in_pats):
            include.update(fnmatch.filter(all_checks, in_pat))

        transitive_in: set[str] = set()
        for direct_in in include:
            transitive_parents = self.get_reachable_nodes(
                node=direct_in,
                get_successors=self.get_parents,
            )

            transitive_in.update(transitive_parents)

        include.update(transitive_in)
        exclude.update(transitive_ex)

        final = include.difference(exclude)
        return list(final)

    def get_check_execution_order(self) -> list[str]:
        """Get the execution order of checks.

        This follows the topological order on the check graph.

        Returns
        -------
        list[str]
            A list of check ids representing the order of checks to run.
        """
        graph: TopologicalSorter = TopologicalSorter()
        for node in self._all_checks_mapping:
            graph.add(node)
        for node, children_entries in self._check_relationships_mapping.items():
            for child in children_entries:
                graph.add(child, node)
        return list(graph.static_order())

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

        for check_id in self.execution_order:
            check = all_checks.get(check_id)

            if not check:
                logger.error("Check %s is not defined yet. Please add the implementation for %s.", check_id, check_id)
                results[check_id] = CheckResult(
                    check=CheckInfo(
                        check_id=check_id,
                        check_description="",
                        eval_reqs=[],
                    ),
                    result=CheckResultData(
                        result_type=CheckResultType.UNKNOWN,
                        result_tables=[],
                    ),
                )
                continue

            # Don't run excluded checks
            if check_id not in self.checks_to_run:
                logger.debug(
                    "Check %s is disabled by user configuration.",
                    check.check_info.check_id,
                )
                continue

            # Look up check results to see if this check should be run based on its parent status
            skipped_info = self._should_skip_check(check, results)
            if skipped_info:
                skipped_checks.append(skipped_info)

            try:
                results[check_id] = check.run(target, skipped_info)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logger.error("Exception in check %s: %s. Run in verbose mode to get more information.", check_id, exc)
                logger.debug(traceback.format_exc())
                logger.info("Check %s has failed.", check_id)
                return results

        return results

    def prepare(self) -> bool:
        """Prepare for the analysis.

        Return False if there are any errors that cause the analysis to not be able to begin.

        Returns
        -------
        bool
            True if there are no errors, else False.
        """
        if not self._all_checks_mapping:
            logger.error("Cannot run because there is no check registered.")
            return False

        try:
            self.execution_order = self.get_check_execution_order()
        except CycleError as error:
            logger.error("Found circular dependencies in registered checks: %s", str(error))
            return False

        ex_pats = defaults.get_list(section="analysis.checks", option="exclude", fallback=[])
        in_pats = defaults.get_list(section="analysis.checks", option="include", fallback=["*"])
        try:
            checks_to_run = self.get_final_checks(ex_pats, in_pats)
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
