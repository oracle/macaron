.. Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
.. Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

.. _analyze-command-cli:

=======
Analyze
=======

-----------
Description
-----------

Analyze a public GitHub repository (and optionally the repositories of its dependencies) to determine its :term:`SLSA` posture.

-----
Usage
-----

.. code-block:: shell

    usage: ./run_macaron.sh analyze
        [-h] [-sbom SBOM_PATH] [-rp REPO_PATH] [-purl PACKAGE_URL]
        [-b BRANCH] [-d DIGEST] [-pe PROVENANCE_EXPECTATION] [-pf PROVENANCE_FILE]
        [--deps-depth DEPS_DEPTH] [-g TEMPLATE_PATH] [--python-venv PYTHON_VENV]
        [--local-maven-repo LOCAL_MAVEN_REPO] [--force-analyze-source]

-------
Options
-------

.. option:: -h, --help

    Show this help message and exit.

.. option:: -sbom SBOM_PATH, --sbom-path SBOM_PATH

    The path to the Software Bill of Materials (SBOM) of the analysis target.
    If this option is set, dependency resolution must be enabled by using the
    `--deps-depth` option.

.. option:: -rp REPO_PATH, --repo-path REPO_PATH

    The path to the repository, which can be either local or remote.

.. option:: -purl PACKAGE_URL, --package-url PACKAGE_URL

    The Package URL (PURL) string used to uniquely identify the target software component for analysis.
    This PURL string can also be used in the policies passed to the policy engine for the same target.

.. option:: -b BRANCH, --branch BRANCH

    The branch of the repository that you want to check out. If not set, Macaron will use the default branch.

.. option:: -d DIGEST, --digest DIGEST

    The digest of the commit you want to check out in the branch. If not set, Macaron will use the latest commit.

.. option:: -pe PROVENANCE_EXPECTATION, --provenance-expectation PROVENANCE_EXPECTATION

    The path to the provenance expectation file or directory.

.. option:: -pf PROVENANCE_FILE, --provenance-file PROVENANCE_FILE

    The path to the provenance file in in-toto format.

.. option:: --deps-depth DEPS_DEPTH

    The depth of the dependency resolution. Possible values are:

    - `0`: Disable dependency resolution.
    - `1`: Resolve direct dependencies only.
    - `inf`: Resolve all transitive dependencies (default: `0`).

    **Note**: If `--sbom-path` or `--python-venv` is set, this option must be specified.

.. option:: -g TEMPLATE_PATH, --template-path TEMPLATE_PATH

    The path to the Jinja2 HTML template file. Please ensure that the file has either `.html` or `.j2` extensions.

.. option:: --python-venv PYTHON_VENV

    The path to the Python virtual environment of the target software component.
    If this option is set, dependency resolution must be enabled with `--deps-depth`.

.. option:: --local-maven-repo LOCAL_MAVEN_REPO

    The path to the local `.m2` Maven repository. If this option is not used, Macaron will use the default location at `$HOME/.m2`.

.. option:: --verify-provenance

    Allow the analysis to attempt to verify provenance files as part of its normal operations.

.. option:: --force-analyze-source

    Forces PyPI source code analysis to run, regardless of other heuristic results.

-----------
Environment
-----------

``GITHUB_TOKEN`` – The GitHub personal access token is needed for to run the analysis. For more information on how to obtain a GitHub token, see instructions in :ref:`Prepare GitHub access token <prepare-github-token>`.
