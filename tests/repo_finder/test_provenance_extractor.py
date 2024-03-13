# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the provenance extractor on valid example provenances."""
import json

import pytest

from macaron.repo_finder.provenance_extractor import (
    JsonExtractionException,
    ProvenanceExtractionException,
    extract_repo_and_commit_from_provenance,
    json_extract,
)
from macaron.slsa_analyzer.provenance.intoto import validate_intoto_payload
from macaron.util import JsonType


@pytest.fixture(name="slsa_v1_gcb_1_provenance")
def slsa_v1_gcb_1_provenance_() -> str:
    """Return a valid SLSA v1 provenance using build type gcb and sourceToBuild."""
    return """
                {
                    "_type": "https://in-toto.io/Statement/v1",
                    "subject": [],
                    "predicateType": "https://slsa.dev/provenance/v1",
                    "predicate": {
                        "buildDefinition": {
                            "buildType": "https://slsa-framework.github.io/gcb-buildtypes/triggered-build/v1",
                            "externalParameters": {
                                "sourceToBuild": {
                                    "repository": "https://github.com/oracle/macaron"
                                }
                            },
                            "resolvedDependencies": [
                                {
                                    "uri": "git+https://github.com/oracle/macaron@refs/heads/staging",
                                    "digest": { "sha1": "51aa22a42ec1bffa71518041a6a6d42d40bf50f0" }
                                }
                            ]
                        }
                    }
                }
            """


@pytest.fixture(name="slsa_v1_gcb_2_provenance")
def slsa_v1_gcb_2_provenance_() -> str:
    """Return a valid SLSA v1 provenance using build type gcb and configSource."""
    return """
                {
                    "_type": "https://in-toto.io/Statement/v1",
                    "subject": [],
                    "predicateType": "https://slsa.dev/provenance/v1",
                    "predicate": {
                        "buildDefinition": {
                            "buildType": "https://slsa-framework.github.io/gcb-buildtypes/triggered-build/v1",
                            "externalParameters": {
                                "configSource": {
                                    "repository": "https://github.com/oracle/macaron"
                                }
                            },
                            "resolvedDependencies": [
                                {
                                    "uri": "git+https://github.com/oracle/macaron@refs/heads/staging",
                                    "digest": {
                                        "sha1": "51aa22a42ec1bffa71518041a6a6d42d40bf50f0"
                                    }
                                }
                            ]
                        }
                    }
                }
            """


@pytest.fixture(name="slsa_v1_github_provenance")
def slsa_v1_github_provenance_() -> str:
    """Return a valid SLSA v1 provenance using build type GitHub."""
    return """
                {
                    "_type": "https://in-toto.io/Statement/v1",
                    "subject": [],
                    "predicateType": "https://slsa.dev/provenance/v1",
                    "predicate": {
                        "buildDefinition": {
                            "buildType": "https://slsa-framework.github.io/github-actions-buildtypes/workflow/v1",
                            "externalParameters": {
                                "workflow": {
                                    "repository": "https://github.com/oracle/macaron"
                                }
                            },
                            "resolvedDependencies": [
                                {
                                    "uri": "git+https://github.com/oracle/macaron@refs/heads/staging",
                                    "digest": {
                                       "gitCommit": "51aa22a42ec1bffa71518041a6a6d42d40bf50f0"
                                    }
                                },
                                {
                                    "uri": "git+https://github.com/oracle-samples/macaron@refs/heads/main"
                                }
                            ]
                        }
                    }
                }
            """


@pytest.fixture(name="slsa_v02_provenance")
def slsa_v02_provenance_() -> str:
    """Return a valid SLSA v02 provenance."""
    return """
                {
                    "_type": "https://in-toto.io/Statement/v0.1",
                    "subject": [],
                    "predicateType": "https://slsa.dev/provenance/v0.2",
                    "predicate": {
                        "invocation": {
                            "configSource": {
                                "uri": "git+https://github.com/oracle/macaron@refs/heads/staging",
                                "digest": {
                                    "sha1": "51aa22a42ec1bffa71518041a6a6d42d40bf50f0"
                                }
                            }
                        }
                    }
                }
            """


