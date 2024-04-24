# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the base CI service."""


from pathlib import Path

import pytest

from macaron.slsa_analyzer.ci_service.base_ci_service import BaseCIService


@pytest.mark.parametrize(
    ("entry_conf", "kws", "repo_path", "expect"),
    [
        (
            ["a.txt", "b.txt"],
            ["build_keyword"],
            Path(__file__).parent.joinpath("resources", "base_ci_service", "empty"),
            ("", ""),
        ),
        (
            ["a.txt", "b.txt"],
            ["build_keyword"],
            Path(__file__).parent.joinpath("resources", "base_ci_service", "files_with_no_kws"),
            ("", ""),
        ),
        # The first encounter of a keyword is returned.
        (
            ["a.txt", "b.txt"],
            ["build_keyword1", "build_keyword2"],
            Path(__file__).parent.joinpath("resources", "base_ci_service", "files_with_kws"),
            ("build_keyword1", "a.txt"),
        ),
        # Non_exist config files.
        (
            ["non_exist.txt", "file_not_found.txt"],
            ["build_keyword1", "build_keyword2"],
            Path(__file__).parent.joinpath("resources", "base_ci_service", "files_with_kws"),
            ("", ""),
        ),
    ],
)
def test_has_kws_in_config(entry_conf: list[str], kws: list[str], repo_path: str, expect: tuple[str, str]) -> None:
    """Test has keywords in config check."""
    base_ci_service = BaseCIService("base")  # type: ignore
    base_ci_service.entry_conf = entry_conf
    assert base_ci_service.has_kws_in_config(kws=kws, build_tool_name="foo", repo_path=repo_path) == expect
