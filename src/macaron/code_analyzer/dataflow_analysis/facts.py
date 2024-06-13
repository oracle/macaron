# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

from __future__ import annotations

import abc
import csv
import io
import os
import os.path
from abc import ABC
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, TypeVar, Union


class FactParseError(Exception):
    pass


def consume_whitespace(text: str) -> str:
    text_end_idx = len(text)
    space_end_idx = text_end_idx
    idx = 0
    while idx < text_end_idx:
        if text[idx].isspace():
            idx = idx + 1
        else:
            space_end_idx = idx
            break
    return text[space_end_idx:text_end_idx]


def consume(text: str, token: str) -> str:
    if text.startswith(token):
        return text[len(token) :]
    raise FactParseError(text)


# returns (name, remainder_text)
def parse_qualified_name(text: str) -> tuple[str, str]:
    text = consume_whitespace(text)
    text_end_idx = len(text)
    name_end_idx = text_end_idx
    idx = 0
    while idx < text_end_idx:
        if text[idx].isalnum() or text[idx] == "_" or text[idx] == "?" or text[idx] == ".":
            idx = idx + 1
        else:
            name_end_idx = idx
            break
    return text[0:name_end_idx], text[name_end_idx:text_end_idx]


def enquote_datalog_string_literal(literal: str) -> str:
    return '"' + literal.replace("\\", "\\\\").replace('"', '\\"') + '"'


class LocationSpecifier(abc.ABC):
    @abc.abstractmethod
    def to_datalog_fact_string(self) -> str:
        pass

    @staticmethod
    def parse_location_specifier(text: str) -> tuple[LocationSpecifier, str]:
        text = consume(text, "$")
        kind, text = parse_qualified_name(text)
        match kind:
            case "Filesystem":
                text = consume(text, "(")
                path_val, text = Value.parse_value(text)
                text = consume_whitespace(text)
                text = consume(text, ")")
                return Filesystem(path_val), text
            case "Variable":
                text = consume(text, "(")
                name_val, text = Value.parse_value(text)
                text = consume_whitespace(text)
                text = consume(text, ")")
                return Variable(name_val), text
            case "Artifact":
                text = consume(text, "(")
                name_val, text = Value.parse_value(text)
                text = consume(text, ",")
                text = consume_whitespace(text)
                file_val, text = Value.parse_value(text)
                text = consume(text, ")")
                return Artifact(name_val, file_val), text
        raise FactParseError()


def parse_symbol(text: str) -> tuple[str, str]:
    text = consume(text, '"')
    text_end_idx = len(text)
    str_end_idx = text_end_idx
    idx = 0
    in_escape = False
    char_list = []
    while idx < text_end_idx:
        if text[idx] == "\\":
            if not in_escape:
                in_escape = True
            else:
                char_list.append("\\")
                in_escape = False
        elif text[idx] == '"':
            if not in_escape:
                str_end_idx = idx
                break
            else:
                char_list.append('"')
                in_escape = False
        else:
            char_list.append(text[idx])
        idx = idx + 1

    str = "".join(char_list)
    text = text[str_end_idx:]
    text = consume(text, '"')
    return str, text


@dataclass(frozen=True)
class Location:
    scope: str
    loc: LocationSpecifier

    def to_datalog_fact_string(self) -> str:
        return "[" + enquote_datalog_string_literal(self.scope) + ", " + self.loc.to_datalog_fact_string() + "]"

    @staticmethod
    def parse_location(text: str) -> tuple[Location, str]:
        text = consume_whitespace(text)
        text = consume(text, "[")
        scope, text = parse_symbol(text)
        text = consume(text, ",")
        text = consume_whitespace(text)
        loc, text = LocationSpecifier.parse_location_specifier(text)
        text = consume_whitespace(text)
        text = consume(text, "]")
        return Location(scope, loc), text


