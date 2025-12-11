# Copyright (c) 2023 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Definitions of dataflow analysis representation for value expressions and abstract storage locations.

Also includes an incomplete implementation of serialization/deserialization to a Souffle-datalog-compatible representation,
which originated as a remnant of a previous prototype version that involved the datalog engine in the analysis, but
is retained here because the serialization is useful for producing a human-readable string representation for debugging purposes,
and it may be necessary in future to make these expressions available to the policy engine (which uses datalog).
Deserialization is currently non-functional primarily due to the inability to deserialize scope identity, but may
potentially be revisited in future, so is left here for posterity.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from enum import Enum, auto

from macaron.errors import CallGraphError, ParseError


class Value(abc.ABC):
    """Base class for value expressions.

    Subclasses should be comparable by structural equality.
    """

    @abc.abstractmethod
    def to_datalog_fact_string(self) -> str:
        """Return string representation of expression (in datalog serialized format)."""

    def __str__(self) -> str:
        return self.to_datalog_fact_string()

    def __repr__(self) -> str:
        return self.__str__()


class LocationSpecifier(abc.ABC):
    """Base class for location expressions.

    Subclasses should be comparable by structural equality.
    """

    @abc.abstractmethod
    def to_datalog_fact_string(self) -> str:
        """Return string representation of expression (in datalog serialized format)."""

    def __str__(self) -> str:
        return self.to_datalog_fact_string()

    def __repr__(self) -> str:
        return self.__str__()


# Sequence number to automatically give scopes unique names.
# note: not thread safe
SCOPE_SEQUENCE_NUMBER = 0


class Scope:
    """Representation of a scope in which a location may exist.

    This allows for distinct locations with the same name/path/expression to exist separately in different namespaces.

    A scope may have an outer scope, such that a read from a scope may return values from
    the outer scope(s).

    Unlike other expression classes, scopes are distinguished by object identity and not
    structural equality (TODO now that scopes have names, maybe should revisit this since
    it makes serialization/deserialization difficult).
    """

    #: Name for display purposes.
    identifier: str
    #: Outer scope, if any.
    outer_scope: Scope | None

    def __init__(self, name: str, outer_scope: Scope | None = None) -> None:
        """Initialize scope.

        Parameters
        ----------
        name: str
            Name for display purposes (a sequence number will automatically be appended to make it unique).
        outer_scope: Scope | None
            Outer scope, if any.
        """
        self.outer_scope = outer_scope
        global SCOPE_SEQUENCE_NUMBER  # pylint: disable=global-statement
        self.identifier = str(SCOPE_SEQUENCE_NUMBER) + "_" + name
        SCOPE_SEQUENCE_NUMBER += 1

    def __hash__(self) -> int:
        return id(self)

    def __eq__(self, other: object) -> bool:
        return self is other

    def to_datalog_fact_string(self, include_outer_scope: bool = False) -> str:
        """Return string representation of scope (in datalog serialized format)."""
        return (
            "$Scope("
            + enquote_datalog_string_literal(self.identifier)
            + (
                ", " + self.outer_scope.to_datalog_fact_string()
                if include_outer_scope and self.outer_scope is not None
                else ""
            )
            + ")"
        )

    def __str__(self) -> str:
        return self.to_datalog_fact_string()

    def __repr__(self) -> str:
        return self.__str__()


class ParameterPlaceholderScope(Scope):
    """Special scope placeholder to allow generic parameterized expressions.

    TODO This is not really a proper subclass of Scope, should revisit type relationship.
    """

    #: Parameter name.
    name: str

    def __init__(self, name: str) -> None:  # pylint: disable=super-init-not-called
        """Initialize placeholder scope with given parameter name."""
        self.identifier = "param_" + name
        self.name = name

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, ParameterPlaceholderScope) and other.name == self.name

    def to_datalog_fact_string(self, include_outer_scope: bool = False) -> str:
        """Return string representation of scope (in datalog serialized format)."""
        return "$ParameterPlaceholderScope(" + enquote_datalog_string_literal(self.name) + ")"

    def __str__(self) -> str:
        return self.to_datalog_fact_string()

    def __repr__(self) -> str:
        return self.__str__()


