# Copyright (c) 2025 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the logic to normalize a JDK version string as a major version number."""

import re

# The oldest major JDK version we recognize. Newer major versions are accepted as they are released,
# so that a JDK released after this module was written (e.g. 25 or 26) is not rejected.
MIN_SUPPORTED_JAVA_MAJOR_VERSION = 5

LEADING_DIGITS_PATTERN = re.compile(r"\d+")


def normalize_jdk_version(jdk_version_str: str) -> str | None:
    """Return the major JDK version number.

    We assume that the JDK version string is already valid (e.g Using a JDK
    version that is available in the real world).

    For 1.x versions, we return the major version as ``x``.

    Parameters
    ----------
    jdk_version_str: str
        The JDK version string.

    Returns
    -------
    str | None
        The major JDK version number as a string, or None if there is an error.

    Examples
    --------
    >>> normalize_jdk_version("19")
    '19'
    >>> normalize_jdk_version("19-ea")
    '19'
    >>> normalize_jdk_version("11.0.1")
    '11'
    >>> normalize_jdk_version("1.8")
    '8'
    >>> normalize_jdk_version("25.0.1")
    '25'
    >>> normalize_jdk_version("1.4")
    """
    first, _, after = jdk_version_str.partition(".")
    if first == "1":
        # Cases like 1.8.0_523
        # Or 1.8
        jdk_major_ver, _, _ = after.partition(".")
    else:
        # Cases like 11 or 11.0 or 11.0.1
        jdk_major_ver = first

    # Only keep the leading digits to handle edge cases:
    #   pkg:maven/org.apache.druid.integration-tests/druid-it-cases@25.0.0
    #         - "8 (Azul Systems Inc. 25.282-b08)"
    #   pkg:maven/io.helidon.reactive.media/helidon-reactive-media-jsonp@4.0.0-ALPHA1
    #         - "19-ea"
    match = LEADING_DIGITS_PATTERN.match(jdk_major_ver.strip())
    if not match:
        return None

    major_version = int(match.group())
    if major_version < MIN_SUPPORTED_JAVA_MAJOR_VERSION:
        return None

    return str(major_version)
