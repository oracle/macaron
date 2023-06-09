# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains a class to store results from the BuildAsCodeCheck subchecks."""

import logging
import os

from attr import dataclass

from macaron.config.defaults import defaults
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool
from macaron.slsa_analyzer.build_tool.pip import Pip
from macaron.slsa_analyzer.ci_service.circleci import CircleCI
from macaron.slsa_analyzer.ci_service.github_actions import GHWorkflowType
from macaron.slsa_analyzer.ci_service.gitlab_ci import GitLabCI
from macaron.slsa_analyzer.ci_service.jenkins import Jenkins
from macaron.slsa_analyzer.ci_service.travis import Travis
from macaron.slsa_analyzer.specs.ci_spec import CIInfo

logger: logging.Logger = logging.getLogger(__name__)


def has_deploy_command(commands: list[list[str]], build_tool: BaseBuildTool) -> str:
    """Check if the bash command is a build and deploy command."""
    # Account for Python projects having separate tools for packaging and publishing.
    deploy_tool = build_tool.publisher if build_tool.publisher else build_tool.builder
    for com in commands:

        # Check for empty or invalid commands.
        if not com or not com[0]:
            continue
        # The first argument in a bash command is the program name.
        # So first check that the program name is a supported build tool name.
        # We need to handle cases where the first argument is a path to the program.
        cmd_program_name = os.path.basename(com[0])
        if not cmd_program_name:
            logger.debug("Found invalid program name %s.", com[0])
            continue

        check_build_commands = any(build_cmd for build_cmd in deploy_tool if build_cmd == cmd_program_name)

        # Support the use of interpreters like Python that load modules, i.e., 'python -m pip install'.
        check_module_build_commands = any(
            interpreter == cmd_program_name
            and com[1]
            and com[1] in build_tool.interpreter_flag
            and com[2]
            and com[2] in deploy_tool
            for interpreter in build_tool.interpreter
        )
        prog_name_index = 2 if check_module_build_commands else 0

        if check_build_commands or check_module_build_commands:
            # Check the arguments in the bash command for the deploy goals.
            # If there are no deploy args for this build tool, accept as deploy command.
            if not build_tool.deploy_arg:
                logger.info("No deploy arguments required. Accept %s as deploy command.", str(com))
                return str(com)

            for word in com[(prog_name_index + 1) :]:
                # TODO: allow plugin versions in arguments, e.g., maven-plugin:1.6.8:deploy.
                if word in build_tool.deploy_arg:
                    logger.info("Found deploy command %s.", str(com))
                    return str(com)
    return ""


@dataclass
class DeploySubcheckResults:
    """DataClass containing information required from deploy command subchecks."""

    certainty: float = 0.0
    justification: list[str | dict[str, str]] = [""]
    deploy_cmd: str = ""
    trigger_link: str = ""
    source_link: str = ""
    html_url: str = ""
    config_name: str = ""
    workflow_name: str = ""


