# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
Wrapper classes for invoking souffle by subprocess and getting the resulting tables.

Implements a context manager to create and clean up temporary directories.

Example
-------
with SouffleWrapper(fact_dir="facts", output_dir="output") as sfl:
    text = "<souffle program>"
    result = sfl.interpret_text(text)
    assert result == {"path": [["1", "2"], ["1", "3"], ["2", "3"]]}

    new_result = sfl.interpret_file("filename", with_prelude="<souffle snippet>")

"""

import csv
import glob
import logging
import os
import shutil
import subprocess  # nosec B404
import tempfile
from types import TracebackType
from typing import Optional

logger: logging.Logger = logging.getLogger(__name__)


class SouffleError(Exception):
    """An exception occurring with the call to souffle."""

    def __init__(
        self, command: Optional[list[str] | str] = None, message: str = "An error occurred with calling Souffle."
    ):
        self.message = message
        self.command = command
        super().__init__(self.message)


class SouffleWrapper:
    """Wrapper class for managing the temporary working directory of the souffle interpreter."""

    _souffle: str
    output_dir: str
    include_dir: str
    fact_dir: str
    library_dir: str
    TEMP_SOURCEFILE_NAME = "source.dl"

    def __init__(
        self,
        souffle_full_path: str = "souffle",
        output_dir: Optional[str] = None,
        include_dir: str = os.curdir,
        fact_dir: str = os.curdir,
        library_dir: str = os.curdir,
    ):
        self.temp_dir = tempfile.mkdtemp()
        self.orig_dir = os.path.abspath(os.curdir)
        self._souffle = souffle_full_path
        if output_dir is not None:
            self.output_dir = os.path.abspath(output_dir)
        else:
            self.output_dir = os.path.join(self.temp_dir, "output")
            os.mkdir(self.output_dir)

        self.include_dir = os.path.abspath(include_dir)
        self.fact_dir = os.path.abspath(fact_dir)
        self.library_dir = os.path.abspath(library_dir)

    def _invoke_souffle(self, source_file: str, additional_args: Optional[list[str]] = None) -> None:
        additional_args = [] if additional_args is None else additional_args
        cmd = [
            self._souffle,
            source_file,
            f"--include-dir={self.include_dir}",
            f"--output-dir={self.output_dir}",
            f"--fact-dir={self.fact_dir}",
            f"--library-dir={self.library_dir}",
        ] + additional_args
        logger.info("Executing souffle: %s", " ".join(cmd))
        result = subprocess.run(cmd, shell=False, capture_output=True, cwd=self.temp_dir, check=False)  # nosec B603
        # Souffle doesn't exit with non-zero when the datalog program contains errors, but check anyway
        if result.returncode != 0 or len(result.stderr) > 0:
            raise SouffleError(message=str(result.stderr), command=cmd)

    def interpret_file(self, filename: str, with_prelude: str = "") -> dict:
        """
        Interpret a file.

        Parameters
        ----------
            filename: str the file to run
            with_prelude: str string literal to append to the start of the file before running it
        """
        with open(filename, encoding="utf-8") as file:
            text = file.read()
            return self.interpret_text(text + with_prelude)

    def interpret_text(self, text: str) -> dict:
        """
        Interpret a string literal.

        Parameters
        ----------
            text: str string literal to interpret
        """
        source_file = os.path.join(self.temp_dir, self.TEMP_SOURCEFILE_NAME)

        with open(source_file, "w", encoding="utf-8") as file:
            file.write(text)

        self._invoke_souffle(source_file)
        output = self.load_csv_output()
        return output

    def load_csv_output(self) -> dict:
        """Load and return all the csv files from the temporary working directory."""
        result: dict = {}
        for file_name in glob.glob("*.csv", root_dir=self.output_dir):
            with open(os.path.join(self.output_dir, file_name), encoding="utf-8") as file:
                reader = csv.reader(file.readlines(), delimiter="\t")
                result[file_name[0 : file_name.rfind(".")]] = list(reader)
        return result

    def __enter__(self) -> "SouffleWrapper":
        return self

    def __exit__(
        self, exc_type: Optional[type[BaseException]], exc_val: Optional[BaseException], exc_tb: Optional[TracebackType]
    ) -> None:
        self._cleanup()

    def _cleanup(self) -> None:
        shutil.rmtree(self.temp_dir)
