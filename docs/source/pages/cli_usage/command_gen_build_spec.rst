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

    The desired output format for the build specification. The default format is `rc-buildspec`, which is the Reproducible-Central build specification.
    Other formats may be available depending on your configuration.