@pytest.fixture(name="slsa_v01_provenance")
def slsa_v01_provenance_() -> str:
    """Return a valid SLSA v01 provenance."""
    return """
                {
                    "_type": "https://in-toto.io/Statement/v0.1",
                    "subject": [],
                    "predicateType": "https://slsa.dev/provenance/v0.1",
                    "predicate": {
                        "recipe": {
                            "definedInMaterial": 1
                        },
                        "materials": [
                            {
                                "uri": "git+https://github.com/oracle-samples/macaron@refs/heads/main"
                            },
                            {
                                "uri": "git+https://github.com/oracle/macaron@refs/heads/main",
                                "digest": {
                                    "sha256": "51aa22a42ec1bffa71518041a6a6d42d40bf50f0"
                                }
                            }
                        ]
                    }
                }
            """


@pytest.fixture(name="target_repository")
def target_repository_() -> str:
    """Return the target repository URL."""
    return "https://github.com/oracle/macaron"


@pytest.fixture(name="target_commit")
def target_commit_() -> str:
    """Return the target commit hash."""
    return "51aa22a42ec1bffa71518041a6a6d42d40bf50f0"


def test_slsa_v1_gcb_1(slsa_v1_gcb_1_provenance: str, target_repository: str, target_commit: str) -> None:
    """Test SLSA v1 provenance with build type gcb and sourceToBuild."""
    payload = json.loads(slsa_v1_gcb_1_provenance)
    assert isinstance(payload, dict)
    _perform_provenance_comparison(payload, target_repository, target_commit)

    # Set repository to an empty string.
    _json_modify(payload, ["predicate", "buildDefinition", "externalParameters", "sourceToBuild", "repository"], "")
    with pytest.raises(ProvenanceExtractionException):
        _perform_provenance_comparison(payload, "", "")

    # Remove repository key.
    _json_modify(payload, ["predicate", "buildDefinition", "externalParameters", "sourceToBuild", "repository"], None)
    with pytest.raises(ProvenanceExtractionException):
        _perform_provenance_comparison(payload, "", "")

    # Add repository back.
    _json_modify(
        payload,
        ["predicate", "buildDefinition", "externalParameters", "sourceToBuild", "repository"],
        target_repository,
    )
    # Re-test provenance validity.
    _perform_provenance_comparison(payload, target_repository, target_commit)

    # Remove commit.
    _json_modify(payload, ["predicate", "buildDefinition", "resolvedDependencies"], None)
    with pytest.raises(ProvenanceExtractionException):
        _perform_provenance_comparison(payload, "", "")


def test_slsa_v1_gcb_2(slsa_v1_gcb_2_provenance: str, target_repository: str, target_commit: str) -> None:
    """Test SLSA v1 provenance with build type gcb and configSource."""
    payload = json.loads(slsa_v1_gcb_2_provenance)
    assert isinstance(payload, dict)
    _perform_provenance_comparison(payload, target_repository, target_commit)

    # Set repository to an empty string.
    _json_modify(payload, ["predicate", "buildDefinition", "externalParameters", "configSource", "repository"], "")
    with pytest.raises(ProvenanceExtractionException):
        _perform_provenance_comparison(payload, "", "")

    # Remove repository key.
    _json_modify(payload, ["predicate", "buildDefinition", "externalParameters", "configSource", "repository"], None)
    with pytest.raises(ProvenanceExtractionException):
        _perform_provenance_comparison(payload, "", "")

    # Re-add repository key with a bad value.
    _json_modify(payload, ["predicate", "buildDefinition", "externalParameters", "configSource", "repository"], "bad")
    with pytest.raises(ProvenanceExtractionException):
        _perform_provenance_comparison(payload, "", "")


def test_slsa_v1_github(slsa_v1_github_provenance: str, target_repository: str, target_commit: str) -> None:
    """Test SLSA v1 provenance with build type GitHub."""
    payload = json.loads(slsa_v1_github_provenance)
    assert isinstance(payload, dict)
    _perform_provenance_comparison(payload, target_repository, target_commit)

    # Set repository to an empty string.
    _json_modify(payload, ["predicate", "buildDefinition", "externalParameters", "workflow", "repository"], "")
    with pytest.raises(ProvenanceExtractionException):
        _perform_provenance_comparison(payload, "", "")

    # Remove repository key.
    _json_modify(payload, ["predicate", "buildDefinition", "externalParameters", "workflow", "repository"], None)
    with pytest.raises(ProvenanceExtractionException):
        _perform_provenance_comparison(payload, "", "")


