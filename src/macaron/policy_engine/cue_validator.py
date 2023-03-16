# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""The cue module invokes the CUE schema validator."""

import json
import os
import subprocess  # nosec B404
import tempfile

from macaron.config.defaults import defaults
from macaron.config.global_config import global_config
from macaron.util import JsonType, logger


def get_target(policy_path: str, macaron_path: str = "") -> str:
    """Get the analysis target of the policy.

    Parameters
    ----------
    policy_path: str
        The cue policy path.
    macaron_path : str
        Macaron's root path (optional).

    Returns
    -------
    str
        The analysis target identifier. Returns an empty string if no target found.
    """
    if not macaron_path:
        macaron_path = global_config.macaron_path
    cmd = [os.path.join(macaron_path, "bin", "cue_validator"), "-get-target", "-policy", policy_path]

    try:
        result = subprocess.run(  # nosec B603
            cmd,
            capture_output=True,
            check=True,
            cwd=macaron_path,
            timeout=defaults.getint("cue_validator", "timeout", fallback=30),
        )
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ) as error:
        logger.error("Error while parsing the CUE policy: %s", error)
        return ""

    if result.returncode == 0:
        return result.stdout.decode("utf-8")

    logger.error("Failed to get cue policy target: %s", result.stderr)
    return ""


def validate(policy_path: str, prov: JsonType, macaron_path: str = "") -> bool:
    """Validate a json document against a cue policy.

    Parameters
    ----------
    policy_path: str
        The path to the policy.
    prov: JsonType
        The provenance payload.
    macaron_path: str (optional)
        The path to Macaron package.

    Returns
    -------
    bool
        Return true if policy is validated.
    """
    if not macaron_path:
        macaron_path = global_config.macaron_path

    def _remove_temp_file(temp_file: str | None) -> None:
        """Remove the temp file."""
        if not temp_file or not os.path.exists(temp_file):
            return
        try:
            os.remove(temp_file)
        except OSError as error:
            logger.error("Failed to remove file %s", error)

    prov_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False) as prov_file:
            prov_file.write(json.dumps(prov).encode("utf-8"))
            prov_path = prov_file.name
    except OSError as error:
        logger.error("Failed to pass provenance for validation: %s", error)
        _remove_temp_file(prov_path)
        return False

    cmd = [
        os.path.join(macaron_path, "bin", "cue_validator"),
        "-validate",
        "-policy",
        policy_path,
        "-provenance",
        prov_path,
    ]

    try:
        result = subprocess.run(  # nosec B603
            cmd,
            capture_output=True,
            check=True,
            cwd=macaron_path,
            timeout=defaults.getint("cue_validator", "timeout", fallback=30),
        )
        _remove_temp_file(prov_path)
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
    ) as error:
        logger.error("Error while validating the cue policy: %s", error)
        _remove_temp_file(prov_path)
        return False

    if result.returncode == 0:
        return True

    return False
