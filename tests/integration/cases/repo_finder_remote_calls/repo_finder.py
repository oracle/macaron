# Copyright (c) 2023 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This script tests the functionality of the repo finder's remote API calls."""

import logging
import os
import sys

from packageurl import PackageURL

from macaron.config.defaults import defaults
from macaron.repo_finder import repo_validator
from macaron.repo_finder.repo_finder import find_repo
from macaron.repo_finder.repo_finder_deps_dev import DepsDevRepoFinder
from macaron.repo_finder.repo_finder_enums import RepoFinderInfo
from macaron.slsa_analyzer.git_url import clean_url

logger: logging.Logger = logging.getLogger(__name__)

# Set logging debug level.
logger.setLevel(logging.DEBUG)


def test_repo_finder() -> int:
    """Test the functionality of the remote API calls used by the repo finder."""
    if not defaults.has_section("repofinder.java"):
        defaults.add_section("repofinder.java")
    defaults.set("repofinder.java", "find_parents", "True")
    defaults.set("repofinder.java", "repo_pom_paths", "scm.url")
    defaults.set("repofinder.java", "artifact_repositories", "https://repo.maven.apache.org/maven2")

    if not defaults.has_section("repofinder"):
        defaults.add_section("repofinder")
    defaults.set("repofinder", "use_open_source_insights", "True")
    defaults.set("repofinder", "redirect_urls", "\n".join(["gitbox.apache.org", "git-wip-us.apache.org"]))

    if not defaults.has_section("git_service.github"):
        defaults.add_section("git_service.github")
    defaults.set("git_service.github", "hostname", "github.com")

    if not defaults.has_section("git_service.gitlab"):
        defaults.add_section("git_service.gitlab")
    defaults.set("git_service.gitlab", "hostname", "gitlab.com")

    if not defaults.has_section("deps_dev"):
        defaults.add_section("deps_dev")
    defaults.set("deps_dev", "url_netloc", "api.deps.dev")
    defaults.set("deps_dev", "url_scheme", "https")
    defaults.set("deps_dev", "api_endpoint", "v3alpha")
    defaults.set("deps_dev", "purl_endpoint", "purl")

    # Test Java package with SCM metadata in artifact POM.
    match, outcome = find_repo(PackageURL.from_string("pkg:maven/com.fasterxml.jackson.core/jackson-databind@2.14.2"))
    if not match or outcome != RepoFinderInfo.FOUND:
        return os.EX_UNAVAILABLE

    # Test Java package with SCM metadata in artifact's parent POM.
    match, outcome = find_repo(PackageURL.from_string("pkg:maven/commons-cli/commons-cli@1.5.0"))
    if not match or outcome != RepoFinderInfo.FOUND:
        return os.EX_UNAVAILABLE

    # Test deps.dev API for a Python package.
    match, outcome = find_repo(PackageURL.from_string("pkg:pypi/packageurl-python@0.11.1"))
    if not match or outcome != RepoFinderInfo.FOUND:
        return os.EX_UNAVAILABLE

    # Test deps.dev API for a Nuget package.
    match, outcome = find_repo(PackageURL.from_string("pkg:nuget/azure.core"))
    if not match or outcome != RepoFinderInfo.FOUND:
        return os.EX_UNAVAILABLE

    # Test deps.dev API for an NPM package.
    match, outcome = find_repo(PackageURL.from_string("pkg:npm/@colors/colors"))
    if not match or outcome != RepoFinderInfo.FOUND:
        return os.EX_UNAVAILABLE

    # Test deps.dev API for Cargo package.
    match, outcome = find_repo(PackageURL.from_string("pkg:cargo/rand_core"))
    if not match or outcome != RepoFinderInfo.FOUND:
        return os.EX_UNAVAILABLE

    # Test redirecting URL from Apache commons-io package.
    parsed_url = clean_url("https://git-wip-us.apache.org/repos/asf?p=commons-io.git")
    if not parsed_url or not repo_validator.resolve_redirects(parsed_url):
        return os.EX_UNAVAILABLE

    # Test Java package whose SCM metadata only points to the repo in later versions than is provided here.
    purl = PackageURL.from_string("pkg:maven/io.vertx/vertx-auth-common@3.8.0")
    repo, outcome = find_repo(purl)
    if outcome != RepoFinderInfo.FOUND_FROM_PARENT or repo == "https://github.com/eclipse-vertx/vertx-auth":
        return os.EX_UNAVAILABLE
    latest_purl, outcome = DepsDevRepoFinder().get_latest_version(purl)
    assert latest_purl
    if outcome != RepoFinderInfo.FOUND_FROM_LATEST:
        return os.EX_UNAVAILABLE
    repo, outcome = find_repo(latest_purl)
    if outcome != RepoFinderInfo.FOUND_FROM_PARENT or repo != "https://github.com/eclipse-vertx/vertx-auth":
        return os.EX_UNAVAILABLE

    # Test Java package that has no version.
    # Disabling the latest version check ensures that only the missing version is retrieved, preventing the fallback
    # functionality of using the non-Java method to find the version and repository.
    match, outcome = find_repo(
        PackageURL.from_string("pkg:maven/io.vertx/vertx-auth-common"), check_latest_version=False
    )
    if not match or outcome != RepoFinderInfo.FOUND_FROM_PARENT:
        return os.EX_UNAVAILABLE

    return os.EX_OK


if __name__ == "__main__":
    sys.exit(test_repo_finder())
