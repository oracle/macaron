# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""The cue module invokes the CUE schema validator."""

import ctypes
import json
import os
from typing import Callable

from macaron import MACARON_PATH
from macaron.errors import CUEExpectationError, CUERuntimeError
from macaron.util import JsonType

# Load the CUE shared library.
cue = ctypes.CDLL(os.path.join(MACARON_PATH, "bin", "cuevalidate.so"))


def get_target(expectation: str | None) -> str:
    """Get the analysis target of the expectation.

    Parameters
    ----------
    expectation: str | None
        The cue expectation content.

    Returns
    -------
    str
        The analysis target identifier. Returns an empty string if no target found.

    Raises
    ------
    CUERuntimeError, CUEExpectationError
        If expectation is invalid or unable to get the target by invoking the shared library.
    """
    if not expectation:
        raise CUEExpectationError("CUE expectation is empty.")

    cue.target.restype = ctypes.c_void_p

    def _errcheck(
        result: ctypes.c_void_p, func: Callable, args: tuple  # pylint: disable=unused-argument
    ) -> ctypes.c_void_p:
        if not result:
            raise CUERuntimeError("Unable to find target field in CUE expectation.")
        return result

    cue.target.errcheck = _errcheck  # type: ignore
    expectation_buffer = ctypes.create_string_buffer(bytes(expectation, encoding="utf-8"))
    target_ptr = cue.target(expectation_buffer)
    res_bytes = ctypes.string_at(target_ptr)

    # Even though Python & Go have a garbage collector that will free up unused memory,
    # the documentation says it is the caller's responsibility to free up the C string
    # allocated memory. See https://pkg.go.dev/cmd/cgo
    free = cue.free
    free.argtypes = [ctypes.c_void_p]
    free(target_ptr)

    return res_bytes.decode("utf-8")


def validate_expectation(expectation: str | None, prov: JsonType) -> bool:
    """Validate a json document against a cue expectation.

    Parameters
    ----------
    expectation: str | None
        The cue expectation content.
    prov: JsonType
        The provenance payload.

    Returns
    -------
    bool
        Return true if expectation is validated.

    Raises
    ------
    CUERuntimeError, CUEExpectationError
        If expectation is invalid or unable to validate the expectation by invoking the shared library.
    """
    if not expectation:
        raise CUEExpectationError("CUE policies is empty.")

    expectation_buffer = ctypes.create_string_buffer(bytes(expectation, encoding="utf-8"))
    prov_buffer = ctypes.create_string_buffer(bytes(json.dumps(prov), encoding="utf-8"))

    def _errcheck(result: int, func: Callable, args: tuple) -> int:  # pylint: disable=unused-argument
        if result == -1:
            raise CUERuntimeError("Unable to validate the CUE expectation")
        return result

    cue.target.errcheck = _errcheck  # type: ignore
    result = bool(cue.validate(expectation_buffer, prov_buffer))
    return result
