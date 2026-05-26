# Copyright (c) 2023 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module handles invoking the souffle policy engine on a database."""

import logging
import os
import re
import sys

from sqlalchemy import MetaData, create_engine, select

from macaron import __version__ as mcn_version
from macaron.console import access_handler
from macaron.database.table_definitions import Analysis
from macaron.policy_engine.souffle import SouffleError, SouffleWrapper
from macaron.policy_engine.souffle_code_generator import (
    SouffleProgram,
    get_souffle_import_prelude,
    project_table_to_key,
    project_with_fk_join,
)

logger: logging.Logger = logging.getLogger(__name__)

POLICY_REQUIREMENT_SENTINEL = 'policy_check_requirement("__macaron_no_policy__", "__macaron_no_check__").'

STANDARD_POLICY_OUTPUTS = {
    "passed_policies",
    "failed_policies",
    "component_satisfies_policy",
    "component_violates_policy",
}

POLICY_HEAD_RE = re.compile(r'Policy\s*\(\s*"(?P<policy_id>[^"]+)"', re.MULTILINE)
CHECK_REQUIREMENT_RE = re.compile(
    r"check_(?:passed|failed)(?:_with_confidence)?\s*\([^,]+,\s*\"(?P<check_id>[^\"]+)\"",
    re.MULTILINE,
)
RULE_HEAD_RE = re.compile(r"(?P<relation>[A-Za-z_][A-Za-z0-9_]*)\s*\(")
RELATION_CALL_RE = re.compile(r"!?\s*(?P<relation>[A-Za-z_][A-Za-z0-9_]*)\s*\(")
IGNORED_REQUIREMENT_RELATIONS = {
    "Policy",
    "apply_policy_to",
    "cat",
    "check_failed",
    "check_failed_with_confidence",
    "check_passed",
    "check_passed_with_confidence",
    "component_violates_policy",
    "is_component",
    "is_repo",
    "match",
    "policy_applies_to",
    "policy_check_requirement",
    "to_string",
    "transitive_dependency",
}


