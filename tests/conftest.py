# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Fixtures for tests."""
from pathlib import Path
from typing import NoReturn

import pytest

from macaron.config.defaults import create_defaults, defaults, load_defaults
from macaron.slsa_analyzer.build_tool.gradle import Gradle
from macaron.slsa_analyzer.build_tool.maven import Maven
from macaron.slsa_analyzer.build_tool.poetry import Poetry

# We need to pass fixture names as arguments to maintain an order.
# pylint: disable=redefined-outer-name


@pytest.fixture()
def test_dir() -> Path:
    """Set the root test_dir path.

    Returns
    -------
    Path
        The root path to the test directory.
    """
    return Path(__file__).parent


@pytest.fixture()
def macaron_path() -> Path:
    """Set the Macaron path.

    Returns
    -------
    Path
        The Macaron path.
    """
    return Path(__file__).parent.parent


@pytest.fixture(autouse=True)
def setup_test(test_dir: Path, macaron_path: Path) -> NoReturn:  # type: ignore
    """Set up the necessary values for the tests.

    Parameters
    ----------
    test_dir: Path
        Depends on test_dir fixture.
    macaron_path: Path
        Depends on macaron_path fixture.

    Returns
    -------
    NoReturn
    """
    # Load values from defaults.ini.
    if not test_dir.joinpath("defaults.ini").exists():
        create_defaults(str(test_dir), str(macaron_path))

    load_defaults(str(macaron_path))
    yield
    defaults.clear()


@pytest.fixture(autouse=True)
def maven_tool(setup_test) -> Maven:  # type: ignore # pylint: disable=unused-argument
    """Create a Maven tool instance.

    Parameters
    ----------
    setup_test
        Depends on setup_test fixture.

    Returns
    -------
    Maven
        The Maven instance.
    """
    maven = Maven()
    maven.load_defaults()
    return maven


@pytest.fixture(autouse=True)
def gradle_tool(setup_test) -> Gradle:  # type: ignore # pylint: disable=unused-argument
    """Create a Gradle tool instance.

    Parameters
    ----------
    setup_test
        Depends on setup_test fixture.

    Returns
    -------
    Gradle
        The Gradle instance.
    """
    gradle = Gradle()
    gradle.load_defaults()
    return gradle


@pytest.fixture(autouse=True)
def poetry_tool(setup_test) -> Poetry:  # type: ignore # pylint: disable=unused-argument
    """Create a Poetry tool instance.

    Parameters
    ----------
    setup_test
        Depends on setup_test fixture.

    Returns
    -------
    Poetry
        The Poetry instance.
    """
    poetry = Poetry()
    poetry.load_defaults()
    return poetry
