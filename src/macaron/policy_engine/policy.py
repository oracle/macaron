# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the parser for provenance policy."""

import logging
import os
from dataclasses import dataclass, field
from functools import reduce
from typing import Any, Callable, Generic, TypeVar, Union

import yamale
from yamale.schema import Schema

from macaron.parsers.yaml.loader import YamlLoader

logger: logging.Logger = logging.getLogger(__name__)

SCHEMA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "policy_schema.yaml")

POLICY_SCHEMA: Schema = yamale.make_schema(SCHEMA_DIR)

SubscriptPathType = list[Union[str, int]]
Primitive = Union[str, bool, int, float]
PolicyDef = Union[Primitive, dict, list]
PolicyFn = Callable[[Any], bool]
GPolicy = TypeVar("GPolicy", bound="Policy")


class InvalidPolicyError(Exception):
    """Happen when the policy is invalid."""


class PolicyRuntimeError(Exception):
    """Happen if there are errors while validating the policy against a target."""


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


def _gen_policy_func(policy: PolicyDef, path: SubscriptPathType = None) -> PolicyFn:
    """Get the policy verify function from the policy data.

    Parameters
    ----------
    policy : PolicyType
        The policy data.
    path : SubscriptPathType
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
    res_path: SubscriptPathType = [] if not path else path
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


# pylint: disable=invalid-name
@dataclass
class Policy(Generic[GPolicy]):
    """The policy is used to validate a target provenance.

    Parameters
    ----------
    ID : str
        The ID of the policy.
    description : str
        The description of the policy.
    """

    ID: str
    description: str
    _definition: PolicyDef | None = field(default=None)
    _validator: PolicyFn | None = field(default=None)

    @classmethod
    def make_policy(cls, file_path: os.PathLike | str) -> GPolicy | None:
        """Generate a Policy from a policy yaml file.

        Parameters
        ----------
        file_path : os.PathLike
            The path to the yaml file.

        Returns
        -------
        GPolicy | None
            The Policy instance that has been initialized.
        """
        logger.info("Generating a policy from file %s", file_path)
        policy: Policy = Policy("", "", None, None)

        # First load from the policy yaml file. We also validate the policy
        # against the schema.
        policy_content = YamlLoader.load(file_path, POLICY_SCHEMA)
        if not policy_content:
            logger.error("Cannot load the policy yaml file at %s.", file_path)
            return None

        policy.ID = policy_content.get("metadata").get("id")
        policy.description = policy_content.get("metadata").get("description")

        # Then we parse the policy content.
        try:
            logger.info("Parsing the policy definition of Policy %s", policy.ID)
            policy._validator = _gen_policy_func(policy_content.get("definition"))
        except InvalidPolicyError as error:
            logger.error("Cannot parse the policy definition for %s - %s", policy, error)
            return None

        logger.info("Successfully loaded %s", policy)

        # Ignore mypy because mypy flag policy as not having the same type
        # as GPolicy.
        return policy  # type: ignore

    def __str__(self) -> str:
        return f"Policy(id='{self.ID}', description='{self.description}')"

    def validate(self, prov: Any) -> bool:
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
