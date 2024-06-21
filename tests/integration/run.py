# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Integration test utility."""

from __future__ import annotations

import argparse
import glob
import logging
import logging.config
import os
import shutil
import subprocess  # nosec B404
import sys
import time
from abc import abstractmethod
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Generic, TypedDict, TypeVar, cast

import cfgv  # type: ignore
from ruamel.yaml import YAML

T = TypeVar("T")

logger = logging.getLogger(sys.argv[0])

environ = dict(os.environ)
# Disable pulling the release docker image to test the locally built image instead.
environ["DOCKER_PULL"] = "never"


def patch_env(patch: Mapping[str, str | None]) -> dict[str, str]:
    """Patch env."""
    copied_env = dict(environ)  # Make a copy.

    for var, value in patch.items():
        if value is None:
            copied_env.pop(var, None)
        else:
            copied_env[var] = value

    return copied_env


def configure_logging(verbose: bool) -> None:
    """Configure logging."""
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": "[%(levelname)s|%(module)s]: %(message)s",
                },
                "verbose": {
                    "format": "[%(levelname)s|%(module)s|L%(lineno)d]: %(message)s",
                },
            },
            "handlers": {
                "stderr": {
                    "class": "logging.StreamHandler",
                    "level": "DEBUG" if verbose else "INFO",
                    "formatter": "verbose" if verbose else "standard",
                    "stream": "ext://sys.stderr",
                },
            },
            "root": {
                "level": "DEBUG",
                "handlers": ["stderr"],
            },
        }
    )


COMPARE_SCRIPTS: dict[str, Sequence[str]] = {
    "analysis_report": ["tests", "e2e", "compare_e2e_result.py"],
    "policy_report": ["tests", "policy_engine", "compare_policy_reports.py"],
    "deps_report": ["tests", "dependency_analyzer", "compare_dependencies.py"],
    "vsa": ["tests", "vsa", "compare_vsa.py"],
}


def check_required_file(cwd: str) -> Callable[[str], None]:
    """Check for a required file of a test case."""

    def _check(v: str) -> None:
        filepath = os.path.join(cwd, v)
        if not os.path.isfile(filepath):
            raise cfgv.ValidationError(f"File {filepath} does not exist.")

    return cast(Callable[[str], None], cfgv.check_and(cfgv.check_string, _check))


def check_env(env: object) -> None:
    """Check for a required file of a test case."""
    if not isinstance(env, dict):
        raise cfgv.ValidationError("Value of the 'env' field must be a dictionary.")
    for k, v in env.items():
        if not (v is None or isinstance(v, str)):
            raise cfgv.ValidationError(f"Value of key '{k}' is not a str or null.")


class StepConfig(TypedDict):
    """Configuration for a step."""

    name: str
    kind: str
    options: dict


@dataclass
class Step(Generic[T]):
    """A step in a test case."""

    step_id: int
    name: str
    options: T
    env: dict[str, str | None]
    expect_fail: bool

    @abstractmethod
    def cmd(self, macaron_cmd: str) -> list[str]:
        """Get the shell command of the step."""
        raise NotImplementedError()

    def show_command(self, macaron_cmd: str) -> None:
        """Log the command that the step runs."""
        args = self.cmd(macaron_cmd=macaron_cmd)
        logger.info("Step [%s] '%s'", self.step_id, self.name)
        logger.info("Command: '%s'", " ".join(args))

    def run_command(self, cwd: str, macaron_cmd: str) -> int:
        """Run the step."""
        args = self.cmd(macaron_cmd=macaron_cmd)
        logger.info("Start running step [%s] '%s'", self.step_id, self.name)
        logger.info("Command: '%s'", " ".join(args))

        start_time = time.monotonic_ns()
        res = subprocess.run(
            args=args,
            cwd=cwd,
            env=patch_env(self.env),
            check=False,
        )  # nosec: B603
        end_time = time.monotonic_ns()

        if self.expect_fail:
            if res.returncode == 0:
                logger.error(
                    "Command '%s' unexpectedly exited with zero code while non-zero code expected.",
                    " ".join(args),
                )
                return 1
        else:
            if res.returncode != 0:
                logger.error(
                    "Command '%s' unexpectedly exited with non-zero code.",
                    " ".join(args),
                )
                return 1

        time_taken = (end_time - start_time) / 1e9
        logger.info(
            "Time taken for step [%s] '%s': %.4f seconds.",
            *(self.step_id, self.name, time_taken),
        )
        return 0

    def run_interactively(self, cwd: str, macaron_cmd: str) -> int:
        """Run in interactive mode."""
        inp = None
        while inp not in ["y", "n"]:
            inp = input(f"> Run step [{self.step_id}] '{self.name}' ('y' for yes/'n' for no)? ")
        if inp == "y":
            return self.run_command(cwd=cwd, macaron_cmd=macaron_cmd)
        return 0


