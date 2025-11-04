# Copyright (c) 2023 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Parser for GitHub Actions expression language."""

from typing import cast

from lark import Lark, Token, Tree

from macaron.code_analyzer.dataflow_analysis import facts

# Parser for GitHub Actions expression language grammar.
github_expr_parser = Lark(
    r"""
    _expr: literal
        | identifier
        | _operator_expr
        | function_call

    literal: BOOLEAN_LITERAL
           | NULL_LITERAL
           | NUMBER_LITERAL
           | STRING_LITERAL

    BOOLEAN_LITERAL: "true" | "false"

    NULL_LITERAL: "null"

    NUMBER_LITERAL: SIGNED_NUMBER

    STRING_LITERAL: "'" STRING_INNER + "'"

    STRING_INNER: /.*?/s

    CNAMEWITHDASH: ("_"|LETTER) ("_"|"-"|LETTER|DIGIT)*

    identifier: CNAMEWITHDASH

    _operator_expr: paren_expr
                 | property_deref
                 | property_deref_object_filter
                 | index_expr
                 | not_expr
                 | and_expr
                 | or_expr
                 | less_than_expr
                 | less_than_equal_expr
                 | greater_than_expr
                 | greater_than_equal_expr
                 | equal_expr
                 | not_equal_expr

    paren_expr: "(" _expr ")"
    property_deref: _expr "." identifier
    property_deref_object_filter: _expr "." "*"
    index_expr: _expr "[" _expr "]"
    not_expr: "!" _expr
    and_expr: _expr "&&" _expr
    or_expr: _expr "||" _expr
    less_than_expr: _expr "<" _expr
    less_than_equal_expr: _expr "<=" _expr
    greater_than_expr: _expr ">" _expr
    greater_than_equal_expr: _expr ">=" _expr
    equal_expr: _expr "==" _expr
    not_equal_expr: _expr "!=" _expr

    function_call: identifier "(" _expr ("," _expr)* ")"

    %import common.SIGNED_NUMBER
    %import common.WS
    %import common.LETTER
    %import common.DIGIT
    %import common._STRING_INNER
    %ignore WS
    """,
    start="_expr",
)


def extract_expr_variable_name(node: Token | Tree[Token]) -> str | None:
    """Return variable access path for token.

    If the given node is a variable access or sequence of property accesses, return the
    access path as a string, otherwise return None.
    """
    if isinstance(node, Tree) and node.data == "property_deref":
        rest = extract_expr_variable_name(node.children[0])
        property_identifier = cast(Tree, node.children[1])
        if rest is not None:
            identifier = cast(Token, property_identifier.children[0])
            return rest + "." + identifier
    elif isinstance(node, Tree) and node.data == "identifier":
        identifier = cast(Token, node.children[0])
        return cast(str, identifier.value)

    return None


def extract_value_from_expr_string(s: str, var_scope: facts.Scope | None) -> facts.Value | None:
    """Return a value expression representation of a string containing GitHub Actions expressions.

    GitHub Action expressions within the string are denoted by "${{ <expr> }}".

    Returns None if it is unrepresentable.
    """
    cur_idx = 0
    cur_expr_begin = s.find("${{")
    values: list[facts.Value] = []
    while cur_expr_begin != -1:
        cur_str = s[cur_idx:cur_expr_begin]
        values.append(facts.StringLiteral(cur_str))
        cur_expr_end = s.find("}}", cur_expr_begin)
        cur_expr = s[cur_expr_begin + 3 : cur_expr_end]
        parse_tree = github_expr_parser.parse(cur_expr)

        node = parse_tree.children[0]

        var_str = extract_expr_variable_name(node)
        if var_str is not None and var_scope is not None:
            values.append(
                facts.Read(
                    loc=facts.Location(scope=var_scope, loc=facts.Variable(name=facts.StringLiteral(literal=var_str)))
                )
            )
        else:
            return None

        cur_idx = cur_expr_end + 2
        cur_expr_begin = s.find("${{", cur_idx)
    last_str = s[cur_idx:]

    values.append(facts.StringLiteral(last_str))

    if len(values) == 1:
        return values[0]

    cur_concat = facts.BinaryStringOp.get_string_concat(values[0], values[1])

    for val in values[2:]:
        cur_concat = facts.BinaryStringOp.get_string_concat(cur_concat, val)
    return cur_concat
