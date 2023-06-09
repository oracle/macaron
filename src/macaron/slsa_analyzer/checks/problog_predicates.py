# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Contains ProbLog predicates that return the results stored in the BuildAsCodeSubchecks dataclass."""
from problog.extern import problog_export

from macaron.slsa_analyzer.checks.build_as_code_subchecks import build_as_code_subcheck_results


@problog_export("-int")  # type: ignore
def ci_parsed_check() -> float:
    """Get the value of the subcheck.

    Returns
    -------
    Certainty
        The certainty of the check.
    """
    return build_as_code_subcheck_results.ci_parsed()


@problog_export("-int")  # type: ignore
def deploy_action_check() -> float:
    """Get the value of the subcheck.

    Returns
    -------
    Certainty
        The certainty of the check.
    """
    return build_as_code_subcheck_results.deploy_action()


@problog_export("-int")  # type: ignore
def deploy_command_check() -> float:
    """Get the value of the subcheck.

    Returns
    -------
    Certainty
        The certainty of the check.
    """
    return build_as_code_subcheck_results.deploy_command()


@problog_export("-int")  # type: ignore
def deploy_kws_check() -> float:
    """Get the value of the subcheck.

    Returns
    -------
    Certainty
        The certainty of the check.
    """
    return build_as_code_subcheck_results.deploy_kws()


@problog_export("-int")  # type: ignore
def workflow_trigger_deploy_commmand() -> float:
    """Get the value of the subcheck.

    Returns
    -------
    Certainty
        The certainty of the check.
    """
    return build_as_code_subcheck_results.workflow_trigger_deploy_command()


@problog_export("-int")  # type: ignore
def workflow_trigger_deploy_action() -> float:
    """Get the value of the subcheck.

    Returns
    -------
    Certainty
        The certainty of the check.
    """
    return build_as_code_subcheck_results.workflow_trigger_deploy_action()
