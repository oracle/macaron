# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""The policy registry module manages policies about provenances and the whole analysis."""

import logging
import os
from typing import Any, Optional

from macaron.policy_engine.policy import Policy, SoufflePolicy

logger: logging.Logger = logging.getLogger(__name__)


class PolicyRegistry:
    """
    The policy registry class stores policies and their results.

    Parameters
    ----------
    macaron_path: str
        The path to the macaron module
    policy_paths: list[str]
        The list of policy file paths. ``all((os.isfile(path) for path in policy_paths))`` must be True.
    """

    policies: dict[str, Policy]
    souffle_policies: list[SoufflePolicy]
    evaluated: bool

    def __init__(self, macaron_path: str, policy_paths: list[str]) -> None:
        self.policies: dict[str, Policy] = {}
        self.souffle_policies: list[SoufflePolicy] = []
        self.evaluated = False

        for policy_path in policy_paths:
            _, ext = os.path.splitext(policy_path)
            if ext in (".yaml", ".yml"):
                policy = Policy.make_policy(policy_path)
                if policy:
                    self.policies[policy.target] = policy
            elif ext in (".cue",):
                policy = Policy.make_cue_policy(macaron_path, policy_path)
                if policy:
                    self.policies[policy.target] = policy
            elif ext == ".dl":
                sfl_policy = SoufflePolicy.make_policy(policy_path)
                if sfl_policy:
                    self.souffle_policies.append(sfl_policy)
            else:
                logger.error("Unsupported policy format: %s", policy_path)

    def get_policy_for_target(self, repo_full_name: str) -> Optional[Policy]:
        """
        Get the policy that applies to a repository.

        Parameters
        ----------
        repo_full_name: str
            The full name of the repository, formatted "organization/repo-name"

        Returns
        -------
        Optional[Policy]
            A policy if one is found, otherwise None.
        """
        if repo_full_name in self.policies:
            return self.policies[repo_full_name]
        if "any" in self.policies:
            return self.policies["any"]
        return None

    def evaluate_souffle_policies(self, database_path: str, restrict_to_analysis: int | None = None) -> list[Any]:
        """Evaluate all known souffle policies.

        Parameters
        ----------
        database_path: str
            The path to the database file to evaluate the policy against
        restrict_to_analysis: int | None
            Optional, if is not None then restrict policy evaluation to the repositories associated with the analysis id
            ``restrict_to_analysis``.

        Returns
        -------
        list[Any]
            The list of analysis results where the analysis failed.
        """
        fail_results = []
        for policy in self.souffle_policies:
            policy.evaluate(database_path=database_path, analysis_id=restrict_to_analysis)
            if any(policy.get_failed()):
                logger.info("Failed policy %s", policy.get_failed())
                fail_results += policy.get_failed()
            if any(policy.get_passed()):
                logger.info("Passed policy %s", policy.get_passed())
        self.evaluated = True
        return fail_results

    def get_souffle_results(
        self, repo_id: Optional[int] = None
    ) -> tuple[list[SoufflePolicy.PolicyResult], list[SoufflePolicy.PolicyResult]]:
        """
        Return the passing and failing policy results for all known souffle policies.

        Parameters
        ----------
        repo_id: Optional[int]
            The id (primary key) of the repository to get the policy results for. If none then all results are returned.

        Returns
        -------
        tuple[list[Any], list[Any]]
            passing_results, failing_results. Lists of passing and failing policy results.
        """
        if not self.evaluated:
            raise ValueError("Must first evaluate policies")

        failed = []
        passed = []

        def keep(res: Any) -> bool:
            return (repo_id is None) or (res.repo == repo_id)

        for policy in self.souffle_policies:
            passed += list(filter(keep, policy.get_passed()))
            failed += list(filter(keep, policy.get_failed()))

        return passed, failed
