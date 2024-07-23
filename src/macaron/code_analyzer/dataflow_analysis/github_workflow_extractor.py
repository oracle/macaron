# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

from collections import defaultdict
from dataclasses import dataclass
from pprint import pformat

from macaron.code_analyzer.dataflow_analysis import bash_extractor, facts, github_expr_extractor
from macaron.parsers import bashparser, github_workflow_model



@dataclass(frozen=True)
class StepContext:
    filesystem_scope: str
    base_id: str
    github_output_var_scope: str
    github_output_var_prefix: str

def extract_yaml_spec_from_step(step: github_workflow_model.Step, step_context: StepContext) -> facts.YamlSpec:
    fields: dict[facts.YamlFieldAccessPath, facts.Value | None] = {}
    if "id" in step:
        id = step["id"]
        val = github_expr_extractor.extract_value_from_expr_string(id, step_context.github_output_var_scope)
        fields[facts.YamlFieldAccessPath(("id",))] = val
    if "if" in step:
        if_clause = step["if"]
        if isinstance(if_clause, str):
            val = github_expr_extractor.extract_value_from_expr_string(if_clause, step_context.github_output_var_scope)
        else:
            val = None
        fields[facts.YamlFieldAccessPath(("if",))] = val
    if "name" in step:
        name = step["name"]
        val = github_expr_extractor.extract_value_from_expr_string(name, step_context.github_output_var_scope)
        fields[facts.YamlFieldAccessPath(("name",))] = val
    if "uses" in step:
        uses = step["uses"]
        val = github_expr_extractor.extract_value_from_expr_string(uses, step_context.github_output_var_scope)
        fields[facts.YamlFieldAccessPath(("uses",))] = val
    if "run" in step:
        run = step["run"]
        val = github_expr_extractor.extract_value_from_expr_string(run, step_context.github_output_var_scope)
        fields[facts.YamlFieldAccessPath(("run",))] = val
    if "working-directory" in step:
        working_dir = step["working-directory"]
        val = github_expr_extractor.extract_value_from_expr_string(working_dir, step_context.github_output_var_scope)
        fields[facts.YamlFieldAccessPath(("working-directory",))] = val
    if "shell" in step:
        shell = step["shell"]
        val = github_expr_extractor.extract_value_from_expr_string(shell, step_context.github_output_var_scope)
        fields[facts.YamlFieldAccessPath(("shell",))] = val
    if "with" in step:
        with_spec = step["with"]
        if isinstance(with_spec, dict):
            for env_key, env_val in with_spec.items():
                if isinstance(env_val, str):
                    val = github_expr_extractor.extract_value_from_expr_string(env_val, step_context.github_output_var_scope)
                    fields[facts.YamlFieldAccessPath(("with", env_key))] = val
                else:
                    # TODO
                    pass
        else:
            # TODO
            pass
    if "env" in step:
        env_spec = step["env"]
        if isinstance(env_spec, dict):
            for env_key, env_val in env_spec.items():
                if isinstance(env_val, str):
                    val = github_expr_extractor.extract_value_from_expr_string(env_val, step_context.github_output_var_scope)
                    fields[facts.YamlFieldAccessPath(("env", env_key))] = val
                else:
                    # TODO
                    pass
        else:
            # TODO
            pass
    if "continue-on-error" in step:
        continue_on_error = step["continue-on-error"]
        # TODO
    if "timeout-minutes" in step:
        timeout_minutes = step["timeout-minutes"]
        # TODO

    return facts.YamlSpec(fields)
        

def extract_from_run_step(
    step: github_workflow_model.RunStep, step_context: StepContext, id_creator: facts.UniqueIdCreator
) -> facts.OperationNode:
    id_str = "step"
    if "id" in step:
        id_str = id_str + "::" + step["id"]

    id_str = id_str + "@" + step_context.base_id
    unique_id = id_creator.get_next_id(id_str)

    run_val = step["run"]

    parsed_bash = bashparser.parse_raw(run_val, "/home/nicallen/macaron/src/macaron/")

    shell_context = bash_extractor.ShellContext(
        base_id=step_context.base_id + ".shell",
        filesystem_scope=step_context.filesystem_scope,
        github_output_var_scope=step_context.github_output_var_scope,
        github_output_var_prefix=step_context.github_output_var_prefix,
        env_var_scope="env:" + step_context.base_id + ".shell",
    )

    shell_block = bash_extractor.extract_from_simple_bash_stmts(parsed_bash["Stmts"], shell_context, id_creator)

    yaml_spec = extract_yaml_spec_from_step(step, step_context)

    return facts.OperationNode(id=unique_id, block=shell_block, operation_details=yaml_spec, parsed_obj=step)


