# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the parser for provenance policy."""

import hashlib
import logging
import os
from dataclasses import dataclass, field
from functools import reduce
from typing import Any, Callable, NamedTuple, Optional, Self, Union

import yamale
from yamale.schema import Schema

from macaron.database.table_definitions import PolicyTable
from macaron.parsers.yaml.loader import YamlLoader
from macaron.policy_engine.exceptions import InvalidPolicyError, PolicyRuntimeError
from macaron.policy_engine.policy_engine import copy_prelude, get_generated
from macaron.policy_engine.souffle import SouffleError, SouffleWrapper
from macaron.policy_engine.souffle_code_generator import restrict_to_analysis
from macaron.util import JsonType

logger: logging.Logger = logging.getLogger(__name__)

SCHEMA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "policy_schema.yaml")

POLICY_SCHEMA: Schema = yamale.make_schema(SCHEMA_DIR)

SubscriptPathType = list[Union[str, int]]
Primitive = Union[str, bool, int, float]
PolicyDef = Union[Primitive, dict, list, None]
PolicyFn = Callable[[Any], bool]


def _get_val(data: Any, path: SubscriptPathType, default: Any = None) -> Any:
    """Return the value for an element by subscripting ``data`` using ``path``.

    The subscription can be performed for both list and dict (given that ``path`` accepts
    both str and int elements). If an error happens, this method will always return the
    ``default`` value.

    Parameters
    ----------
    data : Any
        The data to perform subscripting on.
    path : Iterable[str, int]
        Contains the keys or index to perform subscripting.

    Returns
    -------
    Any
        The target value.

    Examples
    --------
    >>> a = {"A": {"B" : 5, "C": [1, 2]}}
    >>> _get_val(a, ["A", "B"])
    5
    >>> _get_val(a, [])
    {'A': {'B': 5, 'C': [1, 2]}}
    >>> _get_val(a, ["A"])
    {'B': 5, 'C': [1, 2]}
    >>> _get_val(a, ["A", "C", 0])
    1
    >>> print(_get_val(a, None))
    None
    """
    try:
        return reduce(lambda x, y: x[y], path, data)
    except (KeyError, TypeError, IndexError):
        return default


def _get_path_as_str(path: SubscriptPathType) -> str:
    result = ""
    for ele in path:
        result = ".".join([result, str(ele)])
    return result.lstrip(".")


def _gen_policy_func(policy: PolicyDef, path: Optional[SubscriptPathType] = None) -> PolicyFn:
    """Get the policy verify function from the policy data.

    Parameters
    ----------
    policy : PolicyType
        The policy data.
    path : Optional[SubscriptPathType]
        Describe the path taken to get to the current ``policy``.

    Returns
    -------
    Callable
        A function to verify any provenance according to the policy.

    Raises
    ------
    InvalidPolicyError
        If the provided policy is invalid.
    """
    res_path: SubscriptPathType = path or []
    match policy:
        case str() | bool() | int() | float():
            logger.debug("%sPrimitive(policy=%s, path=%s)", "\t" * len(res_path), str(policy), res_path)

            def parse(target: Any) -> bool:
                """Parse the primitive target policy.

                The actual comparison happens at this level.
                Therefore the primitives' functions has error loggings.
                """
                if policy != _get_val(target, res_path):
                    logger.error(
                        "%s: expected %s, got %s", _get_path_as_str(res_path), policy, _get_val(target, res_path)
                    )
                    return False

                logger.info("%s: validation successful.", _get_path_as_str(res_path))
                return True

            return parse

        case list():
            logger.debug("%sList(policy=%s, path=%s)", "\t" * len(res_path), str(policy), res_path)
            list_subs: list[Callable] = []
            for index, ele in enumerate(policy):
                new_path = res_path + [index]
                list_subs.append(_gen_policy_func(ele, new_path))
            return lambda x: all(sub(x) for sub in list_subs)

        case dict():
            logger.debug("%sDict(policy=%s, path=%s)", "\t" * len(res_path), str(policy), res_path)
            dict_subs: list[Callable] = []
            for key, value in policy.items():
                new_path = res_path + [key]
                dict_subs.append(_gen_policy_func(value, new_path))
            return lambda x: all(sub(x) for sub in dict_subs)

        case None:
            logger.debug("%sNoneType(path=%s)", "\t" * len(res_path), res_path)
            return lambda x: not _get_val(x, res_path)

        case _:
            raise InvalidPolicyError(f"No support for policy {policy}")