class ShellStepOptions(TypedDict):
    """The configuration options of a shell step."""

    cmd: str


@dataclass
class ShellStep(Step[ShellStepOptions]):
    """A shell step in a test case, which allows for running arbitrary shell commands."""

    @staticmethod
    def options_schema() -> cfgv.Map:
        """Generate the schema of a shell step."""
        return cfgv.Map(
            "shell options",
            None,
            *[
                cfgv.Required(key="cmd", check_fn=cfgv.check_string),
            ],
        )

    def cmd(self, macaron_cmd: str) -> list[str]:
        return self.options["cmd"].strip().split()


class CompareStepOptions(TypedDict):
    """Configuration of a compare step."""

    kind: str
    result: str
    expected: str


@dataclass
class CompareStep(Step[CompareStepOptions]):
    """A compare step."""

    @staticmethod
    def options_schema(cwd: str, check_expected_result_files: bool) -> cfgv.Map:
        """Generate the schema of a compare step."""
        if check_expected_result_files:
            check_file = check_required_file(cwd)
        else:
            check_file = cfgv.check_string

        return cfgv.Map(
            "compare options",
            None,
            *[
                cfgv.Required(
                    key="kind",
                    check_fn=cfgv.check_one_of(tuple(COMPARE_SCRIPTS.keys())),
                ),
                cfgv.Required(
                    key="result",
                    check_fn=cfgv.check_string,
                ),
                cfgv.Required(
                    key="expected",
                    check_fn=check_file,
                ),
            ],
        )

    def cmd(self, macaron_cmd: str) -> list[str]:
        kind = self.options["kind"]
        result_file = self.options["result"]
        expected_file = self.options["expected"]
        return [
            "python3",
            os.path.abspath(os.path.join(*COMPARE_SCRIPTS[kind])),
            *[result_file, expected_file],
        ]

    def run_interactively(self, cwd: str, macaron_cmd: str) -> int:
        """Run in interactive mode."""
        inp = None
        while inp not in ["y", "n", "u"]:
            inp = input(f"> Run step {[self.step_id]} '{self.name}' ('y' for yes/'n' for no/'u' for update)? ")
        if inp == "y":
            return self.run_command(cwd=cwd, macaron_cmd=macaron_cmd)
        if inp == "u":
            return self.update_result(cwd=cwd)
        return 0

    def update_result(self, cwd: str) -> int:
        """Update the expected result file."""
        kind = self.options["kind"]
        result_file = os.path.join(cwd, self.options["result"])
        expected_file = os.path.join(cwd, self.options["expected"])
        if kind == "vsa":
            proc = subprocess.run(
                args=[
                    "python3",
                    os.path.abspath(os.path.join(*COMPARE_SCRIPTS[kind])),
                    "--update",
                    *[result_file, expected_file],
                ],
                check=False,
            )  # nosec: B603
            if proc.returncode != 0:
                logger.error("Failed to update %s.", expected_file)
                return 1
        else:
            try:
                shutil.copy2(result_file, expected_file)
            except OSError as err:
                logger.error(
                    "Failed to copy %s to %s: %s",
                    *(result_file, expected_file, err),
                )
                return 1

        logger.info(
            "Updated %s %s from %s successfully.",
            *(kind, expected_file, result_file),
        )
        return 0


class AnalyzeStepOptions(TypedDict):
    """The configuration options of an analyze step."""

    main_args: Sequence[str]
    command_args: Sequence[str]
    ini: str | None
    expectation: str | None
    provenance: str | None
    sbom: str | None


