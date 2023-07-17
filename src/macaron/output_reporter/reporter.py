# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains reporter classes for creating reports of Macaron analyzed results."""

import abc
import json
import logging
import os
from copy import deepcopy
from typing import Optional

from jinja2 import (
    Environment,
    FileSystemLoader,
    TemplateNotFound,
    TemplateRuntimeError,
    TemplateSyntaxError,
    select_autoescape,
)

import macaron.output_reporter.jinja2_extensions as jinja2_extensions  # pylint: disable=consider-using-from-import
from macaron.output_reporter.results import Report
from macaron.output_reporter.scm import SCMStatus

logger: logging.Logger = logging.getLogger(__name__)

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")


class FileReporter(abc.ABC):
    """The reporter that handles writing data to disk files."""

    def __init__(self, mode: str = "w", encoding: str = "utf-8"):
        """Initialize instance.

        Parameters
        ----------
        mode : str, optional
            The mode to open the target files, by default "w".
        encoding : str, optional
            The encoding used to handle disk files, by default "utf-8".
        """
        self.mode = mode
        self.encoding = encoding

    def write_file(self, file_path: str, data: str) -> bool:
        """Write the data into a file.

        Parameters
        ----------
        file_path : str
            The path to the target file.
        data : Any
            The data to write into the file.

        Returns
        -------
        bool
            True if succeeded else False.
        """
        try:
            with open(file_path, mode=self.mode, encoding=self.encoding) as file:
                logger.info("Writing to file %s", file_path)
                file.write(data)
                return True
        except OSError as error:
            logger.error("Cannot write to %s. Error: %s", file_path, error)
            return False

    @abc.abstractmethod
    def generate(self, target_dir: str, report: Report | dict) -> None:
        """Generate a report file.

        This method is implemented in subclasses.

        Parameters
        ----------
        target_dir : str
            The directory to store all output files.
        report : Report | dict
            The report to be generated.
        """


class JSONReporter(FileReporter):
    """This class handles writing reports to JSON files."""

    def __init__(self, mode: str = "w", encoding: str = "utf-8", indent: int = 4):
        """Initialize instance.

        Parameters
        ----------
        mode: str, optional
            The file operation mode.
        encoding: str, optional
            The encoding.
        indent : int, optional
            The indent for the JSON output, by default 4.
        """
        super().__init__(mode, encoding)
        self.indent = indent

    def generate(self, target_dir: str, report: Report | dict) -> None:
        """Generate JSON report files.

        Each record is stored in a separate JSON file, the name of each
        file is the name of the repo.

        A dependencies.json is also created to store the information of all resolved dependencies.

        Parameters
        ----------
        target_dir : str
            The directory to store all output files.
        report: Report | dict
            The report to be generated.
        """
        if not isinstance(report, Report):
            return
        try:
            dep_file_name = os.path.join(target_dir, "dependencies.json")
            serialized_configs = list(report.get_serialized_configs())
            self.write_file(dep_file_name, json.dumps(serialized_configs, indent=self.indent))

            for record in report.get_records():
                if record.context and record.status == SCMStatus.AVAILABLE:
                    file_name = os.path.join(target_dir, f"{record.context.component.report_file_name}.json")
                    json_data = json.dumps(record.get_dict(), indent=self.indent)
                    self.write_file(file_name, json_data)
        except TypeError as error:
            logger.critical("Cannot serialize output report to JSON: %s", error)


class HTMLReporter(FileReporter):
    """This class handles writing reports to HTML files."""

    def __init__(
        self,
        mode: str = "w",
        encoding: str = "utf-8",
        env: Optional[Environment] = None,
        target_template: str = "macaron.html",
    ) -> None:
        """Initialize instance.

        Parameters
        ----------
        mode: str, optional
            The file operation mode.
        encoding: str, optional
            The encoding.
        env : Optional[Environment]
            The pre-initiated ``jinja2.Environment`` instance for the HTMLReporter. If this is not
            provided, a default jinja2.Environment will be initialized.
        target_template : str
            The target template. It will be looked up from the jinja2.Environment instance.
        """
        super().__init__(mode, encoding)
        if env:
            self.env = env
        else:
            self.env = Environment(
                loader=FileSystemLoader(TEMPLATE_DIR),
                autoescape=select_autoescape(enabled_extensions=["html", "j2"]),
                trim_blocks=True,
                lstrip_blocks=True,
            )

        self._init_extensions()

        self.template = None
        try:
            self.template = self.env.get_template(target_template)
        except TemplateNotFound:
            logger.error("Cannot find the template to load.")

    def _init_extensions(self) -> None:
        """Dynamically add Jinja2 extension filters and tests."""
        filters = {}
        tests = {}

        if jinja2_extensions.filter_extensions or jinja2_extensions.test_extensions:
            for name, custom_filter in jinja2_extensions.filter_extensions.items():
                if hasattr(jinja2_extensions, custom_filter):
                    filters[name] = getattr(jinja2_extensions, custom_filter)

            for name, test in jinja2_extensions.test_extensions.items():
                if hasattr(jinja2_extensions, test):
                    tests[name] = getattr(jinja2_extensions, test)

        self.env.tests.update(tests)
        self.env.filters.update(filters)

    def generate(self, target_dir: str, report: Report | dict) -> None:
        """Generate HTML report files.

        Each record is stored in a separate HTML file, the name of each
        file is the name of the repo.

        The target_template is used to load the template within the initialized
        jinja2.Environment. If it failed to load, no HTML files will be generated.

        Parameters
        ----------
        target_dir : str
            The directory to store all output files.
        report: Report | dict
            The report to be generated.
        """
        if not self.template or not isinstance(report, Report):
            return

        try:
            for record in report.get_records():
                if record.context and record.status == SCMStatus.AVAILABLE:
                    file_name = os.path.join(target_dir, f"{record.context.component.report_file_name}.html")
                    # Make a deep copy because we don't want to keep any modification from Jinja
                    # in the original data.
                    html = self.template.render(deepcopy(record.get_dict()))
                    self.write_file(file_name, html)
        except TemplateSyntaxError as error:
            location = f"line {error.lineno}"
            name = error.filename or error.name
            if name:
                location = f'File "{name}", {location}'
            logger.info("jinja2.TemplateSyntaxError: \n\t%s\n\t%s", error.message, location)
        except TemplateRuntimeError as error:
            logger.error("jinja2.TemplateRunTimeError: %s", error)


class PolicyReporter(FileReporter):
    """This class writes policy engine reports to a JSON file."""

    def __init__(self, mode: str = "w", encoding: str = "utf-8", indent: int = 4):
        """Initialize instance.

        Parameters
        ----------
        mode: str, optional
            The file operation mode.
        encoding: str, optional
            The encoding.
        indent : int, optional
            The indent for the JSON output, by default 4.
        """
        super().__init__(mode, encoding)
        self.indent = indent

    def generate(self, target_dir: str, report: Report | dict) -> None:
        """Generate JSON report files.

        Each record is stored in a separate JSON file, the name of each
        file is the name of the repo.

        A dependencies.json is also created to store the information of all resolved dependencies.

        Parameters
        ----------
        target_dir : str
            The directory to store all output files.
        report: Report | dict
            The report to be generated.
        """
        if not isinstance(report, dict):
            return
        try:
            self.write_file(os.path.join(target_dir, "policy_report.json"), json.dumps(report, indent=self.indent))
        except (TypeError, ValueError, OSError) as error:
            logger.critical("Cannot serialize the policy report to JSON: %s", error)
