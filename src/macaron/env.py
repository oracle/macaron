# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Context managers related to environment variables."""

import contextlib
import os
from collections.abc import Generator, Mapping


@contextlib.contextmanager
def patched_env(
    patch: Mapping[str, str | None],
    _env: dict[str, str] | None = None,
) -> Generator[None, None, None]:
    """Create a context in which ``os.environ`` is temporarily updated according to ``patch``.

    Out of the context, ``os.environ`` retains its original state.

    Parameters
    ----------
    patch : Mapping[str, str | None]
        A mapping (immutable) in which:
        - each key is an environment variable
        - each value is the value to set to the corresponding environment variable.
        If value is ``None``, the environment variable is "unset".
    _env : dict[str, str] | None
        The environment being updated.
        This is ``None`` by default, in which case ``os.environ`` is being updated.
    """
    env = os.environ if _env is None else _env

    # Make a copy of the environment before updating.
    before = dict(env)

    for var, value in patch.items():
        if value is None:
            env.pop(var, None)
        else:
            env[var] = value

    yield

    # Restore the environment to the original state.
    env.clear()
    env.update(before)