@dataclass
class AnalyzeStep(Step):
    """A step running the ``macaron analyze`` command."""

    @staticmethod
    def options_schema(cwd: str) -> cfgv.Map:
        """Generate the schema of an analyze step."""
        return cfgv.Map(
            "analyze options",
            None,
            *[
                cfgv.NoAdditionalKeys(
                    [
                        "main_args",
                        "command_args",
                        "env",
                        "ini",
                        "expectation",
                        "provenance",
                        "sbom",
                    ],
                ),
                cfgv.Optional(
                    key="main_args",
                    check_fn=cfgv.check_array(cfgv.check_string),
                    default=[],
                ),
                cfgv.Optional(
                    key="command_args",
                    check_fn=cfgv.check_array(cfgv.check_string),
                    default=[],
                ),
                cfgv.Optional(
                    key="ini",
                    check_fn=check_required_file(cwd),
                    default=None,
                ),
                cfgv.Optional(
                    key="expectation",
                    check_fn=check_required_file(cwd),
                    default=None,
                ),
                cfgv.Optional(
                    key="provenance",
                    check_fn=check_required_file(cwd),
                    default=None,
                ),
                cfgv.Optional(
                    key="sbom",
                    check_fn=check_required_file(cwd),
                    default=None,
                ),
            ],
        )

    def cmd(self, macaron_cmd: str) -> list[str]:
        """Generate the command of the step."""
        args = [macaron_cmd]
        args.extend(self.options["main_args"])
        ini_file = self.options.get("ini", None)
        if ini_file is not None:
            args.extend(["--defaults-path", ini_file])
        args.append("analyze")
        expectation_file = self.options.get("expectation", None)
        if expectation_file is not None:
            args.extend(["--provenance-expectation", expectation_file])
        provenance_file = self.options.get("provenance", None)
        if provenance_file is not None:
            args.extend(["--provenance-file", provenance_file])
        sbom_file = self.options.get("sbom", None)
        if sbom_file is not None:
            args.extend(["--sbom-path", sbom_file])
        args.extend(self.options["command_args"])
        return args


class VerifyStepOptions(TypedDict):
    """The configuration options of a verify step."""

    main_args: Sequence[str]
    command_args: Sequence[str]
    database: str
    policy: str | None
    show_prelude: bool


@dataclass
class VerifyStep(Step[VerifyStepOptions]):
    """A step running the ``macaron verify-policy`` command."""

    @staticmethod
    def options_schema(cwd: str) -> cfgv.Map:
        """Generate the schema of a verify step."""
        return cfgv.Map(
            "verify options",
            None,
            *[
                cfgv.Optional(
                    key="main_args",
                    check_fn=cfgv.check_array(cfgv.check_string),
                    default=[],
                ),
                cfgv.Optional(
                    key="command_args",
                    check_fn=cfgv.check_array(cfgv.check_string),
                    default=[],
                ),
                cfgv.Optional(
                    key="database",
                    check_fn=cfgv.check_string,
                    default="./output/macaron.db",
                ),
                cfgv.Optional(
                    key="policy",
                    check_fn=check_required_file(cwd),
                    default=None,
                ),
                cfgv.Optional(
                    key="show_prelude",
                    check_fn=cfgv.check_bool,
                    default=False,
                ),
            ],
        )

    def cmd(self, macaron_cmd: str) -> list[str]:
        """Generate the command of the step."""
        args = [macaron_cmd]
        args.extend(self.options["main_args"])
        args.append("verify-policy")
        args.extend(["--database", self.options["database"]])
        args.extend(self.options["command_args"])
        policy_file = self.options["policy"]
        if policy_file is not None:
            args.extend(["--file", policy_file])
        show_prelude = self.options["show_prelude"]
        if show_prelude:
            args.extend(["--show-prelude"])
        return args


def gen_step_schema(cwd: str, check_expected_result_files: bool) -> cfgv.Map:
    """Generate schema for a step."""
    return cfgv.Map(
        "steps[*]",
        "name",
        *[
            cfgv.Required(
                key="name",
                check_fn=cfgv.check_string,
            ),
            cfgv.Required(
                key="kind",
                check_fn=cfgv.check_one_of(
                    (
                        "shell",
                        "compare",
                        "analyze",
                        "verify",
                    ),
                ),
            ),
            cfgv.ConditionalRecurse(
                condition_key="kind",
                condition_value="shell",
                key="options",
                schema=ShellStep.options_schema(),
            ),
            cfgv.ConditionalRecurse(
                condition_key="kind",
                condition_value="compare",
                key="options",
                schema=CompareStep.options_schema(
                    cwd=cwd,
                    check_expected_result_files=check_expected_result_files,
                ),
            ),
            cfgv.ConditionalRecurse(
                condition_key="kind",
                condition_value="analyze",
                key="options",
                schema=AnalyzeStep.options_schema(cwd=cwd),
            ),
            cfgv.ConditionalRecurse(
                condition_key="kind",
                condition_value="verify",
                key="options",
                schema=VerifyStep.options_schema(cwd=cwd),
            ),
            cfgv.Optional(
                key="env",
                check_fn=check_env,
                default={},
            ),
            cfgv.Optional(
                key="expect_fail",
                check_fn=cfgv.check_bool,
                default=False,
            ),
        ],
    )


