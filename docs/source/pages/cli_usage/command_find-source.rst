.. Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
.. Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

.. _find-source-command-cli:

===========
Find Source
===========

-----------
Description
-----------

Find the source commit, and optionally source repository, of a target artifact.

-----
Usage
-----

.. code-block:: shell

    usage: ./run_macaron.sh find-source -purl PURL [-rp REPO_PATH]

-------
Options
-------

.. option:: -h, --help

    Show this help message and exit

.. option:: -purl PACKAGE_URL, --package-url PACKAGE_URL

    The PURL string used to uniquely identify the artifact.

.. option:: -rp REPO_PATH, --repo-path REPO_PATH

    The path to the repository.
