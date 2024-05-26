# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This analyzer checks the suspicious pattern within setup.py."""

import ast
import logging
import os
import re
import shutil
import tarfile
import tempfile
import zipfile

import requests

from macaron.slsa_analyzer.checks.check_result import Confidence
from macaron.slsa_analyzer.package_registry.pypi_registry import PyPIApiClient
from macaron.slsa_analyzer.pypi_heuristics.analysis_result import RESULT
from macaron.slsa_analyzer.pypi_heuristics.base_analyzer import BaseAnalyzer
from macaron.slsa_analyzer.pypi_heuristics.heuristics import HEURISTIC

logger: logging.Logger = logging.getLogger(__name__)


class SuspiciousSetupAnalyzer(BaseAnalyzer):
    """Analyzer checks heuristic."""

    def __init__(self, api_client: PyPIApiClient) -> None:
        super().__init__(name="suspicious_setup_analyzer", heuristic=HEURISTIC.SUSPICIOUS_SETUP)
        self.blacklist: list = ["base64", "request"]
        self.api_client = api_client

    def _get_setup_source_code(self) -> str | None:
        """Get the source code in setup.py.

        Parameters
        ----------
            package_name (str): PyPI package's name
            version (str): The version of the package
            destination_dir (str): The location of the tmp

        Returns
        -------
            str | None: Source code.
        """
        # Create a temporary directory to store the downloaded source
        temp_dir = tempfile.mkdtemp()

        try:
            sourcecode_url = self.api_client.get_sourcecode_url()
            if sourcecode_url is None:
                return None
            response = requests.get(sourcecode_url, stream=True, timeout=40)
            response.raise_for_status()
            filename = sourcecode_url.split("/")[-1]
            with open(os.path.join(temp_dir, filename), "wb") as f:
                f.write(response.content)

            files = os.listdir(temp_dir)
            try:
                with tarfile.open(os.path.join(temp_dir, files[0]), "r:gz") as tar:
                    tar.extractall(temp_dir)  # nosec B202
            except tarfile.ReadError as exception:
                # Handle the ReadError
                logger.debug("Error reading tar file: %s", exception)

                try:
                    # Open the zip file
                    with zipfile.ZipFile(os.path.join(temp_dir, files[0]), "r") as zip_ref:
                        # Extract all contents of the zip file
                        zip_ref.extractall(temp_dir)  # nosec B202
                except zipfile.BadZipFile as bad_zip_exception:
                    # Handle the BadZipFile exception
                    logger.debug("Error reading zip file: %s", bad_zip_exception)
                    # You can add more specific handling if needed
                except zipfile.LargeZipFile as large_zip_exception:
                    # Handle the LargeZipFile exception
                    logger.debug("Zip file too large to read: %s", large_zip_exception)

            for root, _, files in os.walk(temp_dir):
                for file in files:
                    if file == "setup.py":
                        file_path = os.path.join(root, file)
                        with open(file_path, encoding="utf-8") as py_file:
                            return py_file.read()
            return None
        finally:
            # Clean up the temporary directory
            shutil.rmtree(temp_dir)

    def analyze(self) -> tuple[RESULT, Confidence | None]:
        """Analyze suspicious packages are imported in setup.py.

        Returns
        -------
            tuple[RESULT, Confidence | None]: Result and confidence.
        """
        content: str | None = self._get_setup_source_code()
        if content is None:
            return RESULT.SKIP, None

        imports = set()
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.add(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module
                    if node.level > 0 and module:
                        _module = "." * node.level + module
                        for alias in node.names:
                            if alias.name:
                                import_name = _module + "." + alias.name
                                imports.add(import_name)
        except SyntaxError:
            pattern = r"^\s*import\s+(\w+)(?:\s+as\s+\w+)?(?:\s*,\s*\w+)*\s*$|^\s*from\s+(\w+)\s+import\s+\w+ \
            (?:\s+as\s+\w+)?(?:\s*,\s*\w+(?:\s+as\s+\w+)?)*\s*$"
            for line in content.splitlines():
                match = re.match(pattern, line)
                if match:
                    imports.update(filter(None, match.groups()))
        suspicious_setup = any(suspicious_keyword in imp for imp in imports for suspicious_keyword in self.blacklist)
        if suspicious_setup:
            return RESULT.FAIL, Confidence.LOW
        return RESULT.PASS, Confidence.MEDIUM  # The malicious code might placed in other script, so not HIGH