class CaseConfig(TypedDict):
    """The configuration of a test case."""

    description: str
    tags: Sequence[str]
    steps: Sequence[StepConfig]


@dataclass
class Case:
    """A single test case."""

    case_dir: str
    description: str
    steps: list[Step]

    def run(self, macaron_cmd: str, interactive: bool, dry: bool) -> int:
        """Run the case."""
        logger.info("-" * 60)
        logger.info("Case started: '%s'.", self.case_dir)
        for line in self.description.strip().splitlines():
            logger.info("  %s", line)

        ret = 0

        # Clean up previous results
        output_dir = os.path.join(self.case_dir, "output")
        if not dry and os.path.isdir(output_dir):
            remove_output = True
            if interactive:
                inp = None
                while inp not in ["y", "n"]:
                    inp = input(f"> Remove {output_dir}? (y/n) ")
                if inp == "n":
                    remove_output = False
            if remove_output:
                logger.info("Removing old copy of '%s'", output_dir)
                shutil.rmtree(output_dir)

        for step in self.steps:
            if dry:
                step.show_command(macaron_cmd=macaron_cmd)
            elif interactive:
                ret = step.run_interactively(cwd=self.case_dir, macaron_cmd=macaron_cmd)
            else:
                ret = step.run_command(cwd=self.case_dir, macaron_cmd=macaron_cmd)
            if ret != 0:
                logger.error("Case failed: '%s'.", self.case_dir)
                return ret

        if not dry:
            logger.info("Case passed: '%s'.", self.case_dir)
        return 0

    def update(self, macaron_cmd: str) -> int:
        """Run the test case in update mode."""
        for step in self.steps:
            if isinstance(step, CompareStep):
                ret = step.update_result(cwd=self.case_dir)
            else:
                ret = step.run_command(cwd=self.case_dir, macaron_cmd=macaron_cmd)

            if ret != 0:
                return ret

        return 0

    @staticmethod
    def schema(cwd: str, check_expected_result_files: bool) -> cfgv.Map:
        """Generate the schema of a compare step."""
        return cfgv.Map(
            "test_case",
            None,
            *[
                cfgv.Required(
                    key="description",
                    check_fn=cfgv.check_string,
                ),
                cfgv.Optional(
                    key="tags",
                    check_fn=cfgv.check_array(cfgv.check_string),
                    default=[],
                ),
                cfgv.RequiredRecurse(
                    key="steps",
                    schema=cfgv.Array(
                        of=gen_step_schema(
                            cwd=cwd,
                            check_expected_result_files=check_expected_result_files,
                        ),
                        allow_empty=False,
                    ),
                ),
            ],
        )


def find_test_case_dirs_under(root_dir: str) -> set[str]:
    """Find all test case directories under a root directory.

    Each directory containing a ``test.yaml`` file is a test case directory.
    """
    test_case_dirs = set()
    for test_config_file in glob.iglob(f"{root_dir}/**/test.yaml", recursive=True):
        test_case_dir = os.path.dirname(test_config_file)
        test_case_dirs.add(test_case_dir)
    return test_case_dirs


def collect_test_case_dirs(test_case_dir_args: list[str]) -> list[str]:
    """Collect all test case directories given a list of CLI input arguments.

    Parameters
    ----------
    test_case_dir_args : list[str]
        Each test case directory argument should either:
        - Be a directory containing a ``test.yaml`` file, or
        - Be a glob ending with ``/...``, which triggers recursively searching
        subdirectories for those containing a ``test.yaml`` file.

    Returns
    -------
    list[str]
        Test case directories, each contains a ``test.yaml`` file.
    """
    test_case_dirs: set[str] = set()
    for test_case_dir in test_case_dir_args:
        if test_case_dir.endswith("/..."):
            test_case_dirs = test_case_dirs.union(find_test_case_dirs_under(root_dir=test_case_dir[:-4]))
        else:
            test_case_dirs.add(test_case_dir)
    return sorted(test_case_dirs)


class InvalidConfigError(cfgv.ValidationError):
    """Error raised when there is a schema error in a test config file."""