def extract_from_action_step(
    step: github_workflow_model.ActionStep, step_context: StepContext, id_creator: facts.UniqueIdCreator
) -> facts.OperationNode:
    id_str = "step"
    if "id" in step:
        id_str = id_str + "::" + step["id"]
    id_str = id_str + "@" + step_context.base_id
    unique_id = id_creator.get_next_id(id_str)

    write_base_id_str = "write@" + step_context.base_id
    block_base_id_str = "block@" + step_context.base_id
    release_base_id_str = "release@" + step_context.base_id

    # TODO factor the models out to make it more extensible

    block: facts.BlockNode | None = None

    if step["uses"] == "nicallen/arbitrary-file":
        if "with" in step and isinstance(step["with"], dict) and "path" in step["with"]:
            path_str = str(step["with"]["path"])
            path_val = github_expr_extractor.extract_value_from_expr_string(
                path_str, step_context.github_output_var_scope
            )
            if path_val is not None:
                location_val = facts.Location(scope=step_context.filesystem_scope, loc=facts.Filesystem(path=path_val))
                unique_write_id_str = id_creator.get_next_id(write_base_id_str)
                written_val = facts.ArbitraryNewData(at=unique_write_id_str)

                write_stmts: list[facts.Statement] = [
                    facts.Write(id=unique_write_id_str, location=location_val, value=written_val)
                ]
                block_id = id_creator.get_next_id(block_base_id_str)
                block = facts.StatementBlockNode(id=block_id, statements=write_stmts)

    elif step["uses"] == "actions/upload-artifact" or step["uses"].startswith("actions/upload-artifact@"):
        if "with" in step and isinstance(step["with"], dict) and "name" in step["with"] and "path" in step["with"]:
            name_str = str(step["with"]["name"])
            paths = [x.strip() for x in str(step["with"]["path"]).split("\n")]
            name_val = github_expr_extractor.extract_value_from_expr_string(
                name_str, step_context.github_output_var_scope
            )

            write_stmts: list[facts.Statement] = []

            if name_val is not None:
                for path_str in paths:
                    path_val = github_expr_extractor.extract_value_from_expr_string(
                        path_str, step_context.github_output_var_scope
                    )
                    if path_val is not None:
                        artifact_val = facts.Location(
                            scope="pipeline_artifacts",
                            loc=facts.Artifact(
                                name=name_val,
                                file=facts.UnaryStringOp(op=facts.UnaryStringOperator.BaseName, operand=path_val),
                            ),
                        )
                        written_val = facts.Read(
                            loc=facts.Location(scope=step_context.filesystem_scope, loc=facts.Filesystem(path=path_val))
                        )

                        unique_write_id_str = id_creator.get_next_id(write_base_id_str)

                        write_stmts.append(
                            facts.Write(id=unique_write_id_str, location=artifact_val, value=written_val)
                        )

                block_id = id_creator.get_next_id(block_base_id_str)
                block = facts.StatementBlockNode(id=block_id, statements=write_stmts)

    elif step["uses"] == "actions/download-artifact" or step["uses"].startswith("actions/download-artifact@"):
        if "with" in step and isinstance(step["with"], dict) and "name" in step["with"]:
            name_str = str(step["with"]["name"])
            name_val = github_expr_extractor.extract_value_from_expr_string(
                name_str, step_context.github_output_var_scope
            )
            if name_val is not None:
                artifact_file_list = facts.UnaryLocationReadOp(
                    op=facts.UnaryLocationReadOperator.AnyFileUnderDirectory,
                    operand=facts.Location(
                        scope="pipeline_artifacts",
                        loc=facts.Artifact(name=name_val, file=facts.StringLiteral(literal="")),
                    ),
                )
                filesystem_val = facts.Location(
                    scope=step_context.filesystem_scope, loc=facts.Filesystem(path=facts.InductionVar())
                )
                written_val = facts.Read(
                    loc=facts.Location(
                        scope="pipeline_artifacts", loc=facts.Artifact(name=name_val, file=facts.InductionVar())
                    )
                )
                unique_write_id_str = id_creator.get_next_id(write_base_id_str)
                write_stmts: list[facts.Statement] = [
                    facts.WriteForEach(
                        id=unique_write_id_str,
                        collection=artifact_file_list,
                        location=filesystem_val,
                        value=written_val,
                    )
                ]

                block_id = id_creator.get_next_id(block_base_id_str)
                block = facts.StatementBlockNode(id=block_id, statements=write_stmts)

    elif step["uses"] == "softprops/action-gh-release" or step["uses"].startswith("softprops/action-gh-release@"):
        if "with" in step and isinstance(step["with"], dict) and "files" in step["with"]:
            paths = [x.strip() for x in str(step["with"]["files"]).split("\n")]
            unique_release_id_str = id_creator.get_next_id(release_base_id_str)
            name_val = facts.StringLiteral(literal=unique_release_id_str)

            write_stmts: list[facts.Statement] = []
            for path_str in paths:
                path_val = github_expr_extractor.extract_value_from_expr_string(
                    path_str, step_context.github_output_var_scope
                )
                if path_val is not None:
                    artifact_val = facts.Location(scope="releases", loc=facts.Artifact(name=name_val, file=path_val))
                    written_val = facts.Read(
                        loc=facts.Location(scope=step_context.filesystem_scope, loc=facts.Filesystem(path=path_val))
                    )
                    unique_write_id_str = id_creator.get_next_id(write_base_id_str)
                    write_stmts.append(facts.Write(id=unique_write_id_str, location=artifact_val, value=written_val))

            block_id = id_creator.get_next_id(block_base_id_str)
            block = facts.StatementBlockNode(id=block_id, statements=write_stmts)

    if block is None:
        block_id = id_creator.get_next_id(block_base_id_str)
        block = facts.StatementBlockNode(id=block_id, statements=[])

    yaml_spec = extract_yaml_spec_from_step(step, step_context)

    return facts.OperationNode(id=unique_id, block=block, operation_details=yaml_spec, parsed_obj=step)


