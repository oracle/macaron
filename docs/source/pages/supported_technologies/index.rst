.. Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
.. Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

.. _supported_technologies:

======================
Supported Technologies
======================

-----------
Build Tools
-----------

Macaron is able to detect the build and deployment scripts for the following build tools and package managers while analyzing the CI configurations,
such as GitHub Actions workflows.

* Maven
* Gradle
* Pip
* Poetry
* npm
* Yarn
* Go
* Docker


.. _supported_git_services:

------------
Git Services
------------

Currently, we support the following Git services for version control. If you need support for any other Git services, feel free to open a GitHub issue.

* `GitHub <https://github.com>`_
* `GitLab <https://gitlab.com>`_

------------
CI Services
------------

Currently, we support the following Continuous Integration (CI) services for automatically building and deploying artifacts. If you need support for any other CI services, feel free to open a GitHub issue.

.. list-table::
   :header-rows: 1

   * - CI Service
     - Support
   * - `GitHub Actions <https://github.com/features/actions>`_
     -
        * Detecting deployment steps by building a call graph for workflows and reachable shell scripts
        * Support for various GitHub APIs, such as Releases
   * - `GitLab <https://gitlab.com>`_
     - Partial support for detecting deployment steps
   * - `Jenkins <https://www.jenkins.io>`_
     - Partial support for detecting deployment steps
   * - `Travis CI <https://www.travis-ci.com>`_
     - Partial support for detecting deployment steps
   * - `CircleCI <https://circleci.com/>`_
     - Partial support for detecting deployment steps

------------------
Package Registries
------------------

.. list-table::
   :widths: 25 50 25
   :header-rows: 1

   * - Package Registry
     - Support
     - Documentation
   * - `JFrog Artifactory <https://jfrog.com/artifactory>`_
     - Projects built with Gradle and published to a JFrog Artifactory repo following `Maven layout <https://maven.apache.org/repository/layout.html>`_
     - :doc:`page </pages/supported_technologies/jfrog>`
   * - `Maven Central Artifactory <https://central.sonatype.com>`_
     - Projects built with Gradle or Maven and published on the Maven Central Artifactory.
     - :doc:`page </pages/supported_technologies/maven_central>`
   * - `npm Registry <https://registry.npmjs.org>`_
     - Projects built with npm or Yarn and published on the npm registry.
     - :doc:`page </pages/supported_technologies/npm_registry>`
   * - `Python Package Index (PyPI) <https://pypi.org/>`_
     - Projects built with Pip or Poetry and published on the PyPI registry.
     - :doc:`page </pages/supported_technologies/pypi_registry>`

-----------
Provenances
-----------

.. list-table::
   :widths: 25 50 25
   :header-rows: 1

   * - Provenance
     - Support
     - Documentation
   * - :term:`SLSA`
     -
       * | `SLSA provenance version 0.2 <https://slsa.dev/spec/v0.2/provenance>`_. The provenance should be published in one of the following ways:
         | - as a GitHub release asset.
         | - on the `npm registry <https://registry.npmjs.org>`_.
     - :doc:`page </pages/supported_technologies/jfrog>`
   * - :term:`Witness`
     -
       * Witness provenance version 0.1
       * Projects built with Gradle on GitLab CI
       * The provenance should be published on JFrog Artifactory
     - :doc:`page </pages/supported_technologies/jfrog>`

.. _supported_automatic_deps_resolution:

-------------------------------
Automatic dependency resolution
-------------------------------

Currently, we support the following type of project for automatic dependency resolution.

* Java Maven
* Java gradle

--------
See also
--------

.. toctree::
   :maxdepth: 1

   jfrog
   witness
   maven_central
   npm_registry
   pypi_registry
