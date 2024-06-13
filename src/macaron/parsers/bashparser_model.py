# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https:#oss.oracle.com/licenses/upl/.

# Type definitions for Bash AST as produced (and json-serialised) by the "mvdan.cc/sh/v3/syntax" bash parser

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, NotRequired, Optional, TypedDict, TypeGuard, Union

class Pos(TypedDict):
    Offset: int
    Line: int
    Col: int

class Comment(TypedDict):
    Hash: Pos
    Text: str

WordPart = Union[
    "Lit", "SglQuoted", "DblQuoted", "ParamExp", "CmdSubst", "ArithmExp", "ProcSubst", "ExtGlob", "BraceExp"
]

ArithmExpr = Union["BinaryArithm", "UnaryArithm", "ParenArithm", "Word"]

UnAritOperator = int


class UnAritOperators(Enum):
    Not = 34  # !
    BitNegation = 35  # ~
    Inc = 36  # ++
    Dec = 37  # --
    Plus = 68  # +
    Minus = 70  # -


class UnaryArithm(TypedDict):
    Type: Literal['UnaryArithm']
    Pos: Pos
    End: Pos
    OpPos: Pos
    Op: UnAritOperator
    Post: NotRequired[bool]
    X: ArithmExpr


def is_unary_arithm(expr: ArithmExpr) -> TypeGuard[UnaryArithm]:
    return "Type" in expr and expr["Type"] == "UnaryArithm"


BinAritOperator = int


class BinAritOperators(Enum):
    Add = 68  # +
    Sub = 70  # -
    Mul = 38  # *
    Quo = 85  # /
    Rem = 76  # %
    Pow = 39  # **
    Eql = 40  # ==
    Gtr = 54  # >
    Lss = 56  # <
    Neq = 41  # !=
    Leq = 42  # <=
    Geq = 43  # >=
    And = 9  # &
    Or = 12  # |
    Xor = 80  # ^
    Shr = 55  # >>
    Shl = 61  # <<

    AndArit = 10  # &&
    OrArit = 11  # ||
    Comma = 82  # ,
    TernQuest = 72  # ?
    TernColon = 87  # :

    Assgn = 74  # =
    AddAssgn = 44  # +=
    SubAssgn = 45  # -=
    MulAssgn = 46  # *=
    QuoAssgn = 47  # /=
    RemAssgn = 48  # %=
    AndAssgn = 49  # &=
    OrAssgn = 50  # |=
    XorAssgn = 51  # ^=
    ShlAssgn = 52  # <<=
    ShrAssgn = 53  # >>=


class BinaryArithm(TypedDict):
    Type: Literal['BinaryArithm']
    Pos: Pos
    End: Pos
    OpPos: Pos
    Op: BinAritOperator
    X: ArithmExpr
    Y: ArithmExpr


def is_binary_arithm(expr: ArithmExpr) -> TypeGuard[BinaryArithm]:
    return "Type" in expr and expr["Type"] == "BinaryArithm"


class ParenArithm(TypedDict):
    Type: Literal['ParenArithm']
    Pos: Pos
    End: Pos
    Lparen: Pos
    Rparen: Pos
    X: ArithmExpr


def is_paren_arithm(expr: ArithmExpr) -> TypeGuard[ParenArithm]:
    return "Type" in expr and expr["Type"] == "ParenArithm"


def is_word_arithm(expr: ArithmExpr) -> TypeGuard[Word]:
    return "Type" not in expr


class Lit(TypedDict):
    Type: Literal['Lit']
    Pos: Pos
    End: Pos
    ValuePos: Pos
    ValueEnd: Pos
    Value: str


def is_lit(part: WordPart) -> TypeGuard[Lit]:
    return part["Type"] == "Lit"


class SglQuoted(TypedDict):
    Type: Literal['SglQuoted']
    Pos: Pos
    End: Pos
    Left: Pos
    Right: Pos
    Dollar: NotRequired[bool]
    Value: str


def is_sgl_quoted(part: WordPart) -> TypeGuard[SglQuoted]:
    return part["Type"] == "SglQuoted"


class DblQuoted(TypedDict):
    Type: Literal['DblQuoted']
    Pos: Pos
    End: Pos
    Left: Pos
    Right: Pos
    Dollar: NotRequired[bool]
    Parts: list[WordPart]


