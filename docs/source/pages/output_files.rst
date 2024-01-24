.. Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
.. Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

.. _output_files_guide:

==================
Output Files Guide
==================

.. note:: Please see :ref:`pages/cli_usage/index:common options` for the instructions on how to set the output directory of Macaron.

--------------------------------
Output files of macaron analyze
--------------------------------

^^^^^^^^^^^^^^^^^^^
Top level structure
^^^^^^^^^^^^^^^^^^^

.. code-block::

    output/
        ├── .gradle/
        ├── .m2/
        ├── build_log/
        ├── git_repos/
        ├── reports/
        ├── debug.log
        ├── macaron.db
        └── sbom_debug.json

^^^^^^^
Reports
^^^^^^^

The report files of Macaron (from using the :ref:`analyze command <analyze-command-cli>`) are generated into the ``reports`` directory.

.. code-block::

    output/
    └── reports/
        └── ...

''''''''''''''''''
Unique result path
''''''''''''''''''

For each target software component, Macaron creates a directory under ``reports`` to store the report files. This directory
path is formed from the PURL string of that component. The final path is created using the following template:

.. code-block::

    <path_to_output>/reports/<purl_type>/<purl_namespace>/<purl_name>

For more information on the three fields ``type``, ``namespace`` and ``name`` of a PURL string, please see
`PURL Specification <https://github.com/package-url/purl-spec/blob/master/PURL-SPECIFICATION.rst>`_.

Typically, when a repository path is provided as the main software component of the :ref:`analyze command <analyze-command-cli>`,
a PURL is generated from the repository path, which is then later used in generating the unique report path.

For example, when running this command:

.. code-block::

  ./run_macaron.sh analyze -rp https://github.com/micronaut-projects/micronaut-core

The report files will be stored into:

.. code-block::

  <path_to_output>/reports/github_com/micronaut-projects/micronaut-core

.. note:: In the unique path, only ASCII letters, digits and ``-`` are allowed. Prohibited characters are changed into
  ``_``. No changes to the letter case are made.

For example, the reports for `<https://github.com/micronaut-projects/micronaut-core>`_ will be stored under
``<path_to_output>/reports/github_com/micronaut-projects/micronaut-core``.

''''''''''''
Report types
''''''''''''

Macaron creates three types of reports:

#. JSON reports (``*.json`` files): contain the analysis result.
#. HTML reports (``*.html`` files): display the analysis result in HTML pages.
#. Dependencies report (``dependencies.json``): contain the list of dependencies that Macaron found for the target repository.

.. note:: The JSON and HTML reports for dependencies (if any) are stored in the same directory as the target repository.

For example, for `<https://github.com/micronaut-projects/micronaut-core>`_ the report directory can have the following structure:

.. code-block::

    output/
    └── reports/
        └── github_com/
            └── micronaut-projects
                └── micronaut-core
                    ├── dependencies.json
                    ├── micronaut-core.html
                    ├── micronaut-core.json
                    ├── dependency_1.html
                    ├── dependency_1.json
                    ├── dependency_2.html
                    ├── dependency_2.json
                    └── ...

^^^^^^^^^^^^^^^^^^^
Cloned repositories
^^^^^^^^^^^^^^^^^^^

The ``git_repos`` directory is used to clone repositories into during the analysis. Each remote repository is cloned to a unique path
within ``git_repos`` following the same strategy as `Unique result path`_.

For example, `<https://github.com/micronaut-projects/micronaut-core>`_ will be cloned into:

.. code-block::

    output/
    └── git_repos
        └── micronaut-projects
            └── micronaut-core

By default, if a local path is provided to the :ref:`analyze command <analyze-command-cli>`, this path will be treated as a relative path
to the directory:

.. code-block::

    output/
    └── git_repos
        └── local_repos

.. note:: Please see :ref:`pages/using:analyzing a locally cloned repository` to know how to set the directory for analyzing local repositories.

.. _output_files_macaron_verify_policy:

-------------------------------------
Output files of macaron verify-policy
-------------------------------------

As part of the ``macaron verify-policy`` command, Macaron generates a :ref:`Verification Summary Attestation<vsa>` (VSA) with the following strategy:

* If the Datalog policy applies to a unique software component identified by a unique PURL, a VSA is generated based on the latest analysis results for that specific software component in the Macaron database.
* Otherwise, if the Datalog policy applies to multiple software components identified by multiple different PURLs, no VSA will be generated.

The VSA file will be generated into ``output/vsa.intoto.jsonl`` by default.

.. code-block::

    output/
    └── vsa.intoto.jsonl


Users can manually inspect the payload of the VSA generated by Macaron with the following command:

.. code-block:: bash

    cat output/vsa.intoto.jsonl | jq -r '.payload' | base64 -d | jq


For more details about the Macaron-generated VSAs, please refer to the :ref:`Verification Summary Attestation page<vsa>`.


------
Others
------

^^^^^^^^^^
macaron.db
^^^^^^^^^^

The file is the SQLite database used by Macaron for storing analysis results.

^^^^^^^^^
debug.log
^^^^^^^^^

This file stores the log messages from the latest run of Macaron.

^^^^^^^^^
build_log
^^^^^^^^^

This is the directory for storing the log from running external components such as `CycloneDx SBOM Maven plugin <https://github.com/CycloneDX/cyclonedx-maven-plugin>`_, `CycloneDx SBOM Gradle plugin <https://github.com/CycloneDX/cyclonedx-gradle-plugin>`_ or the `slsa-verifier <https://github.com/slsa-framework/slsa-verifier>`_.

^^^^^^^^^^^^^^^
sbom_debug.json
^^^^^^^^^^^^^^^

This file contain the debug information for running the SBOM generator to obtain dependencies of a repository.

^^^^^^^^^^^^^^^
.m2 and .gradle
^^^^^^^^^^^^^^^

These two directories cache the content of ``~/.m2`` and ``~/.gradle`` in the Docker container between different runs (which are
mainly updated by the CycloneDX SBOM plugins).
This will helps subsequent runs on the same target repository faster.
