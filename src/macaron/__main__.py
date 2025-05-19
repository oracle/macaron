# Copyright (c) 2022 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This is the main entrypoint to run Macaron."""

import argparse
import json
import logging
import os
import sys
from importlib import metadata as importlib_metadata

from jinja2 import Environment, FileSystemLoader, select_autoescape
from packageurl import PackageURL

import macaron
from macaron.config.defaults import create_defaults, load_defaults
from macaron.config.global_config import global_config
from macaron.errors import ConfigurationError
from macaron.output_reporter.reporter import HTMLReporter, JSONReporter, PolicyReporter
from macaron.policy_engine.policy_engine import run_policy_engine, show_prelude
from macaron.repo_finder import repo_finder
from macaron.slsa_analyzer.analyzer import Analyzer
from macaron.slsa_analyzer.git_service import GIT_SERVICES
from macaron.slsa_analyzer.package_registry import PACKAGE_REGISTRIES
from macaron.slsa_analyzer.provenance.intoto.errors import LoadIntotoAttestationError
from macaron.slsa_analyzer.provenance.loader import load_provenance_payload
from macaron.vsa.vsa import generate_vsa

logger: logging.Logger = logging.getLogger(__name__)


def analyze_slsa_levels_single(analyzer_single_args: argparse.Namespace) -> None:
    """Run the SLSA checks against a single target repository."""
    if analyzer_single_args.deps_depth == "inf":
        deps_depth = -1
    else:
        try:
            deps_depth = int(analyzer_single_args.deps_depth)
        except ValueError:
            logger.error("Please provide '1', '0' or 'inf' to `--deps-depth`")
            sys.exit(os.EX_USAGE)

    if deps_depth not in [-1, 0, 1]:
        logger.error("Please provide '1', '0' or 'inf' to `--deps-depth`")
        sys.exit(os.EX_USAGE)

    if not (analyzer_single_args.repo_path or analyzer_single_args.package_url):
        # We don't mention --config-path as a possible option in this log message as it going to be move soon.
        # See: https://github.com/oracle/macaron/issues/417
        logger.error(
            """Analysis target missing. Please provide a package url (PURL) and/or repo path.
            Examples of a PURL can be seen at https://github.com/package-url/purl-spec:
            pkg:github/micronaut-projects/micronaut-core."""
        )
        sys.exit(os.EX_USAGE)

    # Set provenance expectation path.
    if analyzer_single_args.provenance_expectation is not None:
        if not os.path.exists(analyzer_single_args.provenance_expectation):
            logger.critical(
                'The provenance expectation file "%s" does not exist.', analyzer_single_args.provenance_expectation
            )
            sys.exit(os.EX_OSFILE)
        global_config.load_expectation_files(analyzer_single_args.provenance_expectation)

    # Set Python virtual environment path.
    if analyzer_single_args.python_venv is not None:
        if not os.path.exists(analyzer_single_args.python_venv):
            logger.critical(
                'The Python virtual environment path "%s" does not exist.', analyzer_single_args.python_venv
            )
            sys.exit(os.EX_OSFILE)
        global_config.load_python_venv(analyzer_single_args.python_venv)

    # Set local maven repo path.
    if analyzer_single_args.local_maven_repo is None:
        # Load the default user local .m2 directory.
        # Exit on error if $HOME is not set or empty.
        home_dir = os.getenv("HOME")
        if not home_dir:
            logger.critical("Environment variable HOME is not set.")
            sys.exit(os.EX_USAGE)

        local_maven_repo = os.path.join(home_dir, ".m2")
        if not os.path.isdir(local_maven_repo):
            logger.debug("The default local Maven repo at %s does not exist. Ignore ...")
            global_config.local_maven_repo = None

        global_config.local_maven_repo = local_maven_repo
    else:
        user_provided_local_maven_repo = analyzer_single_args.local_maven_repo
        if not os.path.isdir(user_provided_local_maven_repo):
            logger.error("The user provided local Maven repo at %s is not valid.", user_provided_local_maven_repo)
            sys.exit(os.EX_USAGE)

        global_config.local_maven_repo = user_provided_local_maven_repo

    if analyzer_single_args.force_analyze_source and not analyzer_single_args.analyze_source:
        logger.error("'--force-analyze-source' requires '--analyze-source'.")
        sys.exit(os.EX_USAGE)

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
            sys.exit(os.EX_NOINPUT)

        analyzer.reporters.append(html_reporter)
    else:
        analyzer.reporters.append(HTMLReporter())
    analyzer.reporters.append(JSONReporter())

    run_config = {}
    repo_path = analyzer_single_args.repo_path
    purl = analyzer_single_args.package_url
    branch = analyzer_single_args.branch
    digest = analyzer_single_args.digest

    if repo_path and purl:
        # To provide the purl together with the repository path, the user must specify the commit digest unless the
        # purl has a version.
        try:
            purl_object = PackageURL.from_string(purl)
        except ValueError as error:
            logger.debug("Could not parse PURL: %s", error)
            sys.exit(os.EX_USAGE)
        if not (purl_object.version or digest):
            logger.error(
                "Please provide the commit digest for the repo at %s that matches to the PURL string %s. Or "
                "include the version in the PURL",
                repo_path,
                purl,
            )
            sys.exit(os.EX_USAGE)

    # We need to use empty strings when the input values are of None type. This is because this dictionary will be
    # passed into the Configuration instance, where the existing values in Configuration.options are replaced by
    # whatever we assign it here. Technically, the data in ``Configuration`` class are not limited to only strings.
    # Therefore, it could be cases where the ``purl`` field is initialized as an empty string in the constructor
    # of the Configuration class, but if `` analyzer_single_args.package_url`` is None, the ``purl`` field is set
    # to None in the Configuration instance.
    # This inconsistency could cause potential issues when Macaron handles those inputs.
    # TODO: improve the implementation of ``Configuration`` class to avoid such inconsistencies.
    run_config = {
        "target": {
            "id": purl or repo_path or "",
            "purl": purl or "",
            "path": repo_path or "",
            "branch": branch or "",
            "digest": digest or "",
        }
    }

    prov_payload = None
    if analyzer_single_args.provenance_file:
        try:
            prov_payload = load_provenance_payload(analyzer_single_args.provenance_file)
        except LoadIntotoAttestationError as error:
            logger.error("Error while loading the input provenance file: %s", error)
            sys.exit(os.EX_DATAERR)

    status_code = analyzer.run(
        run_config,
        analyzer_single_args.sbom_path,
        deps_depth,
        provenance_payload=prov_payload,
        verify_provenance=analyzer_single_args.verify_provenance,
        analyze_source=analyzer_single_args.analyze_source,
        force_analyze_source=analyzer_single_args.force_analyze_source,
    )
    sys.exit(status_code)