class Value(abc.ABC):
    @abc.abstractmethod
    def to_datalog_fact_string(self) -> str:
        pass

    @staticmethod
    def parse_value(text: str) -> tuple[Value, str]:
        text = consume(text, "$")
        kind, text = parse_qualified_name(text)
        match kind:
            case "StringLiteral":
                text = consume(text, "(")
                str, text = parse_symbol(text)
                text = consume_whitespace(text)
                text = consume(text, ")")
                return StringLiteral(str), text
            case "Read":
                text = consume(text, "(")
                loc, text = Location.parse_location(text)
                text = consume_whitespace(text)
                text = consume(text, ")")
                return Read(loc), text
            case "ArbitraryNewData":
                text = consume(text, "(")
                str, text = parse_symbol(text)
                text = consume_whitespace(text)
                text = consume(text, ")")
                return ArbitraryNewData(str), text
            case "UnaryStringOp":
                text = consume(text, "(")
                un_operator, text = parse_un_op(text)
                text = consume(text, ",")
                text = consume_whitespace(text)
                operand_val, text = Value.parse_value(text)
                text = consume(text, ")")
                return UnaryStringOp(un_operator, operand_val), text
            case "BinaryStringOp":
                text = consume(text, "(")
                bin_operator, text = parse_bin_op(text)
                text = consume(text, ",")
                text = consume_whitespace(text)
                operand1, text = Value.parse_value(text)
                text = consume(text, ",")
                text = consume_whitespace(text)
                operand2, text = Value.parse_value(text)
                text = consume(text, ")")
                return BinaryStringOp(bin_operator, operand1, operand2), text
            case "InductionVar":
                return InductionVar(), text
            case "UnaryLocationReadOp":
                text = consume(text, "(")
                un_loc_operator, text = parse_un_loc_read_op(text)
                text = consume(text, ",")
                text = consume_whitespace(text)
                operand_loc, text = Location.parse_location(text)
                text = consume(text, ")")
                return UnaryLocationReadOp(un_loc_operator, operand_loc), text
        raise FactParseError()


@dataclass(frozen=True)
class StringLiteral(Value):
    literal: str

    def to_datalog_fact_string(self) -> str:
        return "$StringLiteral(" + enquote_datalog_string_literal(self.literal) + ")"


@dataclass(frozen=True)
class Read(Value):
    loc: Location

    def to_datalog_fact_string(self) -> str:
        return "$Read(" + self.loc.to_datalog_fact_string() + ")"


@dataclass(frozen=True)
class ArbitraryNewData(Value):
    at: str

    def to_datalog_fact_string(self) -> str:
        return "$ArbitraryNewData(" + enquote_datalog_string_literal(self.at) + ")"


class UnaryStringOperator(Enum):
    BaseName = auto()


def un_op_to_datalog_fact_string(op: UnaryStringOperator) -> str:
    if op == UnaryStringOperator.BaseName:
        return "$BaseName"
    raise ValueError("unknown UnaryStringOperator")


def parse_un_op(text: str) -> tuple[UnaryStringOperator, str]:
    text = consume(text, "$")
    name, text = parse_qualified_name(text)
    match name:
        case "BaseName":
            return UnaryStringOperator.BaseName, text
    raise FactParseError()


class BinaryStringOperator(Enum):
    StringConcat = auto()


def bin_op_to_datalog_fact_string(op: BinaryStringOperator) -> str:
    if op == BinaryStringOperator.StringConcat:
        return "$StringConcat"
    raise ValueError("unknown BinaryStringOperator")


def parse_bin_op(text: str) -> tuple[BinaryStringOperator, str]:
    text = consume(text, "$")
    name, text = parse_qualified_name(text)
    match name:
        case "StringConcat":
            return BinaryStringOperator.StringConcat, text
    raise FactParseError()


@dataclass(frozen=True)
class UnaryStringOp(Value):
    op: UnaryStringOperator
    operand: Value

    def to_datalog_fact_string(self) -> str:
        return (
            "$UnaryStringOp("
            + un_op_to_datalog_fact_string(self.op)
            + ", "
            + self.operand.to_datalog_fact_string()
            + ")"
        )


@dataclass(frozen=True)
class BinaryStringOp(Value):
    op: BinaryStringOperator
    operand1: Value
    operand2: Value

    def to_datalog_fact_string(self) -> str:
        return (
            "$BinaryStringOp("
            + bin_op_to_datalog_fact_string(self.op)
            + ", "
            + self.operand1.to_datalog_fact_string()
            + ", "
            + self.operand2.to_datalog_fact_string()
            + ")"
        )


@dataclass(frozen=True)
class InductionVar(Value):
    def to_datalog_fact_string(self) -> str:
        return "$InductionVar"


class UnaryLocationReadOperator(Enum):
    FileList = auto()
    AnyFileUnderDirectory = auto()