@dataclass
class SoufflePolicy:
    """

    A high level for about the analysis described in souffle datalog.

    Parameters
    ----------
    text: str
        The full text content of the policy
    sha: str
        The sha256 sum digest for the policy text


    """

    text: str
    sha: str
    filename: str
    # The result returned by souffle
    _result: dict | None
    # The list of repository, policy pairs failing
    _failed: list["SoufflePolicy.PolicyResult"]
    # The list of repository, policy pairs passing
    _passed: list["SoufflePolicy.PolicyResult"]

    class PolicyResult(NamedTuple):
        """
        Stores the result of a souffle policy.

        Parameters
        ----------
        policy: str
            The unique identifier for the policy
        repo: int
            The primary key of the repository the result applies to
        reason: str | None
            Optional justification for the result
        """

        policy: str
        repo: int
        reason: str | None

        @staticmethod
        def from_row(row: list[str]) -> "SoufflePolicy.PolicyResult":
            """
            Construct a policy result from a row returned by souffle.

            Parameters
            ----------
            row: list[str]
                A list conforming to ["policy name", "repo primary key"], and optionally a third value storing feedback.
            """
            repo = int(row[0])
            reason = row[1]
            policy = row[2]
            return SoufflePolicy.PolicyResult(policy, repo, reason)

    @classmethod
    def make_policy(cls, file_path: os.PathLike | str) -> Optional["SoufflePolicy"]:
        """
        Create a souffle policy.

        Parameters
        ----------
        file_path: os.PathLike | str
            The file path to the policy
        """
        policy = SoufflePolicy(
            text="", sha="", filename=str(os.path.basename(file_path)), _result=None, _failed=[], _passed=[]
        )
        with open(file_path, encoding="utf-8") as file:
            policy.text = file.read()
            policy.sha = str(hashlib.sha256(policy.text.encode("utf-8")).hexdigest())
        return policy

    def result_for_repo(
        self, repository: int
    ) -> tuple[list["SoufflePolicy.PolicyResult"], list["SoufflePolicy.PolicyResult"]]:
        """
        Get the passing and failing policies for a repository.

        Parameters
        ----------
        repository: int
            The primary key for the repository record

        Returns
        -------
        tuple[list, list]
            list of passing policy results, list of failing policy results
        """
        if self._result is None:
            raise ValueError("Policy not evaluated yet.")

        failed = list(filter(lambda x: x.repo == repository, self._failed))
        passed = list(filter(lambda x: x.repo == repository, self._passed))
        return passed, failed

    def evaluate(
        self, database_path: os.PathLike | str, analysis_id: int | None = None, repo: int | None = None
    ) -> bool:
        """
        Evaluate this policy against a database.

        Parameters
        ----------
        database_path: os.PathLike | str
            The file path to the database
        analysis_id: int | None
            Optional, the analysis instance to restrict the policy analysis to.
        repo: int | None
            Optional, the repository to check for policy compliance

        Returns
        -------
        int
            If a repo is passed: true iff the repo is compliant to the policy
            Otherwise: true iff the whole database is compliant: no policies fail.
        """
        try:
            with SouffleWrapper() as sfl:
                prelude = get_generated(database_path)
                if analysis_id is not None:
                    prelude.update(restrict_to_analysis([analysis_id]))
                copy_prelude(database_path, sfl, prelude=prelude)
                res = sfl.interpret_text(self.text)
                self._result = res
        except SouffleError as err:
            logger.error("Unable to evaluate policy %s", err)
            return False

        all_failed = list(map(SoufflePolicy.PolicyResult.from_row, self._result["repo_violates_policy"]))
        all_passed = list(map(SoufflePolicy.PolicyResult.from_row, self._result["repo_satisfies_policy"]))
        self._failed = all_failed
        self._passed = all_passed
        if repo:
            failed = list(filter(lambda x: x.repo == repo, all_failed))
            return any(failed)
        return any(all_failed)

    def get_failed(self) -> list["SoufflePolicy.PolicyResult"]:
        """Return the results for failing policies."""
        return list(self._failed)

    def get_passed(self) -> list["SoufflePolicy.PolicyResult"]:
        """Return the results for passing policies."""
        return list(self._passed)


