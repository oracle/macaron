# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""The build_tool package contains the supported build tools for Macaron."""

from .base_build_tool import BaseBuildTool
from .docker import Docker
from .go import Go
from .gradle import Gradle
from .maven import Maven
from .npm import NPM
from .pip import Pip
from .poetry import Poetry
from .yarn import Yarn

# The list of supported build tools. The order of the list determine the order
# in which each build tool is checked against the target repository.
BUILD_TOOLS: list[BaseBuildTool] = [Gradle(), Maven(), Poetry(), Pip(), Docker(), NPM(), Yarn(), Go()]
