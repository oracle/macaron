# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

from dataclasses import dataclass

from macaron.code_analyzer.dataflow_analysis import facts
from macaron.parsers import bashparser_model
from pprint import pformat


@dataclass(frozen=True)
class ShellContext:
    base_id: str
    github_output_var_scope: str
    github_output_var_prefix: str
    filesystem_scope: str
    env_var_scope: str


def has_no_control_flow(stmts: list[bashparser_model.Stmt]) -> bool:
    for stmt in stmts:
        if not bashparser_model.is_call_expr(stmt["Cmd"]):
            return False
    return True


def extract_from_simple_bash_stmts(
    stmts: list[bashparser_model.Stmt], context: ShellContext, id_creator: facts.UniqueIdCreator
) -> facts.BlockNode:
    if not has_no_control_flow(stmts):
        raise Exception("shell script too complex")  # TODO better exception type

    write_base_id_str = "write@" + context.base_id
    block_base_id_str = "block@" + context.base_id

    sequence: list[facts.Node] = []

    stmt_idx = 0

    for stmt in stmts:
        cmd = stmt["Cmd"]

        if bashparser_model.is_call_expr(cmd):
            args = cmd.get("Args", [])
            if len(args) == 0:
                fact_stmt_list: list[facts.Statement] = []
                assigns = cmd.get("Assigns", [])
                for assign in assigns:
                    lhs_str = assign["Name"]["Value"]
                    lhs_loc = facts.Location(
                        scope=context.env_var_scope, loc=facts.Variable(name=facts.StringLiteral(literal=lhs_str))
                    )
                    if "Value" in assign:
                        rhs_content = parse_dbl_quoted_string_content(assign["Value"]["Parts"])
                        if rhs_content is not None:
                            rhs_val = convert_shell_value_sequence_to_fact_value(rhs_content, context)
                            fact_stmt_list.append(
                                facts.Write(
                                    id=id_creator.get_next_id(write_base_id_str), location=lhs_loc, value=rhs_val
                                )
                            )
                stmt_node = facts.StatementBlockNode(
                    id=id_creator.get_next_id(block_base_id_str), statements=fact_stmt_list
                )
                sequence.append(stmt_node)
            else:
                shell_cmd_base_id_str = "shellcmd::" + str(stmt_idx) + "@" + context.base_id
                # TODO revise and complete operation bits
                shell_arg_values: list[facts.Value | None] = []
                for arg in args:
                    shell_arg_val = convert_shell_word_to_value(arg, context)
                    shell_arg_values.append(shell_arg_val)

                fact_stmt_list: list[facts.Statement] = []


                # TODO revise mvn identification based on Macaron's existing rules
                if is_literal_word(args[0], "mvn"):
                    is_build = False
                    for arg in args:
                        if (
                            is_literal_word(arg, "package")
                            or is_literal_word(arg, "verify")
                            or is_literal_word(arg, "install")
                            or is_literal_word(arg, "deploy")
                        ):
                            is_build = True
                            break

                    if is_build:
                        write_id = id_creator.get_next_id(write_base_id_str)
                        coll = facts.UnaryLocationReadOp(
                            op=facts.UnaryLocationReadOperator.AnyFileUnderDirectory,
                            operand=facts.Location(
                                scope=context.filesystem_scope,
                                loc=facts.Filesystem(path=facts.StringLiteral("./target")),
                            ),
                        )
                        loc = facts.Location(
                            scope=context.filesystem_scope, loc=facts.Filesystem(path=facts.InductionVar())
                        )
                        val = facts.ArbitraryNewData(at=write_id)
                        fact_stmt_list.append(facts.WriteForEach(id=write_id, collection=coll, location=loc, value=val))

                for r in stmt.get("Redirs", []):
                    if (
                        r["Op"] == bashparser_model.RedirOperators.AppOut.value
                        and "Word" in r
                        and len(r["Word"]["Parts"]) == 1
                    ):

                        env_var = parse_env_var_read_word(r["Word"], True)
                        if env_var == "GITHUB_OUTPUT":
                            if len(args) == 2 and is_literal_word(args[0], "echo"):
                                echoed_content = parse_dbl_quoted_string(args[1])
                                if echoed_content is not None:
                                    lhs_content, rhs_content = split_on_first_str(echoed_content, "=")
                                    if len(lhs_content) > 0 and len(rhs_content) > 0:
                                        lhs_val = convert_shell_value_sequence_to_fact_value(lhs_content, context)
                                        lhs_val_with_prefix = facts.BinaryStringOp(
                                            op=facts.BinaryStringOperator.StringConcat,
                                            operand1=facts.StringLiteral(literal=context.github_output_var_prefix),
                                            operand2=lhs_val,
                                        )
                                        lhs_loc = facts.Location(
                                            scope=context.github_output_var_scope,
                                            loc=facts.Variable(name=lhs_val_with_prefix),
                                        )
                                        rhs_val = convert_shell_value_sequence_to_fact_value(rhs_content, context)
                                        fact_stmt_list.append(
                                            facts.Write(
                                                id=id_creator.get_next_id(write_base_id_str),
                                                location=lhs_loc,
                                                value=rhs_val,
                                            )
                                        )

                stmt_node = facts.StatementBlockNode(
                    id=id_creator.get_next_id(block_base_id_str), statements=fact_stmt_list
                )

                op_node = facts.OperationNode(
                    id=id_creator.get_next_id(shell_cmd_base_id_str), block=stmt_node, operation_details=None, parsed_obj=None
                )  # TODO parsed_obj

                sequence.append(op_node)

        stmt_idx = stmt_idx + 1

    block = facts.create_cfg_block_from_sequence(
        unique_block_id=id_creator.get_next_id(block_base_id_str), sequence=sequence
    )

    return block


