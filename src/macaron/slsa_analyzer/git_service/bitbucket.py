# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the spec for the BitBucket service."""

from macaron.slsa_analyzer import git_url
from macaron.slsa_analyzer.git_service.base_git_service import BaseGitService


class BitBucket(BaseGitService):
    """This class contains the spec of the BitBucket service."""

    def __init__(self) -> None:
        super().__init__("bitbucket")

    def load_defaults(self) -> None:
        pass

    def can_clone_remote_repo(self, url: str) -> bool:
        pass

    def is_detected(self, url: str) -> bool:
        parsed_url = git_url.parse_remote_url(url)
        if not parsed_url or self.name not in parsed_url.netloc:
            return False

        return True
