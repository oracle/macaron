# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module implements CUE policies."""
import hashlib
import logging
import os
from typing import Self

from macaron.policy_engine.cue import cue_validator
from macaron.policy_engine.exceptions import CUEPolicyError, CUERuntimeError
from macaron.policy_engine.policy import Policy

logger: logging.Logger = logging.getLogger(__name__)


class CUEPolicy(Policy):
    """A sub-class of the Policy class to make CUE policies."""

    @classmethod
    def make_policy(cls, policy_path: os.PathLike | str) -> Self | None:
        """Construct a cue policy.

        Note: we require CUE policies to have a "target" field.

        Parameters
        ----------
        policy_path: os.PathLike | str
            The path to the policy file.

        Returns
        -------
        Self
            The instantiated policy object.
        """
        logger.info("Generating a policy from file %s", policy_path)
        policy: Policy = Policy(
            "CUE policy has no ID",
            "CUE policy has no description",
            policy_path,
            "",
            None,
            None,
            "CUE",
        )

        try:
            with open(policy_path, encoding="utf-8") as policy_file:
                policy.text = policy_file.read()
                policy.sha = str(hashlib.sha256(policy.text.encode("utf-8")).hexdigest())
                policy.target = cue_validator.get_target(policy.text)
                policy._validator = (  # pylint: disable=protected-access
                    lambda provenance: cue_validator.validate_policy(policy.text, provenance)
                )
        except (OSError, CUERuntimeError, CUEPolicyError) as error:
            logger.error("CUE policy error: %s", error)
            return None

        # TODO remove type ignore once mypy adds support for Self.
        return policy  # type: ignore
