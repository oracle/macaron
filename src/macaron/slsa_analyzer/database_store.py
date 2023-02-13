# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""The database_store module contains the methods to store analysis results to the database."""

from datetime import datetime

from macaron import __version__
from macaron.config.defaults import defaults
from macaron.database.database_manager import DatabaseManager
from macaron.database.table_definitions import (
    AnalysisTable,
    CheckFactsTable,
    CheckResultTable,
    RepositoryAnalysis,
    SLSARequirement,
)
from macaron.output_reporter.results import Record
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.checks.check_result import CheckResultType
from macaron.util import logger


def store_analyze_context_to_db(
    table_name: str, db_man: DatabaseManager, analysis: AnalysisTable, analyze_ctx: AnalyzeContext
) -> dict:
    """Store the content of an analyzed context into the database.

    Parameters
    ----------
    table_name: str
        The name of the main analysis table
    db_man : DatabaseManager
        The database manager object managing the session to which to add the results.
    analysis: AnalysisTable
        The analysis record which this result belongs to.
    analyze_ctx : AnalyzeContext
        The analyze context to store into the database.
    """
    logger.info(
        "Inserting result of %s to %s",
        analyze_ctx.repo_full_name,
        defaults.get("database", "db_name", fallback="macaron.db"),
    )

    # Ensure result table is created
    result_table = AnalyzeContext.get_analysis_result_table(table_name)
    db_man.create_tables()

    # Store old result format
    repository_analysis = RepositoryAnalysis(repository_id=analyze_ctx.repository_table.id, analysis_id=analysis.id)
    db_man.add_and_commit(repository_analysis)

    # Store the context's slsa level
    db_man.add_and_commit(analyze_ctx.get_slsa_level_table())

    # Store check result table
    for check in analyze_ctx.check_results.values():

        check_table = CheckResultTable()
        check_table.check_id = check["check_id"]
        check_table.repository = analyze_ctx.repository_table.id
        check_table.passed = check["result_type"] == CheckResultType.PASSED
        check_table.skipped = check["result_type"] == CheckResultType.SKIPPED
        db_man.add(check_table)

        if "result_tables" in check:
            for table in check["result_tables"]:
                if isinstance(table, CheckFactsTable):
                    table.repository = analyze_ctx.repository_table.id
                    table.check_result = check_table.id
                db_man.add_and_commit(table)

    # Store SLSA Requirements
    results = analyze_ctx.get_analysis_result_data()
    for key, value in analyze_ctx.ctx_data.items():
        if value.is_pass:
            requirement = SLSARequirement(
                repository=analyze_ctx.repository_table.id,
                requirement=key.name,
                requirement_name=value.name,
                feedback=value.feedback,
            )
            db_man.add_and_commit(requirement)

    db_man.insert(result_table, results)
    return results


def store_analysis_to_db(db_man: DatabaseManager, main_record: Record) -> AnalysisTable:
    """Store the analysis to the database."""
    db_man.create_tables()

    analysis = AnalysisTable(
        analysis_time=datetime.now().isoformat(sep="T", timespec="seconds"),
        macaron_version=__version__,
    )
    if main_record.context is not None:
        analysis.repository = main_record.context.repository_table.id
    else:
        return analysis

    db_man.add_and_commit(analysis)

    return analysis
