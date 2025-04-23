# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains implementation of osv.dev service."""

import logging
import urllib.parse

import requests
from packaging import version

from macaron.config.defaults import defaults
from macaron.errors import APIAccessError
from macaron.json_tools import json_extract
from macaron.slsa_analyzer.git_url import get_tags_via_git_remote, is_commit_hash
from macaron.util import send_post_http_raw

logger: logging.Logger = logging.getLogger(__name__)


class OSVDevService:
    """The deps.dev service class."""

    @staticmethod
    def get_vulnerabilities_purl(purl: str) -> list:
        """Retrieve vulnerabilities associated with a specific package URL (PURL) by querying the OSV API.

        This method calls the OSV query API with the provided package URL (PURL) to fetch any known vulnerabilities
        associated with that package.

        Parameters
        ----------
        purl : str
            A string representing the Package URL (PURL) of the package to query for vulnerabilities.

        Returns
        -------
        list
            A list of vulnerabilities under the key "vulns" if any vulnerabilities are found
            for the provided package.

        Raises
        ------
        APIAccessError
            If there are issues with the API URL construction, missing configuration values, or invalid responses.
        """
        return OSVDevService.call_osv_query_api({"package": {"purl": purl}})

    @staticmethod
    def get_vulnerabilities_package_name(ecosystem: str, name: str) -> list:
        """
        Retrieve vulnerabilities associated with a specific package name and ecosystem by querying the OSV API.

        This method calls the OSV query API with the provided ecosystem and package name to fetch any known vulnerabilities
        associated with that package.

        Parameters
        ----------
        ecosystem : str
            A string representing the ecosystem of the package (e.g., "GitHub Actions", "npm", etc.).

        name : str
            A string representing the name of the package to query for vulnerabilities.

        Returns
        -------
        list
            A list of vulnerabilities under the key "vulns" if any vulnerabilities are found
            for the provided ecosystem and package name.

        Raises
        ------
        APIAccessError
            If there are issues with the API URL construction, missing configuration values, or invalid responses.
        """
        return OSVDevService.call_osv_query_api({"package": {"ecosystem": ecosystem, "name": name}})

    @staticmethod
    def get_vulnerabilities_package_name_batch(packages: list) -> list:
        """Retrieve vulnerabilities for a batch of packages based on their ecosystem and name.

        This method constructs a batch query to the OSV API to check for vulnerabilities in
        multiple packages by querying the ecosystem and package name. It processes the results
        while preserving the order of the input packages. If a package has associated vulnerabilities,
        it is included in the returned list.

        Parameters
        ----------
        packages : list
            A list of dictionaries, where each dictionary represents a package with keys:
            - "ecosystem" (str): The package's ecosystem (e.g., "GitHub Actions", "npm").
            - "name" (str): The name of the package.

        Returns
        -------
        list
            A list of packages from the input `packages` list that have associated vulnerabilities.
            The order of the returned packages matches the order of the input.

        Raises
        ------
        APIAccessError
            If there is an issue with querying the OSV API or if the results do not match the expected size.
        """
        query_data: dict[str, list] = {"queries": []}

        for pkg in packages:
            query_data["queries"].append({"package": {"ecosystem": pkg["ecosystem"], "name": pkg["name"]}})

        # The results returned by OSV reports the vulnerabilities, preserving the order.
        osv_res = OSVDevService.call_osv_querybatch_api(query_data, len(packages))
        results = []
        for index, res in enumerate(osv_res):
            if not res:
                continue
            results.append(packages[index])

        return results

    @staticmethod
    def get_osv_url(endpoint: str) -> str:
        """Construct a full API URL for a given OSV endpoint using values from the .ini configuration.

        The configuration is expected to be in a section named `[osv_dev]` within the defaults object,
        and must include the following keys:

        - `url_netloc`: The base domain of the API.
        - `url_scheme` (optional): The scheme (e.g., "https"). Defaults to "https" if not provided.
        - A key matching the provided `endpoint` argument (e.g., "query_endpoint"), which defines the URL path.

        Parameters
        ----------
        endpoint: str
            The key name of the endpoint in the `[osv_dev]` section to construct the URL path.

        Returns
        -------
        str
            The fully constructed API URL.

        Raises
        ------
        APIAccessError
            If required keys are missing from the configuration or if the URL cannot be constructed.
        """
        section_name = "osv_dev"
        if not defaults.has_section(section_name):
            raise APIAccessError(f"The section [{section_name}] is missing in the .ini configuration file.")
        section = defaults[section_name]

        url_netloc = section.get("url_netloc")
        if not url_netloc:
            raise APIAccessError(
                f'The "url_netloc" key is missing in section [{section_name}] of the .ini configuration file.'
            )
        url_scheme = section.get("url_scheme", "https")
        query_endpoint = section.get(endpoint)
        if not query_endpoint:
            raise APIAccessError(
                f'The "query_endpoint" key is missing in section [{section_name}] of the .ini configuration file.'
            )
        try:
            return urllib.parse.urlunsplit(
                urllib.parse.SplitResult(
                    scheme=url_scheme,
                    netloc=url_netloc,
                    path=query_endpoint,
                    query="",
                    fragment="",
                )
            )
        except ValueError as error:
            raise APIAccessError("Failed to construct the API URL.") from error

    @staticmethod
    def call_osv_query_api(query_data: dict) -> list:
        """Query the OSV (Open Source Vulnerability) knowledge base API with the given data.

        This method sends a POST request to the OSV API and processes the response to extract
        information about vulnerabilities based on the provided query data.

        Parameters
        ----------
        query_data : dict
            A dictionary containing the query parameters to be sent to the OSV API.
            The query data should conform to the format expected by the OSV API for querying vulnerabilities.

        Returns
        -------
        list
            A list of vulnerabilities under the key "vulns" if the query is successful
            and the response is valid.

        Raises
        ------
        APIAccessError
            If there are issues with the API URL construction, missing configuration values, or invalid responses.
        """
        try:
            url = OSVDevService.get_osv_url("query_endpoint")
        except APIAccessError as error:
            raise error
        response = send_post_http_raw(url, json_data=query_data, headers=None)
        res_obj = None
        if response:
            try:
                res_obj = response.json()
            except requests.exceptions.JSONDecodeError as error:
                raise APIAccessError(f"Unable to get a valid response from {url}: {error}") from error

        vulns = res_obj.get("vulns") if res_obj else None

        if isinstance(vulns, list):
            return vulns

        return []

    @staticmethod
    def call_osv_querybatch_api(query_data: dict, expected_size: int | None = None) -> list:
        """Query the OSV (Open Source Vulnerability) knowledge base API in batch mode and retrieves vulnerability data.

        This method sends a batch query to the OSV API and processes the response to extract
        a list of results. The method also validates that the number of results matches an
        optional expected size. It handles API URL construction, error handling, and response
        validation.

        Parameters
        ----------
        query_data : dict
            A dictionary containing the batch query data to be sent to the OSV API. This data
            should conform to the expected format for batch querying vulnerabilities.

        expected_size : int, optional
            The expected number of results from the query. If provided, the method checks that
            the number of results matches this value. If the actual number of results does
            not match the expected size, an exception is raised. Default is None.

        Returns
        -------
        list
            A list of results from the OSV API containing the vulnerability data that matches
            the query parameters.

        Raises
        ------
        APIAccessError
            If any of the required configuration keys are missing, if the API URL construction
            fails, or if the response from the OSV API is invalid or the number of results
            does not match the expected size.
        """
        try:
            url = OSVDevService.get_osv_url("querybatch_endpoint")
        except APIAccessError as error:
            raise error

        response = send_post_http_raw(url, json_data=query_data, headers=None)
        res_obj = None
        if response:
            try:
                res_obj = response.json()
            except requests.exceptions.JSONDecodeError as error:
                raise APIAccessError(f"Unable to get a valid response from {url}: {error}") from error

        results = res_obj.get("results") if res_obj else None

        if isinstance(results, list):
            if expected_size:
                if len(results) != expected_size:
                    raise APIAccessError(
                        f"Failed to retrieve a valid result from {url}: result count does not match the expected count."
                    )

            return results

        raise APIAccessError(f"The response from {url} does not contain a valid 'results' list.")

    @staticmethod
    def is_version_affected(
        vuln: dict, pkg_name: str, pkg_version: str, ecosystem: str, source_repo: str | None = None
    ) -> bool:
        """Check whether a specific version of a package is affected by a vulnerability.

        This method parses a vulnerability dictionary to determine whether a given package
        version falls within the affected version ranges for the specified ecosystem. The
        function handles version comparisons, extracting details about introduced and fixed
        versions, and determines if the version is affected by the vulnerability.

        Parameters
        ----------
        vuln : dict
            A dictionary representing the vulnerability data. It should contain the affected
            versions and ranges of the package in question, as well as the details of the
            introduced and fixed versions for each affected range.

        pkg_name : str
            The name of the package to check for vulnerability. This should match the package
            name in the vulnerability data.

        pkg_version : str
            The version of the package to check against the vulnerability data.

        ecosystem : str
            The ecosystem (e.g., npm, GitHub Actions) to which the package belongs. This should
            match the ecosystem in the vulnerability data.

        source_repo : str | None, optional
            The source repository URL, used if the `pkg_version` is a commit hash. If provided,
            the method will try to retrieve the corresponding version tag from the repository.
            Default is None.

        Returns
        -------
        bool
            Returns True if the given package version is affected by the vulnerability,
            otherwise returns False.

        Raises
        ------
        APIAccessError
            If the vulnerability data is incomplete or malformed, or if the version strings
            cannot be parsed correctly. This is raised in cases such as:
            - Missing affected version information
            - Malformed version data (e.g., invalid version strings)
            - Failure to parse the version ranges
        """
        # Check if a source repository is provided and if the package version is a commit hash.
        # If the package version is a commit hash, retrieve the corresponding tags from the remote repository
        # and try to match the commit hash with the tag. If a match is found, update `pkg_version` to the tag.
        if source_repo and is_commit_hash(pkg_version):
            tags: dict = get_tags_via_git_remote(source_repo) or {}
            for tag, commit in tags.items():
                if commit.startswith(pkg_version):
                    pkg_version = tag
                    break

            # If we were not able to find a tag for the commit hash, raise an exception.
            if is_commit_hash(pkg_version):
                raise APIAccessError(f"Failed to find a tag for {pkg_name}@{pkg_version}.")

        affected = json_extract(vuln, ["affected"], list)
        if not affected:
            raise APIAccessError(f"Received invalid response for {pkg_name}@{pkg_version}.")

        affected_ranges: list | None = None
        for rec in affected:
            if (
                (affected_pkg := json_extract(rec, ["package", "name"], str))
                and affected_pkg == pkg_name
                and (affected_eco := json_extract(rec, ["package", "ecosystem"], str))
                and affected_eco == ecosystem
            ):
                affected_ranges = json_extract(rec, ["ranges"], list)
                break

        if not affected_ranges:
            raise APIAccessError(f"Failed to extract affected versions for {pkg_name}@{pkg_version}.")

        for affected_range in affected_ranges:
            events = json_extract(affected_range, ["events"], list)
            if not events:
                raise APIAccessError(f"Failed to extract affected versions for {pkg_name}@{pkg_version}.")

            introduced = None
            fixed = None
            for e in events:
                if "introduced" in e:
                    introduced = e["introduced"]
                if "fixed" in e:
                    fixed = e["fixed"]

            # TODO: convert commit to tag & version
            parsed_introduced = version.Version("0")
            if introduced:
                try:
                    parsed_introduced = version.Version(introduced)
                except version.InvalidVersion as error:
                    logger.debug(error)

            parsed_fix = None
            if fixed:
                try:
                    parsed_fix = version.Version(fixed)
                except version.InvalidVersion as error:
                    logger.debug(error)

            try:
                parsed_version = version.Version(pkg_version)
            except version.InvalidVersion as error:
                raise APIAccessError(f"Failed to parse version string {pkg_version}.") from error

            try:
                if parsed_version > parsed_introduced or parsed_version == parsed_introduced:
                    if parsed_fix is not None:
                        if parsed_version == parsed_fix or parsed_version > parsed_fix:
                            continue

                    # If a fixed version does not exist, the current version is affected.
                    return True
            # We should not get this error, but if we do, we avoid false positives and continue with the next
            # version range.
            except ValueError as error:
                logger.debug(error)
                continue

        # If current version is smaller than the introduced version, it is not affected.
        return False
