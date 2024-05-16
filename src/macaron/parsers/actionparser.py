# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the parser for GitHub Actions Workflow files."""

import json
import logging
import os.path
from typing import cast

import jsonschema
import yamale

from macaron import MACARON_PATH
from macaron.errors import ParseError
from macaron.parsers.github_workflow_model import Step, Workflow, as_run_step

logger: logging.Logger = logging.getLogger(__name__)


def parse(workflow_path: str) -> Workflow:
    """Parse the GitHub Actions workflow YAML file.

    Parameters
    ----------
    workflow_path : str
        Path to the GitHub Actions.

    Returns
    -------
    Workflow
        The parsed workflow.

    Raises
    ------
    ParseError
        When parsing fails with errors.
    """
    try:
        parse_result = yamale.make_data(workflow_path, parser="ruamel")
    except OSError as error:
        raise ParseError("Cannot parse GitHub Workflow: " + workflow_path) from error

    if len(parse_result) != 1:
        raise ParseError("Cannot parse GitHub Workflow: " + workflow_path)

    github_workflow_schema_filename = os.path.join(MACARON_PATH, "resources", "schemastore", "github-workflow.json")

    with open(github_workflow_schema_filename, encoding="utf-8") as schema_file:
        schema = json.load(schema_file)

    try:
        jsonschema.validate(parse_result[0][0], schema)
    except jsonschema.ValidationError as e:
        raise ParseError("Cannot parse GitHub Workflow, schema validation failed: " + workflow_path) from e

    return cast(Workflow, parse_result[0][0])


def get_run_step(step: Step) -> str | None:
    """Get the parsed GitHub Action run step for inlined shell scripts.

    If the run step cannot be validated this function returns None.

    Parameters
    ----------
    step: Step
        The parsed step object.

    Returns
    -------
    str | None
        The inlined run script or None if the run step cannot be validated.
    """
    run_step = as_run_step(step)
    if run_step is not None:
        return run_step["run"]
    return None


def get_step_input(step: Step, key: str) -> str | None:
    """Get an input value from a GitHub Action step.

    If the input value cannot be found or the step inputs cannot be validated this function
    returns None.

    Parameters
    ----------
    step: Step
        The parsed step object.
    key: str
        The key to be looked up.

    Returns
    -------
    str | None
        The input value or None if it doesn't exist or the parsed object validation fails.
    """
    with_section = step.get("with")
    if isinstance(with_section, dict):
        return str(with_section.get(key))

    return None