def load_config(
    test_config_dir: str,
    check_expected_result_files: bool,
) -> CaseConfig:
    """Load a test case config.

    Parameters
    ----------
    test_config_dir : str
        The test case directory containing a ``test.yaml`` file.
    check_expected_result_files : bool
        Whether to check for expected result files.

    Returns
    -------
    CaseConfig
        The configuration of the test case.
    """
    test_config_file = os.path.join(test_config_dir, "test.yaml")
    yaml = YAML(typ="safe")
    return cast(
        CaseConfig,
        cfgv.load_from_filename(
            filename=test_config_file,
            schema=Case.schema(
                check_expected_result_files=check_expected_result_files,
                cwd=test_config_dir,
            ),
            load_strategy=yaml.load,
            exc_tp=InvalidConfigError,
        ),
    )


def parse_step_config(step_id: int, step_config: Mapping) -> Step:
    """Parse the configuration of a step."""
    kind = step_config["kind"]
    step_cls = {
        "analyze": AnalyzeStep,
        "verify": VerifyStep,
        "shell": ShellStep,
        "compare": CompareStep,
    }[kind]
    return step_cls(  # type: ignore  # https://github.com/python/mypy/issues/3115
        step_id=step_id,
        name=step_config["name"],
        options=step_config["options"],
        env=step_config["env"],
        expect_fail=step_config["expect_fail"],
    )


def load_test_cases(
    test_case_dirs: list[str],
    check_expected_result_files: bool,
    include_tags: list[str] | None = None,
    exclude_tags: list[str] | None = None,
) -> list[Case] | None:
    """Load the test cases from the test case directories.

    Parameters
    ----------
    test_case_dirs : list[str]
        Test case directores.
    check_expected_result_files : bool
        Whether to check if expected result files are valid.
    include_tags : list[str] | None
        A selected test case must contain all of these tags.
    exclude_tags : list[str] | None
        A selected test case must not contain any of these tags.
    """
    include_tags = include_tags or []
    exclude_tags = exclude_tags or []

    err = False
    test_cases: list[Case] = []

    for test_case_dir in test_case_dirs:
        try:
            case_config = load_config(test_case_dir, check_expected_result_files)
        except InvalidConfigError as exc:
            logger.error("Case '%s' fails validation.", test_case_dir)
            logger.error(exc.error_msg)
            err = True
        else:
            # Each --include-tag/--exclude-tag argument adds an additional constraint
            # that a selected test case needs to satisfy, i.e. a selected test case must:
            # - contains all tags specified with --include-tag
            # - contains no tag specified with --exclude-tag
            select_case = True
            for include_tag in include_tags:
                if include_tag not in case_config["tags"]:
                    logger.info(
                        "Skipping case '%s' for not having tag '%s'.",
                        *(test_case_dir, include_tag),
                    )
                    select_case = False
                    break
            for exclude_tag in exclude_tags:
                if exclude_tag in case_config["tags"]:
                    logger.info(
                        "Skipping case '%s' for having tag '%s'",
                        *(test_case_dir, exclude_tag),
                    )
                    select_case = False
                    break
            if not select_case:
                continue
            steps = []
            for step_id, step_config in enumerate(case_config["steps"]):
                step = parse_step_config(step_id, step_config)
                steps.append(step)
            test_case = Case(
                case_dir=test_case_dir,
                description=case_config["description"],
                steps=steps,
            )
            test_cases.append(test_case)
            logger.info("Case '%s' passes validation.", test_case_dir)

    if err:
        logger.error("Error encountered while loading test config.")
        return None

    return test_cases


def do_check(test_case_dirs: list[str], check_expected_result_files: bool) -> int:
    """Execute the check command."""
    test_cases = load_test_cases(
        test_case_dirs,
        check_expected_result_files=check_expected_result_files,
    )
    if test_cases is None:
        return 1
    return 0


def do_run(
    test_case_dirs: list[str],
    macaron_cmd: str,
    include_tags: list[str],
    exclude_tags: list[str],
    interactive: bool,
    dry: bool,
) -> int:
    """Execute the run command."""
    test_cases = load_test_cases(
        test_case_dirs,
        check_expected_result_files=not interactive,
        include_tags=include_tags,
        exclude_tags=exclude_tags,
    )

    if test_cases is None:
        return 1

    logger.info("Running the following test cases:")
    for test_case in test_cases:
        logger.info("* %s", test_case.case_dir)

    for test_case in test_cases:
        ret = test_case.run(
            macaron_cmd=macaron_cmd,
            interactive=interactive,
            dry=dry,
        )
        if ret != 0:
            return ret
    return 0


