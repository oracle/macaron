# Copyright (c) 2025 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module implements the logic to generate a dockerfile from a Python buildspec."""

import logging
import re
from textwrap import dedent

from bs4 import BeautifulSoup, FeatureNotFound
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from macaron.build_spec_generator.common_spec.base_spec import BaseBuildSpecDict
from macaron.errors import GenerateBuildSpecError
from macaron.util import send_get_http_raw

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
    if buildspec["has_binaries"]:
        raise GenerateBuildSpecError("We currently do not support generating a dockerfile for non-pure Python packages")
    language_version: str | None = pick_specific_version(buildspec["language_version"])
    if language_version is None:
        raise GenerateBuildSpecError("Could not derive specific interpreter version")
    try:
        version = Version(language_version)
    except InvalidVersion as error:
        logger.debug("Ran into issue converting %s to a version: %s", language_version, error)
        raise GenerateBuildSpecError("Derived interpreter version could not be parsed") from error
    if not buildspec["build_tools"]:
        raise GenerateBuildSpecError("Cannot generate dockerfile when build tool is unknown")
    if not buildspec["build_commands"]:
        raise GenerateBuildSpecError("Cannot generate dockerfile when build command is unknown")
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

    modern_build_command = build_tool_install + " ".join(x for x in buildspec["build_commands"][0])
    legacy_build_command = (
        'if test -f "setup.py"; then pip install wheel && python setup.py bdist_wheel; '
        "else python -m build --wheel -n; fi"
    )

    wheel_url = buildspec["upstream_artifacts"]["wheel"]
    wheel_name = wheel_url.rsplit("/", 1)[-1]

    dockerfile_content = f"""
    #syntax=docker/dockerfile:1.10
    FROM oraclelinux:9

    # Install core tools
    RUN dnf -y install which wget tar unzip git

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
      perf expat expat-devel mpdecimal python3-pip \\
      perl perl-File-Compare

    {openssl_install_commands(version)}

    ENV LD_LIBRARY_PATH=/opt/openssl/lib
    ENV CPPFLAGS=-I/opt/openssl/include
    ENV LDFLAGS=-L/opt/openssl/lib

    # Build interpreter and create venv
    RUN <<EOF
        cd Python-{language_version}
        ./configure --with-pydebug
        make -s -j $(nproc)
        make install
        ./python -m ensurepip
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
    RUN source /deps/bin/activate &&  {modern_build_command if version in SpecifierSet(">=3.6") else legacy_build_command}

    # Validate script
    RUN cat <<'EOF' >/validate
        # Capture artifacts generated
        ARTIFACTS=(/src/dist/*)
        # Ensure we only have one artefact
        [ ${{#ARTIFACTS[@]}} -eq 1 ] || {{ echo "Unexpected artifacts prodced!"; exit 1; }}
        # BUILT_WHEEL is the artefact we built
        BUILT_WHEEL=${{ARTIFACTS[0]}}
        # Download the wheel
        wget -q {wheel_url}
        # Compare wheel names
        [ $(basename $BUILT_WHEEL) == "{wheel_name}" ] || {{ echo "Wheel name does not match!"; exit 1; }}
        # Compare file tree
        (unzip -Z1 $BUILT_WHEEL | sort) > built.tree
        (unzip -Z1 "{wheel_name}" | sort ) > pypi_artefact.tree
        diff -u built.tree pypi_artefact.tree || {{ echo "File trees do not match!"; exit 1; }}
        echo "Success!"
    EOF

    ENTRYPOINT ["/bin/bash","/validate"]
    """

    return dedent(dockerfile_content)


