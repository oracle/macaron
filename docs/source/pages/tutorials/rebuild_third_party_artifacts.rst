.. Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
.. Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

.. _tutorial-gen-build-spec:

*********************************************************
Rebuilding Third-Party Artifacts from Source with Macaron
*********************************************************

In this tutorial, you'll learn how to use Macaron's new ``gen-build-spec`` command to automatically generate build specification (buildspec) files from analyzed software packages.
These buildspecs help document and automate the build process for packages, enabling reproducibility and ease of integration with infrastructures such as Reproducible Central.

.. list-table::
   :widths: 25
   :header-rows: 1

   * - Currently Supported packages
   * - Maven packages built with Gradle or Maven

.. contents:: :local:

**********
Motivation
**********

Software ecosystems such as Maven Central are foundational to modern software supply chains, providing centralized repositories for libraries, plugins, and other components. However, one ongoing challenge is the separation between distributed binaries and their corresponding source code and build processes. For example, in Maven Central, there is often no direct, transparent link between a published binary and the environment in which it was built. In fact, recent studies show that around 84% of the top 1200 most commonly used Java artifacts are not built through transparent CI/CD pipelines.

This lack of transparency introduces security risks: users must trust not just the upstream source code, but also the build environment itself—including tools, plugins, and configuration details—which may not be visible or reproducible. As supply chain security becomes increasingly critical, rebuilding artifacts from source has become an essential strategy. This process enables deeper code review, verification of binary-source equivalence, and greater control over dependencies.

However, rebuilding artifacts reliably is difficult due to differences in build environments (such as JDK versions or specific build commands), and the challenge only increases with large, complex dependency graphs. Macaron addresses these issues by automating the extraction of build specifications from open CI/CD workflows (like GitHub Actions), improving source code detection, and providing the tools needed to make reproducible rebuilds easier and more robust. By supporting this workflow, Macaron helps increase both the security and transparency of the open-source software supply chain.

**********
Background
**********

A build specification is a file that describes all necessary information to rebuild a package from source. This includes metadata such as the build tool, the specific build command to run, the language version, e.g., JDK for Java, and artifact coordinates. Macaron can now generate this file automatically for supported ecosystems, greatly simplifying reproducible builds.

The generated buildspec will be stored in an ecosystem- and PURL-specific path under the ``output/`` directory (see more under :ref:`Output Files Guide <output_files_guide>`).

******************************
Installation and Prerequisites
******************************

You need:

* Docker
* Macaron image (see :ref:`installation-guide`)
* GitHub Token (see :ref:`prepare-github-token`)

*************************
Step 1: Analyze a Package
*************************

Before generating a buildspec, Macaron must first analyze the target package. For example, to analyze a Maven Java package:

.. code-block:: shell

    ./run_macaron.sh analyze -purl pkg:maven/org.apache.hugegraph/computer-k8s@1.0.0

This command will inspect the source repository, CI/CD configuration, and extract build-related data into the local database at ``output/macaron.db``.

*******************************************
Step 2: Generate a Build Specification File
*******************************************

After analysis is complete, you can generate a buildspec for the package using the ``gen-build-spec`` command.

.. code-block:: shell

    ./run_macaron.sh gen-build-spec -purl pkg:maven/org.apache.hugegraph/computer-k8s@1.0.0 --database output/macaron.db


After execution, the buildspec will be created at:

.. code-block:: text

    output/<purl_based_path>/macaron.buildspec

where ``<purl_based_path>`` is the directory structure according to the PackageURL (PURL).

In the example above, the buildspec is located at:

.. code-block:: text

    output/maven/org_apache_hugegraph/computer-k8s/macaron.buildspec

*****************************************
Step 3: Review and Use the Buildspec File
*****************************************

The generated buildspec uses the `Reproducible Central buildspec <https://reproducible-central.org/spec/>`_ format, for example:

.. code-block:: ini

    # Copyright (c) 2025, Oracle and/or its affiliates.
    # Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.
    # Generated by Macaron version 0.15.0
    # Input PURL - pkg:maven/org.apache.hugegraph/computer-k8s@1.0.0
    # Initial default JDK version 8 and default build command [['mvn', '-DskipTests=true', ... ]]
    groupId=org.apache.hugegraph
    artifactId=computer-k8s
    version=1.0.0
    gitRepo=https://github.com/apache/hugegraph-computer
    gitTag=d2b95262091d6572cc12dcda57d89f9cd44ac88b
    tool=mvn
    jdk=8
    newline=lf
    command="mvn -DskipTests=true -Dmaven.test.skip=true -Dmaven.site.skip=true -Drat.skip=true -Dmaven.javadoc.skip=true clean package"
    buildinfo=target/computer-k8s-1.0.0.buildinfo

You can now use this file to automate reproducible builds, for example as part of the Reproducible Central infrastructure.

*******************************
How It Works: Behind the Scenes
*******************************

The ``gen-build-spec`` command extracts build data from Macaron’s SQLite database, using several modules:

- **macaron_db_extractor.py:** extracts metadata and build information using SQLAlchemy ORM mapped classes.
- **Maven and Gradle CLI Parsers:** parses and patches build commands from CI/CD configs, to ensure compatibility with reproducible build systems.
- **jdk_finder.py:** identifies the JDK version by parsing CI/CD config or, when unavailable, extracting it from ``META-INF/MANIFEST.MF`` in Maven Central artifacts.
- **jdk_version_normalizer.py:** ensures only the major JDK version is included, as required by the buildspec format.

This feature is described in more detail in our accepted ASE 2025 Industry ShowCase paper: `"Unlocking Reproducibility: Automating re-Build Process for Open-Source Software" <https://arxiv.org/pdf/2509.08204>`_.

***********************************
Frequently Asked Questions (FAQs)
***********************************

*Q: What formats are supported for buildspec output?*
A: Currently, only ``rc-buildspec`` is supported.

*Q: Do I need to analyze the package every time before generating a buildspec?*
A: No, you only need to analyze the package once unless you want to update the database with newer information.

*Q: Can Macaron generate buildspecs for other ecosystems besides Maven?*
A: Ecosystem support is actively expanding. See :ref:`Supported Builds <supported_build_gen_tools>` for the latest details.

***********************************
Future Work and Contributions
***********************************

We plan to support more ecosystems, deeper integration with artifact repositories, and more user-configurable buildspec options. Contributions are welcome!

***********************************
See Also
***********************************

- :ref:`Output Files Guide <output_files_guide>`
- :ref:`installation-guide`
- :ref:`Supported Builds <supported_build_gen_tools>`
