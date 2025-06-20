# Copyright (c) 2023 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""The cue module invokes the CUE schema validator."""

import os
import subprocess  # nosec B404

from macaron import MACARON_PATH
from macaron.config.defaults import defaults
from macaron.errors import CUEExpectationError, CUERuntimeError


def get_target(expectation_path: str | None) -> str:
    """Get the analysis target of the expectation.

    Parameters
    ----------
    expectation_path: str | None
        The cue expectation path.

    Returns
    -------
    str
        The analysis target identifier. Returns an empty string if no target found.

    Raises
    ------
    CUERuntimeError, CUEExpectationError
        If expectation is invalid or unable to get the target by invoking the shared library.
    """
    if not expectation_path:
        raise CUEExpectationError("CUE expectation path is not provided.")

    cmd = [
        os.path.join(MACARON_PATH, "bin", "cuevalidator"),
        "-target-policy",
        expectation_path,
    ]

    try:
        result = subprocess.run(  # nosec B603
            cmd,
            capture_output=True,
            check=True,
            cwd=MACARON_PATH,
            timeout=defaults.getint("cue_validator", "timeout", fallback=30),
        )
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
    ) as error:
        raise CUERuntimeError("Unable to process CUE expectation.") from error

    if result.returncode == 0:
        return result.stdout.decode("utf-8")

    raise CUEExpectationError("Unable to find target field in CUE expectation.")


def validate_expectation(expectation_path: str, prov_stmt_path: str) -> bool:
    """Validate a json document against a cue expectation.

    Parameters
    ----------
    expectation_path: str
        The cue expectation path.
    prov_stmt_path: str
        The provenance statement path.

    Returns
    -------
    bool
        Return true if expectation is validated.

    Raises
    ------
    CUERuntimeError
        If expectation is invalid or unable to validate the expectation by invoking the shared library.
    """
    cmd = [
        os.path.join(MACARON_PATH, "bin", "cuevalidator"),
        "-validate-policy",
        expectation_path,
        "-validate-provenance",
        prov_stmt_path,
    ]

    try:
        result = subprocess.run(  # nosec B603
            cmd,
            capture_output=True,
            check=True,
            cwd=MACARON_PATH,
            timeout=defaults.getint("cue_validator", "timeout", fallback=30),
        )
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
    ) as error:
        raise CUERuntimeError("Unable to process CUE expectation or provenance.") from error

    if result.returncode == 0:
        if result.stdout.decode("utf-8") == "True":
            return True
        if result.stdout.decode("utf-8") == "False":
            return False

    raise CUERuntimeError("Something unexpected happened while validating the provenance against CUE expectation.")
