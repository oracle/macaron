# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the BuildAsCodeCheck class."""

from dataclasses import dataclass
import itertools
import logging
import os
from enum import Enum

from pgmpy.factors.discrete import TabularCPD
from pgmpy.inference import VariableElimination
from pgmpy.models.BayesianModel import BayesianNetwork
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.sqltypes import String

from macaron.config.defaults import defaults
from macaron.database.database_manager import ORMBase
from macaron.database.table_definitions import CheckFactsTable
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.build_tool.base_build_tool import BaseBuildTool, NoneBuildTool
from macaron.slsa_analyzer.build_tool.pip import Pip
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import CheckResult, CheckResultType
from macaron.slsa_analyzer.ci_service.base_ci_service import NoneCIService
from macaron.slsa_analyzer.ci_service.circleci import CircleCI
from macaron.slsa_analyzer.ci_service.github_actions import GHWorkflowType
from macaron.slsa_analyzer.ci_service.gitlab_ci import GitLabCI
from macaron.slsa_analyzer.ci_service.jenkins import Jenkins
from macaron.slsa_analyzer.ci_service.travis import Travis
from macaron.slsa_analyzer.registry import registry
from macaron.slsa_analyzer.slsa_req import ReqName

logger: logging.Logger = logging.getLogger(__name__)


class BuildAsCodeTable(CheckFactsTable, ORMBase):
    """Check justification table for build_as_code."""

    __tablename__ = "_build_as_code_check"
    build_tool_name: Mapped[str] = mapped_column(String, nullable=True)
    ci_service_name: Mapped[str] = mapped_column(String, nullable=True)
    build_trigger: Mapped[str] = mapped_column(String, nullable=True)
    deploy_command: Mapped[str] = mapped_column(String, nullable=True)
    build_status_url: Mapped[str] = mapped_column(String, nullable=True)


@dataclass
class Evidence:
    """This class contains the evidence for a check."""

    name: str = ""
    # evidence_type: EvidenceType = EvidenceType.CLUE
    state: bool = False
    weight: float = 0
    norm_weight: float = 0
    description: str = ""
    mutual_exclusion: list[str] = None
    depends_on: list[str] = None
    children: list[str] = None

    # TODO: add optional dependencies on other factors, i.e. build tool, CI service.

    def __str__(self) -> str:
        return f"Name: {self.name}, weight: {self.weight}, state: {self.state}."


class EvidenceGraph():
    """This class contains the graph representation of evidence for a check."""

    def __init__(self, check_id, evidence: dict[str, Evidence]) -> None:
        self.nodes = [check_id, *evidence.keys()]
        self.edges = []
        self.evidence = evidence
        self.check_id = check_id

        # Construct edges list based on dependencies
        # a -> b -> c == [(a, b), (b, c)]
        for item in evidence.values():
            if item.depends_on:
                for dependent in item.depends_on:
                    self.edges.append((dependent, item.name))

        # Initialize the BN with the edges
        self.model = BayesianNetwork(self.edges)

        cpds: list[TabularCPD] = []

        for item in self.evidence.values():
            if not item.depends_on:
                # Evidence is a root value, i.e., no parents and |values| == 2
                cpds.append(TabularCPD(variable=item.name, variable_card=2, values=[[item.weight], [
                    1 - item.weight]]))

            else:
                # Evidence is dependent on another piece of evidence.
                true_states = []

                # TODO: extend for multiple parents.
                for parent in item.depends_on:
                    tmp_weight = self.evidence[parent].weight
                    true_states.extend([[item.weight, tmp_weight]])

                lst = list(itertools.product(*true_states))

                true_values = [sum(itemm) for itemm in lst]
                false_values = [(1.0 - sum(itemm)) for itemm in lst]
                values = [true_values, false_values]

                cpds.append(TabularCPD(variable=item.name,
                                       variable_card=2,
                                       values=values,
                                       evidence=item.depends_on,
                                       evidence_card=[2 for parent in item.depends_on]))

        for item in cpds:
            self.model.add_cpds(item)

    def validate_network(self) -> bool:
        """Check that the network is a DAG with no cycles."""
        return self.model.check_model()

    def perform_variable_elimination(self):
        """Perform Variable Elimination on the model."""
        # Setup evidence to be used for inference.
        collected_evidence = {}
        for item in self.evidence.values():
            collected_evidence[item.name] = item.state

        # Remove the check_id node from the collected evidence, as we can't have evidence for node that we're inferring.
        collected_evidence.pop(self.check_id)

        # Initialize the class to perform variable elimination.
        check_infer = VariableElimination(self.model)

        # Perform variable elimination inference on the network using the found evidence.
        query = check_infer.query(variables=[self.check_id], evidence=collected_evidence)

        logger.info("Evidence: %s", collected_evidence)
        logger.info("------------------ QUERY OUTPUT ------------------")
        logger.info(query)

        # TODO: investigate MAP query as potential option. MAP outputs most probable state of the 'variables', so will output True or False for build_as_code_check.
        map_query = check_infer.map_query(variables=[self.check_id], evidence=collected_evidence)
        logger.info(map_query)

        return query