def test_slsa_v02(slsa_v02_provenance: str, target_repository: str, target_commit: str) -> None:
    """Test SLSA v0.2 provenance."""
    payload = json.loads(slsa_v02_provenance)
    assert isinstance(payload, dict)
    _perform_provenance_comparison(payload, target_repository, target_commit)

    # Set repository to an empty string.
    _json_modify(payload, ["predicate", "invocation", "configSource", "uri"], "")
    with pytest.raises(ProvenanceExtractionException):
        _perform_provenance_comparison(payload, "", "")

    # Remove repository key.
    _json_modify(payload, ["predicate", "invocation", "configSource", "uri"], None)
    with pytest.raises(ProvenanceExtractionException):
        _perform_provenance_comparison(payload, "", "")

    # Re-add repository and re-validate.
    _json_modify(
        payload, ["predicate", "invocation", "configSource", "uri"], f"git+{target_repository}@refs/heads/main"
    )
    _perform_provenance_comparison(payload, target_repository, target_commit)

    # Remove commit.
    _json_modify(payload, ["predicate", "invocation", "configSource", "digest", "sha1"], None)
    with pytest.raises(ProvenanceExtractionException):
        _perform_provenance_comparison(payload, "", "")


def test_slsa_v01(slsa_v01_provenance: str, target_repository: str, target_commit: str) -> None:
    """Test SLSA v0.1 provenance."""
    payload = json.loads(slsa_v01_provenance)
    assert isinstance(payload, dict)
    _perform_provenance_comparison(payload, target_repository, target_commit)

    # Set repository to an empty string.
    materials = json_extract(payload, ["predicate", "materials"], list)
    material_index = json_extract(payload, ["predicate", "recipe", "definedInMaterial"], int)
    _json_modify(materials[material_index], ["uri"], "")
    _json_modify(payload, ["predicate", "materials"], materials)
    with pytest.raises(ProvenanceExtractionException):
        _perform_provenance_comparison(payload, "", "")

    # Remove repository.
    _json_modify(materials[material_index], ["uri"], None)
    _json_modify(payload, ["predicate", "materials"], materials)
    with pytest.raises(ProvenanceExtractionException):
        _perform_provenance_comparison(payload, "", "")

    # Restore repository and re-validate.
    _json_modify(materials[material_index], ["uri"], f"git+{target_repository}@refs/heads/main")
    _json_modify(payload, ["predicate", "materials"], materials)
    _perform_provenance_comparison(payload, target_repository, target_commit)

    # Set material index to an invalid value.
    _json_modify(payload, ["predicate", "recipe", "definedInMaterial"], 10)
    with pytest.raises(ProvenanceExtractionException):
        _perform_provenance_comparison(payload, "", "")


@pytest.fixture(name="witness_gitlab_provenance")
def witness_gitlab_provenance_() -> str:
    """Return a Witness v0.1 provenance with a GitLab attestation."""
    return """
                {
                    "_type": "https://in-toto.io/Statement/v0.1",
                    "subject": [],
                    "predicateType": "https://witness.testifysec.com/attestation-collection/v0.1",
                    "predicate": {
                        "name": "test",
                        "attestations": [
                            {
                                "type": "https://witness.dev/attestations/gitlab/v0.1",
                                "attestation": {
                                    "projecturl": "https://gitlab.com/tinyMediaManager/tinyMediaManager"
                                }
                            },
                            {
                                "type": "https://witness.dev/attestations/git/v0.1",
                                "attestation": {
                                    "commithash": "cf6080a92d1c748ba5f05ea16529e05e5c641a49"
                                }
                            }
                        ]
                    }
                }
            """


@pytest.fixture(name="witness_github_provenance")
def witness_github_provenance_() -> str:
    """Return a Witness v0.1 provenance with a GitHub attestation."""
    return """
                {
                    "_type": "https://in-toto.io/Statement/v0.1",
                    "subject": [],
                    "predicateType": "https://witness.testifysec.com/attestation-collection/v0.1",
                    "predicate": {
                        "name": "test",
                        "attestations": [
                            {
                                "type": "https://witness.dev/attestations/github/v0.1",
                                "attestation": {
                                    "projecturl": "https://github.com/oracle/macaron"
                                }
                            },
                            {
                                "type": "https://witness.dev/attestations/git/v0.1",
                                "attestation": {
                                    "commithash": "51aa22a42ec1bffa71518041a6a6d42d40bf50f0"
                                }
                            }
                        ]
                    }
                }
            """