def verify_policy(verify_policy_args: argparse.Namespace) -> int:
    """Run policy engine and verify the Datalog policy.

    Returns
    -------
    int
        Returns os.EX_OK if successful or the corresponding error code on failure.
    """
    if not os.path.isfile(verify_policy_args.database):
        logger.critical("The database file does not exist.")
        return os.EX_OSFILE

    if verify_policy_args.show_prelude:
        show_prelude(verify_policy_args.database)
        return os.EX_OK

    if verify_policy_args.file:
        if not os.path.isfile(verify_policy_args.file):
            logger.critical('The policy file "%s" does not exist.', verify_policy_args.file)
            return os.EX_OSFILE

        with open(verify_policy_args.file, encoding="utf-8") as file:
            policy_content = file.read()

        result = run_policy_engine(verify_policy_args.database, policy_content)
        vsa = generate_vsa(policy_content=policy_content, policy_result=result)
        if vsa is not None:
            vsa_filepath = os.path.join(global_config.output_path, "vsa.intoto.jsonl")
            logger.info(
                "Generating the Verification Summary Attestation (VSA) to %s.",
                os.path.relpath(vsa_filepath, os.getcwd()),
            )
            logger.info(
                "To decode and inspect the payload, run `cat %s | jq -r '.payload' | base64 -d | jq`.",
                os.path.relpath(vsa_filepath, os.getcwd()),
            )
            try:
                with open(vsa_filepath, mode="w", encoding="utf-8") as file:
                    file.write(json.dumps(vsa))
            except OSError as err:
                logger.error(
                    "Could not generate the VSA to %s. Error: %s", os.path.relpath(vsa_filepath, os.getcwd()), err
                )

        policy_reporter = PolicyReporter()
        policy_reporter.generate(global_config.output_path, result)

        if ("failed_policies" in result) and any(result["failed_policies"]):
            return os.EX_DATAERR
        if len(result.get("passed_policies", [])) == 0:
            logger.error("Found no component passing policies.")
            return os.EX_DATAERR

        return os.EX_OK

    return os.EX_USAGE