@dataclass(frozen=True, repr=False)
class Location:
    """A location expression qualified with the scope it resides in."""

    #: Scope the location resides in.
    scope: Scope
    #: Location expression.
    loc: LocationSpecifier

    def to_datalog_fact_string(self) -> str:
        """Return string representation of expression (in datalog serialized format)."""
        return "[" + self.scope.to_datalog_fact_string() + ", " + self.loc.to_datalog_fact_string() + "]"

    def __str__(self) -> str:
        return self.to_datalog_fact_string()

    def __repr__(self) -> str:
        return self.__str__()


@dataclass(frozen=True, repr=False)
class StringLiteral(Value):
    """Value expression representing a string literal."""

    #: String literal.
    literal: str

    def to_datalog_fact_string(self) -> str:
        """Return string representation of expression (in datalog serialized format)."""
        return "$StringLiteral(" + enquote_datalog_string_literal(self.literal) + ")"


@dataclass(frozen=True, repr=False)
class Read(Value):
    """Value expression representing a read of the value stored at a location."""

    #: Read value location.
    loc: Location

    def to_datalog_fact_string(self) -> str:
        """Return string representation of expression (in datalog serialized format)."""
        return "$Read(" + self.loc.to_datalog_fact_string() + ")"


@dataclass(frozen=True, repr=False)
class ArbitraryNewData(Value):
    """Value expression representing some arbitrary data."""

    #: Name distiguishing the origin of the data.
    at: str

    def to_datalog_fact_string(self) -> str:
        """Return string representation of expression (in datalog serialized format)."""
        return "$ArbitraryNewData(" + enquote_datalog_string_literal(self.at) + ")"


@dataclass(frozen=True, repr=False)
class InstalledPackage(Value):
    """Value expression representing an installed package, with identifying metadata (name, version, etc.)."""

    #: Package name.
    name: Value
    #: Package version.
    version: Value
    #: Package distribution.
    distribution: Value
    #: URL of the package.
    url: Value

    def to_datalog_fact_string(self) -> str:
        """Return string representation of expression (in datalog serialized format)."""
        return (
            "$InstalledPackage("
            + self.name.to_datalog_fact_string()
            + ", "
            + self.version.to_datalog_fact_string()
            + ", "
            + self.distribution.to_datalog_fact_string()
            + ", "
            + self.url.to_datalog_fact_string()
            + ")"
        )


class UnaryStringOperator(Enum):
    """Unary operators."""

    BASENAME = auto()
    BASE64_ENCODE = auto()
    BASE64DECODE = auto()


def un_op_to_datalog_fact_string(op: UnaryStringOperator) -> str:
    """Return string representation of operator (in datalog serialized format)."""
    if op == UnaryStringOperator.BASENAME:
        return "$BaseName"
    if op == UnaryStringOperator.BASE64_ENCODE:
        return "$Base64Encode"
    if op == UnaryStringOperator.BASE64DECODE:
        return "$Base64Decode"
    raise CallGraphError("unknown UnaryStringOperator")


class BinaryStringOperator(Enum):
    """Binary operators."""

    STRING_CONCAT = auto()


def bin_op_to_datalog_fact_string(op: BinaryStringOperator) -> str:
    """Return string representation of operator (in datalog serialized format)."""
    if op == BinaryStringOperator.STRING_CONCAT:
        return "$StringConcat"
    raise CallGraphError("unknown BinaryStringOperator")


@dataclass(frozen=True, repr=False)
class UnaryStringOp(Value):
    """Value expression representing a unary operator."""

    #: Operator.
    op: UnaryStringOperator
    #: Operand value.
    operand: Value

    def to_datalog_fact_string(self) -> str:
        """Return string representation of expression (in datalog serialized format)."""
        return (
            "$UnaryStringOp("
            + un_op_to_datalog_fact_string(self.op)
            + ", "
            + self.operand.to_datalog_fact_string()
            + ")"
        )


