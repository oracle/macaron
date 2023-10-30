# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
This module test the slsa_analyzer.requirement module
"""

from macaron.slsa_analyzer.slsa_req import SLSAReqStatus


def test_slsa_requirements_status() -> None:
    """
    Test requirement status
    """
    req_status = SLSAReqStatus()
    assert (False, False, "") == req_status.get_tuple()

    feedback = "This repo passes this requirement"
    req_status.set_status(True, feedback)
    assert req_status.is_addressed
    assert req_status.is_pass
    assert req_status.feedback == feedback
    assert (True, True, feedback) == req_status.get_tuple()