# pylint: disable=invalid-name
@dataclass
class Policy:
    """The policy is used to validate a target provenance.

    TODO: Refactor this into separate policy classes for cue, yaml, souffle.
        Add abstract method Policy.match(filename) which returns whether this policy can be constructed from the file
        The policy framework (policy_registry.py) iterates filenames and calls match on each policy class, if a policy
        wants to use it that policy is constructed on that file.
    TODO: Refactor to allow more precise policy to provenance matching
        - Metadata for CUE policies
        - Method to resolve multiple policies applying to the same repository-full-name: select policy using provenance
          content and/or commit sha? (However probably want to avoid something too complex like a priority hierarchy)


    Parameters
    ----------
    ID : str
        The ID of the policy.
    description : str
        The description of the policy.
    path: os.PathLike | str
        The path to the policy.
    target: str
        The full repository name this policy applies to
    text: str | None
        The full text content of the policy
    sha: str | None
        The sha256sum digest of the policy
    policy_type: str
        The kind of policy: YAML_DIFF or CUE
    """

    ID: str
    description: str
    path: os.PathLike | str
    target: str
    text: str | None
    sha: str | None
    policy_type: str
    _definition: PolicyDef | None = field(default=None)
    _validator: PolicyFn | None = field(default=None)

    def get_policy_table(self) -> PolicyTable:
        """Get the bound ORM object for the policy."""
        return PolicyTable(
            policy_id=self.ID, description=self.description, policy_type=self.policy_type, sha=self.sha, text=self.text
        )

    @classmethod
    def make_policy(cls, policy_path: os.PathLike | str) -> Self | None:
        """Generate a Policy from a policy yaml file.

        Parameters
        ----------
        policy_path : os.PathLike
            The path to the yaml file.

        Returns
        -------
        Self | None
            The instantiated policy object.
        """
        logger.info("Generating a policy from file %s", policy_path)
        policy: Policy = Policy("", "", "", "", None, None, "YAML_DIFF")

        # First load from the policy yaml file. We also validate the policy
        # against the schema.
        policy_content = YamlLoader.load(policy_path, POLICY_SCHEMA)

        if not policy_content:
            logger.error("Cannot load the policy yaml file at %s.", policy_path)
            return None

        with open(policy_path, encoding="utf-8") as f:
            policy.text = f.read()
            policy.sha = str(hashlib.sha256(policy.text.encode("utf-8")).hexdigest())

        policy.ID = policy_content.get("metadata").get("id")
        policy.description = policy_content.get("metadata").get("description")
        policy.path = policy_path
        if "target" in policy_content.get("metadata"):
            policy.target = policy_content.get("metadata").get("target")
        else:
            policy.target = "any"

        # Then we parse the policy content.
        try:
            logger.debug("Parsing the policy definition of Policy %s", policy.path)
            policy._validator = _gen_policy_func(policy_content.get("definition"))
            logger.info("Successfully loaded %s", policy)
        except InvalidPolicyError as error:
            logger.error("Cannot parse the policy definition for %s - %s", policy, error)
            return None

        # TODO remove type ignore once mypy adds support for Self.
        return policy  # type: ignore

    def __str__(self) -> str:
        return f"Policy(id='{self.ID}', description='{self.description}, path='{self.path}')"

    def validate(self, prov: JsonType) -> bool:
        """Validate the provenance against this policy.

        Parameters
        ----------
        prov : Any
            The provenance to validate.

        Returns
        -------
        bool

        Raises
        ------
        PolicyRuntimeError
            If there are errors happened during the validation process.
        """
        if not self._validator:
            raise PolicyRuntimeError(f"Cannot find the validator for policy {self.ID}")

        return self._validator(prov)
