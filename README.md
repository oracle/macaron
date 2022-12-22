# Macaron

![Macaron](./docs/source/assets/macaron.svg)

Macaron is a supply chain security analysis tool from [Oracle Labs](https://labs.oracle.com/pls/apex/r/labs/labs/intro), which focuses on the build integrity of an artifact and the artifact dependencies. It is based on the [Supply chain Levels for Software Artifacts (SLSA)](https://slsa.dev/) specification, which aims at preventing some of the software supply chain attacks as the systems get more complex, especially with respect to the use of open-source third-party code in applications. Attacks include stealing credentials, injecting malicious code etc., and it is critical to have security assurance on the third-party code to guarantee that the integrity of the code has not been compromised.

Macaron uses [SLSA requirements specifications v0.1](https://slsa.dev/spec/v0.1/requirements) to define concrete rules for protecting software integrity that can be checked for compliance requirements automatically. Macaron provides a customizable checker platform that makes it easy to define checks that depend on each other. This is particularly useful for implementing checks for SLSA levels. In addition, Macaron also checks a user-specified policy for the repository to detect unexpected behavior in the build process. Macaron is a work-in-progress project and currently supports Maven and Gradle Java build systems only. We plan to support build systems for other languages, such as Python in future.

## Table of Contents

* [Getting started](#getting-started)
* [Running Macaron](#running-macaron)
* [How to Contribute](#how-to-contribute)
* [Security issue reports](#security-issue-reports)
* [License](#license)


## Getting started

**Prerequisites**
- Python 3.11
- Go 1.18
- JDK 11

**Prepare the environment**

Clone the project and install Macaron.

```bash
make venv
. .venv/bin/activate
make setup
```

## Running Macaron

```bash
usage: macaron [-h] [-v] [-o OUTPUT_DIR] -t PERSONAL_ACCESS_TOKEN {analyze,dump_defaults,verify} ...
```

The main parameters for Macaron are:
- `[-v]`: Run Macaron with more debug outputs.
- `[-o OUTPUT_DIR]`: The directory to store the results. The default value will be the Macaron repo path.
- `-t PERSONAL_ACCESS_TOKEN`: The GitHub access token. It's mandatory to have one for using any feature of Macaron. A valid token will provide increased ***request rate***, ***request limit*** and access to resources (e.g. GitHub Actions workflow data). Macaron is tested for valid GitHub access tokens only. The method to obtain a GitHub personal access token is described in the next section.

Apart from the main parameters listed above, you should choose the command to run, which requires other parameters. At the moment, Macaron has three commands.
- `analyze`: analyze the SLSA level of a single repository.
- `dump_defaults`: dump the default values in the output directory.
- `verify`: verify a provenance against a policy.


### Obtaining the GitHub personal access token
Create your own Github access token (please refer to the instructions [here](https://docs.github.com/en/github/authenticating-to-github/keeping-your-account-and-data-secure/creating-a-personal-access-token)). When creating this token, make sure to assign **at least** `repo` permissions.

The GitHub token should be stored in an environment variable and supplied to Macaron via command line parameters.

### Analyzing SLSA levels of a repository
*This section describes the `analyze` command of Macaron.*

Run this command to determine the SLSA level of a repository:

```bash
python -m macaron [-v] analyze -rp <path_to_target_repo> [-b <branch_name>] [-d <digest>] -c <config_path>
```

The main input parameters of the `analyze` command:
- `-rp <path_to_target_repo>` specifies the path to the repository to analyze. This path can be both a local path (e.g. `/path/to/repo`) or a remote path (e.g. `git@github.com:organization/repo_name.git` or `https://github.com/organization/repo_name.git`).
- `[-b <branch_name>]`: The name of the branch to analyze. If not specified, Macaron will checkout the default branch (if a remote path is supplied) or use the current branch that HEAD is on (if a local path is supplied).
- `[-d <digest>]`: The hash of the commit to checkout in the current branch. This hash must be in full form. If not specified, Macaron will checkout the latest commit of the current branch.
- `-c <config_path>`: The path to the configuration yaml file. This option cannot be used together with the `-rp` option.

Example I: Analyzing the GitHub repository [apache/maven](https://github.com/apache/maven) on **the latest commit of the default branch** without using a config file:

```bash
python -m macaron -t $GH_TOKEN -o output analyze -rp https://github.com/apache/maven.git
```

Example II: Doing the same thing as Example I, but using a config file:

```bash
python -m macaron -t $GH_TOKEN -o output analyze -c <path-to-maven_config.yaml>
```

```yaml
target:
  id: "apache/maven"
  branch: ""
  digest: ""
  path: "https://github.com/apache/maven.git"
```

The results of the examples above will be stored in ``output/reports/github_com/apache/maven/`` in HTML and JSON formats.

**Notes:**
- Macaron automatically detects and analyzes direct dependencies for Java Maven projects. This process might take a while during the first run but will be faster during the subsequent runs. To skip analyzing the dependencies you can pass ``--skip-deps`` option.
- If you supply a remote path, the repository is cloned to `git_repos/` before the analysis starts. If the repository has already been cloned to `git_repos/`, Macaron will not clone the repository and proceed to analyze the local repo instead.
- The `branch` and `digest` in the config file or `-b` and `-d` in the CLI are all optional and can be omitted.

### Verifying a policy

Macaron, currently, provides a PoC policy engine that checks a verified SLSA provenance against compliance requirements expressed as a policy. The result is reported in the JSON and HTML reports as a check called `mcn_policy_check_1`.

```bash
python -m macaron -t $GH_TOKEN -po <path-to-policy.yaml> analyze -rp https://github.com/apache/maven.git
```

The policy is a YAML file that contains expected values of predicates in SLSA provenance v0.2. Here is an example policy file:

```yaml
metadata:
  id: MACARON_1
  description: "Micronaut policy - SLSA provenance v0.2."

definition:
  _type: https://in-toto.io/Statement/v0.1
  predicateType: https://slsa.dev/provenance/v0.2

  predicate:
    builder:
      id: https://github.com/slsa-framework/slsa-github-generator/.github/workflows/generator_generic_slsa3.yml@refs/tags/v1.2.1
    buildType: https://github.com/slsa-framework/slsa-github-generator/generic@v1

    invocation:
      configSource:
        uri: git+https://github.com/micronaut-projects/micronaut-security@refs/tags/v3.8.3
        entryPoint: .github/workflows/release.yml
```

You can also run the policy verifier directly like below:

```bash
python -m macaron -po <path_to_policy.yaml> verify -pr <path_to_prov_file>
```

**Note.** The policy engine is under active development and will support more complex policies soon. Stay tuned.

## How to Contribute

We welcome contributions! See our [general contribution guidelines](./CONTRIBUTING.md).

To contribute to Macaron, first create a [virtual environment](https://docs.python.org/3/tutorial/venv.html) by either using the [Makefile](https://www.gnu.org/software/make/manual/make.html#toc-An-Introduction-to-Makefiles):

```bash
make venv  # Create a new virtual environment in .venv folder using Python 3.11.
```

or for a specific version of Python:

```bash
PYTHON=python3.11 make venv  # Same virtual environment for a different Python version.
```

Activate the virtual environment:

```bash
. .venv/bin/activate
```

Finally, set up Macaron with all of its extras and initialize the local git hooks:

```bash
make setup
```

With that in place, you’re ready to build and contribute to Macaron!

### Updating dependent packages

It’s likely that during development you’ll add or update dependent packages in the `pyproject.toml` file, which requires an update to the virtual environment:

```bash
make upgrade
```

### Git hooks

Using the pre-commit tool and its `.pre-commit-config.yaml` configuration, the following git hooks are active in this repository:

- When committing code, a number of [pre-commit hooks](https://git-scm.com/book/en/v2/Customizing-Git-Git-Hooks#_committing_workflow_hooks) ensure that your code is formatted according to [PEP 8](https://www.python.org/dev/peps/pep-0008/) using the [`black`](https://github.com/psf/black) tool, and they’ll invoke [`flake8`](https://github.com/PyCQA/flake8) (and various plugins), [`pylint`](https://github.com/PyCQA/pylint) and [`mypy`](https://github.com/python/mypy) to check for lint and correct types. There are more checks, but those two are the important ones. You can adjust the settings for these tools in the `pyproject.toml` or `.flake8` configuration files.
- The [commit message hook](https://git-scm.com/book/en/v2/Customizing-Git-Git-Hooks#_committing_workflow_hooks) enforces [conventional commit messages](https://www.conventionalcommits.org/) and that, in turn, enables a _semantic release_ of this package on the Github side: upon merging changes into the `main` branch, the [release action](https://github.com/github.com/oracle-samples/blob/main/.github/workflows/release.yaml) uses the [Commitizen tool](https://commitizen-tools.github.io/commitizen/) to produce a [changelog](https://en.wikipedia.org/wiki/Changelog) and it computes the next version of this package and publishes a release — all based on the commit messages of a release.
- Using a [pre-push hook](https://git-scm.com/book/en/v2/Customizing-Git-Git-Hooks#_other_client_hooks) this package is also set up to run [`pytest`](https://github.com/pytest-dev/pytest); in addition, the [`coverage`](https://github.com/nedbat/coveragepy) plugin makes sure that _all_ of your package’s code is covered by tests and [Hypothesis](https://hypothesis.works/) is already installed to help with generating test payloads.

You can also run these hooks manually, which comes in very handy during daily development tasks. For example

```bash
make check-code
```

runs all the code checks (i.e. `bandit`, `flake8`, `pylint` and `mypy`), whereas

```bash
make check
```

runs _all_ installed git hooks over your code. For more control over the code checks, the Makefile also implements the `check-bandit`, `check-flake8`, `check-lint`, `check-mypy`, and `check-go` goals.

### Testing

As mentioned above, this repository is set up to use [pytest](https://pytest.org/) either standalone or as a pre-push git hook. Tests are stored in the `tests/` folder, and you can run them manually like so:
```bash
make test
```

which runs all tests in both your local Python virtual environment. For more options, see the [pytest command-line flags](https://docs.pytest.org/en/6.2.x/reference.html#command-line-flags). Also note that pytest includes [doctest](https://docs.python.org/3/library/doctest.html), which means that module and function [docstrings](https://www.python.org/dev/peps/pep-0257/#what-is-a-docstring) may contain test code that executes as part of the unit tests.

Test code coverage is already tracked using [coverage](https://github.com/nedbat/coveragepy) and the [pytest-cov](https://github.com/pytest-dev/pytest-cov) plugin for pytest, and it measures how much code in the `src/macaron/` folder is covered by tests.

Hypothesis is a package that implements [property based testing](https://en.wikipedia.org/wiki/QuickCheck) and that provides payload generation for your tests based on strategy descriptions ([more](https://hypothesis.works/#what-is-hypothesis)). Using its [pytest plugin](https://hypothesis.readthedocs.io/en/latest/details.html#the-hypothesis-pytest-plugin) Hypothesis is ready to be used for this package.

To run integration tests run:

```bash
make integration-test
```

### Generating documentation

As mentioned above, all package code should make use of [Python docstrings](https://www.python.org/dev/peps/pep-0257/) in [reStructured text format](https://www.python.org/dev/peps/pep-0287/). Using these docstrings and the documentation template in the `docs/source/` folder, you can then generate proper documentation in different formats using the [Sphinx](https://github.com/sphinx-doc/sphinx/) tool:

```bash
make docs
```

This example generates documentation in HTML, which can then be found here:

```bash
open docs/_build/html/index.html
```

## Security issue reports

Security issue reports should follow our [reporting guidelines](./SECURITY.md).

## License

Macaron is licensed under the [Universal Permissive License (UPL), Version 1.0](./LICENSE.txt).
