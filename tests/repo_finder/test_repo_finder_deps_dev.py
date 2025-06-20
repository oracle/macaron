# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the deps.dev repo finder."""
import pytest
from packageurl import PackageURL
from pytest_httpserver import HTTPServer

from macaron.repo_finder.repo_finder_deps_dev import DepsDevRepoFinder
from macaron.repo_finder.repo_finder_enums import RepoFinderInfo


def test_find_repo_url_failure(deps_dev_service_mock: dict) -> None:
    """Test find repo function."""
    purl = PackageURL.from_string(f"pkg:pypi/example{deps_dev_service_mock['api']}")
    result, outcome = DepsDevRepoFinder().find_repo(purl)
    assert not result
    assert outcome == RepoFinderInfo.DDEV_API_ERROR


@pytest.mark.parametrize(
    ("data", "expected_outcome"),
    [
        ('{"foo": "bar"}', RepoFinderInfo.DDEV_JSON_INVALID),
        ('{"links": [{"url": 1}]}', RepoFinderInfo.DDEV_NO_URLS),
        ('{"links": [{"url": "test://test.test"}]}', RepoFinderInfo.DDEV_NO_VALID_URLS),
    ],
)
def test_find_repo_links_failures(
    httpserver: HTTPServer, deps_dev_service_mock: dict, data: str, expected_outcome: RepoFinderInfo
) -> None:
    """Test invalid links."""
    purl = PackageURL.from_string("pkg:pypi/example@2")
    target_url = (
        f"/{deps_dev_service_mock['api']}/{deps_dev_service_mock['purl']}/pkg:{purl.type}/{purl.name}@{purl.version}"
    )

    httpserver.expect_request(target_url).respond_with_data(data)
    result, outcome = DepsDevRepoFinder().find_repo(purl)

    assert not result
    assert outcome == expected_outcome


def test_find_repo_success(httpserver: HTTPServer, deps_dev_service_mock: dict) -> None:
    """Test repo finder success."""
    purl = PackageURL.from_string("pkg:pypi/example@2")
    target_url = (
        f"/{deps_dev_service_mock['api']}/{deps_dev_service_mock['purl']}/pkg:{purl.type}/{purl.name}@{purl.version}"
    )

    httpserver.expect_request(target_url).respond_with_data('{"links": [{"url": "http://github.com/oracle/macaron"}]}')
    result, outcome = DepsDevRepoFinder().find_repo(purl)

    assert result
    assert outcome == RepoFinderInfo.FOUND


@pytest.mark.parametrize(
    "repo_url",
    [
        "http::::://130/test",
        "http://github.com/oracle/macaron",
    ],
)
def test_get_project_info_invalid_url(
    deps_dev_service_mock: dict, repo_url: str  # pylint: disable=unused-argument
) -> None:
    """Test get project info invalid url."""
    assert not DepsDevRepoFinder().get_project_info(repo_url)


def test_get_project_info_invalid_json(httpserver: HTTPServer, deps_dev_service_mock: dict) -> None:
    """Test get project info invalid json."""
    server_url = "/oracle/macaron"
    repo_url = f"{deps_dev_service_mock['base_scheme']}://{deps_dev_service_mock['base_netloc']}{server_url}"
    target_url = f"/{deps_dev_service_mock['api']}/projects/{deps_dev_service_mock['base_hostname']}{server_url}"
    httpserver.expect_request(target_url).respond_with_data("INVALID JSON")

    assert not DepsDevRepoFinder().get_project_info(repo_url)


def test_get_project_info_success(httpserver: HTTPServer, deps_dev_service_mock: dict) -> None:
    """Test get project info success."""
    path = "/oracle/macaron"
    repo_url = f"{deps_dev_service_mock['base_scheme']}://{deps_dev_service_mock['base_netloc']}{path}"
    target_url = f"/{deps_dev_service_mock['api']}/projects/{deps_dev_service_mock['base_hostname']}{path}"
    httpserver.expect_request(target_url).respond_with_data('{"foo": "bar"}')

    assert DepsDevRepoFinder().get_project_info(repo_url)


