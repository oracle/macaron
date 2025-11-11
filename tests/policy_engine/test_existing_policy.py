# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the existing-policy flag supported by the policy engine."""

import argparse
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from macaron.__main__ import verify_policy


def test_verify_existing_policy_success(tmp_path: Path) -> None:
    """When an existing policy is provided and package-url is valid, verify_policy returns EX_OK."""
    db_file = os.path.join(tmp_path, "macaron.db")
    with open(db_file, "w", encoding="utf-8") as f:
        f.write("")

    # Use a MagicMock for the handler.
    mock_handler = MagicMock()

    # Fake run_policy_engine and generate_vsa that returns a fixed result.
    fake_run = MagicMock(return_value={"passed_policies": [["check-component"]], "failed_policies": []})
    fake_generate_vsa = MagicMock(return_value=None)

    # Fake PolicyReporter class: when called, returns an instance with generate method.
    fake_policy_reporter_cls = MagicMock()
    fake_policy_reporter_inst = MagicMock()
    fake_policy_reporter_inst.generate.return_value = None
    fake_policy_reporter_cls.return_value = fake_policy_reporter_inst

    with (
        patch("macaron.__main__.run_policy_engine", fake_run),
        patch("macaron.__main__.generate_vsa", fake_generate_vsa),
        patch("macaron.__main__.access_handler.get_handler", return_value=mock_handler),
        patch("macaron.__main__.PolicyReporter", fake_policy_reporter_cls),
    ):
        policy_args = argparse.Namespace(
            database=str(db_file),
            show_prelude=False,
            file=None,
            existing_policy="malware-detection",
            package_url="pkg:pypi/django",
        )
        result = verify_policy(policy_args)
        assert result == os.EX_OK


def test_verify_existing_policy_not_found(tmp_path: Path) -> None:
    """Requesting a non-existent policy returns usage error."""
    db_file = os.path.join(tmp_path, "macaron.db")
    with open(db_file, "w", encoding="utf-8") as f:
        f.write("")
    policy_args = argparse.Namespace(
        database=str(db_file),
        show_prelude=False,
        file=None,
        existing_policy="no-such-policy",
        package_url="pkg:pypi/django",
    )
    result = verify_policy(policy_args)
    assert result == os.EX_USAGE
