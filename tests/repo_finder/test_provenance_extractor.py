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
def slsa_v1_gcb_1_provenance_() -> dict[str, JsonType]:
    """Return a valid SLSA v1 provenance using build type gcb and sourceToBuild."""
    return _load_and_validate_josn(
        """
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
    )


@pytest.fixture(name="slsa_v1_gcb_2_provenance")
def slsa_v1_gcb_2_provenance_() -> dict[str, JsonType]:
    """Return a valid SLSA v1 provenance using build type gcb and configSource."""
    return _load_and_validate_josn(
        """
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
    )


@pytest.fixture(name="slsa_v1_github_provenance")
def slsa_v1_github_provenance_() -> dict[str, JsonType]:
    """Return a valid SLSA v1 provenance using build type GitHub."""
    return _load_and_validate_josn(
        """
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
    )


@pytest.fixture(name="slsa_v02_provenance")
def slsa_v02_provenance_() -> dict[str, JsonType]:
    """Return a valid SLSA v02 provenance."""
    return _load_and_validate_josn(
        """
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
    )


@pytest.fixture(name="slsa_v01_provenance")
def slsa_v01_provenance_() -> dict[str, JsonType]:
    """Return a valid SLSA v01 provenance."""
    return _load_and_validate_josn(
        """
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
    )


@pytest.fixture(name="witness_gitlab_provenance")
def witness_gitlab_provenance_() -> dict[str, JsonType]:
    """Return a Witness v0.1 provenance with a GitLab attestation."""
    return _load_and_validate_josn(
        """
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
    )


