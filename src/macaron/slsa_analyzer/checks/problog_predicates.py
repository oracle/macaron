# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Contains ProbLog predicates that return the results stored in the BuildAsCodeSubchecks dataclass."""
import logging

from problog.extern import problog_export

from macaron.slsa_analyzer.checks.build_as_code_subchecks import build_as_code_subcheck_results

FAILED_CHECK = 0.0

logger: logging.Logger = logging.getLogger(__name__)


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
    depends_on = [ci_parsed_check() > 0]
    if not all(depends_on):
        return FAILED_CHECK
    return build_as_code_subcheck_results.deploy_action()


@problog_export("-int")  # type: ignore
def deploy_command_check() -> float:
    """Get the value of the subcheck.

    Returns
    -------
    Certainty
        The certainty of the check.
    """
    depends_on = [ci_parsed_check() > 0.0]
    if not all(depends_on):
        return FAILED_CHECK
    return build_as_code_subcheck_results.deploy_command()


@problog_export("-int")  # type: ignore
def deploy_kws_check() -> float:
    """Get the value of the subcheck.

    Returns
    -------
    Certainty
        The certainty of the check.
    """
    depends_on = [ci_parsed_check() == 0.0]
    if not all(depends_on):
        return FAILED_CHECK
    return build_as_code_subcheck_results.deploy_kws()


@problog_export("-int")  # type: ignore
def workflow_trigger_deploy_command_check() -> float:
    """Get the value of the subcheck.

    Returns
    -------
    Certainty
        The certainty of the check.
    """
    depends_on = [deploy_command_check() > 0.0]
    if not all(depends_on):
        return FAILED_CHECK
    workflow_name = build_as_code_subcheck_results.check_results["deploy_command"].workflow_name
    return build_as_code_subcheck_results.workflow_trigger(workflow_file=workflow_name)


@problog_export("-int")  # type: ignore
def workflow_trigger_deploy_action_check() -> float:
    """Get the value of the subcheck.

    Returns
    -------
    Certainty
        The certainty of the check.
    """
    depends_on = [deploy_action_check() > 0.0]
    print(all(depends_on))
    if not all(depends_on):
        return FAILED_CHECK
    workflow_name = build_as_code_subcheck_results.check_results["deploy_action"].workflow_name
    return build_as_code_subcheck_results.workflow_trigger(workflow_file=workflow_name)


@problog_export("-int")  # type: ignore
def test_deploy_action_check() -> float:
    """Get the value of the subcheck.

    Returns
    -------
    Certainty
        The certainty of the check.
    """
    depends_on = [deploy_action_check() > 0.0]
    if not all(depends_on):
        return FAILED_CHECK
    workflow_name = build_as_code_subcheck_results.check_results["deploy_action"].workflow_name
    return build_as_code_subcheck_results.test_deploy_action(workflow_name=workflow_name)


@problog_export("-int")  # type: ignore
def publishing_workflow_check() -> float:
    """Get the value of the subcheck.

    Returns
    -------
    Certainty
        The certainty of the check.
    """
    depends_on = [workflow_trigger_deploy_action_check() > 0.0]
    if not all(depends_on):
        return FAILED_CHECK
    # workflow_name = build_as_code_subcheck_results.check_results["deploy_action"]
    return build_as_code_subcheck_results.pypi_publishing_workflow()