def un_loc_read_op_to_datalog_fact_string(op: UnaryLocationReadOperator) -> str:
    if op == UnaryLocationReadOperator.FileList:
        return "$FileList"
    elif op == UnaryLocationReadOperator.AnyFileUnderDirectory:
        return "$AnyFileUnderDirectory"
    raise ValueError("unknown UnaryLocationReadOperator")


def parse_un_loc_read_op(text: str) -> tuple[UnaryLocationReadOperator, str]:
    text = consume(text, "$")
    name, text = parse_qualified_name(text)
    match name:
        case "FileList":
            return UnaryLocationReadOperator.FileList, text
        case "AnyFileUnderDirectory":
            return UnaryLocationReadOperator.AnyFileUnderDirectory, text
    raise FactParseError()


@dataclass(frozen=True)
class UnaryLocationReadOp(Value):
    op: UnaryLocationReadOperator
    operand: Location

    def to_datalog_fact_string(self) -> str:
        return (
            "$UnaryLocationReadOp("
            + un_loc_read_op_to_datalog_fact_string(self.op)
            + ", "
            + self.operand.to_datalog_fact_string()
            + ")"
        )


@dataclass(frozen=True)
class Filesystem(LocationSpecifier):
    path: Value

    def to_datalog_fact_string(self) -> str:
        return "$Filesystem(" + self.path.to_datalog_fact_string() + ")"


@dataclass(frozen=True)
class Variable(LocationSpecifier):
    name: Value

    def to_datalog_fact_string(self) -> str:
        return "$Variable(" + self.name.to_datalog_fact_string() + ")"


@dataclass(frozen=True)
class Artifact(LocationSpecifier):
    name: Value
    file: Value

    def to_datalog_fact_string(self) -> str:
        return "$Artifact(" + self.name.to_datalog_fact_string() + ", " + self.file.to_datalog_fact_string() + ")"


class UniqueIdCreator:
    def __init__(self):
        self.next_index = 0

    def get_next_id(self, non_unique_id: str) -> str:
        uniqueId = str(self.next_index) + "::" + non_unique_id
        self.next_index = self.next_index + 1
        return uniqueId


class DatalogRelationRow(abc.ABC):
    @abc.abstractmethod
    def to_datalog_fact_csv_line(self) -> str:
        pass


def to_csv_string(record: list[str]) -> str:
    outstream = io.StringIO()
    writer = csv.writer(outstream, dialect="unix", lineterminator="")
    writer.writerow(record)
    return outstream.getvalue()


@dataclass(frozen=True)
class Write(DatalogRelationRow):
    id: str
    location: Location
    value: Value

    def to_datalog_fact_csv_line(self) -> str:
        return to_csv_string([self.id, self.location.to_datalog_fact_string(), self.value.to_datalog_fact_string()])


@dataclass(frozen=True)
class WriteForEach(DatalogRelationRow):
    id: str
    collection: Value
    location: Location
    value: Value

    def to_datalog_fact_csv_line(self) -> str:
        return to_csv_string(
            [
                self.id,
                self.collection.to_datalog_fact_string(),
                self.location.to_datalog_fact_string(),
                self.value.to_datalog_fact_string(),
            ]
        )


class OperationKind(Enum):
    YamlSpecGitHubAction = auto()
    ShellCommand = auto()


def operation_kind_to_datalog_fact_string(operation_kind: OperationKind) -> str:
    if operation_kind == OperationKind.YamlSpecGitHubAction:
        return "$YamlSpec($GitHubAction))"
    elif operation_kind == OperationKind.ShellCommand:
        return "$ShellCommand"
    raise ValueError("unknown OperationKind")


class Operation(abc.ABC):
    @abc.abstractmethod
    def get_id(self) -> str:
        pass

    @abc.abstractmethod
    def convert_to_facts(self, db: FactDatabase) -> None:
        pass


@dataclass(frozen=True)
class YamlFieldAccessPath:
    fields: tuple[str]

    def to_datalog_fact_string(self) -> str:
        if len(self.fields) == 0:
            raise ValueError("yaml field access path has no fields")
        result = "[" + enquote_datalog_string_literal(self.fields[-1]) + ",$NoYamlFields]"
        field: str
        for field in self.fields[-2::-1]:
            result = "[" + enquote_datalog_string_literal(field) + ", " + "$SomeYamlFields(" + result + ")" + "]"
        return result