@dataclass(frozen=True, repr=False)
class BinaryStringOp(Value):
    """Value expression representing a binary operator."""

    #: Operator.
    op: BinaryStringOperator
    #: First operand value.
    operand1: Value
    #: Second operand value.
    operand2: Value

    def to_datalog_fact_string(self) -> str:
        """Return string representation of expression (in datalog serialized format)."""
        return (
            "$BinaryStringOp("
            + bin_op_to_datalog_fact_string(self.op)
            + ", "
            + self.operand1.to_datalog_fact_string()
            + ", "
            + self.operand2.to_datalog_fact_string()
            + ")"
        )

    @staticmethod
    def get_string_concat(operand1: Value, operand2: Value) -> Value:
        """Construct a string concatenation operator.

        Applies some simple constant-folding simplifications.
        """
        match operand1, operand2:
            # "a" + "b" = "ab"
            case StringLiteral(op1_lit), StringLiteral(op2_lit):
                return StringLiteral(op1_lit + op2_lit)
            # "" + x = x
            case StringLiteral(""), _:
                return operand2
            # x + "" = x
            case _, StringLiteral(""):
                return operand1
            # (x + "a") + "b" = x + "ab"
            case BinaryStringOp(BinaryStringOperator.STRING_CONCAT, subop1, StringLiteral(subop2_lit)), StringLiteral(
                op2_lit
            ):
                return BinaryStringOp(BinaryStringOperator.STRING_CONCAT, subop1, StringLiteral(subop2_lit + op2_lit))
            # "a" + ("b" + x) = "ab" + x
            case StringLiteral(op1_lit), BinaryStringOp(
                BinaryStringOperator.STRING_CONCAT, StringLiteral(subop1_lit), subop2
            ):
                return BinaryStringOp(BinaryStringOperator.STRING_CONCAT, StringLiteral(op1_lit + subop1_lit), subop2)

        return BinaryStringOp(BinaryStringOperator.STRING_CONCAT, operand1, operand2)


@dataclass(frozen=True, repr=False)
class ParameterPlaceholderValue(Value):
    """Special placeholder value to allow generic parameterized expressions."""

    #: Parameter name.
    name: str

    def to_datalog_fact_string(self) -> str:
        """Return string representation of expression (in datalog serialized format)."""
        return "$ParameterPlaceholderValue(" + enquote_datalog_string_literal(self.name) + ")"


@dataclass(frozen=True, repr=False)
class Symbolic(Value):
    """Value expression representing a symbolic expression.

    Represents an expression that has been "frozen" in symbolic form rather than evaluated concretely.
    """

    #: Symbolic expression.
    val: Value

    def to_datalog_fact_string(self) -> str:
        """Return string representation of expression (in datalog serialized format)."""
        return "$Symbolic(" + self.val.to_datalog_fact_string() + ")"


@dataclass(frozen=True, repr=False)
class SingleBashTokenConstraint(Value):
    """Value expression representing a constraint that the underlying value does not parse as multiple Bash tokens."""

    #: Constrained expression.
    val: Value

    def to_datalog_fact_string(self) -> str:
        """Return string representation of expression (in datalog serialized format)."""
        return "$SingleBashTokenConstraint(" + self.val.to_datalog_fact_string() + ")"


@dataclass(frozen=True, repr=False)
class Filesystem(LocationSpecifier):
    """Location expression representing a filesystem location at a particular file path."""

    #: Filepath value.
    path: Value

    def to_datalog_fact_string(self) -> str:
        """Return string representation of expression (in datalog serialized format)."""
        return "$Filesystem(" + self.path.to_datalog_fact_string() + ")"


@dataclass(frozen=True, repr=False)
class Variable(LocationSpecifier):
    """Location expression representing a variable."""

    #: Variable name.
    name: Value

    def to_datalog_fact_string(self) -> str:
        """Return string representation of expression (in datalog serialized format)."""
        return "$Variable(" + self.name.to_datalog_fact_string() + ")"


@dataclass(frozen=True, repr=False)
class Artifact(LocationSpecifier):
    """Location expression representing a file stored within some named artifact storage location."""

    #: Artifact name.
    name: Value
    #: File name within artifact.
    file: Value

    def to_datalog_fact_string(self) -> str:
        """Return string representation of expression (in datalog serialized format)."""
        return "$Artifact(" + self.name.to_datalog_fact_string() + ", " + self.file.to_datalog_fact_string() + ")"


