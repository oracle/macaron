.. Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
.. Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

.. _using-guide:

=============
Using Macaron
=============

.. note:: The instructions below assume that you have setup you environment correctly to run Macaron (if not, please refer to :ref:`Installation Guide <installation-guide>`).

------------------------------------
Analyzing a public Github repository
------------------------------------

Macaron can analyze a Github public repository (and potentially the repositories of it dependencies) to determine its SLSA posture following the specification of `SLSA v0.1 <https://slsa.dev/spec/v0.1/>`_.

To run Macaron on a Github public repository, we use the following command:

.. code-block:: shell

  ./run_macaron.sh analyze -rp <repo_path>

With ``repo_path`` being the remote path to your target repository.

By default, Macaron will analyze the latest commit of the default branch. However, you could specify the branch and commit digest to run the analysis against:

.. code-block:: shell

  ./run_macaron.sh analyze -rp <repo_path> -b <branch_name> -d <digest>

For example, to analyze the SLSA posture of `micronaut-core <https://github.com/micronaut-projects/micronaut-core>`_ at branch 4.0.x and commit ``82d115b4901d10226552ac67b0a10978cd5bc603`` we could use the following command:

.. code-block:: shell

  ./run_macaron.sh analyze -rp https://github.com/micronaut-projects/micronaut-core -b 4.0.x -d 82d115b4901d10226552ac67b0a10978cd5bc603

.. note:: Macaron automatically detects and analyzes **direct** dependencies for Java Maven and Gradle projects. This process might take a while and can be skipped by using the ``--skip-deps`` option.

Take the same example as above, to disable analyzing `micronaut-core <https://github.com/micronaut-projects/micronaut-core>`_ direct dependencies, we could use the following command:

.. code-block:: shell

  ./run_macaron.sh analyze -rp https://github.com/micronaut-projects/micronaut-core -b 4.0.x -d 82d115b4901d10226552ac67b0a10978cd5bc603 --skip-deps

.. note:: During the analysis, Macaron would generate report files into the output directory in the current workspace. To understand the structure of this directory please see :ref:`Output Files Guide <output_files_guide>`.

With the example above, the generated output reports can be seen here:

- `micronaut-core.html <../_static/examples/micronaut-projects/micronaut-core/analyze_with_repo_path/micronaut-core.html>`__
- `micronaut-core.json <../_static/examples/micronaut-projects/micronaut-core/analyze_with_repo_path/micronaut-core.json>`__

----------------------
Analyzing with an SBOM
----------------------

Macaron can run the analysis against a `CycloneDX <https://cyclonedx.org/>`__ format SBOM, which contains all the necessary information of the target component and its dependencies. This use case is useful when you are running Macaron against a software component that is not available as a public GitHub repository but you still want to analyze the SLSA posture of its dependencies.

CycloneDX provides open-source SBOM generators for different types of project (e.g Maven, Gradle, etc) To know how you could generate an CycloneDX SBOM for your projects, please have a look at their `open-source organization <https://github.com/CycloneDX>`_.

For example, with `micronaut-core <https://github.com/micronaut-projects/micronaut-core>`_ at branch 4.0.x commit ``82d115b4901d10226552ac67b0a10978cd5bc603``, using the `CycloneDX Gradle plugin <https://github.com/CycloneDX/cyclonedx-gradle-plugin>`_ would give us the following `SBOM <./_static/micronaut-projects/micronaut-core/analyze_with_sbom/sbom.json>`_.

To run the analysis against that SBOM, run this command:

..
  TODO: Remove the -rp path after https://github.com/oracle-samples/macaron/issues/108 is merged.

.. code-block:: shell

  ./run_macaron.sh analyze -rp https://github.com/micronaut-projects/micronaut-core -sbom <path_to_sbom>

With ``path_to_sbom`` is the path to the SBOM you want to use.

With the example above, the generated output reports can be seen here:

- `micronaut-core.html <../_static/examples/micronaut-projects/micronaut-core/analyze_with_sbom/micronaut-core.html>`__
- `micronaut-core.json <../_static/examples/micronaut-projects/micronaut-core/analyze_with_sbom/micronaut-core.json>`__

-------------------------------------
Analyzing a locally cloned repository
-------------------------------------

If you have a local repository that you want to analyze, Macaron also supports running the analysis against a local repository.

Assume that the dir tree at the local repository has the following components:

.. code-block:: shell

  boo
  ├── foo
  │   └── target

We can run Macaron against the local repository at ``target`` by using this command:

.. code-block:: shell

  ./run_macaron.sh -lr path/to/boo/foo analyze -rp target <rest_of_args>

With ``rest_of_args`` being the arguments to the ``analyze`` command (e.g. ``-b``, ``-d`` or ``--skip-deps`` similar to two previous examples)

The ``-lr`` flag configure Macaron to looks into ``path/to/boo/foo`` for local repositories. For more information, please see :ref:`CLI options <cli-options>`.

.. note:: If ``-lr`` is not provided, Macaron will looks inside ``<working_directory>/output/git_repos/local_repos/`` whenever you provide a local path to ``-rp``.
