# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Test the Souffle wrapper."""

import os
from pathlib import Path

from macaron.policy_engine.souffle import SouffleError, SouffleWrapper

FACT_DIR = Path(__file__).parent.joinpath("resources").joinpath("facts")
# Test from https://souffle-lang.github.io/simple
TEXT = """.decl edge(x:number, y:number)
.input edge

.decl path(x:number, y:number)
.output path

path(x, y) :- edge(x, y).
path(x, y) :- path(x, z), edge(z, y).
"""


def test_interpret_file() -> None:
    """Test basic call to interpreting a file."""
    with SouffleWrapper(fact_dir=str(FACT_DIR)) as sfl:
        result = sfl.interpret_file(os.path.join(FACT_DIR, "test.dl"), with_prelude=".output edge")
        assert result == {"edge": [["1", "2"], ["2", "3"]], "path": [["1", "2"], ["1", "3"], ["2", "3"]]}


def test_interpret_text() -> None:
    """Test basic call to interpreting a string literal"""
    with SouffleWrapper(fact_dir=str(FACT_DIR)) as sfl:
        result = sfl.interpret_text(TEXT)
        assert result == {"path": [["1", "2"], ["1", "3"], ["2", "3"]]}


def test_error() -> None:
    """Test throwing an error on an invalid souffle program."""
    try:
        with SouffleWrapper() as sfl:
            sfl.interpret_text(".input edge")
    except SouffleError:
        return
    raise ValueError()


def test_consecutive() -> None:
    """
    Test running different programs in the same context.

    We expect the output to accumulate; the output files are
    attached to the context.
    """
    with SouffleWrapper(fact_dir=str(FACT_DIR)) as sfl:
        result = sfl.interpret_file(os.path.join(FACT_DIR, "test.dl"), with_prelude=".output edge")
        assert result == {"edge": [["1", "2"], ["2", "3"]], "path": [["1", "2"], ["1", "3"], ["2", "3"]]}

        result = sfl.interpret_text(TEXT)
        assert result["path"] == [["1", "2"], ["1", "3"], ["2", "3"]]

        result = sfl.interpret_file(os.path.join(FACT_DIR, "test.dl"), with_prelude=".output edge")
        assert result == {"edge": [["1", "2"], ["2", "3"]], "path": [["1", "2"], ["1", "3"], ["2", "3"]]}

        try:
            with SouffleWrapper() as sfl:
                sfl.interpret_text(".input edge")
        except SouffleError:
            return
        raise ValueError()

        ## sfl is terminated after here
