# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Script to compare a generated VSA with an expected payload."""

from __future__ import annotations

import argparse
import base64
import json
import logging
import traceback
from collections.abc import Callable

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logging.basicConfig(format="[%(filename)s:%(lineno)s %(tag)s] %(message)s")


def log_with_tag(tag: str) -> Callable[[str], None]:
    """Generate a log function that prints the name of the file and a tag at the beginning of each line."""

    def log_fn(msg: str) -> None:
        logger.info(msg, extra={"tag": tag})

    return log_fn


log_info = log_with_tag("INFO")
log_err = log_with_tag("ERROR")
log_failed = log_with_tag("FAILED")
log_passed = log_with_tag("PASSED")


def log_diff(name: str, result: object, expected: object) -> None:
    """Pretty-print the diff of two Python objects."""
    output = [
        f"'{name}'",
        *("----  Result  ---", json.dumps(result, indent=4)),
        *("---- Expected ---", json.dumps(expected, indent=4)),
        "-----------------",
    ]
    log_info("\n".join(output))


CompareFn = Callable[[object, object], bool]


def skip_compare(_result: object, _expected: object) -> bool:
    """Return ``True`` always.

    This compare function is used when we want to skip comparing a field.
    """
    return True


def compare_json(
    result: object,
    expected: object,
    compare_fn_map: dict[str, CompareFn],
    name: str = "",
) -> bool:
    """Compare two JSON values.

    This function should not try to return immediately when it encounters a mismatch.
    Rather, it should try to report as many mismatches as possible.

    Parameters
    ----------
    result : object
        The result value.
    expected : object
        The expected value.
    compare_fn_map : dict[str, CompareFn]
        A map from field name to corresponding compare function.
    name : str
        The name of the field.
        Field names must follow the following rules:
        - At the top level: empty string ""
        - A subfield "bar" in an object field with name ".foo" has the name ".foo.bar".
        - A subfield "baz" in an object field with name ".foo.bar" has the name ".foo.bar.baz".
        - The ith element in an array field with name ".foo" have the name ".foo[i]".

    Returns
    -------
    bool
        ``True`` if the comparison is successful, ``False`` otherwise.
    """
    if name in compare_fn_map:
        return compare_fn_map[name](result, expected)

    if isinstance(expected, list):
        if not isinstance(result, list):
            log_err(f"Expected '{name}' to be a JSON array.")
            log_diff(name, result, expected)
            # Nothing else to check.
            return False
        return compare_list(result, expected, compare_fn_map, name)
    if isinstance(expected, dict):
        if not isinstance(result, dict):
            log_err(f"Expected '{name}' to be a JSON object.")
            log_diff(name, result, expected)
            # Nothing else to check.
            return False
        return compare_dict(result, expected, compare_fn_map, name)

    if result != expected:
        log_err(f"Mismatch found in '{name}'")
        log_diff(name, result, expected)
        return False

    return True


def compare_list(
    result: list,
    expected: list,
    compare_fn_map: dict[str, CompareFn],
    name: str,
) -> bool:
    """Compare two JSON arrays.

    Parameters
    ----------
    result : list
        The result array.
    expected : list
        The expected array.
    compare_fn_map : str
        A map from field name to corresponding compare function.
    name : str
        The name of the field whose value is being compared in this function.

    Returns
    -------
    bool
        ``True`` if the comparison is successful, ``False`` otherwise.
    """
    if len(result) != len(expected):
        log_err(f"Expected field '{name}' of length {len(result)} in result to have length {len(expected)}")
        log_diff(name, result, expected)
        # Nothing else to compare
        return False

    equal = True

    for i, (result_element, expected_element) in enumerate(zip(result, expected)):
        equal &= compare_json(
            result=result_element,
            expected=expected_element,
            compare_fn_map=compare_fn_map,
            name=f"{name}[{i}]",
        )

    return equal


def compare_dict(
    result: dict,
    expected: dict,
    compare_fn_map: dict[str, CompareFn],
    name: str,
) -> bool:
    """Compare two JSON objects.

    Parameters
    ----------
    result : dict
        The result object.
    expected : dict
        The expected object.
    compare_fn_map : str
        A map from field name to corresponding compare function.
    name : str
        The name of the field whose value is being compared in this function.

    Returns
    -------
    bool
        ``True`` if the comparison is successful, ``False`` otherwise.
    """
    result_keys_only = result.keys() - expected.keys()
    expected_keys_only = expected.keys() - result.keys()

    equal = True

    if len(result_keys_only) > 0:
        log_err(f"'{name}' in result has the following extraneous fields: {result_keys_only}")
        equal = False

    if len(expected_keys_only) > 0:
        log_err(f"'{name}' in result does not contain these expected fields: {expected_keys_only}")
        equal = False

    common_keys = set(result.keys()).intersection(set(expected.keys()))

    for key in common_keys:
        equal &= compare_json(
            result=result[key],
            expected=expected[key],
            name=f"{name}.{key}",
            compare_fn_map=compare_fn_map,
        )

    return equal


def main() -> int:
    """Compare a Macaron generated VSA with an expected VSA payload.

    Returns
    -------
    int
        0 if the payload in the generated VSA matches the expected payload, or
        non-zero otherwise.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("result_file", help="the result VSA file")
    parser.add_argument("expected_payload_file", help="the expected VSA payload file")
    parser.add_argument(
        "-u",
        "--update",
        action="store_true",
        help="update the expected payload file",
    )
    args = parser.parse_args()

    with open(args.result_file, encoding="utf-8") as file:
        vsa = json.load(file)

    try:
        payload = json.loads(base64.b64decode(vsa["payload"]))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        log_err(f"Error while decoding the VSA payload:\n{traceback.format_exc()}")
        return 1

    if args.update:
        with open(args.expected_payload_file, mode="w", encoding="utf-8") as file:
            json.dump(payload, fp=file, indent=4)
        log_info(f"Updated {args.expected_payload_file}.")
        return 0

    with open(args.expected_payload_file, encoding="utf-8") as file:
        expected_payload = json.load(file)

    log_info(f"Comparing the VSA file {args.result_file} with the expected payload file {args.expected_payload_file}")

    equal = compare_json(
        result=payload,
        expected=expected_payload,
        compare_fn_map={
            ".predicate.timeVerified": skip_compare,
        },
    )

    if not equal:
        log_failed("The payload of the generated VSA does not match the expected payload.")
        return 1

    log_passed("The payload of the generated VSA matches the expected payload")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