class BuildAsCodeCheck(BaseCheck):
    """This class checks the build as code requirement.

    See https://slsa.dev/spec/v0.1/requirements#build-as-code.
    """

    def __init__(self) -> None:
        """Initiate the BuildAsCodeCheck instance."""
        description = (
            "The build definition and configuration executed by the build "
            "service is verifiably derived from text file definitions "
            "stored in a version control system."
        )
        depends_on = [
            ("mcn_trusted_builder_level_three_1", CheckResultType.FAILED),
        ]
        eval_reqs = [ReqName.BUILD_AS_CODE]
        super().__init__(
            check_id="mcn_build_as_code_1",
            description=description,
            depends_on=depends_on,
            eval_reqs=eval_reqs,
            result_on_skip=CheckResultType.PASSED,
        )

        # Can define weight and type here, or leave as default.
        self.evidence = {
            "ci_parsed": Evidence(name="ci_parsed", weight=0.65, description="CI files are parsed for this CI service"),
            "gha_deploy": Evidence(
                name="gha_deploy", weight=0.7, description="Trusted GitHub Action used in CI workflow to deploy", depends_on=["ci_parsed"]
            ),
            "cmd_deploy": Evidence(
                name="cmd_deploy", weight=0.8, description="Bash command used to deploy", depends_on=["ci_parsed"]
            ),
            "dist_has_wheel": Evidence(
                name="dist_has_wheel", weight=0.75, description="/dist directory contains wheel.", depends_on=["cmd_deploy"]
            ),
            # TODO: decide how we'd want to deal with adding edges between the evidence and final outcome.
            # Could automatically add edges between the leaves and the check node.
            self.check_id: Evidence(name=self.check_id, weight=0.85, depends_on=["dist_has_wheel"])  # , "gha_deploy"])
        }

        self.check_confidence_threshold = 0.3

    def _has_deploy_command(self, commands: list[list[str]], build_tool: BaseBuildTool) -> str:
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

    def run_check(self, ctx: AnalyzeContext, check_result: CheckResult) -> CheckResultType:
        """Implement the check in this method.

        Parameters
        ----------
        ctx : AnalyzeContext
            The object containing processed data for the target repo.
        check_result : CheckResult
            The object containing result data of a check.

        Returns
        -------
        CheckResultType
            The result type of the check (e.g. PASSED).
        """
        # Get the build tool identified by the mcn_version_control_system_1, which we depend on.
        build_tool = ctx.dynamic_data["build_spec"].get("tool")
        ci_services = ctx.dynamic_data["ci_services"]

        check_result["check_confidence_threshold"] = self.check_confidence_threshold

        # Checking if a build tool is discovered for this repo.
        if build_tool and not isinstance(build_tool, NoneBuildTool):
            for ci_info in ci_services:
                ci_service = ci_info["service"]
                # Checking if a CI service is discovered for this repo.
                if isinstance(ci_service, NoneCIService):
                    continue

                # TODO: check for build tool specific trusted GHAs.
                trusted_deploy_actions = defaults.get_list("builder.pip.ci.deploy", "github_actions", fallback=[])

                # Check for use of a trusted Github Actions workflow to publish/deploy.
                # TODO: verify that deployment is legitimate and not a test
                if trusted_deploy_actions and isinstance(build_tool, Pip):
                    for callee in ci_info["callgraph"].bfs():
                        workflow_name = callee.name.split("@")[0]

                        if not workflow_name or callee.node_type not in [
                            GHWorkflowType.EXTERNAL,
                            GHWorkflowType.REUSABLE,
                        ]:
                            logger.debug("Workflow %s is not relevant. Skipping...", callee.name)
                            continue
                        if workflow_name in trusted_deploy_actions:
                            trigger_link = ci_service.api_client.get_file_link(
                                ctx.repo_full_name,
                                ctx.commit_sha,
                                ci_service.api_client.get_relative_path_of_workflow(
                                    os.path.basename(callee.caller_path)
                                ),
                            )
                            deploy_action_source_link = ci_service.api_client.get_file_link(
                                ctx.repo_full_name, ctx.commit_sha, callee.caller_path
                            )

                            html_url = ci_service.has_latest_run_passed(
                                ctx.repo_full_name,
                                ctx.branch_name,
                                ctx.commit_sha,
                                ctx.commit_date,
                                os.path.basename(callee.caller_path),
                            )

                            # TODO: include in the justification multiple cases of external action usage
                            justification: list[str | dict[str, str]] = [
                                {
                                    f"The target repository uses build tool {build_tool.name}"
                                    " to deploy": deploy_action_source_link,
                                    "The build is triggered by": trigger_link,
                                },
                                f"Deploy action: {workflow_name}",
                                {"The status of the build can be seen at": html_url}
                                if html_url
                                else "However, could not find a passing workflow run.",
                            ]
                            check_result["justification"].extend(justification)
                            if ctx.dynamic_data["is_inferred_prov"] and ci_info["provenances"]:
                                predicate = ci_info["provenances"][0]["predicate"]
                                predicate["buildType"] = f"Custom {ci_service.name}"
                                predicate["builder"]["id"] = deploy_action_source_link
                                predicate["invocation"]["configSource"][
                                    "uri"
                                ] = f"{ctx.remote_path}@refs/heads/{ctx.branch_name}"
                                predicate["invocation"]["configSource"]["digest"]["sha1"] = ctx.commit_sha
                                predicate["invocation"]["configSource"]["entryPoint"] = trigger_link
                                predicate["metadata"]["buildInvocationId"] = html_url
                                check_result["result_tables"] = [
                                    BuildAsCodeTable(
                                        build_tool_name=build_tool.name,
                                        ci_service_name=ci_service.name,
                                        build_trigger=trigger_link,
                                        deploy_command=workflow_name,
                                        build_status_url=html_url,
                                    )
                                ]
                            # self.evidence["gha_deploy"].state = False
                            # self.evidence["ci_parsed"].state = True
                            # return CheckResultType.PASSED

                # TODO: handle mutual exclusion.
                # if self.evidence["gha_deploy"].state is False:
                for bash_cmd in ci_info["bash_commands"]:
                    deploy_cmd = self._has_deploy_command(bash_cmd["commands"], build_tool)
                    if deploy_cmd:
                        # Get the permalink and HTML hyperlink tag of the CI file that triggered the bash command.
                        trigger_link = ci_service.api_client.get_file_link(
                            ctx.repo_full_name,
                            ctx.commit_sha,
                            ci_service.api_client.get_relative_path_of_workflow(
                                os.path.basename(bash_cmd["CI_path"])
                            ),
                        )
                        # Get the permalink of the source file of the bash command.
                        bash_source_link = ci_service.api_client.get_file_link(
                            ctx.repo_full_name, ctx.commit_sha, bash_cmd["caller_path"]
                        )

                        html_url = ci_service.has_latest_run_passed(
                            ctx.repo_full_name,
                            ctx.branch_name,
                            ctx.commit_sha,
                            ctx.commit_date,
                            os.path.basename(bash_cmd["CI_path"]),
                        )

                        justification_cmd: list[str | dict[str, str]] = [
                            {
                                f"The target repository uses build tool {build_tool.name} "
                                "to deploy": bash_source_link,
                                "The build is triggered by": trigger_link,
                            },
                            f"Deploy command: {deploy_cmd}",
                            {"The status of the build can be seen at": html_url}
                            if html_url
                            else "However, could not find a passing workflow run.",
                        ]
                        check_result["justification"].extend(justification_cmd)
                        if ctx.dynamic_data["is_inferred_prov"] and ci_info["provenances"]:
                            predicate = ci_info["provenances"][0]["predicate"]
                            predicate["buildType"] = f"Custom {ci_service.name}"
                            predicate["builder"]["id"] = bash_source_link
                            predicate["invocation"]["configSource"][
                                "uri"
                            ] = f"{ctx.remote_path}@refs/heads/{ctx.branch_name}"
                            predicate["invocation"]["configSource"]["digest"]["sha1"] = ctx.commit_sha
                            predicate["invocation"]["configSource"]["entryPoint"] = trigger_link
                            predicate["metadata"]["buildInvocationId"] = html_url
                            check_result["result_tables"] = [
                                BuildAsCodeTable(
                                    build_tool_name=build_tool.name,
                                    ci_service_name=ci_service.name,
                                    build_trigger=trigger_link,
                                    deploy_command=deploy_cmd,
                                    build_status_url=html_url,
                                )
                            ]
                        self.evidence["ci_parsed"].state = True
                        self.evidence["cmd_deploy"].state = True
                        self.evidence["dist_has_wheel"].state = True

                # We currently don't parse these CI configuration files.
                # We just look for a keyword for now.
                for unparsed_ci in (Jenkins, Travis, CircleCI, GitLabCI):
                    if isinstance(ci_service, unparsed_ci):
                        if build_tool.ci_deploy_kws[ci_service.name]:
                            config_name = ci_service.has_kws_in_config(
                                build_tool.ci_deploy_kws[ci_service.name], repo_path=ctx.repo_path
                            )
                            if not config_name:
                                break

                            check_result["justification"].append(
                                f"The target repository uses build tool {build_tool.name}"
                                + f" in {ci_service.name} to deploy."
                            )
                            if ctx.dynamic_data["is_inferred_prov"] and ci_info["provenances"]:
                                predicate = ci_info["provenances"][0]["predicate"]
                                predicate["buildType"] = f"Custom {ci_service.name}"
                                predicate["builder"]["id"] = config_name
                                predicate["invocation"]["configSource"][
                                    "uri"
                                ] = f"{ctx.remote_path}@refs/heads/{ctx.branch_name}"
                                predicate["invocation"]["configSource"]["digest"]["sha1"] = ctx.commit_sha
                                predicate["invocation"]["configSource"]["entryPoint"] = config_name
                            check_result["result_tables"] = [
                                BuildAsCodeTable(
                                    build_tool_name=build_tool.name,
                                    ci_service_name=ci_service.name,
                                    deploy_command=deploy_cmd,
                                )
                            ]
                            self.evidence["ci_parsed"].state = False
                            self.evidence["cmd_deploy"].state = True
                            # return CheckResultType.PASSED

            total_weight = sum(ev.weight for ev in self.evidence.values())
            found_evidence: list[Evidence] = []
            confidence_score = 0

            print("EVIDENCE")
            print(self.evidence)
            for item in self.evidence.values():
                if item.state:
                    found_evidence.append(item)

            # Processing evidence and confidence values
            evidence_list: list[str] = []
            for item in found_evidence:
                evidence_list.append(item.description)
                print(item.name, item.weight)
            evidence_str = ", ".join(evidence_list)

            # TODO: ensure that this value hasn't been found.
            evidence_importance = ""  # sorted(self.evidence.values(), key=lambda x: x.weight, reverse=True)

            bayesian_network = EvidenceGraph(self.check_id, self.evidence)

            # TODO: handle ValueError thrown from invalid network.
            logger.info(bayesian_network.validate_network())

            # Print the network
            logger.info("------------------ Network setup ------------------")
            logger.info("Nodes: %s", bayesian_network.model.nodes)
            logger.info("Edges: %s", bayesian_network.model.edges)

            for cpd in bayesian_network.model.cpds:
                logger.info("\n")
                logger.info(cpd)

            query = bayesian_network.perform_variable_elimination()
            confidence_score = query.values[0]

            confidence_score_rounded = round(confidence_score, 4)

            check_result["confidence_score"] = confidence_score_rounded

            # Has the check passed(i.e., is the confidence score above the specified threshold?).
            if confidence_score > self.check_confidence_threshold:
                message = f"The confidence score for this check is: {confidence_score_rounded}."
                ev_msg = f"The evidence found: {evidence_str}."
                check_result["justification"].append(ev_msg)
                check_result["justification"].append(message)
                return CheckResultType.PASSED
            else:
                pass_msg = f"The target repository does not use {build_tool.name} to deploy. "
                conf_msg = (
                    f"The confidence score for this check is {confidence_score_rounded}, "
                    f"which is below the specified threshold of {self.check_confidence_threshold} "
                    "for this check."
                )
                improve_msg = (
                    f"To improve this score, consider including the following piece of evidence: "
                    f"{evidence_importance[0].description}."
                )

                check_result["justification"].append(pass_msg)
                check_result["justification"].append(conf_msg)
                check_result["justification"].append(improve_msg)
                check_result["result_tables"] = [BuildAsCodeTable(build_tool_name=build_tool.name)]
                return CheckResultType.FAILED

        # TODO: construct DAG here,

        check_result["result_tables"] = [BuildAsCodeTable()]
        failed_msg = "The target repository does not have a build tool."
        check_result["justification"].append(failed_msg)
        return CheckResultType.FAILED


registry.register(BuildAsCodeCheck())
