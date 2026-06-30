# Copyright (c) 2026 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Tests for the PyPI package registry."""

import os
import shutil
import tarfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

from macaron.errors import InvalidHTTPResponseError, SourceCodeError
from macaron.slsa_analyzer.package_registry import pypi_registry
from macaron.slsa_analyzer.package_registry.pypi_registry import PyPIInspectorAsset, PyPIPackageJsonAsset, PyPIRegistry


def _raise_during_sourcecode_context(asset: PyPIPackageJsonAsset) -> None:
    """Raise an error inside the sourcecode context manager."""
    with asset.sourcecode():
        raise SourceCodeError("analysis failed")


def test_download_package_sourcecode_flattens_top_level_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Downloaded sdists with a single top-level package directory should clean up from the temp root."""
    package_name = "example-1.0.0"
    pyproject_path = os.path.join(tmp_path, "pyproject.toml")
    with open(pyproject_path, "w", encoding="utf-8") as pyproject_file:
        pyproject_file.write("[build-system]\n")
    archive_path = os.path.join(tmp_path, f"{package_name}.tar.gz")
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(pyproject_path, arcname=os.path.join(package_name, "pyproject.toml"))

    temp_root = os.path.join(tmp_path, "downloads")
    os.makedirs(temp_root)

    def mkdtemp(prefix: str) -> str:
        return os.path.join(temp_root, f"{prefix}abcdef")

    def download_file(_url: str, _headers: dict, dest: str, _timeout: int, _size_limit: int) -> bool:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(archive_path, dest)
        return True

    monkeypatch.setattr(pypi_registry.tempfile, "mkdtemp", mkdtemp)
    monkeypatch.setattr(pypi_registry, "download_file_with_size_limit", download_file)

    source_path = PyPIRegistry().download_package_sourcecode(f"https://example.test/{package_name}.tar.gz")

    assert source_path == os.path.join(temp_root, f"{package_name}_abcdef")
    assert os.path.exists(os.path.join(source_path, "pyproject.toml"))
    assert not os.path.exists(os.path.join(source_path, package_name))

    PyPIRegistry.cleanup_sourcecode_directory(source_path)
    assert not os.path.exists(source_path)


def test_sourcecode_context_cleans_up_when_analysis_raises(tmp_path: Path) -> None:
    """The sourcecode context manager must remove downloads even if the caller fails."""
    source_path = os.path.join(tmp_path, "example-1.0.0_abcdef")
    os.makedirs(source_path)

    registry = PyPIRegistry()
    registry.download_package_sourcecode = MagicMock(return_value=str(source_path))  # type: ignore[method-assign]
    asset = PyPIPackageJsonAsset("example", "1.0.0", False, registry, {}, PyPIInspectorAsset("", [], {}))
    asset.get_sourcecode_url = MagicMock(  # type: ignore[method-assign]
        return_value="https://example.test/example-1.0.0.tar.gz"
    )

    with pytest.raises(SourceCodeError, match="analysis failed"):
        _raise_during_sourcecode_context(asset)

    assert not os.path.exists(source_path)


def test_download_package_sourcecode_cleans_up_when_download_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sdist temp directory should be removed if the download helper raises."""
    package_name = "example-1.0.0"
    source_path = os.path.join(tmp_path, f"{package_name}_abcdef")

    def mkdtemp(prefix: str) -> str:
        path = os.path.join(tmp_path, f"{prefix}abcdef")
        os.makedirs(path)
        return path

    def download_file(_url: str, _headers: dict, _dest: str, _timeout: int, _size_limit: int) -> bool:
        raise requests.exceptions.ConnectionError("download crashed")

    monkeypatch.setattr(pypi_registry.tempfile, "mkdtemp", mkdtemp)
    monkeypatch.setattr(pypi_registry, "download_file_with_size_limit", download_file)

    with pytest.raises(InvalidHTTPResponseError, match="download crashed"):
        PyPIRegistry().download_package_sourcecode(f"https://example.test/{package_name}.tar.gz")

    assert not os.path.exists(source_path)


def test_download_package_wheel_cleans_up_when_download_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The wheel temp directory should be removed if the download helper raises."""
    wheel_name = "example-1.0.0-py3-none-any"
    wheel_path = os.path.join(tmp_path, f"{wheel_name}_abcdef")

    def mkdtemp(prefix: str) -> str:
        path = os.path.join(tmp_path, f"{prefix}abcdef")
        os.makedirs(path)
        return path

    def download_file(_url: str, _headers: dict, _dest: str, _timeout: int, _size_limit: int) -> bool:
        raise requests.exceptions.ConnectionError("download crashed")

    monkeypatch.setattr(pypi_registry.tempfile, "mkdtemp", mkdtemp)
    monkeypatch.setattr(pypi_registry, "download_file_with_size_limit", download_file)

    with pytest.raises(InvalidHTTPResponseError, match="download crashed"):
        PyPIRegistry().download_package_wheel(f"https://example.test/{wheel_name}.whl")

    assert not os.path.exists(wheel_path)
