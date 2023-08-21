======================
Supported Technologies
======================

------------
Git Services
------------

.. list-table::
   :header-rows: 1

   * - Git Service
   * - `GitHub <https://github.com>`_
   * - `GitLab <https://gitlab.com>`_

------------
CI Services
------------

.. list-table::
   :header-rows: 1

   * - CI Service
   * - `GitHub Actions <https://github.com/features/actions>`_


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
     - Only projects built with Gradle and publishing to a JFrog Artifactory repo following `Maven layout <https://maven.apache.org/repository/layout.html>`_
     - :doc:`page </pages/supported_technologies/jfrog>`

-----------
Provenances
-----------

.. list-table::
   :widths: 25 50 25
   :header-rows: 1

   * - Provenance
     - Support
     - Documentation
   * - `SLSA <https://slsa.dev>`_
     - Only provenances under `SLSA version 0.2 <https://slsa.dev/spec/v0.2/provenance>`_.
     - :doc:`page </pages/supported_technologies/jfrog>`
   * - `Witness <https://github.com/testifysec/witness>`_
     - * Only provenances under Witness version 0.1
       * Only projects built with Gradle on GitLab CI provenances and publishing provenances to JFrog Artifactory
     - :doc:`page </pages/supported_technologies/jfrog>`

--------
See also
--------

.. toctree::
   :maxdepth: 1

   jfrog
   witness
