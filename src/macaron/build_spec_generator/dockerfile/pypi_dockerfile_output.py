# Copyright (c) 2025 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module implements the logic to generate a dockerfile from a Python buildspec."""

import logging
import re
from textwrap import dedent

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from macaron.build_spec_generator.common_spec.base_spec import BaseBuildSpecDict
from macaron.errors import GenerateBuildSpecError

logger: logging.Logger = logging.getLogger(__name__)


def gen_dockerfile(buildspec: BaseBuildSpecDict) -> str:
    """Translate the build specification into a dockerfile built on OL9.

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
    language_version: str | None = pick_specific_version(buildspec)
    if language_version is None:
        raise GenerateBuildSpecError("Could not derive specific interpreter version")
    backend_install_commands: str = " && ".join(build_backend_commands(buildspec))
    build_tool_install: str = ""
    if (
        buildspec["build_tools"][0] != "pip"
        and buildspec["build_tools"][0] != "conda"
        and buildspec["build_tools"][0] != "flit"
    ):
        build_tool_install = f"pip install {buildspec['build_tools'][0]} && "
    elif buildspec["build_tools"][0] == "flit":
        build_tool_install = (
            f"pip install {buildspec['build_tools'][0]} && if test -f \"flit.ini\"; then python -m flit.tomlify; fi && "
        )
    dockerfile_content = f"""
    #syntax=docker/dockerfile:1.10
    FROM oraclelinux:9

    # Install core tools
    RUN dnf -y install which wget tar git

    # Install compiler and make
    RUN dnf -y install gcc make

    # Download and unzip interpreter
    RUN <<EOF
        wget https://www.python.org/ftp/python/{language_version}/Python-{language_version}.tgz
        tar -xf Python-{language_version}.tgz
    EOF

    # Install necessary libraries to build the interpreter
    # From: https://devguide.python.org/getting-started/setup-building/
    RUN dnf install \\
      gcc-c++ gdb lzma glibc-devel libstdc++-devel openssl-devel \\
      readline-devel zlib-devel libzstd-devel libffi-devel bzip2-devel \\
      xz-devel sqlite sqlite-devel sqlite-libs libuuid-devel gdbm-libs \\
      perf expat expat-devel mpdecimal python3-pip

    # Build interpreter and create venv
    RUN <<EOF
        cd Python-{language_version}
        ./configure --with-pydebug
        make -s -j $(nproc)
        ./python -m venv /deps
    EOF

    # Clone code to rebuild
    RUN <<EOF
        mkdir src
        cd src
        git clone {buildspec["git_repo"]} .
        git checkout --force {buildspec["git_tag"]}
    EOF

    WORKDIR /src

    # Install build and the build backends
    RUN <<EOF
        {backend_install_commands}
        /deps/bin/pip install build
    EOF

    # Run the build
    RUN {"source /deps/bin/activate && " + build_tool_install + " ".join(x for x in buildspec["build_commands"][0])}
    """

    return dedent(dockerfile_content)


def pick_specific_version(buildspec: BaseBuildSpecDict) -> str | None:
    """Find the latest python interpreter version satisfying inferred constraints.

    Parameters
    ----------
    buildspec: BaseBuildSpecDict
        The base build spec generated for the artifact.

    Returns
    -------
    str | None
        String in format major.minor.patch for the latest valid Python
        interpreter version, or None if no such version can be found.
    """
    # We can most smoothly rebuild Python 3.0.0 and above on OL
    version_set = SpecifierSet(">=3.0.0")
    for version in buildspec["language_version"]:
        try:
            version_set &= SpecifierSet(version)
        except InvalidSpecifier as error:
            logger.debug("Non-standard interpreter version encountered: %s (%s)", version, error)
            # Whilst the Python tags specify interpreter implementation
            # as well as version, with no standard way to parse out the
            # implementation, we can attempt to heuristically:
            try_parse_version = infer_interpreter_version(version)
            if try_parse_version:
                try:
                    version_set &= SpecifierSet(f">={try_parse_version}")
                except InvalidSpecifier as error_for_retry:
                    logger.debug("Could not parse interpreter version from: %s (%s)", version, error_for_retry)

    logger.debug(version_set)

    # Now to get the latest acceptable one, we can step through all interpreter
    # versions. For the most accurate result, we can query python.org for a
    # list of all versions, but for now we can approximate by stepping down
    # through every minor version from 3.14.0 to 3.0.0
    for minor in range(14, -1, -1):
        try:
            if Version(f"3.{minor}.0") in version_set:
                return f"3.{minor}.0"
        except InvalidVersion as error:
            logger.debug("Ran into issue converting %s to a version: %s", minor, error)
            return None
    return None


def infer_interpreter_version(specifier: str) -> str | None:
    """Infer interpreter version from Python-tag.

    Note: This function is called on version specifiers
    that we cannot trivially parse. In the case that
    it is a Python-tag, which is obtained from the
    wheel name, we attempt to infer the corresponding
    interpreter version.

    Parameters
    ----------
    specifier: str
        specifier string that could not be trivially parsed.

    Returns
    -------
    str | None
        The interpreter version inferred from the specifier, or
        None if we cannot parse the specifier as a Python-tag.

    Examples
    --------
    >>> infer_interpreter_version("py3")
    '3'
    >>> infer_interpreter_version("cp314")
    '3.14'
    >>> infer_interpreter_version("pypy311")
    '3.11'
    >>> infer_interpreter_version("malformed123")
    """
    # The primary alternative interpreter implementations are documented here:
    # https://www.python.org/download/alternatives/
    # We parse tags for these implementations using below regular expression:
    pattern = re.compile(r"^(py|cp|ip|pp|pypy|jy|graalpy)(\d{1,3})$")
    parsed_tag = pattern.match(specifier)
    if parsed_tag:
        digits = parsed_tag.group(2)
        # As match succeeded len(digits) \in {1,2,3}
        if len(digits) == 1:
            return parsed_tag.group(2)
        return f"{digits[0]}.{digits[1:]}"
    return None


def build_backend_commands(buildspec: BaseBuildSpecDict) -> list[str]:
    """Generate the installation commands for each inferred build backend.

    Parameters
    ----------
    buildspec: BaseBuildSpecDict
        The base build spec generated for the artifact.

    Returns
    -------
    list[str]
        List of the installation commands.
    """
    if not buildspec["build_requires"]:
        return []
    commands: list[str] = []
    for backend, version_constraint in buildspec["build_requires"].items():
        commands.append(f'/deps/bin/pip install "{backend}{version_constraint}"')
    # For a stable order on the install commands
    commands.sort()
    return commands