@dataclass(frozen=True, repr=False)
class FilesystemAnyUnderDir(LocationSpecifier):
    """Location expression representing any file under a particular directory."""

    #: Directory file path.
    path: Value

    def to_datalog_fact_string(self) -> str:
        """Return string representation of expression (in datalog serialized format)."""
        return "$FilesystemAnyUnderDir(" + self.path.to_datalog_fact_string() + ")"


@dataclass(frozen=True, repr=False)
class ArtifactAnyFilename(LocationSpecifier):
    """Location expression representing any file contained with a named artifact storage location."""

    #: Artifact name.
    name: Value

    def to_datalog_fact_string(self) -> str:
        """Return string representation of expression (in datalog serialized format)."""
        return "$ArtifactAnyFilename(" + self.name.to_datalog_fact_string() + ")"


@dataclass(frozen=True, repr=False)
class ParameterPlaceholderLocation(LocationSpecifier):
    """Special placeholder location expression to allow generic parameterized expressions."""

    #: Parameter name.
    name: str

    def to_datalog_fact_string(self) -> str:
        """Return string representation of expression (in datalog serialized format)."""
        return "$ParameterPlaceholderLocation(" + enquote_datalog_string_literal(self.name) + ")"


@dataclass(frozen=True, repr=False)
class Console(LocationSpecifier):
    """Location expression representing a console, pipe or other text stream."""

    def to_datalog_fact_string(self) -> str:
        """Return string representation of expression (in datalog serialized format)."""
        return "$Console"


@dataclass(frozen=True, repr=False)
class Installed(LocationSpecifier):
    """Location expression representing an installed package."""

    #: Package name.
    name: Value

    def to_datalog_fact_string(self) -> str:
        """Return string representation of expression (in datalog serialized format)."""
        return "$Installed(" + self.name.to_datalog_fact_string() + ")"


def enquote_datalog_string_literal(literal: str) -> str:
    """Enquote a datalog string literal, with appropriate escaping."""
    return '"' + literal.replace("\\", "\\\\").replace('"', '\\"') + '"'


class FactParseError(Exception):
    """Happens when an error occurs during fact parsing."""


def consume_whitespace(text: str) -> str:
    """Consume leading whitespace, returning the remainder to the text."""
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
    """Consume the leading token from the text.

    Raises exception if text does not start with the token.
    """
    if text.startswith(token):
        return text[len(token) :]
    raise FactParseError(text)


def parse_qualified_name(text: str) -> tuple[str, str]:
    """Parse a qualified name, returning the name and the remainder of the text."""
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


def parse_symbol(text: str) -> tuple[str, str]:
    """Parse datalog-serialized string literal."""
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
            char_list.append('"')
            in_escape = False
        else:
            char_list.append(text[idx])
        idx = idx + 1

    lit = "".join(char_list)
    text = text[str_end_idx:]
    text = consume(text, '"')
    return lit, text


def parse_location_specifier(text: str) -> tuple[LocationSpecifier, str]:
    """Deserialize location specifier from string representation (in datalog serialized format)."""
    text = consume(text, "$")
    kind, text = parse_qualified_name(text)
    match kind:
        case "Filesystem":
            text = consume(text, "(")
            path_val, text = parse_value(text)
            text = consume_whitespace(text)
            text = consume(text, ")")
            return Filesystem(path_val), text
        case "Variable":
            text = consume(text, "(")
            name_val, text = parse_value(text)
            text = consume_whitespace(text)
            text = consume(text, ")")
            return Variable(name_val), text
        case "Artifact":
            text = consume(text, "(")
            name_val, text = parse_value(text)
            text = consume(text, ",")
            text = consume_whitespace(text)
            file_val, text = parse_value(text)
            text = consume(text, ")")
            return Artifact(name_val, file_val), text
        case "FilesystemAnyUnderDir":
            text = consume(text, "(")
            path_val, text = parse_value(text)
            text = consume_whitespace(text)
            text = consume(text, ")")
            return FilesystemAnyUnderDir(path_val), text
        case "ArtifactAnyFilename":
            text = consume(text, "(")
            name_val, text = parse_value(text)
            text = consume_whitespace(text)
            text = consume(text, ")")
            return ArtifactAnyFilename(name_val), text
        case "Console":
            return Console(), text
        case "Installed":
            text = consume(text, "(")
            name_val, text = parse_value(text)
            text = consume_whitespace(text)
            text = consume(text, ")")
            return Installed(name_val), text

    raise FactParseError()


