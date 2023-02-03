# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""The cue module invokes the CUE schema validator."""

import json
import os
from ctypes import CDLL, create_string_buffer

from macaron.policy_engine.exceptions import PolicyRuntimeError
from macaron.util import JsonType, logger

cue: CDLL | None = None  # pylint: disable=C0103


def init(macaron_path: os.PathLike | str) -> None:
    """Load the cue shared library."""
    global cue  # pylint: disable=W0603 disable=C0103
    try:
        if cue is None:
            path = os.path.join(macaron_path, "bin/cuevalidate.so")
            cue = CDLL(path)
    except OSError as err:
        logger.error("Unable to load CUE %s", err)
        raise PolicyRuntimeError() from err


def validate(policy: str, prov: JsonType) -> bool:
    """Validate a json document against a cue policy."""
    if cue is None:
        raise PolicyRuntimeError()

    try:
        policy_buffer = create_string_buffer(bytes(policy, encoding="utf-8"))
        json_buffer = create_string_buffer(bytes(json.dumps(prov), encoding="utf-8"))
        result: bool = cue.validate_json(policy_buffer, json_buffer)
    except OSError as err:
        logger.error("Unable to evaluate CUE policy %s", err)
        raise PolicyRuntimeError() from err

    return result