def _souffle_string(value: str) -> str:
    """Return a Souffle string literal for a Python string."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _souffle_statements(policy_content: str) -> list[str]:
    """Split Souffle content into statements, ignoring periods in strings and comments."""
    statements: list[str] = []
    current: list[str] = []
    in_string = False
    escaped = False
    in_line_comment = False
    index = 0

    rule_content = "\n".join(
        line for line in policy_content.splitlines() if not line.lstrip().startswith((".", "#"))
    )

    while index < len(rule_content):
        char = rule_content[index]

        if in_line_comment:
            if char == "\n":
                in_line_comment = False
                current.append(char)
            index += 1
            continue

        if (
            not in_string
            and char == "/"
            and index + 1 < len(rule_content)
            and rule_content[index + 1] == "/"
        ):
            in_line_comment = True
            index += 2
            continue

        if char == '"' and not escaped:
            in_string = not in_string
        escaped = in_string and char == "\\" and not escaped

        if char == "." and not in_string:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
            index += 1
            continue

        current.append(char)
        index += 1

    statement = "".join(current).strip()
    if statement:
        statements.append(statement)

    return statements


def _split_rule(statement: str) -> tuple[str, str] | None:
    """Split a Souffle rule into head and body."""
    in_string = False
    escaped = False
    index = 0
    while index < len(statement) - 1:
        char = statement[index]
        if char == '"' and not escaped:
            in_string = not in_string
        escaped = in_string and char == "\\" and not escaped

        if not in_string and statement[index : index + 2] == ":-":
            return statement[:index].strip(), statement[index + 2 :].strip()
        index += 1

    return None


def _build_rule_body_map(policy_content: str) -> dict[str, list[str]]:
    """Build a map of relation names to their rule bodies."""
    rule_body_map: dict[str, list[str]] = {}
    for statement in _souffle_statements(policy_content):
        rule = _split_rule(statement)
        if not rule:
            continue

        head, body = rule
        relation_match = RULE_HEAD_RE.match(head)
        if not relation_match:
            continue

        relation = relation_match.group("relation")
        if relation in IGNORED_REQUIREMENT_RELATIONS:
            continue
        rule_body_map.setdefault(relation, []).append(body)
    return rule_body_map


def _extract_check_requirements_from_body(
    body: str,
    rule_body_map: dict[str, list[str]],
    visited_relations: set[str],
) -> set[str]:
    """Extract literal check requirements from a rule body and helper relations it calls."""
    requirements = {check_match.group("check_id") for check_match in CHECK_REQUIREMENT_RE.finditer(body)}

    for relation_match in RELATION_CALL_RE.finditer(body):
        relation = relation_match.group("relation")
        if relation in IGNORED_REQUIREMENT_RELATIONS or relation in visited_relations:
            continue

        helper_bodies = rule_body_map.get(relation)
        if not helper_bodies:
            continue

        visited_relations.add(relation)
        for helper_body in helper_bodies:
            requirements.update(_extract_check_requirements_from_body(helper_body, rule_body_map, visited_relations))
        visited_relations.remove(relation)

    return requirements


def policy_check_requirement_facts(policy_content: str) -> str:
    """Build policy_check_requirement facts for literal checks used in Policy rules."""
    requirements: set[tuple[str, str]] = set()
    rule_body_map = _build_rule_body_map(policy_content)
    for statement in _souffle_statements(policy_content):
        rule = _split_rule(statement)
        if not rule:
            continue

        head, body = rule
        policy_match = POLICY_HEAD_RE.match(head)
        if not policy_match:
            continue

        policy_id = policy_match.group("policy_id")
        for check_id in _extract_check_requirements_from_body(body, rule_body_map, set()):
            requirements.add((policy_id, check_id))

    facts = [POLICY_REQUIREMENT_SENTINEL]
    facts.extend(
        f"policy_check_requirement({_souffle_string(policy_id)}, {_souffle_string(check_id)})."
        for policy_id, check_id in sorted(requirements)
    )
    return "\n".join(facts)


def add_policy_check_requirements(policy_content: str) -> str:
    """Append policy check requirement facts to a policy program."""
    return f"{policy_content.rstrip()}\n\n{policy_check_requirement_facts(policy_content)}\n"


def _format_policy_row(values: list[str], labels: list[str] | None = None) -> str:
    """Format a policy output row for console display."""
    if labels and len(labels) == len(values):
        return ", ".join(f"{label}: {value}" for label, value in zip(labels, values, strict=True))
    return " | ".join(values)


def _labels_for_evidence_relation(relation_name: str, values: list[str]) -> list[str] | None:
    """Return friendly column labels for known policy evidence relations."""
    labels_by_relation = {
        "malware_detection_findings": ["component", "failed check"],
        "malware_component_violations": ["component", "failed check"],
        "malware_dependency_violations": ["component", "dependency", "failed check"],
        "malware_policy_violations": ["component", "dependency"],
        "policy_component_check_failures": ["policy", "component", "failed check"],
        "policy_dependency_check_failures": ["policy", "component", "dependency", "failed check"],
    }
    labels = labels_by_relation.get(relation_name)
    if labels and len(labels) == len(values):
        return labels

    lower_name = relation_name.lower()
    if "dependency" in lower_name and len(values) == 3:
        return ["component", "dependency", "evidence"]
    if ("violation" in lower_name or "finding" in lower_name or "evidence" in lower_name) and len(values) == 2:
        return ["component", "evidence"]
    return None


def format_policy_results(results: dict[str, list[list[str]]]) -> str:
    """Return a human-readable policy evaluation summary."""
    failed_policies = results.get("failed_policies", [])
    passed_policies = results.get("passed_policies", [])
    violating_components = results.get("component_violates_policy", [])
    satisfying_components = results.get("component_satisfies_policy", [])
    evidence_relations = {
        relation: rows for relation, rows in results.items() if relation not in STANDARD_POLICY_OUTPUTS and rows
    }

    lines = ["Policy evaluation summary"]
    if failed_policies:
        lines.append("Result: FAILED")
    elif passed_policies:
        lines.append("Result: PASSED")
    else:
        lines.append("Result: NO MATCHING POLICIES")

    lines.append("")
    lines.append("Failed policies:")
    if failed_policies:
        lines.extend(f"  - {row[0]}" for row in failed_policies)
    else:
        lines.append("  - None")

    lines.append("")
    lines.append("Passed policies:")
    if passed_policies:
        lines.extend(f"  - {row[0]}" for row in passed_policies)
    else:
        lines.append("  - None")

    lines.append("")
    lines.append("Violating components:")
    if violating_components:
        for row in violating_components:
            lines.append(f"  - {_format_policy_row(row, ['component id', 'component', 'policy'])}")
    else:
        lines.append("  - None")

    if satisfying_components and not failed_policies:
        lines.append("")
        lines.append("Satisfying components:")
        for row in satisfying_components:
            lines.append(f"  - {_format_policy_row(row, ['component id', 'component', 'policy'])}")

    if evidence_relations:
        lines.append("")
        lines.append("Evidence:")
        for relation, rows in sorted(evidence_relations.items()):
            lines.append(f"  {relation}:")
            for row in rows:
                lines.append(f"    - {_format_policy_row(row, _labels_for_evidence_relation(relation, row))}")

    return "\n".join(lines)


def get_generated(database_path: os.PathLike | str) -> SouffleProgram:
    """Get generated souffle code from database specified by configuration.

    Parameters
    ----------
    database_path: os.PathLike | str
        The path to the database to generate imports and prelude for

    Returns
    -------
    SouffleProgram
        A program containing the declarations and relations for the schema of this database

    See Also
    --------
    souffle_code_generator.py
    """
    if not os.path.isfile(database_path):
        logger.error("Unable to open database %s", database_path)
        sys.exit(1)

    metadata = MetaData()
    engine = create_engine(f"sqlite:///{database_path}", echo=False)
    metadata.reflect(engine)

    prelude = get_souffle_import_prelude(os.path.abspath(database_path), metadata)

    for table_name in metadata.tables.keys():
        table = metadata.tables[table_name]
        if table_name[0] == "_":
            prelude.update(project_table_to_key(f"{table_name[1:]}_attribute", table))
            prelude.update(project_with_fk_join(table))

    return prelude


def copy_prelude(
    database_path: os.PathLike | str,
    sfl: SouffleWrapper,
    prelude: SouffleProgram | None = None,
) -> None:
    """
    Generate and copy the prelude into the souffle instance's include directory.

    Parameters
    ----------
    database_path: os.PathLike | str
        The path to the database the facts will be imported from
    sfl: SouffleWrapper
        The souffle execution context object
    prelude: SouffleProgram | None
        Optional, the prelude to use for the souffle program, if none is given the default prelude is generated from
        the database at database_path.
    """
    if prelude is None:
        prelude = get_generated(database_path)
    sfl.copy_to_includes("import_data.dl", str(prelude))

    folder = os.path.join(os.path.dirname(__file__), "prelude")
    for file_name in os.listdir(folder):
        full_file_name = os.path.join(folder, file_name)
        if not os.path.isfile(full_file_name):
            continue
        with open(full_file_name, encoding="utf-8") as file:
            text = file.read()
            sfl.copy_to_includes(file_name, text)


def run_souffle(database_path: str, policy_content: str) -> dict:
    """Invoke souffle and report result.

    Parameters
    ----------
    database_path: str
        The path to the database to evaluate the policy on
    policy_content: str
        The Souffle policy code to evaluate

    Returns
    -------
    dict
        A dictionary containing all the relations returned by souffle mapping relation_name to the list of rows.
    """
    with SouffleWrapper() as sfl:
        copy_prelude(database_path, sfl)
        try:
            res = sfl.interpret_text(policy_content)
        except SouffleError as error:
            logger.error("COMMAND: %s", error.command)
            logger.error("ERROR: %s", error.message)
            sys.exit(1)

        return res


def _check_version(database_path: str) -> None:
    """Verify that database was generated by a compatible version.

    TODO: improve this check and allow version ranges. Perhaps check
    for major version updates?

    Parameters
    ----------
    database_path: str
        The path to the macaron database
    """
    engine = create_engine(f"sqlite:///{database_path}", echo=False)

    with engine.connect() as conn:
        versions = conn.execute(
            select(Analysis.macaron_version).where(Analysis.macaron_version != mcn_version)
        ).scalar()
        if versions is not None:
            logger.error("Database generated with unsupported versions (%s).", versions)
            logger.error(
                "Only databases generated by Macaron version %s are supported.",
                mcn_version,
            )
            sys.exit(os.EX_DATAERR)


def show_prelude(database_path: str) -> None:
    """Show the Datalog prelude for a database and exit.

    Parameters
    ----------
    database_path: str
        The SQLite database file to show the prelude for.
    """
    prelude = get_generated(database_path)
    logger.info("\n%s", prelude)


def run_policy_engine(database_path: str, policy_content: str) -> dict:
    """Evaluate a policy based on configuration and exit.

    Parameters
    ----------
    database_path: str
        The SQLite database file to evaluate the policy against
    policy_content: str
        The Souffle policy code to evaluate

    Returns
    -------
    dict
        The policy engine result.
    """
    # TODO: uncomment the following line when the check is improved.
    # _check_version(database_path)

    res = run_souffle(database_path, add_policy_check_requirements(policy_content))

    logger.info("%s", format_policy_results(res))
    logger.debug("Raw policy results: %s", res)

    rich_handler = access_handler.get_handler()
    rich_handler.update_policy_engine(res)

    return res