def parse_location(text: str) -> tuple[Location, str]:
    """Deserialize location from string representation (in datalog serialized format).

    Currently non-functional primarily due to the inability to deserialize scope identity.
    """
    raise ParseError("cannot parse, need fix")


def parse_value(text: str) -> tuple[Value, str]:
    """Deserialize value expression from string representation (in datalog serialized format)."""
    text = consume(text, "$")
    kind, text = parse_qualified_name(text)
    match kind:
        case "StringLiteral":
            text = consume(text, "(")
            lit, text = parse_symbol(text)
            text = consume_whitespace(text)
            text = consume(text, ")")
            return StringLiteral(lit), text
        case "Read":
            text = consume(text, "(")
            loc, text = parse_location(text)
            text = consume_whitespace(text)
            text = consume(text, ")")
            return Read(loc), text
        case "ArbitraryNewData":
            text = consume(text, "(")
            at, text = parse_symbol(text)
            text = consume_whitespace(text)
            text = consume(text, ")")
            return ArbitraryNewData(at), text
        case "UnaryStringOp":
            text = consume(text, "(")
            un_operator, text = parse_un_op(text)
            text = consume(text, ",")
            text = consume_whitespace(text)
            operand_val, text = parse_value(text)
            text = consume(text, ")")
            return UnaryStringOp(un_operator, operand_val), text
        case "BinaryStringOp":
            text = consume(text, "(")
            bin_operator, text = parse_bin_op(text)
            text = consume(text, ",")
            text = consume_whitespace(text)
            operand1, text = parse_value(text)
            text = consume(text, ",")
            text = consume_whitespace(text)
            operand2, text = parse_value(text)
            text = consume(text, ")")
            return BinaryStringOp(bin_operator, operand1, operand2), text
        case "ParameterPlaceholderValue":
            text = consume(text, "(")
            name, text = parse_symbol(text)
            text = consume_whitespace(text)
            text = consume(text, ")")
            return ParameterPlaceholderValue(name), text
        case "SingleBashTokenConstraint":
            text = consume(text, "(")
            operand, text = parse_value(text)
            text = consume(text, ")")
            return SingleBashTokenConstraint(operand), text
        case "InstalledPackage":
            text = consume(text, "(")
            name_val, text = parse_value(text)
            text = consume(text, ",")
            text = consume_whitespace(text)
            version_val, text = parse_value(text)
            text = consume(text, ",")
            text = consume_whitespace(text)
            distribution_val, text = parse_value(text)
            text = consume(text, ",")
            text = consume_whitespace(text)
            url_val, text = parse_value(text)
            text = consume(text, ")")
            return InstalledPackage(name_val, version_val, distribution_val, url_val), text
    raise FactParseError()


def parse_un_op(text: str) -> tuple[UnaryStringOperator, str]:
    """Deserialize unary operator from string representation (in datalog serialized format)."""
    text = consume(text, "$")
    name, text = parse_qualified_name(text)
    match name:
        case "BaseName":
            return UnaryStringOperator.BASENAME, text
        case "Base64Encode":
            return UnaryStringOperator.BASE64_ENCODE, text
        case "Base64Decode":
            return UnaryStringOperator.BASE64DECODE, text
    raise FactParseError()


def parse_bin_op(text: str) -> tuple[BinaryStringOperator, str]:
    """Deserialize binary operator from string representation (in datalog serialized format)."""
    text = consume(text, "$")
    name, text = parse_qualified_name(text)
    match name:
        case "StringConcat":
            return BinaryStringOperator.STRING_CONCAT, text
    raise FactParseError()
