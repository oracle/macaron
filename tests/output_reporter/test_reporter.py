# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
This modules contains tests for the JSON reporter.
"""

import os
from typing import Any
from unittest.mock import MagicMock, call, patch

from hypothesis import given
from hypothesis import strategies as st
from jinja2 import Environment, FileSystemLoader, select_autoescape

from macaron.config.target_config import Configuration
from macaron.output_reporter.reporter import HTMLReporter, JSONReporter
from macaron.output_reporter.results import Record, Report, SCMStatus

from ..macaron_testcase import MacaronTestCase
from ..st import JINJA_CONTEXT_DICT

ROOT_PATH = os.path.dirname(os.path.abspath(__file__))


class MockRecord(Record):
    """A mock class for the record."""

    def __init__(self, mock_data: dict) -> None:
        super().__init__(
            record_id="record",
            description="sample_desc",
            pre_config=Configuration({}),
            status=SCMStatus.AVAILABLE,
            context=MagicMock(),
            dependencies=[],
        )
        self.mock_data = mock_data

    def get_dict(self) -> dict:
        return self.mock_data


class TestHTMLReporter(MacaronTestCase):
    """Test the HTMLReporter class."""

    def test_no_html_template_found(self) -> None:
        """Test initializing a HTMLReporter instance with a non-existing template."""
        no_template_reporter = HTMLReporter(target_template="not_exist_template.html")
        assert not no_template_reporter.template

    @given(mock_data=JINJA_CONTEXT_DICT, num_dep=st.integers(min_value=0, max_value=3))
    def test_gen_json_reports(self, mock_data: Any, num_dep: int) -> None:
        """Test if JSONReporter can print JSON files without errors."""
        report = Report(MockRecord(mock_data))
        for _ in range(num_dep):
            report.root_record.dependencies.append(MockRecord(mock_data))

        reporter = JSONReporter()

        with patch("builtins.open") as mock_open:
            reporter.generate("report_paths", report)
            calls = [call(os.path.join("report_paths", "dependencies.json"), mode="w", encoding="utf-8")]
            mock_open.assert_has_calls(calls)

    @given(mock_data=JINJA_CONTEXT_DICT, num_dep=st.integers(min_value=0, max_value=3))
    def test_gen_html_reports(self, mock_data: Any, num_dep: int) -> None:
        """Test if HTMLReporter can print HTML files without errors."""
        report = Report(MockRecord(mock_data))
        for _ in range(num_dep):
            report.root_record.dependencies.append(MockRecord(mock_data))

        custom_jinja_env = Environment(
            loader=FileSystemLoader(ROOT_PATH),
            autoescape=select_autoescape(enabled_extensions=["html", "j2"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )

        reporter = HTMLReporter(env=custom_jinja_env, target_template="template.html")
        with patch("builtins.open") as mock_open:
            reporter.generate("report_paths", report)
            mock_open.assert_called()
