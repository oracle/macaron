.. Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
.. Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

.. _cli-usage:

==================
Command Line Usage
==================

You could use the bash script ``run_macaron.sh`` we provided to run Macaron as a Docker image (For more information please see :ref:`Download Macaron <download-macaron>`). All of the command line options we included in this section can be provide to ``run_macaron.sh`` directly.

For example, with the following command line options:

.. code-block:: shell

	macaron --help

You could run it with:

.. code-block:: shell

	./run_macaron.sh macaron --help

-----
Usage
-----

.. code-block:: shell

	usage: macaron [-h] [-V] [-v] [-o OUTPUT_DIR] [-dp DEFAULTS_PATH] [-lr LOCAL_REPOS_PATH] {analyze,dump-defaults,verify-policy} ...

Macaron's CLI has multiple common flags (e.g ``-h``, ``-V``) and different action commands (e.g. ``analyze``) each has its own set of flags.

.. note:: Running ``--help`` on the main entry ``macaron`` will only print out the help for common flags. To print the help messages for action-specific flags, please provide the name of the action you want to know about. For example: ``./run_macaron.sh analyze --help``.

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

--------
See Also
--------

.. toctree::
	:glob:
	:maxdepth: 1

	action*
