# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module implements a rich console handler for logging."""

import logging
import time
from typing import Any

from rich.console import Group, RenderableType
from rich.live import Live
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TaskID, TextColumn
from rich.rule import Rule
from rich.status import Status
from rich.table import Table

from macaron.slsa_analyzer.checks.check_result import CheckResultType


class Check:
    """Class to represent a check with its status and target."""

    status = "PENDING"
    target = ""


class RichConsoleHandler(RichHandler):
    """A rich console handler for logging with rich formatting and live updates."""

    def __init__(self, *args: Any, verbose: bool = False, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.setLevel(logging.DEBUG)
        self.command = ""
        self.logs: list[str] = []
        self.description_table = Table(show_header=False, box=None)
        self.description_table_content: dict[str, str | Status] = {
            "Full Name:": Status("[green]Processing[/]"),
            "Local Cloned Path:": Status("[green]Processing[/]"),
            "Remote Path:": Status("[green]Processing[/]"),
            "Branch:": Status("[green]Processing[/]"),
            "Commit Hash:": Status("[green]Processing[/]"),
            "Commit Date:": Status("[green]Processing[/]"),
            "Excluded Checks:": Status("[green]Processing[/]"),
            "Final Checks:": Status("[green]Processing[/]"),
            "CI Services:": Status("[green]Processing[/]"),
            "Build Tools:": Status("[green]Processing[/]"),
        }
        self.progress = Progress(
            TextColumn(" RUNNING ANALYSIS"),
            BarColumn(bar_width=None, complete_style="green"),
            MofNCompleteColumn(),
        )
        self.task_id: TaskID
        self.progress_table = Table(show_header=False, box=None)
        self.checks: dict[str, Check] = {}
        self.failed_checks_table = Table(show_header=False, box=None)
        self.summary_table = Table(show_header=False, box=None)
        self.report_table = Table(show_header=False, box=None)
        self.reports = {
            "HTML Report": "Not Generated",
            "Dependencies Report": "Not Generated",
            "JSON Report": "Not Generated",
        }
        self.components_violates_table = Table(show_header=False, box=None)
        self.components_satisfy_table = Table(show_header=False, box=None)
        self.policy_summary_table = Table(show_header=False, box=None)
        self.policy_summary: dict[str, str | Status] = {
            "Passed Policies": "None",
            "Failed Policies": "None",
            "Policy Report": Status("[green]Generating[/]"),
        }
        self.verification_summary_attestation: str | None = None
        self.verbose = verbose
        self.verbose_panel = Panel(
            "\n".join(self.logs),
            title="Verbose Mode",
            title_align="left",
            border_style="blue",
        )
        self.live = Live(get_renderable=self.make_layout, refresh_per_second=10)

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record with rich formatting."""
        log_time = time.strftime("%H:%M:%S")
        msg = self.format(record)

        if record.levelno >= logging.ERROR:
            self.logs.append(f"[red][ERROR][/red] {log_time} {msg}")
        elif record.levelno >= logging.WARNING:
            self.logs.append(f"[yellow][WARNING][/yellow] {log_time} {msg}")
        else:
            self.logs.append(f"[blue][INFO][/blue] {log_time} {msg}")

        self.verbose_panel.renderable = "\n".join(self.logs)

    def add_description_table_content(self, key: str, value: str | Status) -> None:
        """Add or update a key-value pair in the description table."""
        self.description_table_content[key] = value
        description_table = Table(show_header=False, box=None)
        description_table.add_column("Details", justify="left")
        description_table.add_column("Value", justify="left")
        for field, content in self.description_table_content.items():
            description_table.add_row(field, content)

        self.description_table = description_table

    def no_of_checks(self, value: int) -> None:
        """Initialize the progress bar with the total number of checks."""
        self.task_id = self.progress.add_task("analyzing", total=value)

    def update_checks(self, check_id: str, target: str, status: str = "RUNNING") -> None:
        """Update the status and target of a specific check."""
        if check_id not in self.checks:
            self.checks[check_id] = Check()
        self.checks[check_id].status = status
        self.checks[check_id].target = target

        progress_table = Table(show_header=False, box=None)
        progress_table.add_column("Status", justify="left")
        progress_table.add_column("Check", justify="left")
        progress_table.add_column("Target", justify="left")

        for check_name, check in self.checks.items():
            if check.status == "RUNNING":
                progress_table.add_row(Status("[bold green]RUNNING[/]"), check_name, check.target)
        self.progress_table = progress_table

        if self.task_id is not None and status != "RUNNING":
            self.progress.update(self.task_id, advance=1)

    def update_checks_summary(self, checks_summary: dict, total_checks: int) -> None:
        """Update the summary tables based on the checks summary."""
        failed_checks_table = Table(show_header=False, box=None)
        failed_checks_table.add_column("Status", justify="left")
        failed_checks_table.add_column("Check ID", justify="left")
        failed_checks_table.add_column("Description", justify="left")

        failed_checks = checks_summary[CheckResultType.FAILED]
        for check in failed_checks:
            failed_checks_table.add_row(
                "[bold red]FAILED[/]",
                check.check.check_id,
                check.check.check_description,
            )

        self.failed_checks_table = failed_checks_table

        summary_table = Table(show_header=False, box=None)
        summary_table.add_column("Check Result Type", justify="left")
        summary_table.add_column("Count", justify="left")
        summary_table.add_row("Total Checks", str(total_checks), style="white")

        for check_result_type, checks in checks_summary.items():
            if check_result_type == CheckResultType.PASSED:
                summary_table.add_row("PASSED", str(len(checks)), style="green")
            if check_result_type == CheckResultType.FAILED:
                summary_table.add_row("FAILED", str(len(checks)), style="red")
            if check_result_type == CheckResultType.SKIPPED:
                summary_table.add_row("SKIPPED", str(len(checks)), style="yellow")
            if check_result_type == CheckResultType.DISABLED:
                summary_table.add_row("DISABLED", str(len(checks)), style="bright_blue")
            if check_result_type == CheckResultType.UNKNOWN:
                summary_table.add_row("UNKNOWN", str(len(checks)), style="white")

        self.summary_table = summary_table

    def update_report_table(self, report_type: str, report_path: str) -> None:
        """Update the report table with the given report type and path."""
        self.reports[report_type] = report_path
        report_table = Table(show_header=False, box=None)
        report_table.add_column("Report Type", justify="left")
        report_table.add_column("Report Path", justify="left")

        for report_detail, report_value in self.reports.items():
            report_table.add_row(report_detail, report_value, style="blue")

        self.report_table = report_table

    def generate_policy_summary_table(self) -> None:
        """Generate the policy summary table."""
        policy_summary_table = Table(show_header=False, box=None)
        policy_summary_table.add_column("Detail", justify="left")
        policy_summary_table.add_column("Value", justify="left")

        policy_summary_table.add_row(
            "[bold green]Passed Policies[/]",
            self.policy_summary["Passed Policies"],
        )
        policy_summary_table.add_row(
            "[bold red]Failed Policies[/]",
            self.policy_summary["Failed Policies"],
        )
        policy_summary_table.add_row("[bold blue]Policy Report[/]", self.policy_summary["Policy Report"])

        self.policy_summary_table = policy_summary_table

    def update_policy_report(self, report_path: str) -> None:
        """Update the policy report path in the policy summary."""
        self.policy_summary["Policy Report"] = report_path
        self.generate_policy_summary_table()

    def update_vsa(self, vsa_path: str) -> None:
        """Update the verification summary attestation path."""
        self.verification_summary_attestation = vsa_path

    def update_policy_engine(self, results: dict) -> None:
        """Update the policy engine results."""
        components_violates_table = Table(show_header=False, box=None)
        components_violates_table.add_column("Assign No.", justify="left")
        components_violates_table.add_column("Component", justify="left")
        components_violates_table.add_column("Policy", justify="left")

        for values in results["component_violates_policy"]:
            components_violates_table.add_row(values[0], values[1], values[2])

        self.components_violates_table = components_violates_table

        components_satisfy_table = Table(show_header=False, box=None)
        components_satisfy_table.add_column("Assign No.", justify="left")
        components_satisfy_table.add_column("Component", justify="left")
        components_satisfy_table.add_column("Policy", justify="left")

        for values in results["component_satisfies_policy"]:
            components_satisfy_table.add_row(values[0], values[1], values[2])

        self.components_satisfy_table = components_satisfy_table

        self.policy_summary["Passed Policies"] = (
            "\n".join(policy[0] for policy in results["passed_policies"]) if results["passed_policies"] else "None"
        )
        self.policy_summary["Failed Policies"] = (
            "\n".join(policy[0] for policy in results["failed_policies"]) if results["failed_policies"] else "None"
        )

        self.generate_policy_summary_table()

    def make_layout(self) -> Group:
        """Create the overall layout for the console output."""
        layout: list[RenderableType] = []
        if self.command == "analyze":
            layout = layout + [Rule(" DESCRIPTION", align="left")]
            if self.description_table.row_count > 0:
                layout = layout + ["", self.description_table]
            if self.progress_table.row_count > 0:
                layout = layout + ["", self.progress, "", self.progress_table]
            if self.failed_checks_table.row_count > 0:
                layout = layout + [
                    "",
                    Rule(" SUMMARY", align="left"),
                    "",
                    self.failed_checks_table,
                ]
                if self.summary_table.row_count > 0:
                    layout = layout + ["", self.summary_table]
                if self.report_table.row_count > 0:
                    layout = layout + [
                        self.report_table,
                    ]
            elif self.summary_table.row_count > 0:
                layout = layout + [
                    "",
                    Rule(" SUMMARY", align="left"),
                    "",
                    self.summary_table,
                ]
                if self.report_table.row_count > 0:
                    layout = layout + [
                        self.report_table,
                    ]
        elif self.command == "verify-policy":
            if self.policy_summary_table.row_count > 0:
                if self.components_violates_table.row_count > 0:
                    layout = layout + [
                        "[bold red] Components Violates Policy[/]",
                        self.components_violates_table,
                    ]
                else:
                    layout = layout + [
                        "[bold red] Components Violates Policy[/]   [white not italic]None[/]",
                    ]
                if self.components_satisfy_table.row_count > 0:
                    layout = layout + [
                        "",
                        "[bold green] Components Satisfy Policy[/]",
                        self.components_satisfy_table,
                    ]
                else:
                    layout = layout + [
                        "",
                        "[bold green] Components Satisfy Policy[/]  [white not italic]None[/]",
                    ]
                layout = layout + ["", self.policy_summary_table]
                if self.verification_summary_attestation:
                    vsa_table = Table(show_header=False, box=None)
                    vsa_table.add_column("Detail", justify="left")
                    vsa_table.add_column("Value", justify="left")

                    vsa_table.add_row(
                        "[bold blue]Verification Summary Attestation[/]",
                        self.verification_summary_attestation,
                    )

                    layout = layout + [vsa_table]

        if self.verbose:
            layout = layout + ["", self.verbose_panel]
        return Group(*layout)

    def start(self, command: str) -> None:
        """Start the live console display."""
        self.command = command
        if not self.live.is_started:
            self.live.start()

    def close(self) -> None:
        """Stop the live console display."""
        self.live.stop()


class AccessHandler:
    """A class to manage access to the RichConsoleHandler instance."""

    def __init__(self) -> None:
        self.verbose = False
        self.rich_handler = RichConsoleHandler()

    def set_handler(self, verbose: bool) -> RichConsoleHandler:
        """Set the verbosity and create a new RichConsoleHandler instance."""
        self.rich_handler = RichConsoleHandler(verbose)
        return self.rich_handler

    def get_handler(self) -> RichConsoleHandler:
        """Get the current RichConsoleHandler instance."""
        return self.rich_handler


access_handler = AccessHandler()