def extract_from_step(
    step: github_workflow_model.Step, step_context: StepContext, id_creator: facts.UniqueIdCreator
) -> facts.OperationNode:
    if github_workflow_model.is_run_step(step):
        return extract_from_run_step(step, step_context, id_creator)
    elif github_workflow_model.is_action_step(step):
        return extract_from_action_step(step, step_context, id_creator)

    raise ValueError("unknown step kind")


@dataclass(frozen=True)
class JobContext:
    filesystem_scope: str
    base_id: str
    github_output_var_scope: str


def extract_from_normal_job(
    job_unique_id: str, job: github_workflow_model.NormalJob, job_context: JobContext, id_creator: facts.UniqueIdCreator
) -> facts.OperationNode:
    if "steps" in job:
        steps: list[facts.Node] = []
        step_index = 0
        for step in job["steps"]:
            step_id_or_index = str(step_index)
            if "id" in step:
                step_id_or_index = step["id"]

            step_context = StepContext(
                filesystem_scope=job_context.filesystem_scope,
                base_id=job_context.base_id + ".steps." + str(step_index),
                github_output_var_scope=job_context.github_output_var_scope,
                github_output_var_prefix="steps." + step_id_or_index + ".outputs.",
            )

            step_node = extract_from_step(step, step_context, id_creator)
            steps.append(step_node)
            step_index = step_index + 1

        block_id = id_creator.get_next_id("block@" + job_context.base_id)
        block = facts.create_cfg_block_from_sequence(block_id, steps)
    else:
        # No steps, empty block
        block_id = id_creator.get_next_id("block@" + job_context.base_id)
        block = facts.StatementBlockNode(id=block_id, statements=[])

    return facts.OperationNode(id=job_unique_id, block=block, operation_details=None, parsed_obj=job)


def extract_from_reusable_workflow_call_job(
    job_id: str,
    job: github_workflow_model.ReusableWorkflowCallJob,
    job_context: JobContext,
    id_creator: facts.UniqueIdCreator,
) -> facts.OperationNode:
    unique_id = id_creator.get_next_id(job_id)
    # TODO generate block from models of reusable workflows
    block_id = id_creator.get_next_id(job_id + "::block")
    block = facts.StatementBlockNode(id=block_id, statements=[])
    return facts.OperationNode(id=unique_id, block=block, operation_details=None, parsed_obj=job)


def extract_from_job(
    job_id: str, job: github_workflow_model.Job, id_creator: facts.UniqueIdCreator
) -> facts.OperationNode:
    unique_id = id_creator.get_next_id("jobs." + job_id)
    job_context = JobContext(
        filesystem_scope="filesystem:" + unique_id, base_id=unique_id, github_output_var_scope="vars:" + unique_id
    )

    if github_workflow_model.is_normal_job(job):
        return extract_from_normal_job(unique_id, job, job_context, id_creator)
    elif github_workflow_model.is_reusable_workflow_call_job(job):
        return extract_from_reusable_workflow_call_job(unique_id, job, job_context, id_creator)

    raise ValueError("unknown job kind")


def extract_from_workflow(
    workflow: github_workflow_model.Workflow, id_creator: facts.UniqueIdCreator | None = None
) -> facts.OperationNode:
    if id_creator is None:
        id_creator = facts.UniqueIdCreator()
    id_str = "workflow"
    if "name" in workflow:
        id_str = id_str + "::" + workflow["name"]
    id = id_creator.get_next_id(id_str)

    block_id = id_creator.get_next_id(id_str + "::block")

    job_unique_ids: dict[str, str] = {}
    children: list[facts.Node] = []

    for job_id, job in workflow["jobs"].items():
        job_node = extract_from_job(job_id, job, id_creator)
        children.append(job_node)
        job_unique_ids[job_id] = job_node.id

    dependency_graph: dict[str, list[str]] = defaultdict(list)
    for job_id, job in workflow["jobs"].items():
        job_unique_id = job_unique_ids[job_id]
        if "needs" in job:
            needs = job["needs"]
            if isinstance(needs, list):
                for need in needs:
                    # TODO invalid needs id?
                    need_unique_id = job_unique_ids[need]
                    dependency_graph[job_unique_id].append(need_unique_id)
            elif isinstance(needs, str):
                # TODO when is it a str? dynamic expression?
                raise ValueError("needs is a str")

    control_flow_graph = facts.SchedulerCFG(dependency_graph=dependency_graph)

    block = facts.CFGBlockNode(id=block_id, children=children, control_flow_graph=control_flow_graph)

    return facts.OperationNode(id=id, block=block, operation_details=None, parsed_obj=workflow)
