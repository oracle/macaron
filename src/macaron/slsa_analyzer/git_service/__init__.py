# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""The git_service package contains the supported git services for Macaron."""

from .base_git_service import BaseGitService
from .bitbucket import BitBucket
from .github import GitHub
from .gitlab import PubliclyHostedGitLab, SelfHostedGitLab

# The list of supported git services. The order of the list determines the order
# in which each git service is checked against the target repository.
GIT_SERVICES: list[BaseGitService] = [GitHub(), PubliclyHostedGitLab(), SelfHostedGitLab(), BitBucket()]