@pytest.fixture(name="witness_github_provenance")
def witness_github_provenance_() -> dict[str, JsonType]:
    """Return a Witness v0.1 provenance with a GitHub attestation."""
    return _load_and_validate_josn(
        """
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
    )


@pytest.fixture(name="target_repository")
def target_repository_() -> str:
    """Return the target repository URL."""
    return "https://github.com/oracle/macaron"


@pytest.fixture(name="target_commit")
def target_commit_() -> str:
    """Return the target commit hash."""
    return "51aa22a42ec1bffa71518041a6a6d42d40bf50f0"


def test_slsa_v1_gcb_1_is_valid(
    slsa_v1_gcb_1_provenance: dict[str, JsonType], target_repository: str, target_commit: str
) -> None:
    """Test valid SLSA v1 provenance with build type gcb and sourceToBuild."""
    _perform_provenance_comparison(slsa_v1_gcb_1_provenance, target_repository, target_commit)


@pytest.mark.parametrize(
    ("keys", "new_value"),
    [
        (["predicate", "buildDefinition", "externalParameters", "sourceToBuild", "repository"], ""),
        (["predicate", "buildDefinition", "externalParameters", "sourceToBuild", "repository"], None),
        (["predicate", "buildDefinition", "externalParameters", "sourceToBuild", "repository"], "bad_url"),
        (["predicate", "buildDefinition", "resolvedDependencies"], ""),
        (["predicate", "buildDefinition", "resolvedDependencies"], None),
    ],
)
def test_slsa_v1_gcb_1_is_invalid(
    slsa_v1_gcb_1_provenance: dict[str, JsonType], keys: list[str], new_value: JsonType
) -> None:
    """Test invalidly modified SLSA v1 provenance with build type gcb and sourceToBuild."""
    _json_modify(slsa_v1_gcb_1_provenance, keys, new_value)
    with pytest.raises(ProvenanceExtractionException):
        _perform_provenance_comparison(slsa_v1_gcb_1_provenance, "", "")


def test_slsa_v1_gcb_2_is_valid(
    slsa_v1_gcb_2_provenance: dict[str, JsonType], target_repository: str, target_commit: str
) -> None:
    """Test valid SLSA v1 provenance with build type gcb and configSource."""
    _perform_provenance_comparison(slsa_v1_gcb_2_provenance, target_repository, target_commit)


@pytest.mark.parametrize(
    ("keys", "new_value"),
    [
        (["predicate", "buildDefinition", "externalParameters", "configSource", "repository"], ""),
        (["predicate", "buildDefinition", "externalParameters", "configSource", "repository"], None),
        (["predicate", "buildDefinition", "externalParameters", "configSource", "repository"], "bad_url"),
    ],
)
def test_slsa_v1_gcb_2_is_invalid(
    slsa_v1_gcb_2_provenance: dict[str, JsonType], keys: list[str], new_value: JsonType
) -> None:
    """Test invalidly modified SLSA v1 provenance with build type gcb and configSource."""
    _json_modify(slsa_v1_gcb_2_provenance, keys, new_value)
    with pytest.raises(ProvenanceExtractionException):
        _perform_provenance_comparison(slsa_v1_gcb_2_provenance, "", "")


def test_slsa_v1_github_is_valid(
    slsa_v1_github_provenance: dict[str, JsonType], target_repository: str, target_commit: str
) -> None:
    """Test valid SLSA v1 provenance with build type GitHub."""
    _perform_provenance_comparison(slsa_v1_github_provenance, target_repository, target_commit)


@pytest.mark.parametrize(
    ("keys", "new_value"),
    [
        (["predicate", "buildDefinition", "externalParameters", "workflow", "repository"], ""),
        (["predicate", "buildDefinition", "externalParameters", "workflow", "repository"], None),
        (["predicate", "buildDefinition", "externalParameters", "workflow", "repository"], "bad_url"),
    ],
)
def test_slsa_v1_github_is_invalid(
    slsa_v1_github_provenance: dict[str, JsonType], keys: list[str], new_value: JsonType
) -> None:
    """Test invalidly modified SLSA v1 provenance with build type GitHub."""
    _json_modify(slsa_v1_github_provenance, keys, new_value)
    with pytest.raises(ProvenanceExtractionException):
        _perform_provenance_comparison(slsa_v1_github_provenance, "", "")


def test_slsa_v02_is_valid(
    slsa_v02_provenance: dict[str, JsonType], target_repository: str, target_commit: str
) -> None:
    """Test SLSA v0.2 provenance."""
    _perform_provenance_comparison(slsa_v02_provenance, target_repository, target_commit)


@pytest.mark.parametrize(
    ("keys", "new_value"),
    [
        (["predicate", "invocation", "configSource", "uri"], ""),
        (["predicate", "invocation", "configSource", "uri"], None),
        (["predicate", "invocation", "configSource", "uri"], "bad_url"),
        (["predicate", "invocation", "configSource", "digest", "sha1"], ""),
        (["predicate", "invocation", "configSource", "digest", "sha1"], None),
    ],
)
def test_slsa_v02_is_invalid(slsa_v02_provenance: dict[str, JsonType], keys: list[str], new_value: JsonType) -> None:
    """Test invalidly modified SLSA v0.2 provenance."""
    _json_modify(slsa_v02_provenance, keys, new_value)
    with pytest.raises(ProvenanceExtractionException):
        _perform_provenance_comparison(slsa_v02_provenance, "", "")


def test_slsa_v01_is_valid(
    slsa_v01_provenance: dict[str, JsonType], target_repository: str, target_commit: str
) -> None:
    """Test valid SLSA v0.1 provenance."""
    _perform_provenance_comparison(slsa_v01_provenance, target_repository, target_commit)


@pytest.mark.parametrize(
    "new_value",
    [
        "",
        None,
    ],
)
def test_slsa_v01_is_invalid(slsa_v01_provenance: dict[str, JsonType], new_value: JsonType) -> None:
    """Test invalidly modified SLSA v0.1 provenance."""
    materials = json_extract(slsa_v01_provenance, ["predicate", "materials"], list)
    material_index = json_extract(slsa_v01_provenance, ["predicate", "recipe", "definedInMaterial"], int)
    _json_modify(materials[material_index], ["uri"], new_value)
    with pytest.raises(ProvenanceExtractionException):
        _perform_provenance_comparison(slsa_v01_provenance, "", "")


def test_slsa_v01_invalid_material_index(slsa_v01_provenance: dict[str, JsonType]) -> None:
    """Test the SLSA v0.1 provenance with an invalid materials index."""
    _json_modify(slsa_v01_provenance, ["predicate", "recipe", "definedInMaterial"], 10)
    with pytest.raises(ProvenanceExtractionException):
        _perform_provenance_comparison(slsa_v01_provenance, "", "")


def test_witness_gitlab_is_valid(witness_gitlab_provenance: dict[str, JsonType]) -> None:
    """Test valid Witness v0.1 GitLab provenance."""
    _perform_provenance_comparison(
        witness_gitlab_provenance,
        "https://gitlab.com/tinyMediaManager/tinyMediaManager",
        "cf6080a92d1c748ba5f05ea16529e05e5c641a49",
    )


def test_witness_github_is_valid(
    witness_github_provenance: dict[str, JsonType], target_repository: str, target_commit: str
) -> None:
    """Test valid Witness v0.1 GitHub provenance."""
    _perform_provenance_comparison(witness_github_provenance, target_repository, target_commit)


@pytest.mark.parametrize(
    ("keys", "new_value", "attestation_index"),
    [
        (["attestation", "projecturl"], "", 0),
        (["attestation", "projecturl"], None, 0),
        (["attestation", "commithash"], "", 1),
        (["attestation", "commithash"], None, 1),
    ],
)
def test_witness_github_is_invalid(
    witness_github_provenance: dict[str, JsonType], keys: list[str], new_value: JsonType, attestation_index: int
) -> None:
    """Test invalidly modified Witness v0.1 GitHub provenance."""
    attestations = json_extract(witness_github_provenance, ["predicate", "attestations"], list)
    _json_modify(attestations[attestation_index], keys, new_value)
    with pytest.raises(ProvenanceExtractionException):
        _perform_provenance_comparison(witness_github_provenance, "", "")


def test_witness_github_remove_attestation(witness_github_provenance: dict[str, JsonType]) -> None:
    """Test removing Git attestation from Witness V0.1 GitHub provenance."""
    attestations = json_extract(witness_github_provenance, ["predicate", "attestations"], list)
    _json_modify(witness_github_provenance, ["predicate", "attestations"], attestations[:1])
    with pytest.raises(ProvenanceExtractionException):
        _perform_provenance_comparison(witness_github_provenance, "", "")


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


def _perform_provenance_comparison(payload: dict[str, JsonType], expected_repo: str, expected_commit: str) -> None:
    """Accept a provenance and extraction function, assert the extracted values match the expected ones."""
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


def _load_and_validate_josn(payload: str) -> dict[str, JsonType]:
    """Load payload as JSON and validate it is of type dict."""
    json_payload = json.loads(payload)
    assert isinstance(json_payload, dict)
    return json_payload
