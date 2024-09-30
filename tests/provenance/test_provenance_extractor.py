# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the provenance extractor on valid example provenances."""
import json

import pytest
from packageurl import PackageURL

from macaron.errors import ProvenanceError
from macaron.json_tools import JsonType, json_extract
from macaron.provenance.provenance_extractor import (
    check_if_repository_purl_and_url_match,
    extract_repo_and_commit_from_provenance,
)
from macaron.slsa_analyzer.provenance.intoto import validate_intoto_payload


@pytest.fixture(name="slsa_v1_gcb_1_provenance")
def slsa_v1_gcb_1_provenance_() -> dict[str, JsonType]:
    """Return a valid SLSA v1 provenance using build type gcb and sourceToBuild."""
    return _load_and_validate_json(
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
    return _load_and_validate_json(
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
    return _load_and_validate_json(
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


@pytest.fixture(name="slsa_v1_oci_provenance")
def slsa_v1_oci_provenance_() -> dict[str, JsonType]:
    """Return a valid SLSA v1 provenance using the OCI build type."""
    payload = _load_and_validate_json(
        """
            {
                "_type": "https://in-toto.io/Statement/v1",
                "predicateType": "https://slsa.dev/provenance/v1",
                "subject": [],
                "predicate": {
                    "buildDefinition": {
                        "buildType": "",
                        "externalParameters": {
                            "source": "https://github.com/oracle/macaron"
                        },
                        "internalParameters": {
                            "buildEnvVar": {
                                "BLD_COMMIT_HASH": "51aa22a42ec1bffa71518041a6a6d42d40bf50f0"
                            }
                        }
                    }
                }
            }
        """
    )
    # The build type is modified here to avoid issues with excessive line length.
    _json_modify(
        payload,
        ["predicate", "buildDefinition", "buildType"],
        "https://github.com/oracle/macaron/tree/main/src/macaron/resources/provenance-buildtypes/oci/v1",
    )
    return payload


@pytest.fixture(name="slsa_v02_provenance")
def slsa_v02_provenance_() -> dict[str, JsonType]:
    """Return a valid SLSA v02 provenance."""
    return _load_and_validate_json(
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
    return _load_and_validate_json(
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
                                    "sha1": "51aa22a42ec1bffa71518041a6a6d42d40bf50f0"
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
    return _load_and_validate_json(
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
    return _load_and_validate_json(
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
    _test_extract_repo_and_commit_from_provenance(slsa_v1_gcb_1_provenance, target_repository, target_commit)


@pytest.mark.parametrize(
    ("keys", "new_value"),
    [
        (["predicate", "buildDefinition", "resolvedDependencies"], ""),
        (["predicate", "buildDefinition", "resolvedDependencies"], None),
    ],
)
def test_slsa_v1_gcb_is_partially_valid(
    slsa_v1_gcb_1_provenance: dict[str, JsonType], keys: list[str], new_value: JsonType
) -> None:
    """Test partially modified SLSA v1 provenance with build type gbc and sourceToBuild."""
    _json_modify(slsa_v1_gcb_1_provenance, keys, new_value)
    _test_extract_repo_and_commit_from_provenance(slsa_v1_gcb_1_provenance, "https://github.com/oracle/macaron", None)


@pytest.mark.parametrize(
    ("keys", "new_value"),
    [
        (["predicate", "buildDefinition", "externalParameters", "sourceToBuild", "repository"], ""),
        (["predicate", "buildDefinition", "externalParameters", "sourceToBuild", "repository"], None),
    ],
)
def test_slsa_v1_gcb_1_is_invalid(
    slsa_v1_gcb_1_provenance: dict[str, JsonType], keys: list[str], new_value: JsonType
) -> None:
    """Test invalidly modified SLSA v1 provenance with build type gcb and sourceToBuild."""
    _json_modify(slsa_v1_gcb_1_provenance, keys, new_value)
    _test_extract_repo_and_commit_from_provenance(slsa_v1_gcb_1_provenance)


def test_slsa_v1_gcb_2_is_valid(
    slsa_v1_gcb_2_provenance: dict[str, JsonType], target_repository: str, target_commit: str
) -> None:
    """Test valid SLSA v1 provenance with build type gcb and configSource."""
    _test_extract_repo_and_commit_from_provenance(slsa_v1_gcb_2_provenance, target_repository, target_commit)


@pytest.mark.parametrize(
    ("keys", "new_value"),
    [
        (["predicate", "buildDefinition", "externalParameters", "configSource", "repository"], ""),
        (["predicate", "buildDefinition", "externalParameters", "configSource", "repository"], None),
    ],
)
def test_slsa_v1_gcb_2_is_invalid(
    slsa_v1_gcb_2_provenance: dict[str, JsonType], keys: list[str], new_value: JsonType
) -> None:
    """Test invalidly modified SLSA v1 provenance with build type gcb and configSource."""
    _json_modify(slsa_v1_gcb_2_provenance, keys, new_value)
    _test_extract_repo_and_commit_from_provenance(slsa_v1_gcb_2_provenance)


def test_slsa_v1_github_is_valid(
    slsa_v1_github_provenance: dict[str, JsonType], target_repository: str, target_commit: str
) -> None:
    """Test valid SLSA v1 provenance with build type GitHub."""
    _test_extract_repo_and_commit_from_provenance(slsa_v1_github_provenance, target_repository, target_commit)


@pytest.mark.parametrize(
    ("keys", "new_value"),
    [
        (["predicate", "buildDefinition", "externalParameters", "workflow", "repository"], ""),
        (["predicate", "buildDefinition", "externalParameters", "workflow", "repository"], None),
    ],
)
def test_slsa_v1_github_is_invalid(
    slsa_v1_github_provenance: dict[str, JsonType], keys: list[str], new_value: JsonType
) -> None:
    """Test invalidly modified SLSA v1 provenance with build type GitHub."""
    _json_modify(slsa_v1_github_provenance, keys, new_value)
    _test_extract_repo_and_commit_from_provenance(slsa_v1_github_provenance)


def test_slsa_v1_oci_is_valid(
    slsa_v1_oci_provenance: dict[str, JsonType], target_repository: str, target_commit: str
) -> None:
    """Test SLSA v1 oci provenance."""
    _test_extract_repo_and_commit_from_provenance(slsa_v1_oci_provenance, target_repository, target_commit)


@pytest.mark.parametrize(
    ("keys", "new_value"),
    [
        (["predicate", "buildDefinition", "externalParameters", "source"], ""),
        (["predicate", "buildDefinition", "externalParameters", "source"], None),
    ],
)
def test_slsa_v1_oci_is_invalid(
    slsa_v1_oci_provenance: dict[str, JsonType], keys: list[str], new_value: JsonType
) -> None:
    """Test invalidly modified SLSA v1 oci provenance."""
    _json_modify(slsa_v1_oci_provenance, keys, new_value)
    _test_extract_repo_and_commit_from_provenance(slsa_v1_oci_provenance)


def test_slsa_v02_is_valid(
    slsa_v02_provenance: dict[str, JsonType], target_repository: str, target_commit: str
) -> None:
    """Test SLSA v0.2 provenance."""
    _test_extract_repo_and_commit_from_provenance(slsa_v02_provenance, target_repository, target_commit)


@pytest.mark.parametrize(
    ("keys", "new_value", "expected_repo", "expected_commit"),
    [
        (["predicate", "invocation", "configSource", "uri"], "", None, "51aa22a42ec1bffa71518041a6a6d42d40bf50f0"),
        (["predicate", "invocation", "configSource", "uri"], None, None, "51aa22a42ec1bffa71518041a6a6d42d40bf50f0"),
        (["predicate", "invocation", "configSource", "digest", "sha1"], "", "https://github.com/oracle/macaron", None),
        (
            ["predicate", "invocation", "configSource", "digest", "sha1"],
            None,
            "https://github.com/oracle/macaron",
            None,
        ),
    ],
)
def test_slsa_v02_is_partially_valid(
    slsa_v02_provenance: dict[str, JsonType],
    keys: list[str],
    new_value: JsonType,
    expected_repo: str | None,
    expected_commit: str | None,
) -> None:
    """Test partially modified SLSA v0.2 provenance."""
    _json_modify(slsa_v02_provenance, keys, new_value)
    _test_extract_repo_and_commit_from_provenance(slsa_v02_provenance, expected_repo, expected_commit)


@pytest.mark.parametrize(
    "new_value",
    ["", None],
)
def test_slsa_v02_is_invalid(slsa_v02_provenance: dict[str, JsonType], new_value: JsonType) -> None:
    """Test invalidly modified SLSA v0.2 provenance."""
    _json_modify(slsa_v02_provenance, ["predicate", "invocation", "configSource", "uri"], new_value)
    _json_modify(slsa_v02_provenance, ["predicate", "invocation", "configSource", "digest", "sha1"], new_value)
    _test_extract_repo_and_commit_from_provenance(slsa_v02_provenance)


def test_slsa_v01_is_valid(
    slsa_v01_provenance: dict[str, JsonType], target_repository: str, target_commit: str
) -> None:
    """Test valid SLSA v0.1 provenance."""
    _test_extract_repo_and_commit_from_provenance(slsa_v01_provenance, target_repository, target_commit)


@pytest.mark.parametrize(
    ("keys", "new_value", "expected_repo", "expected_commit"),
    [
        (["uri"], "", None, "51aa22a42ec1bffa71518041a6a6d42d40bf50f0"),
        (["uri"], None, None, "51aa22a42ec1bffa71518041a6a6d42d40bf50f0"),
        (["digest", "sha1"], "", "https://github.com/oracle/macaron", None),
        (["digest"], None, "https://github.com/oracle/macaron", None),
    ],
)
def test_slsa_v01_is_partially_valid(
    slsa_v01_provenance: dict[str, JsonType],
    keys: list[str],
    new_value: JsonType,
    expected_repo: str | None,
    expected_commit: str | None,
) -> None:
    """Test partially modified SLSA v0.1 provenance."""
    materials = json_extract(slsa_v01_provenance, ["predicate", "materials"], list)
    assert materials
    material_index = json_extract(slsa_v01_provenance, ["predicate", "recipe", "definedInMaterial"], int)
    assert material_index is not None
    _json_modify(materials[material_index], keys, new_value)
    _test_extract_repo_and_commit_from_provenance(slsa_v01_provenance, expected_repo, expected_commit)


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
    assert materials
    material_index = json_extract(slsa_v01_provenance, ["predicate", "recipe", "definedInMaterial"], int)
    assert material_index is not None
    _json_modify(materials[material_index], ["uri"], new_value)
    _json_modify(materials[material_index], ["digest", "sha1"], new_value)
    _test_extract_repo_and_commit_from_provenance(slsa_v01_provenance)


def test_slsa_v01_invalid_material_index(slsa_v01_provenance: dict[str, JsonType]) -> None:
    """Test the SLSA v0.1 provenance with an invalid materials index."""
    _json_modify(slsa_v01_provenance, ["predicate", "recipe", "definedInMaterial"], 10)
    _test_extract_repo_and_commit_from_provenance(slsa_v01_provenance)


def test_witness_gitlab_is_valid(witness_gitlab_provenance: dict[str, JsonType]) -> None:
    """Test valid Witness v0.1 GitLab provenance."""
    _test_extract_repo_and_commit_from_provenance(
        witness_gitlab_provenance,
        "https://gitlab.com/tinyMediaManager/tinyMediaManager",
        "cf6080a92d1c748ba5f05ea16529e05e5c641a49",
    )


def test_witness_github_is_valid(
    witness_github_provenance: dict[str, JsonType], target_repository: str, target_commit: str
) -> None:
    """Test valid Witness v0.1 GitHub provenance."""
    _test_extract_repo_and_commit_from_provenance(witness_github_provenance, target_repository, target_commit)


@pytest.mark.parametrize(
    ("keys", "new_value", "attestation_index", "expected_repo", "expected_commit"),
    [
        (["attestation", "projecturl"], "", 0, None, "51aa22a42ec1bffa71518041a6a6d42d40bf50f0"),
        (["attestation", "projecturl"], None, 0, None, "51aa22a42ec1bffa71518041a6a6d42d40bf50f0"),
        (["attestation", "commithash"], "", 1, "https://github.com/oracle/macaron", None),
        (["attestation", "commithash"], None, 1, "https://github.com/oracle/macaron", None),
    ],
)
def test_witness_github_is_partially_valid(
    witness_github_provenance: dict[str, JsonType],
    keys: list[str],
    new_value: JsonType,
    attestation_index: int,
    expected_repo: str | None,
    expected_commit: str | None,
) -> None:
    """Test invalidly modified Witness v0.1 GitHub provenance."""
    attestations = json_extract(witness_github_provenance, ["predicate", "attestations"], list)
    assert attestations
    _json_modify(attestations[attestation_index], keys, new_value)
    _test_extract_repo_and_commit_from_provenance(witness_github_provenance, expected_repo, expected_commit)


@pytest.mark.parametrize(
    ("attestation_index", "expected_repo", "expected_commit"),
    [(0, "https://github.com/oracle/macaron", None), (1, None, "51aa22a42ec1bffa71518041a6a6d42d40bf50f0")],
)
def test_witness_github_remove_attestation(
    witness_github_provenance: dict[str, JsonType],
    attestation_index: int,
    expected_repo: str | None,
    expected_commit: str | None,
) -> None:
    """Test removing Git attestation from Witness V0.1 GitHub provenance."""
    attestations = json_extract(witness_github_provenance, ["predicate", "attestations"], list)
    assert attestations
    _json_modify(
        witness_github_provenance,
        ["predicate", "attestations"],
        attestations[attestation_index : attestation_index + 1],
    )
    _test_extract_repo_and_commit_from_provenance(witness_github_provenance, expected_repo, expected_commit)


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
    payload: dict[str, JsonType] = {"_type": type_, "predicateType": predicate_type, "subject": [], "predicate": {}}
    with pytest.raises(ProvenanceError):
        _test_extract_repo_and_commit_from_provenance(payload)


@pytest.mark.parametrize(
    ("url", "purl_string", "expected"),
    [
        ("https://github.com:9000/oracle/macaron", "pkg:github/oracle/macaron", True),
        ("http://user:pass@github.com/oracle/macaron", "pkg:github.com/oracle/macaron", True),
        ("https://bitbucket.org:9000/example/test", "pkg:bitbucket/example/test", True),
        ("http://bitbucket.org/example;key1=1?key2=2#key3=3", "pkg:bitbucket.org/example", True),
    ],
)
def test_compare_purl_and_url(url: str, purl_string: str, expected: bool) -> None:
    """Test comparison of repository type PURLs against matching URLs."""
    purl = PackageURL.from_string(purl_string)
    assert expected == check_if_repository_purl_and_url_match(url, purl)


def _test_extract_repo_and_commit_from_provenance(
    payload: dict[str, JsonType], expected_repo: str | None = None, expected_commit: str | None = None
) -> None:
    """Accept a provenance and extraction function, assert the extracted values match the expected ones."""
    provenance = validate_intoto_payload(payload)
    repo, commit = extract_repo_and_commit_from_provenance(provenance)
    assert expected_repo == repo
    assert expected_commit == commit


def _json_modify(entry: dict | list, keys: list[str], new_value: JsonType) -> None:
    """Modify the value found by following the list of depth-sequential keys inside the passed JSON dictionary.

    The found value will be overwritten by the `new_value` parameter.
    If `new_value` is `None`, the value will be removed.
    If the final key does not exist, it will be created as `new_value`.
    """
    target: dict[str, JsonType] | None = json_extract(entry, keys[:-1], dict)
    if not target:
        return

    if new_value is None:
        del target[keys[-1]]
    else:
        target[keys[-1]] = new_value


def _load_and_validate_json(payload: str) -> dict[str, JsonType]:
    """Load payload as JSON and validate it is of type dict."""
    json_payload = json.loads(payload)
    assert isinstance(json_payload, dict)
    return json_payload