def is_dbl_quoted(part: WordPart) -> TypeGuard[DblQuoted]:
    return part["Type"] == "DblQuoted"


class Slice(TypedDict):
    Offset: ArithmExpr
    Length: ArithmExpr

class Replace(TypedDict):
    All: NotRequired[bool]
    Orig: 'Word'
    With: 'Word'

ParNamesOperator = int


class ParNamesOperators(Enum):
    NamesPrefix = 38  # *
    NamesPrefixWords = 84  # @


ParExpOperator = int


class ParExpOperators(Enum):
    AlternateUnset = 68  # +
    AlternateUnsetOrNull = 69  # :+
    DefaultUnset = 70  # -
    DefaultUnsetOrNull = 71  # :-
    ErrorUnset = 72  # ?
    ErrorUnsetOrNull = 73  # :?
    AssignUnset = 74  # =
    AssignUnsetOrNull = 75  # :=
    RemSmallSuffix = 76  # %
    RemLargeSuffix = 77  # %%
    RemSmallPrefix = 78  # #
    RemLargePrefix = 79  # ##
    UpperFirst = 80  # ^
    UpperAll = 81  # ^^
    LowerFirst = 82  # ,
    LowerAll = 83  # ,,
    OtherParamOps = 84  # @


class Expansion(TypedDict):
    Op: ParExpOperator
    Word: 'Word'

class ParamExp(TypedDict):
    Type: Literal['ParamExp']
    Pos: Pos
    End: Pos
    Dollar: NotRequired[Pos]
    Rbrace: NotRequired[Pos]
    Short: NotRequired[bool]
    Excl: NotRequired[bool]
    Length: NotRequired[bool]
    Width: NotRequired[bool]
    Param: Lit
    Index: NotRequired[ArithmExpr]
    Slice: NotRequired[Slice]
    Repl: NotRequired[Replace]
    Names: NotRequired[ParNamesOperator]
    Exp: NotRequired[Expansion]


def is_param_exp(part: WordPart) -> TypeGuard[ParamExp]:
    return part["Type"] == "ParamExp"


class CmdSubst(TypedDict):
    Type: Literal['CmdSubst']
    Pos: Pos
    End: Pos
    Left: Pos
    Right: Pos
    Stmts: list['Stmt']
    Last: NotRequired[list[Comment]]
    Backquotes: NotRequired[bool]
    TempFile: NotRequired[bool]
    ReplyVar: NotRequired[bool]


def is_cmd_subst(part: WordPart) -> TypeGuard[CmdSubst]:
    return part["Type"] == "CmdSubst"


class ArithmExp(TypedDict):
    Type: Literal['ArithmExp']
    Pos: Pos
    End: Pos
    Left: Pos
    Right: Pos
    Bracket: NotRequired[bool]
    Unsigned: NotRequired[bool]
    X: ArithmExpr


def is_arithm_exp(part: WordPart) -> TypeGuard[ArithmExp]:
    return part["Type"] == "ArithmExp"


ProcOperator = int


class ProcOperators(Enum):
    CmdIn = 66  # <(
    CmdOut = 67  # >(


class ProcSubst(TypedDict):
    Type: Literal['ProcSubst']
    Pos: Pos
    End: Pos
    OpPos: Pos
    Rparen: Pos
    Op: ProcOperator
    Stmts: list['Stmt']
    Last: NotRequired[list[Comment]]


def is_proc_subst(part: WordPart) -> TypeGuard[ProcSubst]:
    return part["Type"] == "ProcSubst"


GlobOperator = int


class GlobOperators(Enum):
    GlobZeroOrOne = 122  # ?(
    GlobZeroOrMore = 123  # *(
    GlobOneOrMore = 124  # +(
    GlobOne = 125  # @(
    GlobExcept = 126  # !(


class ExtGlob(TypedDict):
    Type: Literal['ExtGlob']
    Pos: Pos
    End: Pos
    OpPos: Pos
    Op: GlobOperator
    Pattern: Lit


def is_ext_glob(part: WordPart) -> TypeGuard[ExtGlob]:
    return part["Type"] == "ExtGlob"


class BraceExp(TypedDict):
    Type: Literal['BraceExp']
    Pos: Pos
    End: Pos
    Sequence: NotRequired[bool]
    Elems: list['Word']


def is_brace_exp(part: WordPart) -> TypeGuard[BraceExp]:
    return part["Type"] == "BraceExp"


