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


class TableBuilder:
    """Builder to provide common table-building utilities for console classes."""

    @staticmethod
    def _make_table(content: dict, columns: list[str]) -> Table:
        table = Table(show_header=False, box=None)
        for col in columns:
            table.add_column(col, justify="left")
        for field, value in content.items():
            table.add_row(field, value)
        return table

    @staticmethod
    def _make_checks_table(checks: dict[str, str]) -> Table:
        table = Table(show_header=False, box=None)
        table.add_column("Status", justify="left")
        table.add_column("Check", justify="left")
        for check_name, check_status in checks.items():
            if check_status == "RUNNING":
                table.add_row(Status("[bold green]RUNNING[/]"), check_name)
        return table

    @staticmethod
    def _make_failed_checks_table(failed_checks: list) -> Table:
        table = Table(show_header=False, box=None)
        table.add_column("Status", justify="left")
        table.add_column("Check ID", justify="left")
        table.add_column("Description", justify="left")
        for check in failed_checks:
            table.add_row("[bold red]FAILED[/]", check.check.check_id, check.check.check_description)
        return table

    @staticmethod
    def _make_summary_table(checks_summary: dict, total_checks: int) -> Table:
        table = Table(show_header=False, box=None)
        table.add_column("Check Result Type", justify="left")
        table.add_column("Count", justify="left")
        table.add_row("Total Checks", str(total_checks), style="white")
        color_map = {
            "PASSED": "green",
            "FAILED": "red",
            "SKIPPED": "yellow",
            "DISABLED": "bright_blue",
            "UNKNOWN": "white",
        }
        for check_result_type, checks in checks_summary.items():
            if check_result_type in color_map:
                table.add_row(check_result_type, str(len(checks)), style=color_map[check_result_type])
        return table

    @staticmethod
    def _make_reports_table(reports: dict) -> Table:
        table = Table(show_header=False, box=None)
        table.add_column("Report Type", justify="left")
        table.add_column("Report Path", justify="left")
        for report_type, report_path in reports.items():
            table.add_row(report_type, report_path, style="blue")
        return table


