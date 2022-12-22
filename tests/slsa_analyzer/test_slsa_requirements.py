# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
This module test the slsa_analyzer.requirement module
"""

from unittest import TestCase

from macaron.slsa_analyzer.levels import SLSALevels
from macaron.slsa_analyzer.slsa_req import BUILD_REQ_DESC, Category, SLSAReq, get_requirements_dict


class TestSLSARequirements(TestCase):
    """
    This class provided tests for the Requirement module
    """

    def setUp(self) -> None:
        """
        Create a simple requirement
        """
        name = "sample_req_name"
        desc = "sample_req_desc"
        category = Category.PROVENANCE
        level = SLSALevels.LEVEL1
        self.base_req = SLSAReq(name, desc, category, level)

    def test_status(self) -> None:
        """
        Test addressing status in a requirement
        """
        assert (False, False, "") == self.base_req.get_status()

        feedback = "This repo passes this requirement"
        self.base_req.set_status(True, feedback)
        assert self.base_req.is_addressed
        assert self.base_req.is_pass
        assert self.base_req.feedback == feedback
        assert (True, True, feedback) == self.base_req.get_status()

    def test_get_requirements_dict(self) -> None:
        """
        Test if all the requirements defined in ReqName class are included in the returned dictionary.
        """
        all_reqs = get_requirements_dict()
        assert all(req in all_reqs for req in BUILD_REQ_DESC)
