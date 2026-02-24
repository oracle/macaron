.. Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
.. Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

.. _gen-build-spec-command-cli:

============================
Generate Build Specification
============================

-----------
Description
-----------

Generate a build specification for a given software component.

-----
Usage
-----

.. code-block:: shell

    usage: ./run_macaron.sh gen-build-spec [-h] -purl PACKAGE_URL --database DATABASE [--output-format OUTPUT_FORMAT]

-------
Options
-------

.. option:: -h, --help

    Show this help message and exit.

.. option:: -purl PACKAGE_URL, --package-url PACKAGE_URL

    The PURL (Package URL) string of the software component for which the build specification is to be generated.

.. option:: --database DATABASE

    Path to the database.

.. option:: --output-format OUTPUT_FORMAT

    The output format. Can be `default-buildspec` (default), `rc-buildspec` (Reproducible-central build spec for Java), or `dockerfile` (currently only supported for Python packages)

.. _gen-build-spec-schema:

--------------------------
Build Specification Schema
--------------------------

The corresponding JSON schema is available in the `resources directory <https://github.com/oracle/macaron/tree/main/src/macaron/resources/schemas/macaron_buildspec_schema.json>`_ of the repository. Be sure to use the schema that matches your Macaron release by selecting the appropriate GitHub tag.
