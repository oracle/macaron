# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module exists to validate URLs in terms of their use as a repository that can be analyzed."""
import urllib.parse
from collections.abc import Iterable

from macaron.config.defaults import defaults
from macaron.slsa_analyzer.git_url import clean_url, get_remote_vcs_url
from macaron.util import send_get_http_raw


def find_valid_repository_url(urls: Iterable[str]) -> str:
    """Find a valid URL from the provided URLs.

    Parameters
    ----------
    urls : Iterable[str]
        An Iterable object containing urls.

    Returns
    -------
    str
        A valid URL, or an empty string if none can be found.
    """
    pruned_list = []
    for url in urls:
        parsed_url = clean_url(url)
        if not parsed_url:
            # URLs that failed to parse can be rejected here.
            continue
        redirect_url = resolve_redirects(parsed_url)
        # If a redirect URL is found add it, otherwise add the parsed url.
        pruned_list.append(redirect_url if redirect_url else parsed_url.geturl())

    vcs_set = {get_remote_vcs_url(value) for value in pruned_list if get_remote_vcs_url(value) != ""}

    # To avoid non-deterministic results we sort the URLs.
    vcs_list = sorted(vcs_set)

    if len(vcs_list) < 1:
        return ""

    # Report the first valid URL from the end of the list.
    return vcs_list.pop()


def resolve_redirects(parsed_url: urllib.parse.ParseResult) -> str | None:
    """Resolve redirecting URLs by returning the location they point to.

    Parameters
    ----------
    parsed_url: ParseResult
        A parsed URL.

    Returns
    -------
    str | None
        The resolved redirect location, or None if none was found.
    """
    redirect_list = defaults.get_list("repofinder", "redirect_urls", fallback=[])
    if parsed_url.netloc in redirect_list:
        response = send_get_http_raw(parsed_url.geturl(), allow_redirects=False)
        if not response:
            return None
        return response.headers.get("location")
    return None