def block_or_write_to_cfg_element_datalog_string(is_block: bool, element: str):
    if is_block:
        return "$CFGBlock(" + element + ")"
    else:
        return "$CFGWrite(" + element + ")"


@dataclass(frozen=True)
class SequentialBlockEntry(DatalogRelationRow):
    block: str
    is_block: bool
    element: str

    def to_datalog_fact_csv_line(self) -> str:
        return to_csv_string([self.block, block_or_write_to_cfg_element_datalog_string(self.is_block, self.element)])


@dataclass(frozen=True)
class SequentialBlockEdge(DatalogRelationRow):
    block: str
    from_is_block: bool
    from_element: str
    to_is_block: bool
    to_element: str

    def to_datalog_fact_csv_line(self) -> str:
        return to_csv_string(
            [
                self.block,
                block_or_write_to_cfg_element_datalog_string(self.from_is_block, self.from_element),
                block_or_write_to_cfg_element_datalog_string(self.to_is_block, self.to_element),
            ]
        )


@dataclass(frozen=True)
class SchedulerBlockMember(DatalogRelationRow):
    block: str
    is_block: bool
    element: str

    def to_datalog_fact_csv_line(self) -> str:
        return to_csv_string([self.block, block_or_write_to_cfg_element_datalog_string(self.is_block, self.element)])


@dataclass(frozen=True)
class SchedulerBlockDependency(DatalogRelationRow):
    block: str
    is_block: bool
    element: str
    preceding_is_block: bool
    preceding_element: str

    def to_datalog_fact_csv_line(self) -> str:
        return to_csv_string(
            [
                self.block,
                block_or_write_to_cfg_element_datalog_string(self.is_block, self.element),
                block_or_write_to_cfg_element_datalog_string(self.preceding_is_block, self.preceding_element),
            ]
        )


@dataclass(frozen=True)
class ScopeDirectlyInheritsFrom(DatalogRelationRow):
    from_scope: str
    to_scope: str

    def to_datalog_fact_csv_line(self) -> str:
        return to_csv_string([self.from_scope, self.to_scope])


@dataclass(frozen=True)
class OperationType(DatalogRelationRow):
    operation_id: str
    operation_type: OperationKind

    def to_datalog_fact_csv_line(self) -> str:
        return to_csv_string([self.operation_id, operation_kind_to_datalog_fact_string(self.operation_type)])


@dataclass(frozen=True)
class OperationShellCommandArg(DatalogRelationRow):
    operation_id: str
    arg_index: int
    value: Value | None

    def to_datalog_fact_csv_line(self) -> str:
        val_str: str
        if self.value is not None:
            val_str = "$SomeValue(" + self.value.to_datalog_fact_string() + ")"
        else:
            val_str = "$NoValue"
        return to_csv_string([self.operation_id, str(self.arg_index), val_str])


@dataclass(frozen=True)
class OperationYamlSpecField(DatalogRelationRow):
    operation_id: str
    field: YamlFieldAccessPath
    value: Value | None

    def to_datalog_fact_csv_line(self) -> str:
        val_str: str
        if self.value is not None:
            val_str = "$SomeValue(" + self.value.to_datalog_fact_string() + ")"
        else:
            val_str = "$NoValue"
        return to_csv_string([self.operation_id, self.field.to_datalog_fact_string(), val_str])


@dataclass(frozen=True)
class BlockOperation(DatalogRelationRow):
    block_id: str
    operation_id: str

    def to_datalog_fact_csv_line(self) -> str:
        return to_csv_string([self.block_id, self.operation_id])


@dataclass(frozen=True)
class BlockId(DatalogRelationRow):
    id: str

    def to_datalog_fact_csv_line(self) -> str:
        return to_csv_string([self.id])


RelT = TypeVar("RelT", bound=DatalogRelationRow)


def write_relation_to_file(filename: str, relation: set[RelT]) -> None:
    with open(filename, "w") as f:
        for row in relation:
            f.write(row.to_datalog_fact_csv_line() + "\n")
        f.flush()


