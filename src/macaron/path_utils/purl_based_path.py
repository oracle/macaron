# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains functions to manage PackageURL-based paths."""

import os
import string


def get_purl_based_dir(
    purl_type: str,
    purl_name: str,
    purl_namespace: str | None = None,
) -> str:
    """Return a directory path according to components of a PackageURL.

    Parameters
    ----------
    purl_type: str
        The type component of the PackageURL as string.
    purl_name:str
        The name component of the PackageURL as string.
    purl_namespace: str | None = None
        The namespace component of the PackageURL as string (optional).

    Returns
    -------
    str
        The directory path.

    Examples
    --------
    >>> get_purl_based_dir(purl_type="maven", purl_name="macaron", purl_namespace="oracle")
    'maven/oracle/macaron'
    """
    # Sanitize the path and make sure it's a valid file name.
    # A purl string is an ASCII URL string that can allow uppercase letters for
    # certain parts. So we shouldn't change uppercase letters with lower case
    # to avoid merging results for two distinct PURL strings.
    allowed_chars = string.ascii_letters + string.digits + "-"
    p_type = "".join(c if c in allowed_chars else "_" for c in purl_type)
    p_namespace = "".join(c if c in allowed_chars else "_" for c in purl_namespace) if purl_namespace else ""
    p_name = "".join(c if c in allowed_chars else "_" for c in purl_name)
    return os.path.join(p_type, p_namespace, p_name)