def openssl_install_commands(version: Version) -> str:
    """Appropriate openssl install commands for a given CPython version.

    Parameters
    ----------
    version: Version
        CPython version we are trying to build

    Returns
    -------
    str
       Install commands for the corresponding openssl version
    """
    # As per https://peps.python.org/pep-0644, all Python >= 3.10 requires at least OpenSSL 1.1.1,
    # and 3.6 to 3.9 can be compiled with OpenSSL 1.1.1. Therefore, we compile as below:
    if version in SpecifierSet(">=3.6"):
        openssl_version = "1.1.1w"
        source_url = "https://www.openssl.org/source/old/1.1.1/openssl-1.1.1w.tar.gz"
    # From the same document, "Python versions 3.6 to 3.9 are compatible with OpenSSL 1.0.2,
    # 1.1.0, and 1.1.1". As an attempt to generalize for any >= 3.3, we use OpenSSL 1.0.2.
    else:
        openssl_version = "1.0.2u"
        source_url = "https://www.openssl.org/source/old/1.0.2/openssl-1.0.2u.tar.gz"

    return f"""# Build OpenSSL {openssl_version}
    RUN <<EOF
        wget {source_url}
        tar xzf openssl-{openssl_version}.tar.gz
        cd openssl-{openssl_version}
        ./config --prefix=/opt/openssl --openssldir=/opt/openssl shared zlib
        make -j"$(nproc)"
        make install_sw
    EOF"""


def pick_specific_version(inferred_constraints: list[str]) -> str | None:
    """Find the latest python interpreter version satisfying inferred constraints.

    Parameters
    ----------
    inferred_constraints: list[str]
        List of inferred Python version constraints

    Returns
    -------
    str | None
        String in format major.minor.patch for the latest valid Python
        interpreter version, or None if no such version can be found.

    Examples
    --------
    >>> pick_specific_version([">=3.0"])
    '3.4.10'
    >>> pick_specific_version([">=3.8"])
    '3.8.20'
    >>> pick_specific_version([">=3.0", "!=3.4", "!=3.3", "!=3.5"])
    '3.6.15'
    >>> pick_specific_version(["<=3.12"])
    '3.4.10'
    >>> pick_specific_version(["<=3.12", "==3.6"])
    '3.6.15'
    """
    # We cannot create virtual environments for Python versions <= 3.3.0, as
    # it did not exist back then
    version_set = SpecifierSet(">=3.4.0")
    for version in inferred_constraints:
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

    # Now to get the earliest acceptable one, we can step through all interpreter
    # versions. For the most accurate result, we can query python.org for a
    # list of all versions, but for now we can approximate by stepping up
    # through every minor version from 3.3.0 to 3.14.0
    for minor in range(3, 15, 1):
        try:
            if Version(f"3.{minor}.0") in version_set:
                return get_latest_cpython_patch(3, minor)
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


def get_latest_cpython_patch(major: int, minor: int) -> str:
    """Given major and minor interpreter version, return latest CPython patched version.

    Parameters
    ----------
    major: int
        Major component of version
    minor: int
        Minor component of version

    Returns
    -------
    str
        Full major.minor.patch version string corresponding to latest
        patch for input major and minor.
    """
    latest_patch: Version | None = None
    # We install CPython source
    response = send_get_http_raw("https://www.python.org/ftp/python/")
    if not response:
        raise GenerateBuildSpecError("Failed to fetch index of CPython versions.")

    html: str = ""
    soup: BeautifulSoup | None = None

    try:
        html = response.content.decode("utf-8")
        soup = BeautifulSoup(html, "html.parser")
    except (UnicodeDecodeError, FeatureNotFound) as error:
        raise GenerateBuildSpecError("Failed to parse index of CPython versions.") from error

    # Versions can most reliably be found in anchor tags like:
    # <a href="{Version}/"> {Version}/ </a>
    for anchor in soup.find_all("a", href=True):
        # Get text enclosed in the anchor tag stripping spaces.
        text = anchor.get_text(strip=True)
        sanitized_text = text.rstrip("/")
        # Try to convert to a version.
        try:
            parsed_version = Version(sanitized_text)
            if parsed_version.major == major and parsed_version.minor == minor:
                if latest_patch is None or parsed_version > latest_patch:
                    latest_patch = parsed_version
        except InvalidVersion:
            # Try the next tag
            continue

    if not latest_patch:
        raise GenerateBuildSpecError(f"Failed to infer latest patch for CPython {major}.{minor}")

    return str(latest_patch)


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
        if backend == "setuptools":
            commands.append("/deps/bin/pip install --upgrade setuptools")
        else:
            commands.append(f'/deps/bin/pip install "{backend}{version_constraint}"')
    # For a stable order on the install commands
    commands.sort()
    return commands