@dataclass(frozen=True)
class LiteralOrEnvVar:
    is_env_var: bool
    literal: str


def is_simple_var_read(param_exp: bashparser_model.ParamExp) -> bool:
    if param_exp.get("Excl", False) or param_exp.get("Length", False) or param_exp.get("Width", False):
        return False
    if (
        "Index" in param_exp
        or "Slice" in param_exp
        or "Repl" in param_exp
        or "Names" in param_exp
        or "Exp" in param_exp
    ):
        return False
    return True


def parse_env_var_read_word_part(part: bashparser_model.WordPart, allow_dbl_quoted: bool) -> str | None:
    if bashparser_model.is_dbl_quoted(part):
        if not allow_dbl_quoted:
            return None
        if len(part["Parts"]) == 1:
            part = part["Parts"][0]
        else:
            return None

    if bashparser_model.is_param_exp(part):
        if not is_simple_var_read(part):
            return None
        return part["Param"]["Value"]

    return None


def parse_env_var_read_word(word: bashparser_model.Word, allow_dbl_quoted: bool) -> str | None:
    if len(word["Parts"]) == 1:
        part = word["Parts"][0]
        return parse_env_var_read_word_part(part, allow_dbl_quoted)


def parse_dbl_quoted_string_content(parts: list[bashparser_model.WordPart]) -> list[LiteralOrEnvVar] | None:
    content: list[LiteralOrEnvVar] = []
    for part in parts:
        env_var = parse_env_var_read_word_part(part, False)
        if env_var is not None:
            content.append(LiteralOrEnvVar(is_env_var=True, literal=env_var))
        elif bashparser_model.is_lit(part):
            content.append(LiteralOrEnvVar(is_env_var=False, literal=part["Value"]))
        else:
            return None
    return content


def parse_dbl_quoted_string(word: bashparser_model.Word) -> list[LiteralOrEnvVar] | None:
    if len(word["Parts"]) == 1:
        part = word["Parts"][0]
        if bashparser_model.is_dbl_quoted(part):
            return parse_dbl_quoted_string_content(part["Parts"])

    return None


def parse_singular_literal(word: bashparser_model.Word) -> str | None:
    if len(word["Parts"]) == 1:
        part = word["Parts"][0]
        if bashparser_model.is_lit(part):
            return part["Value"]

    return None


def is_literal_word(word: bashparser_model.Word, literal: str) -> bool:
    singular_literal = parse_singular_literal(word)
    return singular_literal is not None and singular_literal == literal


def convert_shell_value_sequence_to_fact_value(content: list[LiteralOrEnvVar], context: ShellContext) -> facts.Value:
    if len(content) == 0:
        raise ValueError("sequence cannot be empty")

    first_val = convert_shell_value_to_fact_value(content[0], context)
    if len(content) == 1:
        return first_val

    rest_val = convert_shell_value_sequence_to_fact_value(content[1:], context)

    return facts.BinaryStringOp(op=facts.BinaryStringOperator.StringConcat, operand1=first_val, operand2=rest_val)


def convert_shell_value_to_fact_value(val: LiteralOrEnvVar, context: ShellContext) -> facts.Value:
    if val.is_env_var:
        return facts.Read(
            loc=facts.Location(
                scope=context.env_var_scope, loc=facts.Variable(name=facts.StringLiteral(literal=val.literal))
            )
        )
    else:
        return facts.StringLiteral(literal=val.literal)


def convert_shell_word_to_value(word: bashparser_model.Word, context: ShellContext) -> facts.Value | None:
    dbl_quoted_parts = parse_dbl_quoted_string(word)
    if dbl_quoted_parts is not None:
        return convert_shell_value_sequence_to_fact_value(dbl_quoted_parts, context)

    singular_literal = parse_singular_literal(word)
    if singular_literal is not None:
        return facts.StringLiteral(literal=singular_literal)

    return None


def split_on_first_str(content: list[LiteralOrEnvVar], s: str) -> tuple[list[LiteralOrEnvVar], list[LiteralOrEnvVar]]:
    found_str = False
    before_content: list[LiteralOrEnvVar] = []
    after_content: list[LiteralOrEnvVar] = []
    for elem in content:
        if elem.is_env_var:
            if not found_str:
                before_content.append(elem)
            else:
                after_content.append(elem)
        else:
            if not found_str:
                split = elem.literal.split(s, maxsplit=1)
                if len(split) == 2:
                    if split[0] != "":
                        before_content.append(LiteralOrEnvVar(is_env_var=False, literal=split[0]))
                    if split[1] != "":
                        after_content.append(LiteralOrEnvVar(is_env_var=False, literal=split[1]))
                    found_str = True
                else:
                    before_content.append(elem)
            else:
                after_content.append(elem)
    return before_content, after_content
