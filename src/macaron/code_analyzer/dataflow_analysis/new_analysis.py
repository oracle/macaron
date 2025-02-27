# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

from dataclasses import dataclass
from macaron.parsers import bashparser, github_workflow_model

class Node:
    #TODO
    pass

class ControlFlowBlockNode:
    #TODO
    pass

class StatementBlockNode:
    #TODO
    pass

class Scope:
    #TODO
    pass

class InterpretationKey:
    # TODO
    pass

BlockNode = ControlFlowBlockNode | StatementBlockNode

@dataclass(frozen=True)
class GitHubActionsWorkflowContext:
    artifacts: Scope
    releases: Scope
    env: Scope
    job_output_variables: Scope

@dataclass(frozen=True)
class GitHubActionsJobContext:
    workflow_context: GitHubActionsWorkflowContext
    filesystem: Scope
    env: Scope
    step_output_variables: Scope

@dataclass(frozen=True)
class GitHubActionsStepContext:
    job_context: GitHubActionsJobContext
    env: Scope

class GitHubActionsWorkflowNode(Node):
    definition: github_workflow_model.Workflow
    body_interpretations: set[BlockNode]
    context: GitHubActionsWorkflowContext

class GitHubActionsJobNode(Node):
    definition: github_workflow_model.NormalJob
    env_block: StatementBlockNode
    body_interpretations: set[BlockNode]
    output_block: StatementBlockNode
    context: GitHubActionsJobContext

class GitHubActionsReusableWorkflowCallNode(Node):
    definition: github_workflow_model.ReusableWorkflowCallJob
    body_interpretations: set[BlockNode]
    context: GitHubActionsWorkflowContext
    #TODO

class GitHubActionsActionStep(Node):
    definition: github_workflow_model.ActionStep
    #TODO

class GitHubActionsRunStep(Node):
    definition: github_workflow_model.RunStep
    env_block: StatementBlockNode
    body_interpretations: set[BlockNode]

