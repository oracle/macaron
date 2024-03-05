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
        The first valid URL from the iterable, or an empty string if none can be found.
    """
    for url in urls:
        parsed_url = clean_url(url)
        if not parsed_url:
            # URLs that fail to parse can be rejected here.
            continue
        redirect_url = resolve_redirects(parsed_url)
        checked_url = get_remote_vcs_url(redirect_url if redirect_url else parsed_url.geturl())
        if checked_url:
            return checked_url

    return ""


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
