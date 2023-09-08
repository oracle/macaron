# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module exists to validate URLs in terms of their use as a repository that can be analyzed."""
from collections.abc import Iterable

from macaron.slsa_analyzer.git_url import get_remote_vcs_url


def find_valid_repository_url(urls: Iterable[str]) -> str:
    """Find a valid URL from the provided URLs.

    Parameters
    ----------
    urls : Iterable[str]
        An Iterable object containing urls.

    Returns
    -------
    str
        A valid URL or empty if it can't find any valid URL.
    """
    vcs_set = {get_remote_vcs_url(value) for value in urls if get_remote_vcs_url(value) != ""}

    # To avoid non-deterministic results we sort the URLs.
    vcs_list = sorted(vcs_set)

    if len(vcs_list) < 1:
        return ""

    # Report the first valid URL from the end of the list.
    return vcs_list.pop()
