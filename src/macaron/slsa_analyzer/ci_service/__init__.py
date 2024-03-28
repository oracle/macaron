# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""The ci_service package contains the supported CI services for Macaron."""

from macaron.slsa_analyzer.ci_service.github_actions.github_actions_ci import GitHubActions

from .base_ci_service import BaseCIService
from .circleci import CircleCI
from .gitlab_ci import GitLabCI
from .jenkins import Jenkins
from .travis import Travis

# The list of supported CI services. The order of the list determines the order
# in which each ci service is checked against the target repository.
CI_SERVICES: list[BaseCIService] = [GitHubActions(), Jenkins(), Travis(), CircleCI(), GitLabCI()]