class Dependency(TableBuilder):
    """A class to manage the display of dependency analysis in the console."""

    def __init__(self) -> None:
        """Initialize the Dependency instance with default values and tables."""
        self.description_table = Table(show_header=False, box=None)
        self.description_table_content: dict[str, str | Status] = {
            "Package URL:": Status("[green]Processing[/]"),
            "Local Cloned Path:": Status("[green]Processing[/]"),
            "Remote Path:": Status("[green]Processing[/]"),
            "Branch:": Status("[green]Processing[/]"),
            "Commit Hash:": Status("[green]Processing[/]"),
            "Commit Date:": Status("[green]Processing[/]"),
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
        self.checks: dict[str, str] = {}
        self.failed_checks_table = Table(show_header=False, box=None)
        self.summary_table = Table(show_header=False, box=None)
        self.report_table = Table(show_header=False, box=None)
        self.reports = {
            "HTML Report": "Not Generated",
            "Dependencies Report": "Not Generated",
            "JSON Report": "Not Generated",
        }

    def add_description_table_content(self, key: str, value: str | Status) -> None:
        """
        Add or update a key-value pair in the description table.

        Parameters
        ----------
        key : str
            The key to be added or updated.
        value : str or Status
            The value associated with the key.
        """
        self.description_table_content[key] = value
        self.description_table = self._make_table(self.description_table_content, ["Details", "Value"])

    def no_of_checks(self, value: int) -> None:
        """
        Initialize the progress bar with the total number of checks.

        Parameters
        ----------
        value : int
            The total number of checks to be performed.
        """
        self.task_id = self.progress.add_task("analyzing", total=value)

    def remove_progress_bar(self) -> None:
        """Remove the progress bar from the display."""
        self.progress.remove_task(self.task_id)

    def update_checks(self, check_id: str, status: str = "RUNNING") -> None:
        """
        Update the status of a specific check and refresh the progress table.

        Parameters
        ----------
        check_id : str
            The identifier of the check to be updated.
        status : str, optional
            The new status of the check, by default "RUNNING"
        """
        self.checks[check_id] = status
        self.progress_table = self._make_checks_table(self.checks)
        if self.task_id is not None and status != "RUNNING":
            self.progress.update(self.task_id, advance=1)

    def update_checks_summary(self, checks_summary: dict, total_checks: int) -> None:
        """
        Update the summary tables with the results of the checks.

        Parameters
        ----------
        checks_summary : dict
            Dictionary containing lists of checks categorized by their results.
        total_checks : int
            The total number of checks.
        """
        self.failed_checks_table = self._make_failed_checks_table(checks_summary.get("FAILED", []))
        self.summary_table = self._make_summary_table(checks_summary, total_checks)

    def update_report_table(self, report_type: str, report_path: str) -> None:
        """
        Update the report table with the path of a generated report.

        Parameters
        ----------
        report_type : str
            The type of the report (e.g., "HTML Report", "JSON Report").
        report_path : str
            The relative path to the generated report.
        """
        self.reports[report_type] = report_path
        self.report_table = self._make_reports_table(self.reports)

    def mark_failed(self) -> None:
        """Convert any Processing Status entries to Failed."""
        for key, value in self.description_table_content.items():
            if isinstance(value, Status):
                self.description_table_content[key] = "[red]Failed[/red]"

        self.description_table = self._make_table(self.description_table_content, ["Details", "Value"])

    def make_layout(self) -> list[RenderableType]:
        """
        Create the layout for the live console display.

        Returns
        -------
        list[RenderableType]
            A list of rich RenderableType objects containing the layout for the live console display.
        """
        layout: list[RenderableType] = []
        if self.description_table.row_count > 0:
            layout = layout + [
                "",
                self.description_table,
            ]
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
        return layout


class RichConsoleHandler(RichHandler, TableBuilder):
    """A rich console handler for logging with rich formatting and live updates."""

    def __init__(self, *args: Any, verbose: bool = False, **kwargs: Any) -> None:
        """
        Initialize the RichConsoleHandler.

        Parameters
        ----------
        verbose : bool, optional
            if True, enables verbose logging, by default False
        args
            Variable length argument list.
        kwargs
            Arbitrary keyword arguments.
        """
        super().__init__(*args, **kwargs)
        self.setLevel(logging.DEBUG)
        self.command = ""
        self.logs: list[str] = []
        self.error_logs: list[str] = []
        self.description_table = Table(show_header=False, box=None)
        self.description_table_content: dict[str, str | Status] = {
            "Package URL:": Status("[green]Processing[/]"),
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
        self.checks: dict[str, str] = {}
        self.failed_checks_table = Table(show_header=False, box=None)
        self.summary_table = Table(show_header=False, box=None)
        self.report_table = Table(show_header=False, box=None)
        self.reports = {
            "HTML Report": "Not Generated",
            "Dependencies Report": "Not Generated",
            "JSON Report": "Not Generated",
        }
        self.if_dependency: bool = False
        self.dependency_analysis_map: dict[str, int] = {}
        self.dependency_analysis_list: list[Dependency] = []
        self.components_violates_table = Table(box=None)
        self.components_satisfy_table = Table(box=None)
        self.policy_summary_table = Table(show_header=False, box=None)
        self.policy_summary: dict[str, str | Status] = {
            "Passed Policies": "None",
            "Failed Policies": "None",
            "Policy Report": Status("[green]Generating[/]"),
        }
        self.verification_summary_attestation: str | None = None
        self.find_source_table = Table(show_header=False, box=None)
        self.find_source_content: dict[str, str | Status] = {
            "Repository URL:": Status("[green]Processing[/]"),
            "Commit Hash:": Status("[green]Processing[/]"),
            "JSON Report:": "Not Generated",
        }
        for key, value in self.find_source_content.items():
            self.find_source_table.add_row(key, value)
        self.dump_defaults: str | Status = Status("[green]Generating[/]")
        self.gen_build_spec: dict[str, str | Status] = {
            "Build Spec Path:": "Not Generated",
        }
        self.gen_build_spec_table = Table(show_header=False, box=None)
        for key, value in self.gen_build_spec.items():
            self.gen_build_spec_table.add_row(key, value)
        self.verbose = verbose
        self.verbose_panel = Panel(
            "\n".join(self.logs),
            title="Verbose Mode",
            title_align="left",
            border_style="blue",
        )
        self.error_message: str = ""
        self.live = Live(get_renderable=self.make_layout, refresh_per_second=10)

    def emit(self, record: logging.LogRecord) -> None:
        """
        Emit a log record with rich formatting.

        Parameters
        ----------
        record : logging.LogRecord
            The log record to be emitted.
        """
        log_time = time.strftime("%H:%M:%S")
        msg = self.format(record)

        if record.levelno >= logging.ERROR:
            self.logs.append(f"[red][ERROR][/red] {log_time} {msg}")
            self.error_logs.append(f"[red][ERROR][/red] {log_time} {msg}")
        elif record.levelno >= logging.WARNING:
            self.logs.append(f"[yellow][WARNING][/yellow] {log_time} {msg}")
        else:
            self.logs.append(f"[blue][INFO][/blue] {log_time} {msg}")

        self.verbose_panel.renderable = "\n".join(self.logs)

    def add_description_table_content(self, key: str, value: str | Status) -> None:
        """
        Add or update a key-value pair in the description table.

        Parameters
        ----------
        key : str
            The key to be added or updated.
        value : str or Status
            The value associated with the key.
        """
        if self.if_dependency and self.dependency_analysis_list:
            self.dependency_analysis_list[-1].add_description_table_content(key, value)
            return
        self.description_table_content[key] = value
        self.description_table = self._make_table(self.description_table_content, ["Details", "Value"])

    def no_of_checks(self, value: int) -> None:
        """
        Initialize the progress bar with the total number of checks.

        Parameters
        ----------
        value : int
            The total number of checks to be performed.
        """
        if self.if_dependency and self.dependency_analysis_list:
            dependency = self.dependency_analysis_list[-1]
            dependency.no_of_checks(value)
            return
        self.task_id = self.progress.add_task("analyzing", total=value)

    def remove_progress_bar(self) -> None:
        """Remove the progress bar from the display."""
        if self.if_dependency and self.dependency_analysis_list:
            dependency = self.dependency_analysis_list[-1]
            dependency.remove_progress_bar()
            return
        self.progress.remove_task(self.task_id)

    def update_checks(self, check_id: str, status: str = "RUNNING") -> None:
        """
        Update the status of a specific check and refresh the progress table.

        Parameters
        ----------
        check_id : str
            The identifier of the check to be updated.
        status : str, optional
            The new status of the check, by default "RUNNING"
        """
        if self.if_dependency and self.dependency_analysis_list:
            self.dependency_analysis_list[-1].update_checks(check_id, status)
            return
        self.checks[check_id] = status
        self.progress_table = self._make_checks_table(self.checks)
        if self.task_id is not None and status != "RUNNING":
            self.progress.update(self.task_id, advance=1)

    def update_checks_summary(self, checks_summary: dict, total_checks: int) -> None:
        """
        Update the summary tables with the results of the checks.

        Parameters
        ----------
        checks_summary : dict
            Dictionary containing lists of checks categorized by their results.
        total_checks : int
            The total number of checks.
        """
        if self.if_dependency and self.dependency_analysis_list:
            self.dependency_analysis_list[-1].update_checks_summary(checks_summary, total_checks)
            return
        self.failed_checks_table = self._make_failed_checks_table(checks_summary.get("FAILED", []))
        self.summary_table = self._make_summary_table(checks_summary, total_checks)

    def update_report_table(self, report_type: str, report_path: str, record_id: str = "") -> None:
        """
        Update the report table with the path of a generated report.

        Parameters
        ----------
        report_type : str
            The type of the report (e.g., "HTML Report", "JSON Report").
        report_path : str
            The relative path to the generated report.
        """
        if self.reports[report_type] == "Not Generated":
            self.reports[report_type] = report_path
            self.report_table = self._make_reports_table(self.reports)
        elif record_id and record_id in self.dependency_analysis_map:
            record_ind = self.dependency_analysis_map[record_id]
            self.dependency_analysis_list[record_ind].update_report_table(report_type, report_path)

    def is_dependency(self, value: bool, record_id: str) -> None:
        """
        Update the flag indicating whether the analyzed package is a dependency.

        Parameters
        ----------
        value : bool
            True if the package is a dependency, False otherwise.
        """
        self.if_dependency = value
        if self.if_dependency:
            dependency = Dependency()
            self.dependency_analysis_map[record_id] = len(self.dependency_analysis_list)
            self.dependency_analysis_list.append(dependency)

    def generate_policy_summary_table(self) -> None:
        """Generate the policy summary table based on the current policy summary data."""
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
        """
        Update the policy report path in the policy summary.

        Parameters
        ----------
        report_path : str
            The relative path to the policy report.
        """
        self.policy_summary["Policy Report"] = report_path
        self.generate_policy_summary_table()

    def update_vsa(self, vsa_path: str) -> None:
        """
        Update the verification summary attestation path.

        Parameters
        ----------
        vsa_path : str
            The relative path to the verification summary attestation.
        """
        self.verification_summary_attestation = vsa_path

    def update_policy_engine(self, results: dict) -> None:
        """
        Update the policy engine results including components that violate or satisfy policies.

        Parameters
        ----------
        results : dict
            Dictionary containing policy engine results including components that violate or satisfy policies,
            and lists of passed and failed policies.
        """
        components_violates_table = Table(box=None)
        components_violates_table.add_column("Component ID", justify="left")
        components_violates_table.add_column("PURL", justify="left")
        components_violates_table.add_column("Policy Name", justify="left")

        for values in results["component_violates_policy"]:
            components_violates_table.add_row(values[0], values[1], values[2])

        self.components_violates_table = components_violates_table

        components_satisfy_table = Table(box=None)
        components_satisfy_table.add_column("Component ID", justify="left")
        components_satisfy_table.add_column("PURL", justify="left")
        components_satisfy_table.add_column("Policy Name", justify="left")

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

    def update_find_source_table(self, key: str, value: str | Status) -> None:
        """
        Add or update a key-value pair in the find source table.

        Parameters
        ----------
        key : str
            The key to be added or updated.
        value : str or Status
            The value associated with the key.
        """
        self.find_source_content[key] = value
        self.find_source_table = self._make_table(self.find_source_content, ["Details", "Value"])

    def update_dump_defaults(self, value: str | Status) -> None:
        """
        Update the dump defaults value.

        Parameters
        ----------
        value : str or Status
            The value to be set for dump defaults.
        """
        self.dump_defaults = value

    def update_gen_build_spec(self, key: str, value: str | Status) -> None:
        """
        Add or update a key-value pair in the generate build spec table.

        Parameters
        ----------
        key : str
            The key to be added or updated.
        value : str or Status
            The value associated with the key.
        """
        self.gen_build_spec[key] = value
        self.gen_build_spec_table = self._make_table(self.gen_build_spec, ["Details", "Value"])

    def mark_failed(self) -> None:
        """Convert any Processing Status entries to Failed."""
        for key, value in self.description_table_content.items():
            if isinstance(value, Status):
                self.description_table_content[key] = "[red]Failed[/red]"

        self.description_table = self._make_table(self.description_table_content, ["Details", "Value"])

        for key, value in self.find_source_content.items():
            if isinstance(value, Status):
                self.find_source_content[key] = "[red]Failed[/red]"

        self.find_source_table = self._make_table(self.find_source_content, ["Details", "Value"])

        for key, value in self.gen_build_spec.items():
            if isinstance(value, Status):
                self.gen_build_spec[key] = "[red]Failed[/red]"

        self.gen_build_spec_table = self._make_table(self.gen_build_spec, ["Details", "Value"])

        if self.if_dependency and self.dependency_analysis_list:
            for dependency in self.dependency_analysis_list:
                dependency.mark_failed()

    def make_layout(self) -> Group:
        """
        Create the layout for the live console display.

        Returns
        -------
        Group
            A rich Group object containing the layout for the live console display.
        """
        layout: list[RenderableType] = []
        if self.error_logs:
            error_log_panel = Panel(
                "\n".join(self.error_logs),
                title="Error Logs",
                title_align="left",
                border_style="red",
            )
            layout = layout + [error_log_panel]
        if self.command == "analyze":
            if self.description_table.row_count > 0:
                layout = layout + [
                    Rule(" DESCRIPTION", align="left"),
                    "",
                    self.description_table,
                ]
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
            if self.if_dependency and self.dependency_analysis_list:
                for idx, dependency in enumerate(self.dependency_analysis_list, start=1):
                    dependency_layout = dependency.make_layout()
                    layout = (
                        layout
                        + [
                            "",
                            Rule(f" DEPENDENCY {idx}", align="left"),
                        ]
                        + dependency_layout
                    )
        elif self.command == "verify-policy":
            if self.policy_summary_table.row_count > 0:
                if self.components_satisfy_table.row_count > 0:
                    layout = layout + [
                        "[bold green] Components Satisfy Policy[/]",
                        self.components_satisfy_table,
                    ]
                else:
                    layout = layout + [
                        "[bold green] Components Satisfy Policy[/]  [white not italic]None[/]",
                    ]
                if self.components_violates_table.row_count > 0:
                    layout = layout + [
                        "",
                        "[bold red] Components Violate Policy[/]",
                        self.components_violates_table,
                    ]
                else:
                    layout = layout + [
                        "",
                        "[bold red] Components Violate Policy[/]   [white not italic]None[/]",
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
                    if self.verification_summary_attestation != "No VSA generated.":
                        vsa_table.add_row(
                            "[bold blue]Decode and Inspect the Content[/]",
                            f"cat {self.verification_summary_attestation} | jq -r [white]'.payload'[/] | base64 -d | jq",
                        )

                    layout = layout + [vsa_table]
        elif self.command == "find-source":
            if self.find_source_table.row_count > 0:
                layout = layout + [self.find_source_table]
        elif self.command == "dump-defaults":
            dump_defaults_table = Table(show_header=False, box=None)
            dump_defaults_table.add_column("Detail", justify="left")
            dump_defaults_table.add_column("Value", justify="left")
            dump_defaults_table.add_row("Dump Defaults", self.dump_defaults)
            layout = layout + [dump_defaults_table]
        elif self.command == "gen-build-spec":
            if self.gen_build_spec_table.row_count > 0:
                layout = layout + [self.gen_build_spec_table]
        if self.verbose:
            layout = layout + ["", self.verbose_panel]
        if self.error_message:
            error_panel = Panel(
                self.error_message,
                title="Error",
                title_align="left",
                border_style="red",
            )
            layout = layout + ["", error_panel]
        return Group(*layout)

    def error(self, message: str) -> None:
        """
        Handle error logging.

        Parameters
        ----------
        message : str
            The error message to be logged.
        """
        self.error_message = message

    def start(self, command: str) -> None:
        """
        Start the live console display.

        Parameters
        ----------
        command : str
            The command being executed (e.g., "analyze", "verify-policy").
        """
        self.command = command
        if not self.live.is_started:
            self.live.start()

    def close(self) -> None:
        """Stop the live console display."""
        self.live.stop()


class AccessHandler:
    """A class to manage access to the RichConsoleHandler instance."""

    def __init__(self) -> None:
        """Initialize the AccessHandler with a default RichConsoleHandler instance."""
        self.rich_handler = RichConsoleHandler()

    def set_handler(self, verbose: bool) -> RichConsoleHandler:
        """
        Set a new RichConsoleHandler instance with the specified verbosity.

        Parameters
        ----------
        verbose : bool
            if True, enables verbose logging

        Returns
        -------
        RichConsoleHandler
            The new RichConsoleHandler instance.
        """
        self.rich_handler = RichConsoleHandler(verbose=verbose)
        return self.rich_handler

    def get_handler(self) -> RichConsoleHandler:
        """
        Get the current RichConsoleHandler instance.

        Returns
        -------
        RichConsoleHandler
            The current RichConsoleHandler instance.
        """
        return self.rich_handler


access_handler = AccessHandler()
