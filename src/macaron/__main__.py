# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This is the main entrypoint to run Macaron."""

import argparse
import logging
import os
import sys

from jinja2 import Environment, FileSystemLoader, select_autoescape
from yamale.schema.validationresults import ValidationResult

import macaron
from macaron.config.defaults import create_defaults, load_defaults
from macaron.config.global_config import global_config
from macaron.config.target_config import TARGET_CONFIG_SCHEMA
from macaron.output_reporter.reporter import HTMLReporter, JSONReporter
from macaron.parsers.yaml.loader import YamlLoader
from macaron.policy_engine.policy import Policy, PolicyRuntimeError
from macaron.slsa_analyzer.analyzer import Analyzer
from macaron.slsa_analyzer.provenance.loader import ProvPayloadLoader, SLSAProvenanceError

logger: logging.Logger = logging.getLogger(__name__)


def analyze_slsa_levels_single(analyzer_single_args: argparse.Namespace) -> None:
    """Run the SLSA checks against a single target repository."""
    analyzer = Analyzer(global_config.output_path, global_config.build_log_path)

    # Initiate reporters.
    if analyzer_single_args.template_path:
        custom_jinja_env = Environment(
            loader=FileSystemLoader(os.path.dirname(str(analyzer_single_args.template_path))),
            autoescape=select_autoescape(enabled_extensions=["html", "j2"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        html_reporter = HTMLReporter(
            env=custom_jinja_env, target_template=os.path.basename(analyzer_single_args.template_path)
        )
        if not html_reporter.template:
            logger.error("Exiting because the custom template cannot be found.")
            sys.exit(1)

        analyzer.reporters.append(html_reporter)
    else:
        analyzer.reporters.append(HTMLReporter())
    analyzer.reporters.append(JSONReporter())

    run_config = {}

    if analyzer_single_args.repo_path:
        # Generate a config dict similar to a config read from user yaml file.
        run_config = {
            "target": {
                "id": analyzer_single_args.repo_path,
                "path": analyzer_single_args.repo_path,
                "branch": analyzer_single_args.branch,
                "digest": analyzer_single_args.digest,
            },
            "dependencies": [],
        }
        validate_result: ValidationResult = TARGET_CONFIG_SCHEMA.validate(run_config, "config_generated", strict=False)
        if not validate_result.isValid():
            logger.critical("The generated config dict is invalid.")
            sys.exit(1)

    elif analyzer_single_args.config_path:
        # Get user config from yaml file
        run_config = YamlLoader.load(analyzer_single_args.config_path)

    status_code = analyzer.run(run_config, analyzer_single_args.skip_deps)
    sys.exit(status_code)


def verify_prov(verify_args: argparse.Namespace) -> None:
    """Verify a provenance against a user defined policy."""
    prov_file = verify_args.provenance
    policy_file = verify_args.policy

    if not policy_file:
        logger.error("The policy is not provided to complete this action.")
        sys.exit(1)

    try:
        prov_content = ProvPayloadLoader.load(prov_file)
        policy: Policy | None = Policy.make_policy(policy_file)

        if not policy:
            logger.error("Could not load policy at %s.", policy_file)
            sys.exit(1)

        logger.info("Validating the provenance at %s against %s.", prov_file, policy)

        if not policy.validate(prov_content):
            logger.error("The validation for provenance at %s is unsuccessful.", prov_file)
            sys.exit(1)

        logger.info("The validation for provenance at %s is successful.", prov_file)
        sys.exit(0)
    except (SLSAProvenanceError, PolicyRuntimeError) as error:
        logger.error(error)
        sys.exit(1)


def perform_action(action_args: argparse.Namespace) -> None:
    """Perform the indicated action of Macaron."""
    if action_args.action == "dump_defaults":
        # Create the defaults.ini file in the output dir and exit.
        create_defaults(action_args.output_dir, os.getcwd())
        sys.exit(0)

    # Check that the GitHub token is enabled.
    if not action_args.personal_access_token:
        raise argparse.ArgumentError(None, "GitHub access token not set.")

    match action_args.action:
        case "analyze":
            analyze_slsa_levels_single(action_args)
        case "verify":
            verify_prov(action_args)
        case _:
            logger.error("Macaron does not support command option %s.", action_args.action)
            sys.exit(1)


def main() -> None:
    """Execute Macaron as a standalone command-line tool."""
    main_parser = argparse.ArgumentParser(prog="macaron")
    main_parser.add_argument("-v", "--verbose", help="Run Macaron with more debug logs", action="store_true")
    main_parser.add_argument(
        "-t",
        "--personal_access_token",
        required=False,
        help="The GitHub personal access token, which is mandatory for running analysis.",
    )
    main_parser.add_argument(
        "-o",
        "--output-dir",
        default=os.path.join(os.getcwd(), "output"),
        help="The output destination path for Macaron",
    )

    main_parser.add_argument(
        "-dp",
        "--defaults-path",
        default=os.path.join(os.getcwd(), "defaults.ini"),
        help="The path to the defaults configuration file.",
    )

    main_parser.add_argument(
        "-lr",
        "--local-repos-path",
        default="",
        help="The directory where Macaron looks for already cloned repositories.",
    )

    main_parser.add_argument(
        "-po", "--policy", required=False, default="", type=str, help=("The path to the policy yaml file.")
    )

    # Add sub parsers for each action
    sub_parser = main_parser.add_subparsers(dest="action", help="Run macaron <action> --help for help")

    # Use Macaron to analyze one single repository.
    single_analyze_parser = sub_parser.add_parser(name="analyze")
    group = single_analyze_parser.add_mutually_exclusive_group(required=True)

    group.add_argument(
        "-rp",
        "--repo-path",
        required=False,
        type=str,
        help=("The path to the repository, can be local or remote"),
    )

    single_analyze_parser.add_argument(
        "-b",
        "--branch",
        required=False,
        type=str,
        default="",
        help=("The branch of the repository that we want to checkout. If not set, Macaron will use the default branch"),
    )

    single_analyze_parser.add_argument(
        "-d",
        "--digest",
        required=False,
        type=str,
        default="",
        help=(
            "The digest of the commit we want to checkout in the branch. "
            + "If not set, Macaron will use the latest commit"
        ),
    )

    group.add_argument(
        "-c",
        "--config-path",
        required=False,
        type=str,
        default="",
        help=("The path to the user configuration."),
    )

    single_analyze_parser.add_argument(
        "--skip-deps",
        required=False,
        action="store_true",
        default=False,
        help=("Skip automatic dependency analysis."),
    )

    single_analyze_parser.add_argument(
        "-g",
        "--template-path",
        required=False,
        type=str,
        default="",
        help=("The path to the Jinja2 html template (please make sure to use .html or .j2 extensions)."),
    )

    # Dump the default values.
    sub_parser.add_parser(name="dump_defaults", description="Dumps the defaults.ini file to the output directory.")

    # Verifying a provenance against a policy.
    verify_parser = sub_parser.add_parser(name="verify")

    verify_parser.add_argument(
        "-pr", "--provenance", required=True, type=str, help=("The path to the provenance file.")
    )

    args = main_parser.parse_args(sys.argv[1:])

    if not args.action:
        main_parser.print_help()
        sys.exit(1)

    if args.verbose:
        log_level = logging.DEBUG
        log_format = "%(asctime)s [%(name)s:%(funcName)s:%(lineno)d] [%(levelname)s] %(message)s"
    else:
        log_level = logging.INFO
        log_format = "%(asctime)s [%(levelname)s] %(message)s"

    # Set logging config.
    logging.basicConfig(format=log_format, handlers=[logging.StreamHandler()], force=True, level=log_level)

    # Set the output directory
    if args.output_dir:
        if os.path.isfile(args.output_dir):
            logger.error("The output directory already exists. Exiting ...")
            sys.exit(1)

        if os.path.isdir(args.output_dir):
            logger.info("Setting the output directory to %s", args.output_dir)
        else:
            logger.info("No directory at %s. Creating one ...", args.output_dir)
            os.makedirs(args.output_dir)

    # Set logging debug level. We only need to set for the root logger.
    debug_log_path = os.path.join(args.output_dir, "debug.log")
    log_file_handler = logging.FileHandler(debug_log_path, "w")
    log_file_handler.setFormatter(logging.Formatter(log_format))
    logging.getLogger().addHandler(log_file_handler)
    logger.info("The log file of Macaron will be stored in debug.log")

    # Set Macaron's global configuration.
    global_config.load(
        macaron_path=macaron.MACARON_PATH,
        output_path=args.output_dir,
        build_log_path=os.path.join(args.output_dir, "build_log"),
        debug_level=log_level,
        local_repos_path=args.local_repos_path,
        gh_token=args.personal_access_token or "",
        policy_path=args.policy,
        resources_path=os.path.join(macaron.MACARON_PATH, "resources"),
    )

    # Load the default values from defaults.ini files.
    if not load_defaults(args.defaults_path):
        logger.error("Exiting because the defaults configuration could not be loaded.")
        sys.exit(1)

    perform_action(args)


if __name__ == "__main__":
    main()
