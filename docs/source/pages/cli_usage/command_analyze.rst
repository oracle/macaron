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
        [-h] [-sbom SBOM_PATH] [-purl PURL] [-rp REPO_PATH] [-b BRANCH]
        [-d DIGEST] [-pe PROVENANCE_EXPECTATION]
        [--deps-depth DEPS_DEPTH] [-g TEMPLATE_PATH]
        [--python-venv PYTHON_VENV]
        [--local-maven-repo LOCAL_MAVEN_REPO]

-------
Options
-------

.. option:: -h, --help

	Show this help message and exit

.. option:: -sbom SBOM_PATH, --sbom-path SBOM_PATH

    The path to the SBOM of the analysis target.

.. option:: -purl PACKAGE_URL, --package-url PACKAGE_URL

    The PURL string used to uniquely identify the target software component for analysis. Note: this PURL string can be
    consequently used in the policies passed
    to the policy engine for the same target.

.. option:: -rp REPO_PATH, --repo-path REPO_PATH

    The path to the repository, can be local or remote

.. option:: -b BRANCH, --branch BRANCH

    The branch of the repository that we want to checkout. If not set, Macaron will use the default branch

.. option:: -d DIGEST, --digest DIGEST

    The digest of the commit we want to checkout in the branch. If not set, Macaron will use the latest commit

.. option:: -pe PROVENANCE_EXPECTATION, --provenance-expectation PROVENANCE_EXPECTATION

    The path to provenance expectation file or directory.

.. option:: -pf PROVENANCE_FILE, --provenance-file PROVENANCE_FILE

    The path to the provenance file in in-toto format.

.. option:: --deps-depth DEPS_DEPTH

    The depth of the dependency resolution. 0: disable, 1: direct dependencies, inf: all transitive dependencies. (Default: 0)

.. option:: -g TEMPLATE_PATH, --template-path TEMPLATE_PATH

    The path to the Jinja2 html template (please make sure to use .html or .j2 extensions).

.. option::  --python-venv PYTHON_VENV

    The path to the Python virtual environment of the target software component.

.. option:: --local-maven-repo LOCAL_MAVEN_REPO

    The path to the local .m2 directory. If this option is not used, Macaron will use the default location at $HOME/.m2

.. option:: --verify-provenance

    Allow the analysis to attempt to verify provenance files as part of its normal operations.

.. option:: --force-analyze-source

    Forces PyPI sourcecode analysis to run regardless of other heuristic results. Requires '--analyze-source'.

.. option:: --analyze-source

    For improved malware detection, analyze the source code of the (PyPI) package using a textual scan and dataflow analysis.

-----------
Environment
-----------

``GITHUB_TOKEN`` – The GitHub personal access token is needed for to run the analysis. For more information on how to obtain a GitHub token, see instructions in :ref:`Prepare GitHub access token <prepare-github-token>`.
