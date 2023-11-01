# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Helper functions related to environment variables."""

import os
from collections.abc import Mapping


def get_patched_env(
    patch: Mapping[str, str | None],
    _env: dict[str, str] | None = None,
) -> dict[str, str]:
    """Return a dictionary whose elements copied from ``os.environ`` and are updated according to ``patch``.

    This function does not modify ``os.environ``.

    Parameters
    ----------
    patch : Mapping[str, str | None]
        A mapping (immutable) in which:
        - each key is an environment variable.
        - each value is the value to set to the corresponding environment variable.
        If value is ``None``, the environment variable is "unset".
    _env : dict[str, str] | None
        The environment being updated.
        This is ``None`` by default, in which case ``os.environ`` is being updated.

    Returns
    -------
    dict[str, str]
        The the dictionary contains the patched env variables.
    """
    env = os.environ if _env is None else _env

    # Make a copy of the environment.
    copied_env = dict(env)

    for var, value in patch.items():
        if value is None:
            copied_env.pop(var, None)
        else:
            copied_env[var] = value

    return copied_env
