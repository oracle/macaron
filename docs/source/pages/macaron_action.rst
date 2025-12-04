Macaron GitHub Action
=====================

Overview
--------

This document describes the composite GitHub Action defined in ``action.yaml`` at the repository root. The action uses the Macaron CLI to run supply-chain security analysis and policy verification from a GitHub Actions workflow.

Quick usage
-----------

When using this action you can reference the action in your workflow. Example:

.. code-block:: yaml

  jobs:
    analyze:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - name: Run Macaron Security Analysis
          uses: oracle/macaron@v1
          with:
            repo_path: 'https://github.com/example/project'
            output_dir: 'macaron-output'

Example: policy verification only
----------------------------------

To run only the policy verification step (when you already have an output
database), call the action with ``policy_file`` and set ``output_dir`` to the
directory containing ``macaron.db``:

.. code-block:: yaml

  - name: Verify policy
    uses: oracle/macaron@v1
    with:
      policy_file: policy.dl
      output_dir: macaron-output

Inputs
------
The action exposes a number of inputs which map directly to Macaron CLI
options. Key inputs are listed below (see ``action.yaml`` for the full list):

.. list-table:: Action inputs
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
   * - ``deps_depth``
     - Dependency resolution depth (how many levels of transitive dependencies
       to resolve).
     - ``0``
   * - ``github_token``
     - Token used by Macaron to access GitHub (for cloning, API access,
       etc.).
     - ``${{ github.token }}``
   * - ``output_dir``
     - Directory where Macaron writes results (database, reports, artifacts).
     - ``output``
   * - ``upload_attestation``
     - When ``true``, the action will attempt to upload a generated
       verification attestation (VSA) after policy verification.
     - ``false``

Outputs
-------

The composite action exposes the following outputs (set by the
``run_macaron_policy_verification.sh`` script when applicable):

.. list-table:: Action outputs
   :header-rows: 1
   :widths: 20 70

   * - Output
     - Description
   * - ``policy_report``
     - Path to the generated policy report JSON file produced by
       ``macaron verify-policy``. This file contains the policy evaluation
       results.
   * - ``vsa_report``
     - Path to the generated VSA (Verification Summary Attestation) in
       `in-toto <https://in-toto.io/>`_ JSONL format. If no VSA was produced
       during verification, the action emits the string ``"VSA Not Generated."``
       instead of a path.

How the action works
--------------------

1. ``Setup Macaron``: downloads ``run_macaron.sh`` script to install and run macaron in the action.

2. ``Run Macaron Analysis``: calls ``scripts/actions/run_macaron_analysis.sh``
   which assembles the ``macaron analyze`` command from the inputs and runs
   it. Results are written into ``output_dir``.

3. ``Run Macaron Policy Verification``: if a policy file or PURL is supplied,
   the corresponding script runs ``macaron verify-policy`` against the
   analysis database and writes ``policy_report`` and ``vsa_report`` to
   ``$GITHUB_OUTPUT`` when produced.
