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
   * - Python packages built with the built-in ``build`` module and various build tools, like Poetry

.. contents:: :local:

**********
Motivation
**********

Modern software supply chains rely heavily on centralized repositories like Maven Central to provide easy access to libraries and components. However, a major challenge persists: there is often no clear or transparent link between the published binaries and the environments in which they were built. `Our study <https://arxiv.org/pdf/2509.08204>`_ shows that about 84% of popular Java artifacts on Maven Central aren’t built through transparent CI/CD pipelines, leaving users to blindly trust not only the source code but also opaque build processes that can introduce hidden risks.

Addressing this lack of transparency is critical for improving supply chain security. Rebuilding software artifacts from source enables thorough code review, verifies that binaries match their sources, and ensures closer control over dependencies. Yet, recreating build environments is complex, especially with large dependency trees and varying configurations. Macaron tackles these challenges by automatically extracting build specifications from open CI/CD workflows, enhancing source detection, and making reproducible rebuilds more accessible. In doing so, it improves both security and transparency across the open-source software ecosystem.

**********
Background
**********

A build specification is a file that describes all necessary information to rebuild a package from source. This includes metadata such as the build tool, the specific build command to run, the language version, e.g., Python or JDK for Java, and artifact coordinates. Macaron can now generate this file automatically for supported ecosystems, greatly simplifying build from source.

The generated buildspec will be stored in an ecosystem- and PURL-specific path under the ``output/`` directory (see more under :ref:`Output Files Guide <output_files_macaron_build_spec-Gen>`).

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

**************************
Rebuilding a Maven package
**************************

===========================
Step 1: Analyze the Package
===========================

Before generating a buildspec, Macaron must first analyze the target package. For example, to analyze a Maven Java package:

.. code-block:: shell

    ./run_macaron.sh analyze -purl pkg:maven/org.apache.hugegraph/computer-k8s@1.0.0

This command will inspect the source repository, CI/CD configuration, and extract build-related data into the local database at ``output/macaron.db``.

===========================================
Step 2: Generate a Build Specification File
===========================================

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

=========================================
Step 3: Review and Use the Buildspec File
=========================================

By default we generate the buildspec in JSON format as follows:

.. code-block:: ini

    {
        "macaron_version": "0.18.0",
        "group_id": "org.apache.hugegraph",
        "artifact_id": "computer-k8s",
        "version": "1.0.0",
        "git_repo": "https://github.com/apache/hugegraph-computer",
        "git_tag": "d2b95262091d6572cc12dcda57d89f9cd44ac88b",
        "newline": "lf",
        "language_version": [
            "11"
        ],
        "ecosystem": "maven",
        "purl": "pkg:maven/org.apache.hugegraph/computer-k8s@1.0.0",
        "language": "java",
        "build_tools": [
            "maven"
        ],
        "build_commands": [
            [
            "mvn",
            "-DskipTests=true",
            "-Dmaven.site.skip=true",
            "-Drat.skip=true",
            "-Dmaven.javadoc.skip=true",
            "clean",
            "package"
            ]
        ]
    }

If you use the ``rc-buildspec`` output format, the generated buildspec follows the `Reproducible Central buildspec <https://github.com/jvm-repo-rebuild/reproducible-central/blob/master/doc/BUILDSPEC.md>`_ format. For example, you can generate it with:

.. code-block:: shell

    ./run_macaron.sh gen-build-spec -purl pkg:maven/org.apache.hugegraph/computer-k8s@1.0.0 --database output/macaron.db --output-format rc-buildspec

The resulting file will be saved as ``output/buildspec/maven/org_apache_hugegraph/computer-k8s/reproducible_central.buildspec``, and will look like this:

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
    command="mvn -Dmaven.test.skip=true -DskipTests=true -Dmaven.site.skip=true -Drat.skip=true -Dmaven.javadoc.skip=true clean package"
    buildinfo=target/computer-k8s-1.0.0.buildinfo

You can now use this file to automate rebuilding artifacts, for example as part of the Reproducible Central infrastructure.

========================
Step 4: Build Validation
========================

Validating builds is a crucial post-build step that should be performed independently of the build process. Once a build is complete, it is essential to verify that the resulting artifacts meet the established expectations and accurately reflect the original source. Validation techniques vary, ranging from bitwise equivalence, where the artifacts must match exactly at the binary level, to semantic equivalence, which ensures functional similarity even when the binary outputs differ. Each approach offers distinct advantages depending on the specific context.

