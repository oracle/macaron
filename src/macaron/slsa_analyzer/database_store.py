# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""The database_store module contains the methods to store analysis results to the database."""

import logging

from macaron.config.defaults import defaults
from macaron.database.table_definitions import CheckFacts, CheckResult, SLSARequirement
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.check_result import CheckResultType

logger: logging.Logger = logging.getLogger(__name__)


def store_analyze_context_to_db(analyze_ctx: AnalyzeContext) -> None:
    """Store the content of an analyzed context into the database.

    Parameters
    ----------
    analyze_ctx : AnalyzeContext
        The analyze context to store into the database.
    """
    logger.debug(
        "Inserting result of %s to %s",
        analyze_ctx.component.purl,
        defaults.get("database", "db_name", fallback="macaron.db"),
    )

    # Store the context's slsa level.
    analyze_ctx.get_slsa_level_table()

    # Store check result table.
    for check_result in analyze_ctx.check_results.values():
        check_result_row = CheckResult(
            check_id=check_result["check_id"],
            component=analyze_ctx.component,
            passed=check_result["result_type"] == CheckResultType.PASSED,
        )

        if "result_tables" in check_result:
            for check_facts in check_result["result_tables"]:
                if isinstance(check_facts, CheckFacts):
                    check_facts.checkresult = check_result_row
                    check_facts.component = check_result_row.component

    # Store SLSA Requirements.
    for key, value in analyze_ctx.ctx_data.items():
        if value.is_pass:
            SLSARequirement(
                component=analyze_ctx.component,
                requirement_name=key.name,
                requirement_short_description=value.name,
                feedback=value.feedback,
            )
