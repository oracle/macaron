# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Module providing entry point to run dataflow analysis independently of Macaron command.

For experimentation and debugging purposes only.
"""

import sys

from macaron.code_analyzer.dataflow_analysis import analysis, bash, core, github, printing
from macaron.slsa_analyzer.build_tool import Maven


def main() -> None:
    """Entry point for running standalone analysis."""
    raw_workflow_node = analysis.analyse_github_workflow_file(sys.argv[1], None)
    with open("dot", "w", encoding="utf-8") as f:
        printing.print_as_dot_graph(raw_workflow_node, f, include_properties=True, include_states=True)

    nodes: list[core.Node] = [raw_workflow_node]
    while len(nodes) > 0:
        node = nodes.pop()

        if isinstance(node, github.GitHubActionsActionStepNode):
            print("Action {")  # noqa: T201
            print("    name: " + node.uses_name)  # noqa: T201
            print("    version: " + node.uses_version if node.uses_version is not None else "")  # noqa: T201
            print("    with {")  # noqa: T201
            for key, val in node.with_parameters.items():
                print("        " + key + ": " + val.to_datalog_fact_string())  # noqa: T201
            print("    }")  # noqa: T201
            print("}")  # noqa: T201
        if isinstance(node, bash.BashSingleCommandNode):
            print("REACHABLE SECRETS: " + str(analysis.get_reachable_secrets(node)))  # noqa: T201
        for child in node.children():
            nodes.append(child)

    build_tool = Maven()

    for build_cmd in analysis.get_build_tool_commands(core.NodeForest([raw_workflow_node]), build_tool):
        print("build command: " + str(build_cmd["command"]))  # noqa: T201


if __name__ == "__main__":
    main()