class Word(TypedDict):
    Parts: list[WordPart]

RedirOperator = int


class RedirOperators(Enum):
    RdrOut = 54  # >
    AppOut = 55  # >>
    RdrIn = 56  # <
    RdrInOut = 57  # <>
    DplIn = 58  # <&
    DplOut = 59  # >&
    ClbOut = 60  # >|
    Hdoc = 61  # <<
    DashHdoc = 62  # <<-
    WordHdoc = 63  # <<<
    RdrAll = 64  # &>
    AppAll = 65  # &>>


class Redirect(TypedDict):
    Pos: Pos
    End: Pos
    OpPos: Pos
    Op: RedirOperator
    N: NotRequired[Lit]
    Word: NotRequired[Word]
    Hdoc: NotRequired[Word]

class ArrayElem(TypedDict):
    Pos: Pos
    End: Pos
    Index: NotRequired[ArithmExpr]
    Value: NotRequired[Word]
    Comments: NotRequired[list[Comment]]

class ArrayExpr(TypedDict):
    Pos: Pos
    End: Pos
    Lparent: Pos
    Rparen: Pos
    Elems: list[ArrayElem]
    Last: NotRequired[list[Comment]]

class Assign(TypedDict):
    Pos: Pos
    End: Pos
    Append: NotRequired[bool]
    Naked: NotRequired[bool]
    Name: Lit
    Index: NotRequired[ArithmExpr]
    Value: NotRequired[Word]
    Array: NotRequired[ArrayExpr]

Command = Union[
    "CallExpr",
    "IfClause",
    "WhileClause",
    "ForClause",
    "CaseClause",
    "Block",
    "Subshell",
    "BinaryCmd",
    "FuncDecl",
    "ArithmCmd",
    "TestClause",
    "DeclClause",
    "LetClause",
    "TimeClause",
    "CoprocClause",
    "TestDecl",
]

class CallExpr(TypedDict):
    Type: Literal['CallExpr']
    Pos: Pos
    End: Pos
    Assigns: NotRequired[list[Assign]]
    Args: NotRequired[list[Word]]


def is_call_expr(cmd: Command) -> TypeGuard[CallExpr]:
    return cmd["Type"] == "CallExpr"


class IfClause(TypedDict):
    Type: Literal['IfClause']
    Pos: Pos
    End: Pos
    Position: Pos
    ThenPos: NotRequired[Pos]
    FiPos: NotRequired[Pos]
    Cond: list['Stmt']
    CondLast: NotRequired[list[Comment]]
    Then: list['Stmt']
    ThenLast: NotRequired[list[Comment]]
    Else: NotRequired['IfClause']
    Last: NotRequired[list[Comment]]


def is_if_clause(cmd: Command) -> TypeGuard[IfClause]:
    return cmd["Type"] == "IfClause"


class WhileClause(TypedDict):
    Type: Literal['WhileClause']
    Pos: Pos
    End: Pos
    WhilePos: Pos
    DoPos: Pos
    DonePos: Pos
    Cond: list['Stmt']
    CondLast: NotRequired[list[Comment]]
    Do: list['Stmt']
    DoLast: NotRequired[list[Comment]]


def is_while_clause(cmd: Command) -> TypeGuard[WhileClause]:
    return cmd["Type"] == "WhileClause"


Loop = Union["WordIter", "CStyleLoop"]

class WordIter(TypedDict):
    Type: Literal['WordIter']
    Pos: Pos
    End: Pos
    Name: Lit
    InPos: Pos
    Items: list[Word]


def is_word_iter(loop: Loop) -> TypeGuard[WordIter]:
    return loop["Type"] == "WordIter"


class CStyleLoop(TypedDict):
    Type: Literal['CStyleLoop']
    Pos: Pos
    End: Pos
    Lparen: Pos
    Rparen: Pos
    Init: NotRequired[ArithmExpr]
    Cond: NotRequired[ArithmExpr]
    Post: NotRequired[ArithmExpr]


def is_cstyle_loop(loop: Loop) -> TypeGuard[CStyleLoop]:
    return loop["Type"] == "CStyleLoop"


class ForClause(TypedDict):
    Type: Literal['ForClause']
    Pos: Pos
    End: Pos
    ForPos: Pos
    DoPos: Pos
    DonePos: Pos
    Select: NotRequired[bool]
    Braces: NotRequired[bool]
    Loop: Loop
    Do: list['Stmt']
    DoLast: NotRequired[list[Comment]]


