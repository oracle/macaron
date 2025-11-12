# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Tests that every Datalog template has a matching .description file."""

from pathlib import Path

import macaron


def test_datalog_templates_have_descriptions() -> None:
    """Verify each ``*.dl.template`` has a corresponding ``*.description``."""
    datalog_dir = Path(macaron.__file__).resolve().parent.joinpath("resources", "policies", "datalog")
    templates = sorted(datalog_dir.glob("*.dl.template"))

    missing = []
    for tmpl in templates:
        expected_desc = datalog_dir.joinpath(tmpl.name.replace(".dl.template", ".description"))
        if not expected_desc.exists():
            missing.append((tmpl.name, expected_desc))

    if templates and missing:
        missing_list = ", ".join(f"{t} -> {d}" for t, d in missing)
        raise AssertionError("Missing .description files for the following templates: " + missing_list)
