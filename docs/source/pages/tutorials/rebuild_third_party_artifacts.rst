.. Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
.. Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

.. _tutorial-gen-build-spec:

---------------------------------------------------------
Rebuilding Third-Party Artifacts from Source with Macaron
---------------------------------------------------------

In this tutorial, you'll learn how to use Macaron's new ``gen-build-spec`` command to automatically generate build specification (buildspec) files from analyzed software packages.
These buildspecs help document and automate the build process for packages, enabling reproducibility and ease of integration with infrastructures such as `Reproducible Central <https://github.com/jvm-repo-rebuild/reproducible-central>`_. For a more detailed description of this feature, refer to our accepted ASE 2025 Industry Showcase paper: `Unlocking Reproducibility: Automating the Re-Build Process for Open-Source Software <https://arxiv.org/pdf/2509.08204>`_.

.. list-table::
   :widths: 25
   :header-rows: 1

   * - Currently Supported packages
   * - Maven packages built with Gradle or Maven

.. contents:: :local:

**********
Motivation
**********

Modern software supply chains rely heavily on centralized repositories like Maven Central to provide easy access to libraries and components. However, a major challenge persists: there is often no clear or transparent link between the published binaries and the environments in which they were built. `Our study <https://arxiv.org/pdf/2509.08204>`_ shows that about 84% of popular Java artifacts on Maven Central aren’t built through transparent CI/CD pipelines, leaving users to blindly trust not only the source code but also opaque build processes that can introduce hidden risks.

Addressing this lack of transparency is critical for improving supply chain security. Rebuilding software artifacts from source enables thorough code review, verifies that binaries match their sources, and ensures closer control over dependencies. Yet, recreating build environments is complex, especially with large dependency trees and varying configurations. Macaron tackles these challenges by automatically extracting build specifications from open CI/CD workflows, enhancing source detection, and making reproducible rebuilds more accessible. In doing so, it improves both security and transparency across the open-source software ecosystem.

**********
Background
**********

A build specification is a file that describes all necessary information to rebuild a package from source. This includes metadata such as the build tool, the specific build command to run, the language version, e.g., JDK for Java, and artifact coordinates. Macaron can now generate this file automatically for supported ecosystems, greatly simplifying build from source.

The generated buildspec will be stored in an ecosystem- and PURL-specific path under the ``output/`` directory (see more under :ref:`Output Files Guide <output_files_guide>`).

******************************
Installation and Prerequisites
******************************

Skip this section if you already know how to install Macaron.

.. toggle::

    Please follow the instructions :ref:`here <installation-guide>`. In summary, you need:

        * Docker
        * the ``run_macaron.sh``  script to run the Macaron image.

    .. note:: At the moment, Docker alternatives (e.g. podman) are not supported.


    You also need to provide Macaron with a GitHub token through the ``GITHUB_TOKEN``  environment variable.

    To obtain a GitHub Token:

    * Go to ``GitHub settings`` → ``Developer Settings`` (at the bottom of the left side pane) → ``Personal Access Tokens`` → ``Fine-grained personal access tokens`` → ``Generate new token``. Give your token a name and an expiry period.
    * Under ``"Repository access"``, choosing ``"Public Repositories (read-only)"`` should be good enough in most cases.

    Now you should be good to run Macaron. For more details, see the documentation :ref:`here <prepare-github-token>`.

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

After analysis is complete, you can generate a buildspec for the package using the ``gen-build-spec`` command. For more details, refer to the :ref:`gen-build-spec-command-cli`.

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

The generated buildspec uses the `Reproducible Central buildspec <https://github.com/jvm-repo-rebuild/reproducible-central/blob/master/doc/BUILDSPEC.md>`_ format, for example:

.. code-block:: ini

    # Generated by Macaron version 0.18.0

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

You can now use this file to automate rebuilding artifacts, for example as part of the Reproducible Central infrastructure.

************************
Step 4: Build Validation
************************

Validating builds is a crucial post-build step that should be performed independently of the build process. Once a build is complete, it is essential to verify that the resulting artifacts meet the established expectations and accurately reflect the original source. Validation techniques vary, ranging from bitwise equivalence, where the artifacts must match exactly at the binary level, to semantic equivalence, which ensures functional similarity even when the binary outputs differ. Each approach offers distinct advantages depending on the specific context.

For example, `Daleq <https://github.com/binaryeq/daleq>`_ is a tool that disassembles Java bytecode into an intermediate representation to infer equivalence between Java classes. Daleq is developed based on recent `research <https://arxiv.org/abs/2410.08427>`_ that proposes practical levels for establishing binary equivalence. To learn more about how Daleq works, see the `paper <https://arxiv.org/pdf/2508.01530>`_.

*******************************
How It Works: Behind the Scenes
*******************************

The ``gen-build-spec`` works as follows:

- Extracts metadata and build information from Macaron’s local SQLite database.
- Parses and modifies build commands from CI/CD configurations to ensure compatibility with rebuild systems.
- Identifies the JDK version by parsing CI/CD configurations or extracting it from the ``META-INF/MANIFEST.MF`` file in Maven Central artifacts.
- Ensures that only the major JDK version is included, as required by the build specification format.


This feature is described in more detail in our accepted ASE 2025 Industry ShowCase paper: `Unlocking Reproducibility: Automating the Re-Build Process for Open-Source Software <https://arxiv.org/pdf/2509.08204>`_.

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