def is_for_clause(cmd: Command) -> TypeGuard[ForClause]:
    return cmd["Type"] == "ForClause"


CaseOperator = int


class CaseOperators(Enum):
    Break = 30  # ;;
    Fallthrough = 31  # ;&
    Resume = 32  # ;;&
    ResumeKorn = 33  # ;|


class CaseItem(TypedDict):
    Pos: Pos
    End: Pos
    Op: CaseOperator
    OpPos: Pos
    Comments: NotRequired[list[Comment]]
    Patterns: list[Word]
    Stmts: list['Stmt']
    Last: NotRequired[list[Comment]]

class CaseClause(TypedDict):
    Type: Literal['CaseClause']
    Pos: Pos
    End: Pos
    Case: Pos
    In: Pos
    Esac: Pos
    Braces: NotRequired[bool]
    Word: Word
    Items: list[CaseItem]
    Last: NotRequired[list[Comment]]


def is_case_clause(cmd: Command) -> TypeGuard[CaseClause]:
    return cmd["Type"] == "CaseClause"


class Block(TypedDict):
    Type: Literal['Block']
    Pos: Pos
    End: Pos
    Lbrace: Pos
    Rbrace: Pos
    Stmts: list['Stmt']
    Last: NotRequired[list[Comment]]


def is_block(cmd: Command) -> TypeGuard[Block]:
    return cmd["Type"] == "Block"


class Subshell(TypedDict):
    Type: Literal['Subshell']
    Pos: Pos
    End: Pos
    Lparen: Pos
    Rparen: Pos
    Stmts: list['Stmt']
    Last: NotRequired[list[Comment]]


def is_subshell(cmd: Command) -> TypeGuard[Subshell]:
    return cmd["Type"] == "Subshell"


BinCmdOperator = int


class BinCmdOperators(Enum):
    AndStmt = 10  # &&
    OrStmt = 11  # ||
    Pipe = 12  # |
    PipeAll = 13  # |&


class BinaryCmd(TypedDict):
    Type: Literal['BinaryCmd']
    Pos: Pos
    End: Pos
    OpPos: Pos
    Op: BinCmdOperator
    X: 'Stmt'
    Y: 'Stmt'


def is_binary_cmd(cmd: Command) -> TypeGuard[BinaryCmd]:
    return cmd["Type"] == "BinaryCmd"


class FuncDecl(TypedDict):
    Type: Literal['FuncDecl']
    Pos: Pos
    End: Pos
    Position: Pos
    RsrvWord: NotRequired[bool]
    Parens: NotRequired[bool]
    Name: Lit
    Body: 'Stmt'


def is_func_decl(cmd: Command) -> TypeGuard[FuncDecl]:
    return cmd["Type"] == "FuncDecl"


class ArithmCmd(TypedDict):
    Type: Literal['ArithmCmd']
    Pos: Pos
    End: Pos
    Left: Pos
    Right: Pos
    Unsigned: NotRequired[bool]
    X: ArithmExpr


def is_arithm_cmd(cmd: Command) -> TypeGuard[ArithmCmd]:
    return cmd["Type"] == "ArithmCmd"


TestExpr = Union["BinaryTest", "UnaryTest", "ParenTest", "Word"]

BinTestOperator = int


class BinTestOperators(Enum):
    TsReMatch = 112  # =~
    TsNewer = 113  # -nt
    TsOlder = 114  # -ot
    TsDevIno = 115  # -ef
    TsEql = 116  # -eq
    TsNeq = 117  # -ne
    TsLeq = 118  # -le
    TsGeq = 119  # -ge
    TsLss = 120  # -lt
    TsGtr = 121  # -gt
    AndTest = 10  # &&
    OrTest = 11  # ||
    TsMatchShort = 74  # =
    TsMatch = 40  # ==
    TsNoMatch = 41  # !=
    TsBefore = 56  # <
    TsAfter = 54  # >


class BinaryTest(TypedDict):
    Type: Literal['BinaryTest']
    Pos: Pos
    End: Pos
    OpPos: Pos
    Op: BinTestOperator
    X: TestExpr
    Y: TestExpr


def is_binary_test(test_expr: TestExpr) -> TypeGuard[BinaryTest]:
    return "Type" in test_expr and test_expr["Type"] == "BinaryTest"