def find_source(find_args: argparse.Namespace) -> int:
    """Perform repo and commit finding for a passed PURL, or commit finding for a passed PURL and repo."""
    if repo_finder.find_source(find_args.package_url, find_args.repo_path or None):
        return os.EX_OK

    return os.EX_DATAERR


def perform_action(action_args: argparse.Namespace) -> None:
    """Perform the indicated action of Macaron."""
    match action_args.action:
        case "dump-defaults":
            # Create the defaults.ini file in the output dir and exit.
            create_defaults(action_args.output_dir, os.getcwd())
            sys.exit(os.EX_OK)

        case "verify-policy":
            sys.exit(verify_policy(action_args))

        case "analyze":
            if not global_config.gh_token:
                logger.error("GitHub access token not set.")
                sys.exit(os.EX_USAGE)
            # TODO: Here we should try to statically analyze the config before
            # actually running the analysis.
            try:
                for git_service in GIT_SERVICES:
                    git_service.load_defaults()
                for package_registry in PACKAGE_REGISTRIES:
                    package_registry.load_defaults()
            except ConfigurationError as error:
                logger.error(error)
                sys.exit(os.EX_USAGE)

            analyze_slsa_levels_single(action_args)

        case "find-source":
            try:
                for git_service in GIT_SERVICES:
                    git_service.load_defaults()
                for package_registry in PACKAGE_REGISTRIES:
                    package_registry.load_defaults()
            except ConfigurationError as error:
                logger.error(error)
                sys.exit(os.EX_USAGE)

            find_source(action_args)

        case _:
            logger.error("Macaron does not support command option %s.", action_args.action)
            sys.exit(os.EX_USAGE)


