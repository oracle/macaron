# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This package contains the dependency resolvers for Java projects."""


def to_domain_from_known_purl_types(purl_type: str) -> str | None:
    """Return the git service domain from a known web-based purl type.

    This method is used to handle cases where the purl type value is not the git domain but a pre-defined
    repo-based type in https://github.com/package-url/purl-spec/blob/master/PURL-TYPES.rst.

    Note that this method will be updated when there are new pre-defined types as per the PURL specification.

    Parameters
    ----------
    purl_type : str
        The type field of the PURL.

    Returns
    -------
    str | None
        The git service domain corresponding to the purl type or None if the purl type is unknown.
    """
    known_types = {"github": "github.com", "bitbucket": "bitbucket.org"}
    return known_types.get(purl_type, None)
