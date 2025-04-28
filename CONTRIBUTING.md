# Contributing to Macaron

We welcome contributions to this repository from anyone.

If you want to submit a pull request to fix a bug or enhance an existing feature, please first open an issue and link to that issue when you submit your pull request.

If you have any questions about a possible submission, feel free to open an issue too.

## Opening issues

For bugs or enhancement requests, please file a GitHub issue unless it's security related. When filing a bug remember that the better written the bug is, the more likely it is to be fixed. If you think you've found a security vulnerability, do not raise a GitHub issue and follow the instructions in our [security policy](./SECURITY.md).

## Contributing code

We welcome your code contributions. Before submitting code via a pull request, you will need to have signed the [Oracle Contributor Agreement][OCA] (OCA) and your commits need to include the following line using the name and e-mail address you used to sign the OCA:

```text
Signed-off-by: Your Name <you@example.org>
```

This can be automatically added to pull requests by committing with `--sign-off`
or `-s`, e.g.

```text
git commit --signoff
```

Finally, **make sure to sign your commits** following the instructions provided by [GitHub](https://docs.github.com/en/authentication/managing-commit-signature-verification/signing-commits). Note that we run [GitHub's commit verification](https://docs.github.com/en/authentication/managing-commit-signature-verification/about-commit-signature-verification) tool to check the commit signatures. A green `verified` label should appear next to **all** of your commits on GitHub.

### Style Guide

See our [Macaron Style Guide](./docs/source/pages/developers_guide/style_guide.rst).

### Pull request process

1. Ensure there is an issue created to track and discuss the fix or enhancement
   you intend to submit.
2. Fork this repository.
3. Create a branch in your fork to implement the changes. We recommend using the issue number as part of your branch name, e.g. `1234-fixes`.
4. The title of the PR should follow the convention of [commit messages](#commit-messages).
5. Ensure that any documentation is updated with the changes that are required by your change.
6. Ensure that any samples are updated if the base image has been changed.
7. Submit the pull request. *Do not leave the pull request blank*. Explain exactly what your changes are meant to do and provide simple steps on how to validate. your changes. Ensure that you reference the issue you created as well.
8. Choose `main` as the base branch for your PR.
9. We will assign the pull request to 2-3 people for review before it is merged.

### Commit messages

- Commit messages should follow the [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) convention.
- Note that the commit types `fix`, `feat`, and `refactor` should only be used for commits appearing in the next release of the project as a package.
  - The project uses [`commitizen`](https://github.com/commitizen-tools/commitizen) on the commit history to automatically create the `CHANGELOG.md` file. `commitizen` takes into account commits typed with `fix`, `feat` and `refactor`.
  - For small commits to fix a PR during code review, the commit type should be `chore` (instead of `fix` or `refactor`).

### Code review

- A PR must be reviewed and approved by at least one maintainer of the project.
- During code review, fixes to the PR should be new commits (no rebasing).
- Each commit should be kept small for easy review.
- As mentioned in the [commit messages](#commit-messages) section, the type of these commits should be `chore`.

### CI tests

- Each new feature or change PR should provide meaningful CI tests.
- All the tests and security scanning checks in CI should pass and achieve the expected coverage.
- To avoid unnecessary failures in GitHub Actions, make sure `make check` and `make test` work locally.
See below for instructions to set up the development environment.

### Merging PRs

- Before a PR is merged, all commits in the PR should be meaningful.
  - Its commit message should be the same as the PR title if there only one commit.
- PRs should be merged using the `Squash and merge` strategy. In most cases a single commit with
a detailed commit message body is preferred. Make sure to keep the `Signed-off-by` line in the body.

### PyPI Malware Detection Contribution

Please see the [README for the malware analyzer](./src/macaron/malware_analyzer/README.md) for information on contributing Heuristics and code patterns.

## Branching model

* The `main` branch should be used as the base branch for pull requests. The `release` branch is designated for releases and should only be merged into when creating a new release for Macaron.

## Setting up the development environment

### Prerequisites

- Python 3.11
- Go 1.23
- JDK 17

### Prepare the environment

To contribute to Macaron, clone the project and create a [virtual environment](https://docs.python.org/3/tutorial/venv.html) by using the [Makefile](https://www.gnu.org/software/make/manual/make.html#toc-An-Introduction-to-Makefiles):

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

**Note**: Running the above command will prompt you for sudo access to install [Soufflé Datalog engine](https://github.com/souffle-lang/souffle). You can install Soufflé on your system before running `make setup` to avoid getting prompted.

With that in place, you’re ready to build and contribute to Macaron!

### Updating dependent packages

It’s likely that during development you’ll add or update dependent packages in the `pyproject.toml` or `go.mod` files, which requires an update to the environment:

```bash
make upgrade
```

### Running Macaron as a Python package

```bash
usage: macaron [-h]
```

### Obtaining the GitHub personal access token

To obtain a GitHub access token, please see the official instructions [here](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token).

Ideally, the GitHub token must have **read** permissions for the repositories that you want to analyze:

- Every [fine-grained personal-access token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token#creating-a-fine-grained-personal-access-token) should have read permission to public GitHub repositories. However, if you are analyzing a private repository, please select it in the ``Repository Access section``.
- For [classic personal-access token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token#creating-a-personal-access-token-classic), the ``repo.public_repo`` scope must be selected. Please select the whole ``repo`` scope if you are running the analysis against private repositories.

After generating a GitHub personal-access token, please store its value in an environment variable called ``GITHUB_TOKEN``. This environment variable will be read by Macaron for its **analyze** command.

## Running checks and tests locally

### Git hooks

Using the pre-commit tool and its `.pre-commit-config.yaml` configuration, a number of [pre-commit hooks](https://git-scm.com/book/en/v2/Customizing-Git-Git-Hooks#_committing_workflow_hooks) ensure that your code is formatted correctly.

You can also run these hooks manually, which comes in very handy during daily development tasks. For example

```bash
make check-code
```

runs all the code checks (i.e. `bandit`, `flake8`, `pylint`, `mypy`, `actionlint`), whereas

```bash
make check
```

runs _all_ installed git hooks over your code. For more control over the code checks, the Makefile also implements the `check-bandit`, `check-flake8`, `check-lint`, `check-mypy`, and `check-actionlint` goals.


### Testing

To run the tests, please make sure you have setup the development environment first.

#### Unit tests

This repository is set up to perform unit tests either standalone or as a pre-push git hook. Unit tests are stored in the `tests/` folder (except for the `tests/integration` directory), and you can run them manually like so:
```bash
make test
```
which runs all unit tests in your local environment.

You can also add tests to the docstrings in the Python source files or documentation `.rst` files, which will be picked up by pytest from `src/` and `docs/` directories. Here is an example:

```python
def do_something(value: bool = False) -> bool:
    """Return true, always.

    Test this function by adding the following code to the docstring:
    .. code: pycon

        >>> s = Something()
        >>> s.do_something(False)
        True
        >>> s.do_something(value=True)
        True
    """
```

Test code and branch coverage is already tracked using [coverage](https://github.com/nedbat/coveragepy) and the [pytest-cov](https://github.com/pytest-dev/pytest-cov) plugin for pytest, and it measures how much code in the `src/macaron/` folder is covered by tests.

#### Integration tests

To know more about our integration test utility, please see [here](./tests/integration/README.md).

We have two types of integration tests:
1. Integration tests that are run against the Macaron Python package. You can run these tests locally with:
```bash
make integration-test
```
2. Integration tests that are run against the container image. You can run these tests locally with:
```bash
IMAGE=<image_name> MACARON_IMAGE_TAG=<tag> make integration-test-docker
```

Please substitute `<image_name>` and `<tag>` with the values of the container image you want to test. This container image can either be:
- Pulled from `ghcr.io/oracle/macaron`.
- Built from running `make build-docker`.

Note that integration tests can take a long time to complete.

Each integration test case has a set of tags. Please follow these instructions on how a test case is tagged for our CI/CD pipeline:
- If you want a test case to **only** run for the container image, use **only** `macaron-docker-image`.
- If you want a test case to **only** run with the Macaron Python package, use **only** `macaron-python-package`.
- To skip a test case, use `skip`. `skip` still has the same effect if it's used with other tags.
- If you want to run a test case for both the Macaron Python package and the docker container, use both `macaron-python-package` and `macaron-docker-image` tags.
- If you want to run test cases that must contain all of a given set of tags (e.g. `['tag-a', 'tag-b']`), please create an additional tag for those test cases (e.g `tag-a-b`) and use it within `--include-tag`.
- Test cases marked with `npm-registry-testcase` are not run if the environment variable `NO_NPM` is set to `TRUE`. This only applies when you run the integration tests with:
```bash
$ make integration-test
```
- If a test case is relevant to a tutorial, please tag it with `tutorial`.

## Generating documentation

As mentioned above, all package code should make use of [Python docstrings](https://www.python.org/dev/peps/pep-0257/) in [reStructured text format](https://www.python.org/dev/peps/pep-0287/) following [numpydoc style](https://numpydoc.readthedocs.io/en/latest/format.html) (with some exceptions - see our [style guide](https://oracle.github.io/pages/developers_guide/style_guide.html#docstrings)). Using these docstrings and the documentation template in the `docs/source/` folder, you can then generate proper documentation in different formats using the [Sphinx](https://github.com/sphinx-doc/sphinx/) tool:

```bash
make docs
```

This example generates documentation in HTML, which can then be found here:

```bash
open docs/_build/html/index.html
```

For more information see the instructions [here](docs/README.md).

## Code of conduct

Follow the [Golden Rule](https://en.wikipedia.org/wiki/Golden_Rule). If you'd like more specific guidelines, see the [Contributor Covenant Code of Conduct][COC].

[OCA]: https://oca.opensource.oracle.com
[COC]: https://www.contributor-covenant.org/version/1/4/code-of-conduct/