class FactDatabase:
    write: set[Write]
    write_for_each: set[WriteForEach]
    scope_directly_inherits_from: set[ScopeDirectlyInheritsFrom]
    operation: set[OperationType]
    operation_shell_command_arg: set[OperationShellCommandArg]
    operation_yaml_spec_field: set[OperationYamlSpecField]
    sequential_block: set[BlockId]
    sequential_block_entry: set[SequentialBlockEntry]
    sequential_block_edge: set[SequentialBlockEdge]
    scheduler_block: set[BlockId]
    scheduler_block_member: set[SchedulerBlockMember]
    scheduler_block_dependency: set[SchedulerBlockDependency]
    block_operation: set[BlockOperation]
    top_level_block: set[BlockId]

    def __init__(self):
        self.write = set()
        self.write_for_each = set()
        self.scope_directly_inherits_from = set()
        self.operation = set()
        self.operation_shell_command_arg = set()
        self.operation_yaml_spec_field = set()
        self.sequential_block = set()
        self.sequential_block_entry = set()
        self.sequential_block_edge = set()
        self.scheduler_block = set()
        self.scheduler_block_member = set()
        self.scheduler_block_dependency = set()
        self.block_operation = set()
        self.top_level_block = set()

    def write_to_files(self, dir: str):
        os.makedirs(dir, exist_ok=True)
        write_relation_to_file(os.path.join(dir, "Write.facts"), self.write)
        write_relation_to_file(os.path.join(dir, "WriteForEach.facts"), self.write_for_each)
        write_relation_to_file(os.path.join(dir, "ScopeDirectlyInheritsFrom.facts"), self.scope_directly_inherits_from)
        write_relation_to_file(os.path.join(dir, "Operation.facts"), self.operation)
        write_relation_to_file(os.path.join(dir, "OperationShellCommandArg.facts"), self.operation_shell_command_arg)
        write_relation_to_file(os.path.join(dir, "OperationYamlSpecField.facts"), self.operation_yaml_spec_field)
        write_relation_to_file(os.path.join(dir, "SequentialBlock.facts"), self.sequential_block)
        write_relation_to_file(os.path.join(dir, "SequentialBlockEntry.facts"), self.sequential_block_entry)
        write_relation_to_file(os.path.join(dir, "SequentialBlockEdge.facts"), self.sequential_block_edge)
        write_relation_to_file(os.path.join(dir, "SchedulerBlock.facts"), self.scheduler_block)
        write_relation_to_file(os.path.join(dir, "SchedulerBlockMember.facts"), self.scheduler_block_member)
        write_relation_to_file(os.path.join(dir, "SchedulerBlockDependency.facts"), self.scheduler_block_dependency)
        write_relation_to_file(os.path.join(dir, "BlockOperation.facts"), self.block_operation)
        write_relation_to_file(os.path.join(dir, "TopLevelBlock.facts"), self.top_level_block)

    def get_stats(self) -> dict[str, int]:
        result: dict[str, int] = {}
        result["write"] = len(self.write)
        result["writeForEach"] = len(self.write_for_each)
        result["scopeDirectlyInheritsFrom"] = len(self.scope_directly_inherits_from)
        result["operation"] = len(self.operation)
        result["operationShellCommandArg"] = len(self.operation_shell_command_arg)
        result["operationYamlSpecField"] = len(self.operation_yaml_spec_field)
        result["sequentialBlock"] = len(self.sequential_block)
        result["sequentialBlockEntry"] = len(self.sequential_block_entry)
        result["sequentialBlockEdge"] = len(self.sequential_block_edge)
        result["schedulerBlock"] = len(self.scheduler_block)
        result["schedulerBlockMember"] = len(self.scheduler_block_member)
        result["schedulerBlockDependency"] = len(self.scheduler_block_dependency)
        result["blockOperation"] = len(self.block_operation)
        result["topLevelBlock"] = len(self.top_level_block)
        return result


@dataclass(frozen=True)
class YamlSpec(Operation):
    id: str
    fields: dict[YamlFieldAccessPath, Value | None]

    def get_id(self) -> str:
        return self.id

    def convert_to_facts(self, db: FactDatabase) -> None:
        db.operation.add(OperationType(operation_id=self.id, operation_type=OperationKind.YamlSpecGitHubAction))
        for key, val in self.fields.items():
            db.operation_yaml_spec_field.add(OperationYamlSpecField(operation_id=self.id, field=key, value=val))


@dataclass(frozen=True)
class ShellCommand(Operation):
    id: str
    args: tuple[Value | None]

    def get_id(self) -> str:
        return self.id

    def convert_to_facts(self, db: FactDatabase) -> None:
        db.operation.add(OperationType(operation_id=self.id, operation_type=OperationKind.ShellCommand))

        for i, arg in enumerate(self.args):
            db.operation_shell_command_arg.add(OperationShellCommandArg(operation_id=self.id, arg_index=i, value=arg))