For example, `Daleq <https://github.com/binaryeq/daleq>`_ is a tool that disassembles Java bytecode into an intermediate representation to infer equivalence between Java classes. Daleq is developed based on recent `research <https://arxiv.org/abs/2410.08427>`_ that proposes practical levels for establishing binary equivalence. To learn more about how Daleq works, see the `paper <https://arxiv.org/pdf/2508.01530>`_.

*************************
Rebuilding a Python wheel
*************************

The above workflow can be adopted to generate build specifications for Python wheels, often distributed via PyPI, as well. Consider the purl ``pkg:pypi/docker@7.1.0``. We can run analyze like:

.. code-block:: shell

    ./run_macaron.sh analyze -purl pkg:pypi/docker@7.1.0

Similar to the Maven example, it is also possible to generate a JSON buildspec. However, for this tutorial, we will generate a ``dockerfile`` output. To do this, run ``gen-build-spec`` with the ``--output-format`` flag set to ``dockerfile``, as shown below:

.. code-block:: shell

    ./run_macaron.sh gen-build-spec -purl pkg:pypi/docker@7.1.0 --database output/macaron.db --output-format dockerfile

The dockerfile will be created at:

.. code-block:: text

    output/<purl_based_path>/dockerfile.buildspec

Its contents should look like:

.. code-block:: text

    #syntax=docker/dockerfile:1.10
    FROM oraclelinux:9

    # Install core tools
    RUN dnf -y install which wget tar git

    # Install compiler and make
    RUN dnf -y install gcc make

    # Download and unzip interpreter
    RUN <<EOF
        wget https://www.python.org/ftp/python/3.14.0/Python-3.14.0.tgz
        tar -xf Python-3.14.0.tgz
    EOF

    # Install necessary libraries to build the interpreter
    # From: https://devguide.python.org/getting-started/setup-building/
    RUN dnf install \
    gcc-c++ gdb lzma glibc-devel libstdc++-devel openssl-devel \
    readline-devel zlib-devel libzstd-devel libffi-devel bzip2-devel \
    xz-devel sqlite sqlite-devel sqlite-libs libuuid-devel gdbm-libs \
    perf expat expat-devel mpdecimal python3-pip

    # Build interpreter and create venv
    RUN <<EOF
        cd Python-3.14.0
        ./configure --with-pydebug
        make -s -j $(nproc)
        ./python -m venv /deps
    EOF

    # Clone code to rebuild
    RUN <<EOF
        mkdir src
        cd src
        git clone https://github.com/docker/docker-py .
        git checkout --force a3652028b1ead708bd9191efb286f909ba6c2a49
    EOF

    WORKDIR /src

    # Install build and the build backends
    RUN <<EOF
        /deps/bin/pip install "hatchling==1.24.2" && /deps/bin/pip install "hatch-vcs"
        /deps/bin/pip install build
    EOF

    # Run the build
    RUN /deps/bin/python -m build --wheel -n

We can then build the dockerfile like:

.. code-block:: shell

    docker build -f output/<purl_based_path>/dockerfile.buildspec .

If the build succeeds, the package was successfully rebuilt. The image can then be run as needed to perform further validation.

*******************************
How It Works: Behind the Scenes
*******************************

The ``gen-build-spec`` works as follows:

- Extracts metadata and build information from Macaron’s local SQLite database.
- Parses and modifies build commands from CI/CD configurations to ensure compatibility with rebuild systems.
- Identifies the language version, e.g., JDK version by parsing CI/CD configurations or extracting it from the ``META-INF/MANIFEST.MF`` file in Maven Central artifacts.
- Ensures that only the major JDK version is included, as required by the build specification format.


The Java support for this feature is described in more detail in our accepted ASE 2025 Industry ShowCase paper: `Unlocking Reproducibility: Automating the Re-Build Process for Open-Source Software <https://arxiv.org/pdf/2509.08204>`_.

***********************************
Frequently Asked Questions (FAQs)
***********************************

*Q: What formats are supported for buildspec output?*
A: Currently, a default JSON spec and optional ``rc-buildspec`` are supported.

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