class BuildAsCodeSubchecks:
    """Class for storing the results from the BuildAsCodeCheck subchecks."""

    # store analyze context
    def __init__(self, ctx: AnalyzeContext, ci_info: CIInfo) -> None:
        self.ctx = ctx
        self.build_tool: BaseBuildTool = ctx.dynamic_data["build_spec"].get("tool")  # type: ignore
        self.ci_services = ctx.dynamic_data["ci_services"]
        self.check_results: dict[str, DeploySubcheckResults] = {}  # Update this with each check.
        self.ci_info = ci_info
        self.ci_service = ci_info["service"]
        # Certainty value to be returned if a subcheck fails.
        self.failed_check = 0.0

        # TODO: Make subcheck functions available to other checks.

        # TODO: Before each check is run, check whether a certainty result already exists in self.check_results
        # to avoid re-running unecessarily.

    def ci_parsed(self) -> float:
        """Check whether parsing is supported for this CI service's CI config files."""
        check_certainty = 1.0
        # If this check has already been run on this repo, return certainty.

        if self.ci_info["bash_commands"]:
            justification: list[str | dict[str, str]] = ["The CI workflow files for this CI service are parsed."]
            self.check_results["ci_parsed"] = DeploySubcheckResults(
                certainty=check_certainty, justification=justification
            )
            return check_certainty
        return self.failed_check

    def deploy_command(self) -> float:
        """Check for the use of deploy command to deploy."""
        check_certainty = 0.7
        depends_on = [self.ci_parsed() > 0.0]
        if not all(depends_on):
            return self.failed_check

        for bash_cmd in self.ci_info["bash_commands"]:
            deploy_cmd = has_deploy_command(bash_cmd["commands"], self.build_tool)
            if deploy_cmd:
                # Get the permalink and HTML hyperlink tag of the CI file that triggered the bash command.
                trigger_link = self.ci_service.api_client.get_file_link(
                    self.ctx.repo_full_name,
                    self.ctx.commit_sha,
                    self.ci_service.api_client.get_relative_path_of_workflow(os.path.basename(bash_cmd["CI_path"])),
                )
                # Get the permalink of the source file of the bash command.
                bash_source_link = self.ci_service.api_client.get_file_link(
                    self.ctx.repo_full_name, self.ctx.commit_sha, bash_cmd["caller_path"]
                )

                html_url = self.ci_service.has_latest_run_passed(
                    self.ctx.repo_full_name,
                    self.ctx.branch_name,
                    self.ctx.commit_sha,
                    self.ctx.commit_date,
                    os.path.basename(bash_cmd["CI_path"]),
                )

                workflow_name = os.path.basename(html_url)

                justification: list[str | dict[str, str]] = [
                    {
                        f"The target repository uses build tool {self.build_tool.name} to deploy": bash_source_link,
                        "The build is triggered by": trigger_link,
                    },
                    f"Deploy command: {deploy_cmd}",
                    {"The status of the build can be seen at": html_url}
                    if html_url
                    else "However, could not find a passing workflow run.",
                ]

                self.check_results["deploy_command"] = DeploySubcheckResults(
                    certainty=check_certainty,
                    justification=justification,
                    deploy_cmd=deploy_cmd,
                    trigger_link=trigger_link,
                    source_link=bash_source_link,
                    html_url=html_url,
                    workflow_name=workflow_name,
                )

                return check_certainty
        return self.failed_check

    def deploy_kws(self) -> float:
        """Check for the use of deploy keywords to deploy."""
        check_certainty = 0.6
        depends_on = [self.ci_parsed() == 0.0]
        # If this check has already been run on this repo, return certainty.

        if not all(depends_on):
            return self.failed_check

        # We currently don't parse these CI configuration files.
        # We just look for a keyword for now.
        for unparsed_ci in (Jenkins, Travis, CircleCI, GitLabCI):
            if isinstance(self.ci_service, unparsed_ci):
                if self.build_tool.ci_deploy_kws[self.ci_service.name]:
                    deploy_kw, config_name = self.ci_service.has_kws_in_config(
                        self.build_tool.ci_deploy_kws[self.ci_service.name], repo_path=self.ctx.repo_path
                    )
                    if not config_name:
                        return self.failed_check

                    justification: list[str | dict[str, str]] = [f"The target repository uses {deploy_kw} to deploy."]

                    self.check_results["deploy_kws"] = DeploySubcheckResults(
                        certainty=check_certainty,
                        justification=justification,
                        deploy_cmd=deploy_kw,
                        config_name=config_name,
                    )
                    return check_certainty

        return self.failed_check

    def deploy_action(self) -> float:
        """Check for use of a trusted Github Actions workflow to publish/deploy."""
        # TODO: verify that deployment is legitimate and not a test
        check_certainty = 0.8
        depends_on = [self.ci_parsed() > 0]
        if not all(depends_on):
            return self.failed_check

        if isinstance(self.build_tool, Pip):
            trusted_deploy_actions = defaults.get_list("builder.pip.ci.deploy", "github_actions", fallback=[])

            for callee in self.ci_info["callgraph"].bfs():
                workflow_name = callee.name.split("@")[0]

                if not workflow_name or callee.node_type not in [
                    GHWorkflowType.EXTERNAL,
                    GHWorkflowType.REUSABLE,
                ]:
                    logger.debug("Workflow %s is not relevant. Skipping...", callee.name)
                    continue
                if workflow_name in trusted_deploy_actions:
                    trigger_link = self.ci_service.api_client.get_file_link(
                        self.ctx.repo_full_name,
                        self.ctx.commit_sha,
                        self.ci_service.api_client.get_relative_path_of_workflow(os.path.basename(callee.caller_path)),
                    )
                    deploy_action_source_link = self.ci_service.api_client.get_file_link(
                        self.ctx.repo_full_name, self.ctx.commit_sha, callee.caller_path
                    )

                    html_url = self.ci_service.has_latest_run_passed(
                        self.ctx.repo_full_name,
                        self.ctx.branch_name,
                        self.ctx.commit_sha,
                        self.ctx.commit_date,
                        os.path.basename(callee.caller_path),
                    )

                    # TODO: include in the justification multiple cases of external action usage
                    justification: list[str | dict[str, str]] = [
                        {
                            "To deploy": deploy_action_source_link,
                            "The build is triggered by": trigger_link,
                        },
                        f"Deploy action: {workflow_name}",
                        {"The status of the build can be seen at": html_url}
                        if html_url
                        else "However, could not find a passing workflow run.",
                    ]

                    self.check_results["deploy_action"] = DeploySubcheckResults(
                        certainty=check_certainty,
                        justification=justification,
                        deploy_cmd=workflow_name,
                        trigger_link=trigger_link,
                        source_link=deploy_action_source_link,
                        html_url=html_url,
                        workflow_name=workflow_name,
                    )

                    return check_certainty

        return self.failed_check

    def workflow_trigger(self, workflow_name: str) -> str:
        """Check that the workflow is triggered by a valid event."""
        valid_trigger_events = ["workflow-dispatch", "push", "release"]
        for callee in self.ci_info["callgraph"].bfs():
            if callee.name == workflow_name:
                trigger_events = callee.parsed_obj.get("On", {})
                for event in trigger_events:
                    hook = event.get("Hook", {})
                    trigger_type = str(hook.get("Value", ""))
                    if trigger_type in valid_trigger_events:
                        return trigger_type
        return ""

    def workflow_trigger_deploy_command(self) -> float:
        """Check the workflow trigger for the required deploy_command workflow file."""
        check_certainty = 0.9
        depends_on = [self.deploy_command() > 0.0]
        if not all(depends_on):
            return self.failed_check

        workflow_name = self.check_results["deploy_command"].workflow_name
        if workflow_name:
            trigger_type = self.workflow_trigger(workflow_name=workflow_name)
            if trigger_type:
                logger.info("Valid trigger event %s found for the workflow file %s.", trigger_type, workflow_name)
                return check_certainty
        return self.failed_check

    def workflow_trigger_deploy_action(self) -> float:
        """Check the workflow trigger for the required deploy_action workflow file."""
        check_certainty = 0.9
        depends_on = [self.deploy_action() > 0.0]
        if not all(depends_on):
            return self.failed_check

        workflow_name = self.check_results["deploy_action"].workflow_name
        if workflow_name:
            trigger_type = self.workflow_trigger(workflow_name=workflow_name)
        if trigger_type:
            logger.info("Valid trigger event %s found for the workflow file %s.", trigger_type, workflow_name)
            return check_certainty
        return self.failed_check

    def get_subcheck_results(self, subcheck_name: str) -> DeploySubcheckResults:
        """Return the results for a particular subcheck."""
        return self.check_results[subcheck_name]


build_as_code_subcheck_results: BuildAsCodeSubchecks = None  # type: ignore # pylint: disable=invalid-name
