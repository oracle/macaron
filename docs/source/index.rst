.. Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
.. Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

.. _index:

.. meta::
   :description: macaron - A CI/CD security analysis tool for supply-chain attacks
   :keywords: CI/CD, SLSA, supply-chain security

=====================
Macaron documentation
=====================

Macaron is an open-source software supply chain security tool from Oracle Labs to detect and prevent supply chain attacks across ecosystems like Python and Java. It automatically analyzes software packages (e.g., from PyPI or Maven Central) to detect malicious behavior and insecure DevOps practices. Macaron has reported over **225 malicious PyPI packages**, all confirmed and removed by the PyPI security team.

Macaron follows the recommendations of the `SLSA (Supply chain Levels for Software Artifacts) <https://slsa.dev>`_ framework. It features a **flexible and extensible policy engine** that allows users to define and compose custom rules tailored to their CI/CD environments and security goals.

It also supports **attestation verification**, **reproducible builds**, and **malicious artifact detection**, making it a valuable tool for securing the modern software supply chain.

--------
Overview
--------

Macaron is an analysis tool which focuses on the build process for an artifact and its dependencies. As the SLSA requirements
are at a high-level, Macaron first defines these requirements as specific
concrete rules that can be checked automatically. Macaron has a customizable checker platform that makes it easy to define checks that depend on each other.

---------------
Getting started
---------------

To start with Macaron, see the :doc:`Installation </pages/installation>` and :doc:`Using </pages/using>` pages.

For all services and technologies that Macaron supports, see the :doc:`Supported Technologies </pages/supported_technologies/index>` page.

.. _checks:

-------------------------
Current checks in Macaron
-------------------------

The table below shows the current set of actionable checks derived from
the requirements that are currently supported by Macaron.

.. list-table:: Macaron check descriptions
   :widths: 20 40 40
   :header-rows: 1

   * - Check ID
     - Summary
     - Concrete check
   * - ``mcn_build_tool_1``
     - **Build tool exists** - The source code repository includes configurations for a supported build tool used to produce the software component.
     - Detect the build tool used in the source code repository to build the software component.
   * - ``mcn_build_script_1``
     - **Scripted build** - All build steps were fully defined in a “build script”.
     - Identify and validate build script(s).
   * - ``mcn_provenance_available_1``
     - **Provenance available** - Provenances are available.
     - Check for existence of provenances, which can be :term:`SLSA` or :term:`Witness` provenances. If there is no provenance, the repo can still be compliant to level 1 given the build script is available.
   * - ``mcn_provenance_witness_level_one_1``
     - **Witness provenance** - One or more :term:`Witness` provenances are discovered.
     - Check for existence of :term:`Witness` provenances, and whether artifact digests match those in the provenances.
   * - ``mcn_build_service_1``
     - **Build service** - All build steps are run using some build service (e.g. GitHub Actions)
     - Identify and validate the CI service(s) used for the build process.
   * - ``mcn_provenance_verified_1``
     - **Provenance verified** - Provenance is available and verified.
     - See :doc:`SLSA Build Levels </pages/checks/slsa_builds>`
   * - ``mcn_trusted_builder_level_three_1``
     - **Trusted builders** - Guarantees the identification of the top-level build configuration used to initiate the build. The build is verified to be hermetic, isolated, parameterless, and executed in an ephemeral environment.
     - Identify and validate that the builder used in the CI pipeline is a trusted one.
   * - ``mcn_build_as_code_1``
     - **Build as code** - If a trusted builder is not present, this requirement determines that the build definition and configuration executed by the build service is verifiably derived from text file definitions stored in a version control system.
     - Identify and validate the CI service(s) used to build and deploy/publish an artifact.
   * - ``mcn_find_artifact_pipeline_1``
     - **Infer artifact publish pipeline** - When a provenance is not available, checks whether a CI workflow run has automatically published the artifact.
     - Identify a workflow run that has triggered the deploy step determined by the ``Build as code`` check.
   * - ``mcn_provenance_level_three_1``
     - **Provenance Level three** - Check whether the target has SLSA provenance level 3.
     - Use the `slsa-verifier <https://github.com/slsa-framework/slsa-verifier>`_ to attest to the subjects in the SLSA provenance that accompanies an artifact.
   * - ``mcn_provenance_expectation_1``
     - **Provenance expectation** - Check if the provenance meets an expectation.
     - The user can provide an expectation for the provenance as a CUE expectation file, which will be compared against the provenance.
   * - ``mcn_provenance_derived_repo_1``
     - **Provenance derived repo** - Check if the analysis target's repository matches the repository in the provenance.
     - If there is no provenance, this check will fail.
   * - ``mcn_provenance_derived_commit_1``
     - **Provenance derived commit** - Check if the analysis target's commit matches the commit in the provenance.
     - If there is no commit, this check will fail.
   * - ``mcn_scm_authenticity_check_1``
     - **Source repo authenticity** - Check whether the claims of a source code repository made by a package can be corroborated.
     - If the source code repository contains conflicting evidence regarding its claim of the source code repository, this check will fail. If no source code repository or corroborating evidence is found, or if the build system is unsupported, the check will return ``UNKNOWN`` as the result. This check supports Maven artifacts, and other artifacts that have a repository that is confirmed to be from a provenance file.
   * - ``mcn_detect_malicious_metadata_1``
     - **Malicious code detection** - Check whether the source code or package metadata has indicators of compromise.
     - This check performs analysis on PyPI package metadata to detect malicious behavior. It also reports known malware from other ecosystems.
   * - ``mcn_githubactions_vulnerabilities_1``
     - **Detect vulnerable GitHub Actions** - Check whether the GitHub Actions called from the corresponding repo have known vulnerabilities.
     - This check identifies third-party GitHub Actions used in a repository and reports any known vulnerabilities associated with the used versions.

----------------------
How does Macaron work?
----------------------

.. _fig_macaron:

.. figure:: _static/images/macaron_infrastructure.png
   :alt: Macaron infrastructure
   :align: center

   Macaron's infrastructure

Macaron is designed based on a Zero Trust model. It analyzes a target repository as an external
tool and requires minimal configurations. After cloning a repository, Macaron parses the CI
configuration files and bash scripts that are triggered by the CI, creates call graphs and other
intermediate representations as abstractions. Using such abstractions, Macaron implements concrete checks based on a security specification and verifies the desired properties.

.. toctree::
   :maxdepth: 2

   pages/installation
   pages/using
   pages/cli_usage/index
   pages/macaron_action
   pages/tutorials/index
   pages/output_files
   pages/checks/slsa_builds
   pages/vsa
   pages/supported_technologies/index
   pages/developers_guide/index
   glossary
