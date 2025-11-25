# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module acts as the dispatcher to execute the right dockerfile generation logic for a buildspec's ecosystem."""

import macaron.build_spec_generator.dockerfile.pypi_dockerfile_ouput as pypi_output
from macaron.build_spec_generator.common_spec.base_spec import BaseBuildSpecDict
from macaron.errors import GenerateBuildSpecError


def gen_dockerfile(buildspec: BaseBuildSpecDict) -> str:
    """Dispatches the gen_dockerfile corresponding to the build's ecosystem.

    Parameters
    ----------
    buildspec: BaseBuildSpecDict
        The base build spec generated for the artifact.

    Returns
    -------
    str
        Contents of the dockerfile for this artifact's rebuild.

    Raises
    ------
    GenerateBuildSpecError
        Raised if dockerfile cannot be generated.
    """
    match buildspec["ecosystem"]:
        case "pypi":
            return pypi_output.gen_dockerfile(buildspec)
        case _:
            raise GenerateBuildSpecError(
                f"Dockerfile generation for {buildspec['ecosystem']} is not currently supported."
                "Supported ecosystems: pypi"
            )
