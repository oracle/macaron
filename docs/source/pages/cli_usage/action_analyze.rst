=======
Analyze
=======

-----------
Description
-----------

Analyze a Github public repository (and potentially the repositories of it dependencies) to determine its SLSA posture following the specification of `SLSA v0.1 <https://slsa.dev/spec/v0.1/>`_.

-----
Usage
-----

.. code-block:: shell

    usage: macaron analyze
        [-h] [-sbom SBOM_PATH] [-rp REPO_PATH] [-b BRANCH]
        [-d DIGEST] [-pe PROVENANCE_EXPECTATION] [-c CONFIG_PATH]
        [--skip-deps] [-g TEMPLATE_PATH]

-------
Options
-------

.. option:: -h, --help

	Show this help message and exit

.. option:: -sbom SBOM_PATH, --sbom-path SBOM_PATH

    The path to the SBOM of the analysis target.

.. option:: -rp REPO_PATH, --repo-path REPO_PATH

    The path to the repository, can be local or remote


.. option:: -b BRANCH, --branch BRANCH

    The branch of the repository that we want to checkout. If not set, Macaron will use the default branch

.. option:: -d DIGEST, --digest DIGEST

    The digest of the commit we want to checkout in the branch. If not set, Macaron will use the latest commit

.. option:: -pe PROVENANCE_EXPECTATION, --provenance-expectation PROVENANCE_EXPECTATION

    The path to provenance expectation file or directory.

.. option:: -c CONFIG_PATH, --config-path CONFIG_PATH

    The path to the user configuration.

.. option:: --skip-deps

    Skip automatic dependency analysis.

.. option:: -g TEMPLATE_PATH, --template-path TEMPLATE_PATH

    The path to the Jinja2 html template (please make sure to use .html or .j2 extensions).

-----------
Environment
-----------

``GITHUB_TOKEN`` – The GitHub personal access token needed for Macaron to run the analysis. For more information on how to obtain a token for Macaron, please see instructions in :ref:`Prepare GitHub access token <prepare-github-token>`.