def main(argv: list[str] | None = None) -> None:
    """Execute Macaron as a standalone command-line tool.

    Parameters
    ----------
    argv: list[str] | None
        Command-line arguments.
        If ``argv`` is ``None``, argparse automatically looks at ``sys.argv``.
        Hence, we set ``argv = None`` by default.
    """
    # Handle presence of token file. When running Macaron as a container, this file is created by the "run_macaron.sh"
    # script and populated there. If Macaron is being run outside of a container, the token file should not exist, and
    # tokens should be read directly from the environment instead.
    token_file = os.path.join(os.getcwd(), ".macaron_env_file")
    token_dict = {}
    if os.path.exists(token_file):
        # Read values into dictionary.
        try:
            with open(token_file, encoding="utf-8") as file:
                for line in file:
                    if not line or "=" not in line:
                        continue
                    key, value = line.rstrip().split("=", 1)
                    token_dict[key] = value
        except OSError as error:
            logger.error("Could not open token file %s: %s", token_file, error)
            sys.exit(os.EX_OSFILE)
        # Overwrite file contents.
        try:
            with open(token_file, "w", encoding="utf-8"):
                pass
        except OSError as error:
            logger.error("Could not overwrite token file %s: %s", token_file, error)
            sys.exit(os.EX_OSFILE)

    # Check presence of tokens in dictionary or environment, preferring the former.
    global_config.gh_token = _get_token_from_dict_or_env("GITHUB_TOKEN", token_dict)
    global_config.gl_token = _get_token_from_dict_or_env("MCN_GITLAB_TOKEN", token_dict)
    global_config.gl_self_host_token = _get_token_from_dict_or_env("MCN_SELF_HOSTED_GITLAB_TOKEN", token_dict)

    main_parser = argparse.ArgumentParser(prog="macaron")

    main_parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {importlib_metadata.version('macaron')}",
        help="Show Macaron's version number and exit",
    )

    main_parser.add_argument(
        "-v",
        "--verbose",
        help="Run Macaron with more debug logs",
        action="store_true",
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
        default="",
        help="The path to the defaults configuration file.",
    )

    main_parser.add_argument(
        "-lr",
        "--local-repos-path",
        default="",
        help="The directory where Macaron looks for already cloned repositories.",
    )

    # Add sub parsers for each action.
    sub_parser = main_parser.add_subparsers(dest="action", help="Run macaron <action> --help for help")

    # Use Macaron to analyze one single repository.
    single_analyze_parser = sub_parser.add_parser(name="analyze")

    single_analyze_parser.add_argument(
        "-sbom",
        "--sbom-path",
        required=False,
        type=str,
        default="",
        help=(
            "The path to the SBOM of the analysis target. If this is set, "
            + "dependency resolution must be enabled with '--deps-depth'."
        ),
    )

    single_analyze_parser.add_argument(
        "-rp",
        "--repo-path",
        required=False,
        type=str,
        help=("The path to the repository, can be local or remote"),
    )

    single_analyze_parser.add_argument(
        "-purl",
        "--package-url",
        required=False,
        type=str,
        help=(
            "The PURL string used to uniquely identify the target software component for analysis. "
            + "Note: this PURL string can be consequently used in the policies passed to the policy "
            + "engine for the same target."
        ),
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

    single_analyze_parser.add_argument(
        "-pe",
        "--provenance-expectation",
        required=False,
        help=("The path to provenance expectation file or directory."),
    )

    single_analyze_parser.add_argument(
        "-pf",
        "--provenance-file",
        required=False,
        help=("The path to the provenance file in in-toto format."),
    )

    single_analyze_parser.add_argument(
        "--deps-depth",
        required=False,
        default="0",
        help=(
            "The depth of the dependency resolution. 0: disable, 1: direct dependencies, "
            + "inf: all transitive dependencies. (Default: 0)"
        ),
    )

    single_analyze_parser.add_argument(
        "-g",
        "--template-path",
        required=False,
        type=str,
        default="",
        help=("The path to the Jinja2 html template (please make sure to use .html or .j2 extensions)."),
    )

    single_analyze_parser.add_argument(
        "--python-venv",
        required=False,
        help=(
            "The path to the Python virtual environment of the target software component. "
            + "If this is set, dependency resolution must be enabled with '--deps-depth'."
        ),
    )

    single_analyze_parser.add_argument(
        "--local-maven-repo",
        required=False,
        help=(
            "The path to the local .m2 directory. If this option is not used, Macaron will use the default location at $HOME/.m2"
        ),
    )

    single_analyze_parser.add_argument(
        "--analyze-source",
        required=False,
        action="store_true",
        help=(
            "For improved malware detection, analyze the source code of the"
            + " (PyPI) package using a textual scan and dataflow analysis."
        ),
    )

    single_analyze_parser.add_argument(
        "--force-analyze-source",
        required=False,
        action="store_true",
        help=(
            "Forces PyPI sourcecode analysis to run regardless of other heuristic results. Requires '--analyze-source'."
        ),
    )

    single_analyze_parser.add_argument(
        "--verify-provenance",
        required=False,
        action="store_true",
        help=("Allow the analysis to attempt to verify provenance files as part of its normal operations."),
    )

    # Dump the default values.
    sub_parser.add_parser(name="dump-defaults", description="Dumps the defaults.ini file to the output directory.")

    # Verify the Datalog policy.
    vp_parser = sub_parser.add_parser(name="verify-policy")
    vp_group = vp_parser.add_mutually_exclusive_group(required=True)

    vp_parser.add_argument("-d", "--database", required=True, type=str, help="Path to the database.")
    vp_group.add_argument("-f", "--file", type=str, help="Path to the Datalog policy.")
    vp_group.add_argument("-s", "--show-prelude", action="store_true", help="Show policy prelude.")

    # Find the repo and commit of a passed PURL, or the commit of a passed PURL and repo.
    find_parser = sub_parser.add_parser(name="find-source")

    find_parser.add_argument(
        "-purl",
        "--package-url",
        required=True,
        type=str,
        help=("The PURL string to perform repository and commit finding for."),
    )

    find_parser.add_argument(
        "-rp",
        "--repo-path",
        required=False,
        type=str,
        help=(
            "The path to a repository that matches the provided PURL, can be local or remote. "
            "This argument is only required in cases where the repository cannot be discovered automatically."
        ),
    )

    args = main_parser.parse_args(argv)

    if not args.action:
        main_parser.print_help()
        sys.exit(os.EX_USAGE)

    if args.verbose:
        log_level = logging.DEBUG
        log_format = "%(asctime)s [%(name)s:%(funcName)s:%(lineno)d] [%(levelname)s] %(message)s"
    else:
        log_level = logging.INFO
        log_format = "%(asctime)s [%(levelname)s] %(message)s"

    # Set global logging config. We need the stream handler for the initial
    # output directory checking log messages.
    st_handler = logging.StreamHandler(sys.stdout)
    logging.basicConfig(format=log_format, handlers=[st_handler], force=True, level=log_level)

    # Set the output directory.
    if not args.output_dir:
        logger.error("The output path cannot be empty. Exiting ...")
        sys.exit(os.EX_USAGE)

    if os.path.isfile(args.output_dir):
        logger.error("The output directory already exists. Exiting ...")
        sys.exit(os.EX_USAGE)

    if os.path.isdir(args.output_dir):
        logger.info("Setting the output directory to %s", os.path.relpath(args.output_dir, os.getcwd()))
    else:
        logger.info("No directory at %s. Creating one ...", os.path.relpath(args.output_dir, os.getcwd()))
        os.makedirs(args.output_dir)

    # Add file handler to the root logger. Remove stream handler from the
    # root logger to prevent dependencies printing logs to stdout.
    debug_log_path = os.path.join(args.output_dir, "debug.log")
    log_file_handler = logging.FileHandler(debug_log_path, "w")
    log_file_handler.setFormatter(logging.Formatter(log_format))
    logging.getLogger().removeHandler(st_handler)
    logging.getLogger().addHandler(log_file_handler)

    # Add StreamHandler to the Macaron logger only.
    mcn_logger = logging.getLogger("macaron")
    mcn_logger.addHandler(st_handler)

    logger.info("The logs will be stored in debug.log")

    # Set Macaron's global configuration.
    # The path to provenance expectation files will be updated if
    # set through analyze sub-command.
    global_config.load(
        macaron_path=macaron.MACARON_PATH,
        output_path=args.output_dir,
        build_log_path=os.path.join(args.output_dir, "build_log"),
        debug_level=log_level,
        local_repos_path=args.local_repos_path,
        resources_path=os.path.join(macaron.MACARON_PATH, "resources"),
    )

    # Load the default values from defaults.ini files.
    if not load_defaults(args.defaults_path):
        logger.error("Exiting because the defaults configuration could not be loaded.")
        sys.exit(os.EX_NOINPUT)

    perform_action(args)


def _get_token_from_dict_or_env(token: str, token_dict: dict[str, str]) -> str:
    """Return the value of passed token from passed dictionary or os environment."""
    return token_dict[token] if token in token_dict else os.environ.get(token) or ""


if __name__ == "__main__":
    main()
