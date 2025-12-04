# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Functions for printing/displaying dataflow analysis nodes in the form of graphviz (dot) output.

Allows the analysis representation and results to be rendered as a human-readable node-link graph.

Makes use of graphviz's html-like label feature to add detailed information to each node.
Tables are specified in the form of a dict[str, set[tuple[str | None, str]], which is rendered as
a two-column table, with the first column containing each of the keys of the dict, and the second
column containing the corresponding set of values, as a nested vertical table, with each value having
an optional label that, if present, will be rendered in a visually distinguished manner alongside the
value.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import TextIO

from macaron.code_analyzer.dataflow_analysis import core


def print_as_dot_graph(node: core.Node, out: TextIO, include_properties: bool, include_states: bool) -> None:
    """Print root node as dot graph.

    Parameters
    ----------
    node: core.Node
        The root node to print.
    out: TextIO
        Output stream to print to.
    include_properties: bool
        Whether to include detail on the properties of each node (disable to make nodes simpler/smaller).
    include_states: bool
        Whether to include detail on the abstract state at each node (disable to make nodes simpler/smaller).
    """
    out.write("digraph {\n")
    out.write('node [style="filled", fillcolor="white"]\n')
    print_as_dot_string(node, out, include_properties=include_properties, include_states=include_states)
    out.write("}\n")


def get_printable_table_for_state(
    state: core.State, state_filter: core.StateTransferFilter | None = None
) -> dict[str, set[tuple[str | None, str]]]:
    """Return a table of the stringified representation of the state.

    Consists of a mapping of storage locations to the set of values they may contain
    (see module comment for description of the return type).

    Values are additionally labeled with whether they were new and not copied, and whether
    they will be excluded by the given filter.
    """
    result: dict[str, set[tuple[str | None, str]]] = {}
    for key, vals in state.state.items():
        vals_strs: set[tuple[str | None, str]] = {
            (
                str(label.sequence_number)
                + ("*" if not label.copied else "")
                + ("!" if state_filter is not None and not state_filter.should_transfer(key) else ""),
                val.to_datalog_fact_string(),
            )
            for val, label in vals.items()
        }
        key_str = key.to_datalog_fact_string()
        result[key_str] = vals_strs
    return result


def print_as_dot_string(node: core.Node, out: TextIO, include_properties: bool, include_states: bool) -> None:
    """Print node as dot representation (to be embedded within a dot graph).

    Parameters
    ----------
    node: core.Node
        The node to print.
    out: TextIO
        Output stream to print to.
    include_properties: bool
        Whether to include detail on the properties of each node (disable to make nodes simpler/smaller).
    include_states: bool
        Whether to include detail on the abstract state at each node (disable to make nodes simpler/smaller).
    """
    match node:
        case core.ControlFlowGraphNode():
            print_cfg_node_as_dot_string(node, out, include_properties, include_states)
        case core.StatementNode():
            print_statement_node_as_dot_string(node, out, include_properties, include_states)
        case core.InterpretationNode():
            print_interpretation_node_as_dot_string(node, out, include_properties, include_states)


def print_cfg_node_as_dot_string(
    cfg_node: core.ControlFlowGraphNode, out: TextIO, include_properties: bool, include_states: bool
) -> None:
    """Print control-flow-graph node as dot representation (to be embedded within a dot graph).

    Parameters
    ----------
    cfg_node: core.ControlFlowGraphNode
        The control-flow-graph node to print.
    out: TextIO
        Output stream to print to.
    include_properties: bool
        Whether to include detail on the properties of each node (disable to make nodes simpler/smaller).
    include_states: bool
        Whether to include detail on the abstract state at each node (disable to make nodes simpler/smaller).
    """
    out.write("subgraph cluster_n" + str(id(cfg_node)) + "{\n")
    out.write("style=filled\n")
    out.write('fillcolor="#fdf3e4ff"\n')

    subtables: list[tuple[str, dict[str, set[tuple[str | None, str]]], DotHtmlLikeTableConfiguration]] = []
    if include_properties:
        properties_table = cfg_node.get_printable_properties_table()
        if len(properties_table) > 0:
            subtables.append(
                (
                    "Properties",
                    cfg_node.get_printable_properties_table(),
                    DOT_HTML_LIKE_TABLE_CONFIG_CONTROL_FLOW_GRAPH_NODE_PROPERTIES,
                )
            )

    if include_states:
        subtables.append(
            (
                "Before State",
                get_printable_table_for_state(cfg_node.before_state),
                DOT_HTML_LIKE_TABLE_CONFIG_CONTROL_FLOW_GRAPH_NODE_PROPERTIES,
            )
        )
        if core.DEFAULT_EXIT in cfg_node.exit_states:
            subtables.append(
                (
                    "Exit State",
                    get_printable_table_for_state(
                        cfg_node.exit_states[core.DEFAULT_EXIT], cfg_node.get_exit_state_transfer_filter()
                    ),
                    DOT_HTML_LIKE_TABLE_CONFIG_CONTROL_FLOW_GRAPH_NODE_PROPERTIES,
                )
            )
        for exit_type, exit_state in cfg_node.exit_states.items():
            if not isinstance(exit_type, core.DefaultExit):
                subtables.append(
                    (
                        "Exit State (" + exit_type.__class__.__name__ + ")",
                        get_printable_table_for_state(exit_state, cfg_node.get_exit_state_transfer_filter()),
                        DOT_HTML_LIKE_TABLE_CONFIG_CONTROL_FLOW_GRAPH_NODE_PROPERTIES,
                    )
                )

    out.write(
        produce_node_dot_def(
            node_id=("n" + str(id(cfg_node))),
            node_kind="ControlFlowGraph",
            node_type=cfg_node.__class__.__name__,
            node_label=(
                "["
                + ", ".join(
                    [str(cfg_node.created_debug_sequence_num)]
                    + ["(" + str(b) + "-" + str(e) + ")" for b, e in cfg_node.processed_log]
                )
                + "]"
                if include_states
                else None
            ),
            config=DOT_HTML_LIKE_TABLE_CONFIG_CONTROL_FLOW_GRAPH_NODE,
            subtables=subtables,
        )
        + "\n"
    )

    i = 0
    out.write("n" + str(id(cfg_node)) + " -> " + "c" + str(id(cfg_node.get_entry())) + ' [label="entry"]\n')

    for child_node in cfg_node.children():
        out.write(
            "c"
            + str(id(child_node))
            + ' [label="'
            + str(i)
            + '", shape=circle, fontcolor="#ffffffff", fillcolor="#aa643bff"]\n'
        )
        out.write(
            "e"
            + str(id(cfg_node))
            + '_exit [label="exit", shape=circle, fontcolor="#ffffffff", fillcolor="#aa643bff"]\n'
        )
        next_alt_exit_id = 0
        alt_exit_ids: dict[core.ExitType, int] = {}

        for exit_type in child_node.exit_states:
            successors = cfg_node.get_successors(child_node, exit_type)
            for successor in successors:
                if isinstance(successor, core.Node):
                    out.write("c" + str(id(child_node)) + " -> " + "c" + str(id(successor)) + ' [label=""]\n')
                elif isinstance(successor, core.DefaultExit):
                    out.write("c" + str(id(child_node)) + " -> " + "e" + str(id(cfg_node)) + "_exit" + ' [label=""]\n')
                else:
                    if successor not in alt_exit_ids:
                        alt_exit_ids[successor] = next_alt_exit_id
                        next_alt_exit_id = next_alt_exit_id + 1
                    alt_exit_id = alt_exit_ids[successor]
                    out.write(
                        "c"
                        + str(id(child_node))
                        + " -> "
                        + "e"
                        + str(id(cfg_node))
                        + "_alt_exit_"
                        + str(alt_exit_id)
                        + ' [label=""]\n'
                    )

        for alt_exit_id in alt_exit_ids.values():
            out.write(
                "e"
                + str(id(cfg_node))
                + "_alt_exit_"
                + str(alt_exit_id)
                + ' [label="alt-exit", shape=circle, fontcolor="#ffffffff", fillcolor="#aa643bff"]\n'
            )
        i = i + 1
    out.write("}\n")

    for child_node in cfg_node.children():
        out.write("c" + str(id(child_node)) + " -> " + "n" + str(id(child_node)) + ' [label=""]\n')

    for child_node in cfg_node.children():
        print_as_dot_string(child_node, out, include_properties=include_properties, include_states=include_states)


def print_statement_node_as_dot_string(
    node: core.StatementNode, out: TextIO, include_properties: bool, include_states: bool
) -> None:
    """Print statement node as dot representation (to be embedded within a dot graph).

    Parameters
    ----------
    node: core.StatementNode
        The statement node to print.
    out: TextIO
        Output stream to print to.
    include_properties: bool
        Whether to include detail on the properties of each node (disable to make nodes simpler/smaller).
    include_states: bool
        Whether to include detail on the abstract state at each node (disable to make nodes simpler/smaller).
    """
    subtables: list[tuple[str, dict[str, set[tuple[str | None, str]]], DotHtmlLikeTableConfiguration]] = []

    if include_properties:
        properties_table = node.get_printable_properties_table()
        if len(properties_table) > 0:
            subtables.append(
                (
                    "Properties",
                    node.get_printable_properties_table(),
                    DOT_HTML_LIKE_TABLE_CONFIG_STATEMENT_NODE_PROPERTIES,
                )
            )

    if include_states:
        subtables.append(
            (
                "Before State",
                get_printable_table_for_state(node.before_state),
                DOT_HTML_LIKE_TABLE_CONFIG_STATEMENT_NODE_PROPERTIES,
            )
        )
        if core.DEFAULT_EXIT in node.exit_states:
            subtables.append(
                (
                    "Exit State",
                    get_printable_table_for_state(
                        node.exit_states[core.DEFAULT_EXIT], node.get_exit_state_transfer_filter()
                    ),
                    DOT_HTML_LIKE_TABLE_CONFIG_STATEMENT_NODE_PROPERTIES,
                )
            )
        for exit_type, exit_state in node.exit_states.items():
            if not isinstance(exit_type, core.DefaultExit):
                subtables.append(
                    (
                        "Exit State + (" + exit_type.__class__.__name__ + ")",
                        get_printable_table_for_state(exit_state, node.get_exit_state_transfer_filter()),
                        DOT_HTML_LIKE_TABLE_CONFIG_STATEMENT_NODE_PROPERTIES,
                    )
                )

    out.write(
        produce_node_dot_def(
            node_id=("n" + str(id(node))),
            node_kind="Statement",
            node_type=node.__class__.__name__,
            node_label=(
                "["
                + ", ".join(
                    [str(node.created_debug_sequence_num)]
                    + ["(" + str(b) + "-" + str(e) + ")" for b, e in node.processed_log]
                )
                + "]"
                if include_states
                else None
            ),
            config=DOT_HTML_LIKE_TABLE_CONFIG_STATEMENT_NODE,
            subtables=subtables,
        )
        + "\n"
    )


def print_interpretation_node_as_dot_string(
    node: core.InterpretationNode, out: TextIO, include_properties: bool, include_states: bool
) -> None:
    """Print interpretation node as dot representation (to be embedded within a dot graph).

    Parameters
    ----------
    node: core.InterpretationNode
        The interpretation node to print.
    out: TextIO
        Output stream to print to.
    include_properties: bool
        Whether to include detail on the properties of each node (disable to make nodes simpler/smaller).
    include_states: bool
        Whether to include detail on the abstract state at each node (disable to make nodes simpler/smaller).
    """
    subtables: list[tuple[str, dict[str, set[tuple[str | None, str]]], DotHtmlLikeTableConfiguration]] = []

    if include_properties:
        properties_table = node.get_printable_properties_table()
        if len(properties_table) > 0:
            subtables.append(
                (
                    "Properties",
                    node.get_printable_properties_table(),
                    DOT_HTML_LIKE_TABLE_CONFIG_INTERPRETATION_NODE_PROPERTIES,
                )
            )

    if include_states:
        subtables.append(
            (
                "Before State",
                get_printable_table_for_state(node.before_state),
                DOT_HTML_LIKE_TABLE_CONFIG_INTERPRETATION_NODE_PROPERTIES,
            )
        )
        if core.DEFAULT_EXIT in node.exit_states:
            subtables.append(
                (
                    "Exit State",
                    get_printable_table_for_state(
                        node.exit_states[core.DEFAULT_EXIT], node.get_exit_state_transfer_filter()
                    ),
                    DOT_HTML_LIKE_TABLE_CONFIG_INTERPRETATION_NODE_PROPERTIES,
                )
            )
        for exit_type, exit_state in node.exit_states.items():
            if not isinstance(exit_type, core.DefaultExit):
                subtables.append(
                    (
                        "Exit State + (" + exit_type.__class__.__name__ + ")",
                        get_printable_table_for_state(exit_state, node.get_exit_state_transfer_filter()),
                        DOT_HTML_LIKE_TABLE_CONFIG_INTERPRETATION_NODE_PROPERTIES,
                    )
                )

    out.write(
        produce_node_dot_def(
            node_id=("n" + str(id(node))),
            node_kind="Interpretation",
            node_type=node.__class__.__name__,
            node_label=(
                "["
                + ", ".join(
                    [str(node.created_debug_sequence_num)]
                    + ["(" + str(b) + "-" + str(e) + ")" for b, e in node.processed_log]
                )
                + "]"
                if include_states
                else None
            ),
            config=DOT_HTML_LIKE_TABLE_CONFIG_INTERPRETATION_NODE,
            subtables=subtables,
        )
        + "\n"
    )
    for child_node in node.interpretations.values():
        out.write("n" + str(id(node)) + " -> " + "n" + str(id(child_node)) + ' [label="interpretation"]\n')
    for child_node in node.interpretations.values():
        print_as_dot_string(child_node, out, include_properties=include_properties, include_states=include_states)


def escape_for_dot_html_like_label(s: str) -> str:
    """Return string escape for inclusion in a dot html-like label."""
    return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


@dataclass(frozen=True)
class DotHtmlLikeTableConfiguration:
    """Configuration for rendering of dot html-like table."""

    #: Background colour for table header.
    header_colour: str
    #: Font colour for table header.
    header_font_colour: str
    #: Font size for table header.
    header_font_size: int
    #: Whether font of table header should be bold.
    header_font_bold: bool
    #: Background colour for table body.
    body_colour: str
    #: Font colour for table body.
    body_font_colour: str
    #: Font size for table body.
    body_font_size: int


DARK_BLUE = "#6f757eff"
LIGHT_BLUE = "#dae2efff"
DARK_BROWN = "#aa643bff"
LIGHT_BROWN = "#f5debdff"
DARK_PINK = "#a36472ff"
LIGHT_PINK = "#f6dae1ff"
LIGHT_TEXT = "#ffffffff"
DARK_TEXT = "#161513ff"
DARK_GREY = "#7a736eff"
LIGHT_GREY = "#e4e1dcff"


DOT_HTML_LIKE_TABLE_CONFIG_INTERPRETATION_NODE = DotHtmlLikeTableConfiguration(
    header_colour=DARK_PINK,
    header_font_colour=LIGHT_TEXT,
    header_font_size=24,
    header_font_bold=True,
    body_colour=LIGHT_PINK,
    body_font_colour=DARK_TEXT,
    body_font_size=6,
)

DOT_HTML_LIKE_TABLE_CONFIG_INTERPRETATION_NODE_PROPERTIES = dataclasses.replace(
    DOT_HTML_LIKE_TABLE_CONFIG_INTERPRETATION_NODE, header_font_size=12
)

DOT_HTML_LIKE_TABLE_CONFIG_CONTROL_FLOW_GRAPH_NODE = DotHtmlLikeTableConfiguration(
    header_colour=DARK_BROWN,
    header_font_colour=LIGHT_TEXT,
    header_font_size=24,
    header_font_bold=True,
    body_colour=LIGHT_BROWN,
    body_font_colour=DARK_TEXT,
    body_font_size=6,
)

DOT_HTML_LIKE_TABLE_CONFIG_CONTROL_FLOW_GRAPH_NODE_PROPERTIES = dataclasses.replace(
    DOT_HTML_LIKE_TABLE_CONFIG_CONTROL_FLOW_GRAPH_NODE, header_font_size=12
)

DOT_HTML_LIKE_TABLE_CONFIG_STATEMENT_NODE = DotHtmlLikeTableConfiguration(
    header_colour=DARK_BLUE,
    header_font_colour=LIGHT_TEXT,
    header_font_size=24,
    header_font_bold=True,
    body_colour=LIGHT_BLUE,
    body_font_colour=DARK_TEXT,
    body_font_size=6,
)

DOT_HTML_LIKE_TABLE_CONFIG_STATEMENT_NODE_PROPERTIES = dataclasses.replace(
    DOT_HTML_LIKE_TABLE_CONFIG_STATEMENT_NODE, header_font_size=12
)

DOT_HTML_LIKE_TABLE_CONFIG_STATE = DotHtmlLikeTableConfiguration(
    header_colour=DARK_GREY,
    header_font_colour=LIGHT_TEXT,
    header_font_size=12,
    header_font_bold=True,
    body_colour=LIGHT_GREY,
    body_font_colour=DARK_TEXT,
    body_font_size=6,
)


def truncate_long_strings_for_display(s: str) -> str:
    """Truncate long string if necessary for display."""
    if len(s) > 100:
        return s[:100] + "..."
    return s


def produce_dot_html_like_table(
    header: str, data: dict[str, set[tuple[str | None, str]]], config: DotHtmlLikeTableConfiguration
) -> str:
    """Return the given data table rendered as a dot html-like label table.

    See module comment for description of how data tables are rendered.
    """
    lines: list[str] = []
    lines.append(
        '<table bgcolor="'
        + config.body_colour
        + '" align="center" valign="middle" border="0" cellspacing="0" cellborder="1" cellpadding="0">'
    )
    lines.append(
        '  <tr><td colspan="2" bgcolor="'
        + config.header_colour
        + '"><font color="'
        + config.header_font_colour
        + '" point-size="'
        + str(config.header_font_size)
        + '">'
        + ("<b>" if config.header_font_bold else "")
        + escape_for_dot_html_like_label(header)
        + ("</b>" if config.header_font_bold else "")
        + "</font></td></tr>"
    )

    for key, vals in data.items():
        lines.append(
            '  <tr><td><font color="'
            + config.body_font_colour
            + '" point-size="'
            + str(config.body_font_size)
            + '">'
            + escape_for_dot_html_like_label(key)
            + "</font></td>"
        )
        lines.append(
            '    <td><table align="center" valign="middle" border="0" cellspacing="0" cellborder="0" cellpadding="1" rows="*">'
        )
        if len(vals) > 0:
            for val in vals:
                label_part = (
                    (
                        '<font color="'
                        + config.body_font_colour
                        + '" point-size="'
                        + str(config.body_font_size)
                        + '"><b>['
                        + escape_for_dot_html_like_label(val[0])
                        + "] </b></font>"
                    )
                    if val[0] is not None
                    else ""
                )
                lines.append(
                    "      <tr><td>"
                    + label_part
                    + '<font color="'
                    + config.body_font_colour
                    + '" point-size="'
                    + str(config.body_font_size)
                    + '">'
                    + escape_for_dot_html_like_label(truncate_long_strings_for_display(val[1]))
                    + "</font></td></tr>"
                )
        else:
            lines.append("    <tr><td></td></tr>")

        lines.append("    </table></td>")
        lines.append("  </tr>")

    lines.append("</table>")

    return "\n".join(lines)


def produce_node_dot_html_like_label(
    node_kind: str,
    node_type: str,
    node_label: str | None,
    config: DotHtmlLikeTableConfiguration,
    subtables: list[tuple[str, dict[str, set[tuple[str | None, str]]], DotHtmlLikeTableConfiguration]],
) -> str:
    """Return the given node table data rendered as a dot html-like label table.

    Contains nested tables for each subtable (see module comment for description of how data tables are rendered).
    """
    lines: list[str] = []
    lines.append(
        '< <table bgcolor="'
        + config.body_colour
        + '" align="center" valign="middle" border="0" cellspacing="0" cellborder="1" cellpadding="0">'
    )
    lines.append(
        '  <tr><td colspan="2" bgcolor="'
        + config.header_colour
        + '">'
        + '<font color="'
        + config.header_font_colour
        + '" point-size="'
        + str(config.header_font_size)
        + '">'
        + ("<b>" if config.header_font_bold else "")
        + escape_for_dot_html_like_label(node_kind)
        + ("</b>" if config.header_font_bold else "")
        + "</font></td></tr>"
    )
    lines.append(
        '  <tr><td colspan="2"><font color="'
        + config.body_font_colour
        + '" point-size="'
        + str(config.header_font_size)
        + '">'
        + ("<b>" if config.header_font_bold else "")
        + escape_for_dot_html_like_label(node_type)
        + ("</b>" if config.header_font_bold else "")
        + "</font></td></tr>"
    )
    if node_label is not None:
        lines.append(
            '  <tr><td colspan="2"><font color="'
            + config.body_font_colour
            + '" point-size="'
            + str(config.header_font_size)
            + '">'
            + (
                (
                    '<font color="'
                    + config.body_font_colour
                    + '" point-size="'
                    + str(config.body_font_size)
                    + '">'
                    + "<b>"
                    + escape_for_dot_html_like_label(node_label)
                    + "</b></font>"
                )
                if node_label is not None
                else ""
            )
            + "</font></td></tr>"
        )

    for subtable in subtables:
        subtable_header, subtable_data, subtable_config = subtable
        lines.append(
            '  <tr><td colspan="2">'
            + produce_dot_html_like_table(subtable_header, subtable_data, subtable_config)
            + "</td></tr>"
        )

    lines.append("</table> >")

    return "\n".join(lines)


def produce_node_dot_def(
    node_id: str,
    node_kind: str,
    node_type: str,
    node_label: str | None,
    config: DotHtmlLikeTableConfiguration,
    subtables: list[tuple[str, dict[str, set[tuple[str | None, str]]], DotHtmlLikeTableConfiguration]],
) -> str:
    """Return the given node table data rendered as a dot node containig a html-like label table.

    Contains nested tables for each subtable (see module comment for description of how data tables
    are rendered).
    """
    return (
        '"'
        + node_id
        + '" [shape=rectangle, fillcolor="'
        + config.body_colour
        + '" fontname="Oracle Sans Tab", label='
        + produce_node_dot_html_like_label(node_kind, node_type, node_label, config, subtables)
        + "]"
    )


def add_context_owned_scopes_to_properties_table(
    table: dict[str, set[tuple[str | None, str]]], context: core.ContextRef[core.Context]
) -> None:
    """Add an entry to the given data table listing the scopes owned by the given context."""
    owned_scopes = core.get_owned_scopes(context)
    if len(owned_scopes) > 0:
        table["scopes"] = {(None, scope.to_datalog_fact_string(include_outer_scope=True)) for scope in owned_scopes}
