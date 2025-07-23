# Copyright (c) 2022 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.
# grammar: off

"""This module contains the BuildSpec class."""

from typing import TypedDict

from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool


class BuildInfo(TypedDict):
    """This class contains the properties of a build process.

    References
    ----------
        - https://github.com/jfrog/build-info
        - https://reproducible-builds.org/docs/jvm/
    """

    # TODO: Make BuildInfo following the schema at
    # https://github.com/jfrog/build-info-go/blob/main/buildinfo-schema.json.
    status: bool
    """The status of the build."""
    build_log: str
    """The log of the build."""


class BuildSpec(TypedDict):
    """This class contains the specs for building a Java artifact.

    References
    ----------
        - https://github.com/jvm-repo-rebuild/reproducible-central/blob/master/doc/BUILDSPEC.md
    """

    ## GAV of the artifact
    # group_id: str
    # artifactId: str
    # version: str

    ## Source code
    # gitRepo: str
    # gitTag: str
    ## or use source zip archive
    # sourceDistribution: str
    # sourcePath: str
    # sourceRmFiles: str

    ## Rebuild environment prerequisites

    #: The build tools used for building this artifact.
    tools: list[BaseBuildTool]

    #: The build tools that match the software component PackageURL type.
    purl_tools: list[BaseBuildTool]

    # jdk: str
    # newline: str
    ## crlf for Windows, lf for Unix

    ## Rebuild command
    # command: str

    ## Properties observed during the build process
    # build_info: BuildInfo

    ## If the release is finally not reproducible, link to an issue tracker entry if one was created.
    ## diffoscope is the diffoscope command to run
    # diffoscope: str
    # issue: str
