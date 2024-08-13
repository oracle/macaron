# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module validates the result JSON files against a JSON schema."""

import json
import os
import sys
from collections.abc import Sequence

import jsonschema


def main(argv: Sequence[str] | None = None) -> int:
    """Run main logic."""
    if not argv or not len(argv) == 3:
        print("Usage: python3 schema_validate.py <json_path> <schema_path>")
        return os.EX_USAGE

    data_path = sys.argv[1]
    schema_path = sys.argv[2]

    schema = None
    with open(schema_path, encoding="utf-8") as file:
        try:
            schema = json.load(file)
        except json.JSONDecodeError as error:
            print(f"Failed to load schema at {schema_path}, err:\n{error}\n")
            return os.EX_DATAERR

    data = None
    with open(data_path, encoding="utf-8") as file:
        try:
            data = json.load(file)
        except json.JSONDecodeError as error:
            print(f"Failed to load JSON data at {data_path}, err:\n{error}\n")
            return os.EX_DATAERR

    try:
        jsonschema.validate(
            schema=schema,
            instance=data,
        )
        print(f"JSON data at {data_path} PASSED schema {schema_path}.")
        return os.EX_OK
    except jsonschema.ValidationError as error:
        print(f"JSON data at {data_path} FAILED schema {schema_path}, err:\n{error}\n")
        return os.EX_DATAERR
    except jsonschema.SchemaError as error:
        print(f"The schema at {schema_path} is not valid, err:\n{error}\n")
        return os.EX_DATAERR


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
