# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""
This module tests the Limited XML parser.
"""

import os
from pathlib import Path

from macaron.parsers.limited_xmlparser import extract_tags

from ...macaron_testcase import MacaronTestCase


class TestParsers(MacaronTestCase):
    """Test the Limited XML parser."""

    def test_xmlparser_parse(self) -> None:
        """Test parsing xml files."""
        resources_dir = Path(__file__).parent.joinpath("resources")

        with open(os.path.join(resources_dir, "xml_files", "example_pom.xml"), encoding="utf8") as file:
            urls = extract_tags(file.read(), {"project.scm.url"})
            assert len(urls) == 1
            assert urls[0] == "https://example.example/example"

        with open(os.path.join(resources_dir, "xml_files", "obfuscated.xml"), encoding="utf8") as file:
            urls = extract_tags(file.read(), {"project.scm.url"})
            assert len(urls) == 0

        with open(os.path.join(resources_dir, "xml_files", "malformed.xml"), encoding="utf8") as file:
            urls = extract_tags(file.read(), {"project.scm.url"})
            assert len(urls) == 0