# def getIsBlockAndId(cfgElement: SimpleBlock | Write | WriteForEach) -> tuple[bool, str]:
#     if isinstance(cfgElement, SimpleBlock):
#         return True, cfgElement.id
#     else:
#         return False, cfgElement.id

Statement = Union["Write", "WriteForEach"]

# @dataclass(frozen=True)
# class StatementBlock:
#     id: str
#     stmts: list[Statement]

# Block = Union["SimpleBlock", "SchedulerBlock", "SequentialBlock", "Write", "WriteForEach"]

# @dataclass(frozen=True)
# class SimpleBlock:
#     id: str
#     sequence: list[Block]
#     operation: Operation | None

#     def convertToFacts(self, db: FactDatabase) -> None:
#         db.sequentialBlock.add(BlockId(self.id))

#         if self.operation is not None:
#             db.blockOperation.add(BlockOperation(blockId=self.id, operationId=self.operation.getId()))
#             self.operation.convertToFacts(db)

#         if len(self.sequence) != 0:
#             isBlock, element = getIsBlockAndId(self.sequence[0])
#             db.sequentialBlockEntry.add(SequentialBlockEntry(block=self.id, isBlock=isBlock, element=element))

#             for i in range(1, len(self.sequence)):
#                 fromIsBlock, fromElement = getIsBlockAndId(self.sequence[i-1])
#                 toIsBlock, toElement = getIsBlockAndId(self.sequence[i])
#                 db.sequentialBlockEdge.add(SequentialBlockEdge(block=self.id, fromIsBlock=fromIsBlock, fromElement=fromElement, toIsBlock=toIsBlock, toElement=toElement))

#             for elem in self.sequence:
#                 if isinstance(elem, SimpleBlock):
#                     elem.convertToFacts(db)
#                 else:
#                     if isinstance(elem, Write):
#                         db.write.add(elem)
#                     elif isinstance(elem, WriteForEach):
#                         db.writeForEach.add(elem)

# Possible mapping?
# Workflow <--> SchedulerBlock
#   --> NormalJob <--> SequentialBlock
#     --> Step = RunStep | ActionStep
#       | RunStep <--> SequentialBlock
#         --> Bash Statement in run str <--> Invocation --> SequentialBlock
#           --> <implicit semantics> <--> StatementBlock
#             --> <implicit semantics <--> WriteStmt | WriteForEach
#           --> Tokenised Bash Statement <--> BlockOperation + OperationShellCommandArg
#       | ActionStep <--> Invocation --> SequentialBlock
#         --> <implicit semantics <--> StatementBlock
#           --> <implicit semantics> <--> WriteStmt | WriteForEach
#         --> Specification/Fields <--> BlockOperation + OperationYamlSpecField
#   --> ReusableWorkflowCallJob <--> Invocation --> SchedulerBlock/SequentialBlock
#     --> Specification/Fields <--> BlockOperation + OperationYamlSpecField


Node = Union["BlockNode", "OperationNode"]

BlockNode = Union["CFGBlockNode", "StatementBlockNode"]


@dataclass(frozen=True)
class CFGBlockNode:
    id: str
    children: list[Node]
    control_flow_graph: ControlFlowGraph


@dataclass(frozen=True)
class StatementBlockNode:
    id: str
    statements: list[Statement]


@dataclass(frozen=True)
class OperationNode:
    id: str
    block: BlockNode
    parsed_obj: Any  # TODO


ControlFlowGraph = Union["SequenceCFG", "SchedulerCFG"]


@dataclass(frozen=True)
class SequenceCFG:
    entry: str
    flow_graph: dict[str, list[str]]


@dataclass(frozen=True)
class SchedulerCFG:
    dependency_graph: dict[str, list[str]]


def create_cfg_block_from_sequence(unique_block_id: str, sequence: list[Node]) -> CFGBlockNode:
    if len(sequence) == 0:
        raise ValueError("sequence must not be empty")

    entry_id = sequence[0].id
    flow_graph: dict[str, list[str]] = defaultdict(list)

    for i in range(1, len(sequence)):
        flow_graph[sequence[i - 1].id].append(sequence[i].id)

    return CFGBlockNode(
        id=unique_block_id, children=sequence, control_flow_graph=SequenceCFG(entry=entry_id, flow_graph=flow_graph)
    )
