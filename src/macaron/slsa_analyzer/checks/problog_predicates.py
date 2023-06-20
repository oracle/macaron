# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Contains ProbLog predicates that return the results stored in the BuildAsCodeSubchecks dataclass."""
import logging

from problog.extern import problog_export

from macaron.slsa_analyzer.checks.build_as_code_subchecks import build_as_code_subcheck_results

FAILED_CHECK = 0.0

logger: logging.Logger = logging.getLogger(__name__)

# TODO: check that a result doesn't already exist before running the check.


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
    # Verify dependencies and that this check hasn't already been run.
    if not all(depends_on):
        return FAILED_CHECK
    check = build_as_code_subcheck_results.check_results.get("deploy_action")
    if check:
        return check.certainty
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
    # Verify dependencies and that this check hasn't already been run.
    check = build_as_code_subcheck_results.check_results.get("deploy_command")
    if not all(depends_on):
        return FAILED_CHECK
    if check:
        return check.certainty
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
def release_workflow_trigger_deploy_command_check() -> float:
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
    return build_as_code_subcheck_results.release_workflow_trigger(workflow_file=workflow_name)


@problog_export("-int")  # type: ignore
def release_workflow_trigger_deploy_action_check() -> float:
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
    return build_as_code_subcheck_results.release_workflow_trigger(workflow_file=workflow_name)


@problog_export("-int")  # type: ignore
def tested_deploy_action_check() -> float:
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
    return build_as_code_subcheck_results.tested_deploy_action(workflow_name=workflow_name)


@problog_export("-int")  # type: ignore
def publishing_workflow_deploy_action_check() -> float:
    """Get the value of the subcheck.

    Returns
    -------
    Certainty
        The certainty of the check.
    """
    depends_on = [release_workflow_trigger_deploy_action_check()]
    if not all(depends_on):
        return FAILED_CHECK
    # workflow_name = build_as_code_subcheck_results.check_results["deploy_action"]
    return build_as_code_subcheck_results.pypi_publishing_workflow_timestamp()


@problog_export("-int")  # type: ignore
def publishing_workflow_deploy_command_check() -> float:
    """Get the value of the subcheck.

    Returns
    -------
    Certainty
        The certainty of the check.
    """
    depends_on = [release_workflow_trigger_deploy_command_check() > 0.0]
    if not all(depends_on):
        return FAILED_CHECK
    # workflow_name = build_as_code_subcheck_results.check_results["deploy_action"]
    return build_as_code_subcheck_results.pypi_publishing_workflow_timestamp()


@problog_export("-int")  # type: ignore
def step_uses_secrets_deploy_command_check() -> float:
    """Get the value of the subcheck.

    Returns
    -------
    Certainty
        The certainty of the check.
    """
    # TODO: currently we don't store the GHA object during deploy_command_check so
    # can't perform this sub-task (no workflow_info available).
    depends_on = [deploy_command_check() > 0.0]
    if not all(depends_on):
        return FAILED_CHECK
    step_info = build_as_code_subcheck_results.check_results["deploy_command"].workflow_info
    if step_info:
        return build_as_code_subcheck_results.step_uses_secrets(step_info=step_info)
    return FAILED_CHECK


@problog_export("-int")  # type: ignore
def step_uses_secrets_deploy_action_check() -> float:
    """Get the value of the subcheck.

    Returns
    -------
    Certainty
        The certainty of the check.
    """
    depends_on = [deploy_action_check() > 0.0]
    if not all(depends_on):
        return FAILED_CHECK
    step_info = build_as_code_subcheck_results.check_results["deploy_action"].workflow_info
    if step_info:
        return build_as_code_subcheck_results.step_uses_secrets(step_info=step_info)
    return FAILED_CHECK
