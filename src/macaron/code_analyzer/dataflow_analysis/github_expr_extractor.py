# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

from collections import defaultdict
from dataclasses import dataclass
from pprint import pformat
from typing import cast

from lark import Lark, Token, Tree

from macaron.code_analyzer.dataflow_analysis import bash_extractor, facts
from macaron.parsers import bashparser, github_workflow_model

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
                          
    STRING_INNER: /.*?/
                          
    identifier: CNAME
                          
    _operator_expr: paren_expr
                 | property_deref
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
    %import common.CNAME
    %import common._STRING_INNER
    %ignore WS
    """,
    start="_expr",
)


def extract_expr_variable_name(node: Token | Tree[Token]) -> str | None:
    if isinstance(node, Tree) and node.data == "property_deref":
        rest = extract_expr_variable_name(node.children[0])
        property_identifier = cast(Tree, node.children[1])
        if rest is not None:
            id = cast(Token, property_identifier.children[0])
            return rest + "." + id
    elif isinstance(node, Tree) and node.data == "identifier":
        id = cast(Token, node.children[0])
        return cast(str, id.value)

    return None


def extract_value_from_expr_string(s: str, var_scope: str) -> facts.Value | None:
    if "${{" in s:
        if s.startswith("${{") and s.endswith("}}"):
            expr = s.removeprefix("${{").removesuffix("}}")
            parse_tree = github_expr_parser.parse(expr)
            print("EXPR: " + parse_tree.pretty())

            node = parse_tree.children[0]

            var_str = extract_expr_variable_name(node)
            if var_str is not None:
                return facts.Read(
                    loc=facts.Location(scope=var_scope, loc=facts.Variable(name=facts.StringLiteral(literal=var_str)))
                )

    else:
        return facts.StringLiteral(literal=s)

    return None
