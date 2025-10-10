.. Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
.. Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

.. _cli-usage:

==================
Command Line Usage
==================

Use the bash script ``run_macaron.sh`` to run Macaron as a Docker container (for more information on how to get this script, please see :ref:`Download <download-macaron>`).

-----
Usage
-----

.. code-block:: shell

	usage: ./run_macaron.sh [-h] [-V] [-v] [--disable-rich-output] [-o OUTPUT_DIR] [-dp DEFAULTS_PATH] [-lr LOCAL_REPOS_PATH]
               				{analyze,dump-defaults,verify-policy,find-source,gen-build-spec} ...

Macaron's CLI has multiple common flags (e.g ``-h``, ``-V``) and different commands (e.g. ``analyze``), which have their own set of flags.

.. note:: Running ``--help`` on the main entry ``macaron`` will only print out the help for common flags. To print the help messages for command-specific flags, please provide the name of the command you want to know about. For example: ``./run_macaron.sh analyze --help``. The documented flags for each command can be found at `Commands`_.

--------------
Common Options
--------------

.. option:: -h, --help

    Show this help message and exit.

.. option:: -V, --version

    Show Macaron's version number and exit.

.. option:: -v, --verbose

    Run Macaron with more debug logs to provide additional information for debugging.

.. option:: --disable-rich-output

    Disable Rich UI output. This will turn off any rich formatting (e.g., colored output, tables, etc.) used in the terminal UI.

.. option:: -o OUTPUT_DIR, --output-dir OUTPUT_DIR

    The output destination path for Macaron. This is where Macaron will store the results of the analysis.

.. option:: -dp DEFAULTS_PATH, --defaults-path DEFAULTS_PATH

    The path to the defaults configuration file. This file can contain preset values for Macaron's options.

.. option:: -lr LOCAL_REPOS_PATH, --local-repos-path LOCAL_REPOS_PATH

    The directory where Macaron will look for already cloned repositories. This is useful for reusing locally stored repositories without re-cloning them.

---------------------
Environment Variables
---------------------

* ``MACARON_IMAGE_TAG``: The Docker image tag for a specific version of Macaron.

* ``DOCKER_PULL``: Whether to pull the Docker image from the `GitHub Container registry <https://github.com/oracle/macaron/pkgs/container/macaron>`_; must be one of: ``always``, ``missing``, ``never`` (default: ``always``).

---------------
Commands
---------------

.. toctree::
	:glob:
	:maxdepth: 1

	command*
