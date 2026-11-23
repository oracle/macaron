# Copyright (c) 2026 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Test repository redirects without depending on external redirect services."""

from urllib.parse import urlparse

import pytest
from pytest_httpserver import HTTPServer

from macaron.config.defaults import defaults
from macaron.repo_finder.repo_validator import resolve_redirects


@pytest.mark.parametrize("allowed", [True, False])
@pytest.mark.parametrize("status", [302, 200, 404])
def test_repository_redirects(
    httpserver: HTTPServer, monkeypatch: pytest.MonkeyPatch, allowed: bool, status: int
) -> None:
    """Only resolve redirects from configured hosts that return a Location header."""
    source = urlparse(httpserver.url_for("/repos/asf?p=commons-io.git"))
    target = "https://github.com/apache/commons-io"
    monkeypatch.setitem(defaults["repofinder"], "redirect_urls", source.netloc if allowed else "example.org")
    headers = {"Location": target} if status == 302 else {}
    if allowed:
        httpserver.expect_request("/repos/asf", query_string="p=commons-io.git").respond_with_data(
            "", status=status, headers=headers
        )

    assert resolve_redirects(source) == (target if allowed and status == 302 else None)
