# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the logic to nomarlize a JDK version string to a major version number."""

SUPPORTED_JAVA_VERSION = [
    "5",
    "6",
    "7",
    "8",
    "9",
    "10",
    "11",
    "12",
    "13",
    "14",
    "15",
    "16",
    "17",
    "18",
    "19",
    "20",
    "21",
    "22",
    "23",
    "24",
]


def normalize_jdk_version(jdk_version_str: str) -> str | None:
    """Return the major JDK version number.

    We assume that the jdk version string is already valid (e.g not using a JDK
    version that is not available in the real world.

    For 1.x versions, we returns the major version as ``x``.

    Parameters
    ----------
    jdk_version_str: str
        The jdk version string.

    Returns
    -------
    str | None
        The major jdk version number as string or None if there is an error.

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
    """
    first, _, after = jdk_version_str.partition(".")
    jdk_major_ver = None
    if first == "1":
        # Cases like 1.8.0_523
        # Or 1.8
        jdk_major_ver, _, _ = after.partition(".")
    else:
        # Cases like 11 or 11.0 or 11.0.1
        jdk_major_ver = first

    if jdk_major_ver in SUPPORTED_JAVA_VERSION:
        return jdk_major_ver

    # Handle edge cases:
    #   pkg:maven/org.apache.druid.integration-tests/druid-it-cases@25.0.0
    #         - "8 (Azul Systems Inc. 25.282-b08)"
    #   pkg:maven/io.helidon.reactive.media/helidon-reactive-media-jsonp@4.0.0-ALPHA1
    #         - "19-ea"
    for support in SUPPORTED_JAVA_VERSION:
        # Wouldn't work for cases like 19000 but that's not a big problem
        # as long as the result is a valid major version.
        if jdk_major_ver.startswith(support):
            return support

    return None