@pytest.mark.parametrize(
    ("purl_string", "server_url", "data", "expected_outcome"),
    [
        ("pkg:pypi/test@3", False, "", RepoFinderInfo.DDEV_API_ERROR),
        ("pkg:pypi/test@3", True, '{"foo": "bar"}', RepoFinderInfo.DDEV_JSON_INVALID),
        ("pkg:pypi/test@3", True, '{"version": [1]}', RepoFinderInfo.DDEV_JSON_INVALID),
    ],
)
def test_get_latest_version_failures(
    httpserver: HTTPServer,
    deps_dev_service_mock: dict,
    purl_string: str,
    server_url: bool,
    data: str,
    expected_outcome: RepoFinderInfo,
) -> None:
    """Test get latest version failures."""
    purl = PackageURL.from_string(purl_string)

    if server_url:
        target_url = f"/{deps_dev_service_mock['api']}/{deps_dev_service_mock['purl']}/pkg:{purl.type}/{purl.name}"
        httpserver.expect_request(target_url).respond_with_data(data)

    result, outcome = DepsDevRepoFinder().get_latest_version(purl)

    assert not result
    assert outcome == expected_outcome


def test_get_latest_version_success(httpserver: HTTPServer, deps_dev_service_mock: dict) -> None:
    """Test get latest version success."""
    purl = PackageURL.from_string("pkg:pypi/test@3")
    target_url = f"/{deps_dev_service_mock['api']}/{deps_dev_service_mock['purl']}/pkg:{purl.type}/{purl.name}"
    httpserver.expect_request(target_url).respond_with_data(
        '{"version": [{"versionKey":{"version": "4"}, "isDefault":true}]}'
    )
    result, outcome = DepsDevRepoFinder().get_latest_version(purl)
    assert result
    assert outcome == RepoFinderInfo.FOUND_FROM_LATEST


@pytest.mark.parametrize(
    ("purl_string", "server_url", "data"),
    [
        ("pkg:pypi/test", False, ""),
        ("pkg:pypi/test@3", False, ""),
        ("pkg:pypi/test@3", True, '{"foo": "bar"}'),
        ("pkg:pypi/test@3", True, '{"attestations": [1, 2]}'),
        ("pkg:pypi/test@3", True, '{"attestations": [{"url": "*replace_url*/bad_endpoint"}]}'),
        ("pkg:pypi/test@3", True, '{"attestations": [{"url": "*replace_url*"}]}'),
        ("pkg:pypi/test@3", True, '{"attestations": [{"url": "*replace_url*"}], "attestation_bundles": [1,2]}'),
        (
            "pkg:pypi/test@3",
            True,
            '{"attestations": [{"url": "*replace_url*"}], "attestation_bundles": [{"attestations": [1]}]}',
        ),
    ],
)
def test_get_attestation_failures(
    httpserver: HTTPServer, deps_dev_service_mock: dict, purl_string: str, server_url: bool, data: str
) -> None:
    """Test get attestation failures."""
    purl = PackageURL.from_string(purl_string)

    if server_url:
        assert purl.version
        target_url = f"/{deps_dev_service_mock['api']}/{deps_dev_service_mock['purl']}/{purl}"
        if "*replace_url*" in data:
            attestation_url = (
                f"{deps_dev_service_mock['base_scheme']}://{deps_dev_service_mock['base_netloc']}{target_url}"
            )
            data = data.replace("*replace_url*", attestation_url)

        httpserver.expect_request(target_url).respond_with_data(data)

    result, _, _ = DepsDevRepoFinder().get_attestation(purl)
    assert not result


def test_get_attestation_success(httpserver: HTTPServer, deps_dev_service_mock: dict) -> None:
    """Test get attestation success."""
    purl = PackageURL.from_string("pkg:pypi/test@3")
    target_url = f"/{deps_dev_service_mock['api']}/{deps_dev_service_mock['purl']}/{purl}"
    attestation_url = f"{deps_dev_service_mock['base_scheme']}://{deps_dev_service_mock['base_netloc']}{target_url}"
    data = """
        {
            "attestations": [
                {
                    "url": "*replace_url*",
                    "verified": true
                }
            ],
            "attestation_bundles": [
                {
                    "attestations": [
                        {
                            "foo": "bar"
                        }
                    ]
                }
            ]
        }
    """
    data = data.replace("*replace_url*", attestation_url)
    httpserver.expect_request(target_url).respond_with_data(data)
    result, url, verified = DepsDevRepoFinder().get_attestation(purl)
    assert result
    assert url == attestation_url
    assert verified