def test_witness_gitlab(witness_gitlab_provenance: str) -> None:
    """Test Witness v01 GitLab provenance."""
    target_repository = "https://gitlab.com/tinyMediaManager/tinyMediaManager"
    target_commit = "cf6080a92d1c748ba5f05ea16529e05e5c641a49"
    payload = json.loads(witness_gitlab_provenance)
    assert isinstance(payload, dict)
    _perform_provenance_comparison(payload, target_repository, target_commit)

    # Set repository to an empty string.
    attestations = json_extract(payload, ["predicate", "attestations"], list)
    _json_modify(attestations[0], ["attestation", "projecturl"], "")
    _json_modify(payload, ["attestation"], attestations)
    with pytest.raises(ProvenanceExtractionException):
        _perform_provenance_comparison(payload, "", "")

    # Remove repository.
    _json_modify(attestations[0], ["attestation", "projecturl"], None)
    _json_modify(payload, ["attestation"], attestations)
    with pytest.raises(ProvenanceExtractionException):
        _perform_provenance_comparison(payload, "", "")

    # Restore repository and re-validate.
    _json_modify(attestations[0], ["attestation", "projecturl"], target_repository)
    _json_modify(payload, ["attestation"], attestations)
    _perform_provenance_comparison(payload, target_repository, target_commit)

    # Set commit to an empty string.
    _json_modify(attestations[1], ["attestation", "commithash"], "")
    _json_modify(payload, ["attestation"], attestations)
    with pytest.raises(ProvenanceExtractionException):
        _perform_provenance_comparison(payload, "", "")

    # Remove the Git attestation.
    _json_modify(payload, ["attestation"], attestations[:1])
    with pytest.raises(ProvenanceExtractionException):
        _perform_provenance_comparison(payload, "", "")


def test_witness_github(witness_github_provenance: str, target_repository: str, target_commit: str) -> None:
    """Test Witness v01 GitHub provenance."""
    payload = json.loads(witness_github_provenance)
    assert isinstance(payload, dict)
    _perform_provenance_comparison(payload, target_repository, target_commit)


@pytest.mark.parametrize(
    ("type_", "predicate_type"),
    [
        ("https://in-toto.io/Statement/v0.1", "https://slsa.dev/provenance/v1"),
        ("https://in-toto.io/Statement/v1", "https://slsa.dev/provenance/v0.2"),
        ("https://in-toto.io/Statement/v1", "https://slsa.dev/provenance/v0.1"),
        ("https://in-toto.io/Statement/v1", "https://witness.testifysec.com/attestation-collection/v0.1"),
    ],
)
def test_invalid_type_payloads(type_: str, predicate_type: str) -> None:
    """Test payloads with invalid type combinations."""
    payload_text = '{ "_type": ' + f'"{type_}",' + ' "predicateType": ' + f'"{predicate_type}",'
    payload_text = f"{payload_text}" + '"subject": [], "predicate": {} }'
    payload = json.loads(payload_text)
    with pytest.raises(ProvenanceExtractionException):
        _perform_provenance_comparison(payload, "", "")


def _perform_provenance_comparison(payload: JsonType, expected_repo: str, expected_commit: str) -> None:
    """Accept a provenance and extraction function, assert the extracted values match the expected ones."""
    assert isinstance(payload, dict)
    provenance = validate_intoto_payload(payload)
    repo, commit = extract_repo_and_commit_from_provenance(provenance)
    assert expected_repo == repo
    assert expected_commit == commit


def _json_modify(entry: dict[str, JsonType], keys: list[str], new_value: JsonType) -> None:
    """Modify the value found by following the list of depth-sequential keys inside the passed JSON dictionary.

    The found value will be overwritten by the new_value parameter.
    If new_value is None, the value will be removed.
    If the final key does not exist, it will be created as new_value.
    """
    target = entry
    for index, key in enumerate(keys):
        if key not in target:
            if index == len(keys) - 1:
                # Add key.
                target[key] = new_value
                return
            raise JsonExtractionException(f"JSON key not found: {key}")
        next_target = target[key]
        if index == len(keys) - 1:
            if new_value is None:
                # Remove value.
                del target[key]
            else:
                # Replace value
                target[key] = new_value
        else:
            if not isinstance(next_target, dict):
                raise JsonExtractionException(f"Cannot extract value from non-dict type: {str(type(next_target))}")
            target = next_target