UnTestOperator = int


class UnTestOperators(Enum):
    TsExists = 88  # -e
    TsRegFile = 89  # -f
    TsDirect = 90  # -d
    TsCharSp = 91  # -c
    TsBlckSp = 92  # -b
    TsNmPipe = 93  # -p
    TsSocket = 94  # -S
    TsSmbLink = 95  # -L
    TsSticky = 96  # -k
    TsGIDSet = 97  # -g
    TsUIDSet = 98  # -u
    TsGrpOwn = 99  # -G
    TsUsrOwn = 100  # -O
    TsModif = 101  # -N
    TsRead = 102  # -r
    TsWrite = 103  # -w
    TsExec = 104  # -x
    TsNoEmpty = 105  # -s
    TsFdTerm = 106  # -t
    TsEmpStr = 107  # -z
    TsNempStr = 108  # -n
    TsOptSet = 109  # -o
    TsVarSet = 110  # -v
    TsRefVar = 111  # -R
    TsNot = 34  # !


class UnaryTest(TypedDict):
    Type: Literal['UnaryTest']
    Pos: Pos
    End: Pos
    OpPos: Pos
    Op: UnTestOperator
    X: TestExpr


def is_unary_test(test_expr: TestExpr) -> TypeGuard[UnaryTest]:
    return "Type" in test_expr and test_expr["Type"] == "UnaryTest"


class ParenTest(TypedDict):
    Type: Literal['ParenTest']
    Pos: Pos
    End: Pos
    Lparen: Pos
    Rparen: Pos
    X: TestExpr


def is_paren_test(test_expr: TestExpr) -> TypeGuard[ParenTest]:
    return "Type" in test_expr and test_expr["Type"] == "ParenTest"


def is_word_test(test_expr: TestExpr) -> TypeGuard[Word]:
    return "Type" not in test_expr


class TestClause(TypedDict):
    Type: Literal['TestClause']
    Pos: Pos
    End: Pos
    Left: Pos
    Right: Pos
    X: TestExpr


def is_test_clause(cmd: Command) -> TypeGuard[TestClause]:
    return cmd["Type"] == "TestClause"


class DeclClause(TypedDict):
    Type: Literal['DeclClause']
    Pos: Pos
    End: Pos
    Variant: Lit
    Args: list[Assign]


def is_decl_clause(cmd: Command) -> TypeGuard[DeclClause]:
    return cmd["Type"] == "DeclClause"


class LetClause(TypedDict):
    Type: Literal['LetClause']
    Pos: Pos
    End: Pos
    Let: Pos
    Exprs: list[ArithmExpr]


def is_let_clause(cmd: Command) -> TypeGuard[LetClause]:
    return cmd["Type"] == "LetClause"


class TimeClause(TypedDict):
    Type: Literal['TimeClause']
    Pos: Pos
    End: Pos
    Time: Pos
    PosixFormat: NotRequired[bool]
    Stmt: 'Stmt'


def is_time_clause(cmd: Command) -> TypeGuard[TimeClause]:
    return cmd["Type"] == "TimeClause"


class CoprocClause(TypedDict):
    Type: Literal['CoprocClause']
    Pos: Pos
    End: Pos
    Coproc: Pos
    Name: Word
    Stmt: 'Stmt'


def is_coproc_clause(cmd: Command) -> TypeGuard[CoprocClause]:
    return cmd["Type"] == "CoprocClause"


class TestDecl(TypedDict):
    Type: Literal['TestDecl']
    Pos: Pos
    End: Pos
    Position: Pos
    Description: Word
    Body: 'Stmt'


def is_test_decl(cmd: Command) -> TypeGuard[TestDecl]:
    return cmd["Type"] == "TestDecl"


class Stmt(TypedDict):
    Comments: NotRequired[list[Comment]]
    Cmd: Command
    Pos: Pos
    End: Pos
    Position: Pos
    Semicolon: NotRequired[Pos]
    Negated: NotRequired[bool]
    Background: NotRequired[bool]
    Coprocess: NotRequired[bool]
    Redirs: NotRequired[list[Redirect]]

class File(TypedDict):
    Type: Literal['File']
    Name: NotRequired[str]
    Pos: Pos
    End: Pos
    Stmts: list[Stmt]
    Last: NotRequired[list[Comment]]
