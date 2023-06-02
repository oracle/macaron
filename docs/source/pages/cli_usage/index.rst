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

	usage: ./run_macaron.sh [-h] [-V] [-v] [-o OUTPUT_DIR] [-dp DEFAULTS_PATH] [-lr LOCAL_REPOS_PATH] {analyze,dump-defaults,verify-policy} ...

Macaron's CLI has multiple common flags (e.g ``-h``, ``-V``) and different action commands (e.g. ``analyze``), which have their own set of flags.

.. note:: Running ``--help`` on the main entry ``macaron`` will only print out the help for common flags. To print the help messages for action-specific flags, please provide the name of the action you want to know about. For example: ``./run_macaron.sh analyze --help``. The documented flags for each action can be found at `Action Commands`_.

--------------
Common Options
--------------

.. option:: -h, --help

	Show this help message and exit

.. option:: -V, --version

	Show Macaron's version number and exit

.. option:: -v, --verbose

	Run Macaron with more debug logs

.. option:: -o OUTPUT_DIR, --output-dir OUTPUT_DIR

	The output destination path for Macaron

.. option:: -dp DEFAULTS_PATH, --defaults-path DEFAULTS_PATH

	The path to the defaults configuration file.

.. option:: -lr LOCAL_REPOS_PATH, --local-repos-path LOCAL_REPOS_PATH

	The directory where Macaron looks for already cloned repositories.

---------------
Action Commands
---------------

.. toctree::
	:glob:
	:maxdepth: 1

	action*