def do_update(
    test_case_dirs: list[str],
    macaron_cmd: str,
    include_tags: list[str],
    exclude_tags: list[str],
) -> int:
    """Execute the update command."""
    test_cases = load_test_cases(
        test_case_dirs,
        check_expected_result_files=False,
        include_tags=include_tags,
        exclude_tags=exclude_tags,
    )
    if test_cases is None:
        return 1

    ret = 0
    for test_case in test_cases:
        ret = test_case.update(macaron_cmd)
        if ret != 0:
            return ret
    return ret


def main(argv: Sequence[str] | None = None) -> int:
    """Run main logic."""
    arg_parser = argparse.ArgumentParser(sys.argv[0])

    shared_arguments_parser = argparse.ArgumentParser(add_help=False)
    shared_arguments_parser.add_argument(
        "test_case_dirs",
        help="Test data directories. Use the `...` wildcard to discover test case directories recursively.",
        nargs="+",
    )
    shared_arguments_parser.add_argument(
        *("-v", "--verbose"),
        help="Enable verbose logging",
        action="store_true",
        default=False,
    )

    command_parsers = arg_parser.add_subparsers(
        dest="command",
        required=True,
        help="The command to run.",
    )

    command_parsers.add_parser(
        name="check",
        parents=[shared_arguments_parser],
        help="Schema-validate test case config files in the test case directories.",
    )

    command_parsers.add_parser(
        name="vet",
        parents=[shared_arguments_parser],
        help="Validate test case directories.",
    )

    run_parser = command_parsers.add_parser(
        name="run",
        parents=[shared_arguments_parser],
        help="Run test cases in the test data directory.",
    )
    run_parser.add_argument(
        *("-t", "--include-tag"),
        help=(
            "Select only test cases having the tag. "
            "This can be specified multiple times, which will select only cases that have all include tags."
        ),
        action="append",
        default=[],
    )
    run_parser.add_argument(
        *("-e", "--exclude-tag"),
        help=(
            "Select only test cases not having the tag. "
            "This can be specified multiple times, which will select only cases that do not have any exclude tags."
        ),
        action="append",
        default=[],
    )
    run_parser.add_argument(
        *("-m", "--macaron"),
        help="The command to run Macaron. Note: can be path to the run_macaron.sh script.",
        default="macaron",
    )
    run_mode_group = run_parser.add_argument_group(
        title="Run mode",
        description="Special run modes",
    ).add_mutually_exclusive_group()
    run_mode_group.add_argument(
        *("-i", "--interactive"),
        action="store_true",
        help="Run the test cases in interactive mode.",
    )
    run_mode_group.add_argument(
        *("-d", "--dry"),
        action="store_true",
        help=(
            "Run the test cases in dry mode, which does not run any command "
            "but only shows the commands running during a test case."
        ),
    )

    update_parser = command_parsers.add_parser(
        name="update",
        parents=[shared_arguments_parser],
        help="Run test cases, but update expected output files instead of comparing them with expected output.",
    )
    update_parser.add_argument(
        *("-m", "--macaron"),
        help="The command to run Macaron. Note: can be path to the run_macaron.sh script.",
        default="macaron",
    )

    args = arg_parser.parse_args(argv)
    configure_logging(args.verbose)

    test_case_dirs = collect_test_case_dirs(args.test_case_dirs)

    logger.info("Discovered the following test cases:")
    for test_case_dir in test_case_dirs:
        logger.info("* %s", test_case_dir)

    if args.command == "check":
        return do_check(
            test_case_dirs=test_case_dirs,
            check_expected_result_files=False,
        )
    if args.command == "vet":
        return do_check(
            test_case_dirs=test_case_dirs,
            check_expected_result_files=True,
        )

    for script_key, script_relpath in COMPARE_SCRIPTS.items():
        script_path = os.path.join(".", *script_relpath)
        if not os.path.isfile(script_path):
            logger.error(
                "Compare script for '%s' does not exist at '%s'.",
                *(script_key, script_path),
            )
            return 1

    path = shutil.which(args.macaron)
    if path is None:
        logger.error("'%s' is not a command.")
        return 1
    macaron_cmd = os.path.abspath(path)

    if args.command == "run":
        return do_run(
            test_case_dirs=test_case_dirs,
            macaron_cmd=macaron_cmd,
            include_tags=args.include_tag,
            exclude_tags=args.exclude_tag,
            interactive=args.interactive,
            dry=args.dry,
        )
    if args.command == "update":
        return do_update(
            test_case_dirs=test_case_dirs,
            macaron_cmd=macaron_cmd,
            include_tags=args.include_tag,
            exclude_tags=args.exclude_tag,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
