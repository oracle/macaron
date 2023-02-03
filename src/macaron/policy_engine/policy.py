# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the parser for provenance policy."""

import hashlib
import logging
import os
from dataclasses import dataclass, field
from functools import reduce
from typing import Any, Callable, NamedTuple, Optional, Union

import yamale
from yamale.schema import Schema

from macaron.parsers.yaml.loader import YamlLoader
from macaron.policy_engine import cue
from macaron.policy_engine.__main__ import get_generated
from macaron.policy_engine.exceptions import InvalidPolicyError, PolicyRuntimeError
from macaron.policy_engine.souffle import SouffleError, SouffleWrapper
from macaron.slsa_analyzer.table_definitions import PolicyTable
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
    failed:
        The list of repositories, policy pairs failing
    passed:
        The list of repository, policy pairs passing

    """

    text: str
    sha: str
    _result: dict | None
    failed: list["SoufflePolicy.PolicyResult"]
    passed: list["SoufflePolicy.PolicyResult"]

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
            policy = row[0]
            repo = int(row[1])
            reason = None
            if len(row) >= 3:
                reason = row[2]
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
        policy = SoufflePolicy(text="", sha="", _result=None, failed=[], passed=[])
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

        failed = list(filter(lambda x: x.repo == repository, self.failed))
        passed = list(filter(lambda x: x.repo == repository, self.passed))
        return passed, failed

    def evaluate(self, database_path: os.PathLike | str, repo: int | None = None) -> bool:
        """
        Evaluate this policy against a database.

        Parameters
        ----------
        database_path: os.PathLike | str
            The file path to the database
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
                res = sfl.interpret_text(prelude + self.text)
                self._result = res
        except SouffleError as err:
            logger.error("Unable to evaluate policy %s", err)
            return False

        all_failed = list(map(SoufflePolicy.PolicyResult.from_row, self._result["failed_policies"]))
        all_passed = list(map(SoufflePolicy.PolicyResult.from_row, self._result["passed_policies"]))
        self.failed = all_failed
        self.passed = all_passed
        if repo:
            failed = list(filter(lambda x: x.repo == repo, all_failed))
            return any(failed)
        return any(all_failed)


# pylint: disable=invalid-name
@dataclass
class Policy:
    """The policy is used to validate a target provenance.

    Parameters
    ----------
    ID : str
        The ID of the policy.
    description : str
        The description of the policy.
    target: str
        The full repository name this policy applies to
    text: str
        The full text content of the policy
    sha:
        The sha256sum digest of the policy

    """

    ID: str
    description: str
    target: str
    text: str | None
    sha: str | None
    _definition: PolicyDef | None = field(default=None)
    _validator: PolicyFn | None = field(default=None)
    POLICY_TYPE = "YAML_DIFF"

    def get_policy_table(self) -> PolicyTable:
        """Get the bound ORM object for the policy."""
        return PolicyTable(
            policy_id=self.ID, description=self.description, policy_type=self.POLICY_TYPE, sha=self.sha, text=self.text
        )

    @classmethod
    def make_cue_policy(cls, macaron_path: os.PathLike | str, policy_path: os.PathLike | str) -> Optional["Policy"]:
        """Construct a cue policy."""
        logger.info("Generating a policy from file %s", policy_path)
        policy: Policy = Policy("", "", "", None, None, None, None)

        with open(policy_path, encoding="utf-8") as f:
            policy.text = f.read()
            policy.sha = str(hashlib.sha256(policy.text.encode("utf-8")).hexdigest())

        try:
            cue.init(macaron_path)
        except PolicyRuntimeError:
            return None

        policy.ID = "?"
        policy.target = "any"
        policy.description = "?"
        policy._validator = lambda provenance: cue.validate(policy.text, provenance)  # type: ignore
        return policy

    @classmethod
    def make_policy(cls, file_path: os.PathLike | str) -> Optional["Policy"]:
        """Generate a Policy from a policy yaml file.

        Parameters
        ----------
        file_path : os.PathLike
            The path to the yaml file.

        Returns
        -------
        Policy | None
            The Policy instance that has been initialized.
        """
        logger.info("Generating a policy from file %s", file_path)
        policy: Policy = Policy("", "", "", None, None, None, None)

        # First load from the policy yaml file. We also validate the policy
        # against the schema.
        policy_content = YamlLoader.load(file_path, POLICY_SCHEMA)

        if not policy_content:
            logger.error("Cannot load the policy yaml file at %s.", file_path)
            return None

        with open(file_path, encoding="utf-8") as f:
            policy.text = f.read()
            policy.sha = str(hashlib.sha256(policy.text.encode("utf-8")).hexdigest())

        policy.ID = policy_content.get("metadata").get("id")
        policy.description = policy_content.get("metadata").get("description")
        if "target" in policy_content.get("metadata"):
            policy.target = policy_content.get("metadata").get("target")
        else:
            policy.target = "any"

        # Then we parse the policy content.
        try:
            logger.info("Parsing the policy definition of Policy %s", policy.ID)
            policy._validator = _gen_policy_func(policy_content.get("definition"))
        except InvalidPolicyError as error:
            logger.error("Cannot parse the policy definition for %s - %s", policy, error)
            return None

        logger.info("Successfully loaded %s", policy)

        # Ignore mypy because mypy flag policy as not having the same type
        # as Policy.
        return policy

    def __str__(self) -> str:
        return f"Policy(id='{self.ID}', description='{self.description}')"

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
