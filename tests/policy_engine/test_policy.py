# Copyright (c) 2022 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the policies supported by the policy engine."""

import os
import subprocess  # nosec B404
from pathlib import Path

import pytest

from macaron.policy_engine.policy_engine import (
    add_policy_check_requirements,
    format_policy_results,
    get_generated,
    policy_check_requirement_facts,
    run_souffle,
)

POLICY_DIR = Path(__file__).parent.joinpath("resources").joinpath("policies")
POLICY_FILE = os.path.join(POLICY_DIR, "valid", "testpolicy.dl")
DATABASE_FILE = os.path.join(Path(__file__).parent.joinpath("resources", "facts", "macaron.db"))


@pytest.fixture()
def database_setup() -> None:
    """Prepare the database file."""
    if not os.path.exists(DATABASE_FILE):
        if os.path.exists(DATABASE_FILE + ".gz"):
            subprocess.run(["gunzip", "-k", DATABASE_FILE + ".gz"], check=True, shell=False)  # nosec B603 B607


def test_dump_prelude(database_setup) -> None:  # type: ignore # pylint: disable=unused-argument,redefined-outer-name
    """Test loading the policy from file."""
    res = str(get_generated(DATABASE_FILE))
    assert len(res) > 10


def test_eval_policy(database_setup) -> None:  # type: ignore # pylint: disable=unused-argument,redefined-outer-name
    """Test loading the policy from file."""
    with open(POLICY_FILE, encoding="utf-8") as file:
        policy_content = file.read()
    res = run_souffle(os.path.join(POLICY_FILE, DATABASE_FILE), policy_content)
    component_purl = "pkg:github.com/slsa-framework/slsa-verifier@fc50b662fcfeeeb0e97243554b47d9b20b14efac"
    assert res["passed_policies"] == [["trusted_builder"]]
    assert res["component_satisfies_policy"] == [["1", component_purl, "trusted_builder"]]
    assert res["failed_policies"] == [["aggregate_l4"], ["aggregate_l2"]]
    assert res["component_violates_policy"] == [
        ["1", component_purl, "aggregate_l4"],
        ["1", component_purl, "aggregate_l2"],
    ]
    assert res["policy_component_check_failures"] == []
    assert res["policy_dependency_check_failures"] == []


def test_policy_check_requirement_facts_extracts_literal_checks() -> None:
    """Test Macaron generates policy check requirement facts from literal check rules."""
    policy_content = """
Policy("github_actions_vulns", component_id, "GitHub Actions Vulnerability Detection") :-
    check_passed(component_id, "mcn_githubactions_vulnerabilities_1").

Policy("malware_deps", component_id, "Malware Detection") :-
    check_passed(component_id, "mcn_detect_malicious_metadata_1"),
    check_passed(dependency, "mcn_detect_malicious_metadata_1").
"""

    facts = policy_check_requirement_facts(policy_content)

    assert 'policy_check_requirement("__macaron_no_policy__", "__macaron_no_check__").' in facts
    assert 'policy_check_requirement("github_actions_vulns", "mcn_githubactions_vulnerabilities_1").' in facts
    assert 'policy_check_requirement("malware_deps", "mcn_detect_malicious_metadata_1").' in facts


@pytest.mark.usefixtures("database_setup")
def test_policy_evidence_only_includes_policy_checks() -> None:
    """Test policy evidence includes only checks required by the violated policy."""
    component_purl = "pkg:github.com/slsa-framework/slsa-verifier@fc50b662fcfeeeb0e97243554b47d9b20b14efac"
    policy_content = f"""
#include "prelude.dl"

Policy("check-malware", component_id, "Check malware detection.") :-
    check_passed(component_id, "mcn_detect_malicious_metadata_1").

apply_policy_to("check-malware", component_id) :-
    is_component(component_id, "{component_purl}").
"""

    res = run_souffle(DATABASE_FILE, add_policy_check_requirements(policy_content))

    assert res["failed_policies"] == [["check-malware"]]
    assert res["policy_component_check_failures"] == [
        ["check-malware", component_purl, "mcn_detect_malicious_metadata_1"]
    ]


def test_format_policy_results_includes_evidence() -> None:
    """Test policy results are formatted with failed policies, components, and evidence."""
    summary = format_policy_results(
        {
            "passed_policies": [],
            "failed_policies": [["check-dependencies"]],
            "component_satisfies_policy": [],
            "component_violates_policy": [
                ["1", "pkg:pypi/demo-internal-service@1.0.0", "check-dependencies"]
            ],
            "policy_dependency_check_failures": [
                [
                    "check-dependencies",
                    "pkg:pypi/demo-internal-service@1.0.0",
                    "pkg:pypi/durabletask-demo@1.4.2",
                    "mcn_detect_malicious_metadata_1",
                ]
            ],
        }
    )

    assert "Result: FAILED" in summary
    assert "Failed policies:\n  - check-dependencies" in summary
    assert (
        "policy: check-dependencies, "
        "component: pkg:pypi/demo-internal-service@1.0.0, "
        "dependency: pkg:pypi/durabletask-demo@1.4.2, "
        "failed check: mcn_detect_malicious_metadata_1"
    ) in summary
