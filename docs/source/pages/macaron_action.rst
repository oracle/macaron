Macaron GitHub Action
=====================

Overview
--------

This document describes the composite GitHub Action defined in ``action.yaml`` at the repository root. The action uses the Macaron CLI to run supply-chain security analysis and policy verification from a GitHub Actions workflow.

Quick usage
-----------

When you use this action, you can reference it directly in your workflow. For a real-world example, check out our `workflow <https://github.com/oracle/macaron/blob/main/.github/workflows/macaron-analysis.yaml>`_ (we use it for dogfooding), or follow the example below to understand how it works:

.. code-block:: yaml

  jobs:
    analyze:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@08c6903cd8c0fde910a37f88322edcfb5dd907a8 # v5.0.0
        - name: Run Macaron Security Analysis Action
          uses: oracle/macaron@fda4dda04aa7228fcaba162804891806cf5a1375 # v0.22.0
          with:
            repo_path: 'https://github.com/example/project'
            policy_file: check-github-actions
            policy_purl: 'pkg:github.com/example/project'
            reports_retention_days: 90

By default, the action posts a human-friendly results summary to the GitHub Actions run page (job summary). If you upload the results like in this `workflow <https://github.com/oracle/macaron/blob/main/.github/workflows/macaron-analysis.yaml>`_, check this :ref:`documentation <detect-vuln-gh-actions-results>` to see how to read and understand them.

Example: policy verification only
----------------------------------

To run only the policy verification step (when you already have an output
database), call the action with ``policy_file``. If the previous analysis step
used the default output path, you can omit ``output_dir`` here. If you set a
custom ``output_dir`` in the previous step, use the same value here so policy
verification reads the matching ``macaron.db``.

.. code-block:: yaml

  - name: Verify policy
    uses: oracle/macaron@fda4dda04aa7228fcaba162804891806cf5a1375 # v0.22.0
    with:
      policy_file: policy.dl

Inputs
------
The action exposes a number of inputs which map directly to Macaron CLI
options. Key inputs are listed below (see ``action.yaml`` for the full list):

.. list-table::
   :header-rows: 1
   :widths: 20 60 20

   * - Input
     - Description
     - Default
   * - ``repo_path``
     - The path or URL of the repository to analyze.
     -
   * - ``package_url``
     - A PURL identifying a package to analyze instead of a repository.
     -
   * - ``sbom_path``
     - Path to an SBOM file to analyze.
     -
   * - ``python_venv``
     - Path to an existing Python virtualenv (used when analyzing Python
       packages).
     -
   * - ``defaults_path``
     - Path to a Macaron defaults configuration file.
     -
   * - ``policy_file``
     - Path to a Datalog policy file for policy verification.
     -
   * - ``policy_purl``
     - PURL for a pre-defined policy to use with verification.
     -
   * - ``branch`` / ``digest``
     - Checkout options when analyzing a repository (branch name or commit
       digest).
     -
   * - ``provenance_expectation``
     - The path to provenance expectation file or directory.
     -
   * - ``provenance_file``
     - The path to the provenance file in in-toto format.
     -
   * - ``deps_depth``
     - Dependency resolution depth (how many levels of transitive dependencies
       to resolve).
     - ``0``
   * - ``show_prelude``
     - Shows the Datalog prelude for the database.
     -
   * - ``github_token``
     - Token used by Macaron to access GitHub (for cloning, API access,
       etc.).
     - ``${{ github.token }}``
   * - ``output_dir``
     - Directory where Macaron writes results (database, reports, artifacts).
     - ``output``
   * - ``upload_reports``
     - When ``true``, upload generated Macaron reports as a workflow artifact.
     - ``true``
   * - ``reports_artifact_name``
     - Name of the uploaded reports artifact.
     - ``macaron-reports``
   * - ``reports_retention_days``
     - Retention period in days for uploaded reports artifacts.
     - ``90``
   * - ``write_job_summary``
     - When ``true``, write a human-friendly summary to the workflow run page.
     - ``true``
   * - ``upload_attestation``
     - When ``true``, the action will attempt to upload a generated
       verification attestation (VSA) after policy verification. The attestation will be available
       under the ``Actions/management`` tab. This feature requires ``id-token: write`` and
       ``attestations: write`` Job permissions in the GitHub Actions workflow.
     - ``false``
   * - ``subject_path``
     - Path to the artifact serving as the subject of the attestation.
     - ``${{ github.workspace }}``

Outputs
-------

The composite action exposes the following outputs (set by the action steps,
primarily ``Collect report paths``, with some values populated only when
analysis/policy verification generated them):

.. list-table::
   :header-rows: 1
   :widths: 20 70

   * - Output
     - Description
   * - ``html_report_path``
     - Path to the generated HTML analysis report (when available).
   * - ``report_dir``
     - Directory containing generated HTML/JSON reports.
   * - ``db_path``
     - Path to the generated Macaron SQLite database (typically ``<output_dir>/macaron.db``).
   * - ``policy_report``
     - Path to the generated policy report JSON file produced by
       ``macaron verify-policy``. This file contains the policy evaluation
       results.
   * - ``vsa_report``
     - Path to the generated VSA (Verification Summary Attestation) in
       `in-toto <https://in-toto.io/>`_ JSONL format. If no VSA was produced
       during verification, the action emits the string ``"VSA Not Generated."``
       instead of a path. The attestation will be available
       under the ``Actions/management`` tab.
   * - ``vsa_generated``
     - ``true`` when a VSA was generated; otherwise ``false``.

Default Policies
----------------

Macaron provides policy templates to run pre-defined policies:

.. list-table::
   :header-rows: 1
   :widths: 20 60 20

   * - Policy name
     - Description
     - Template
   * - ``check-github-actions``
     - Detects whether a component was built using GitHub Actions that
       are known to be vulnerable or otherwise unsafe. The policy
       evaluates a check named `mcn_githubactions_vulnerabilities_1` and
       reports a passed/failed result for the component when applied.
     - `check-github-actions template <https://github.com/oracle/macaron/blob/main/src/macaron/resources/policies/datalog/check-github-actions.dl.template>`_
   * - ``malware-detection``
     - Checks a component for indicators of malicious or suspicious content.
       The policy evaluates a check named mcn_detect_malicious_metadata_1
       and reports a passed/failed result for the component when applied.
     - `malware-detection template <https://github.com/oracle/macaron/blob/main/src/macaron/resources/policies/datalog/malware-detection.dl.template>`_
   * - ``malware-detection-dependencies``
     - Checks the component and its transitive dependencies for indicators
       of malicious or suspicious content. The policy ensures the component
       and each dependency pass the `mcn_detect_malicious_metadata_1` check.
     - `malware-detection-dependencies template <https://github.com/oracle/macaron/blob/main/src/macaron/resources/policies/datalog/malware-detection-dependencies.dl.template>`_

How the action works
--------------------

1. ``Setup Macaron``: downloads ``run_macaron.sh`` script to install and run macaron in the action.

2. ``Run Macaron Analysis``: calls ``scripts/actions/run_macaron_analysis.sh``
   which assembles the ``macaron analyze`` command from the inputs and runs
   it. Results are written into ``output_dir``.

3. ``Run Macaron Policy Verification``: if ``policy_file`` is supplied,
   the corresponding script runs ``macaron verify-policy`` against the
   analysis database (using ``policy_purl`` when provided) and writes
   policy-related outputs when produced.
