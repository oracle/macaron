.. Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
.. Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

-------------
Source Finder
-------------

This tutorial demonstrates how Macaron can find the source commit of a given artifact, and optionally the source repository, while performing no analyses. This operation exists as a standalone feature, using the ``find-source`` command, for users that wish to utilise only these features of Macaron without spending time performing additional unnecessary steps.

Unlike the integrated commit finder (demonstrated in another tutorial :doc:`here </pages/tutorials/source_finder>`), the ``find-source`` command does not require cloning the target repository, thereby saving time in many cases, and disk space in all cases. For those who still wish to clone the repository as part of the process, a configuration option exists and will be explained below.

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

*********
Execution
*********

To use the ``find-source`` command and find the repository and commit for an artifact, Macaron can be run with the following command:

.. code-block:: shell

    ./run_macaron.sh find-source -purl pkg:npm/semver@7.6.2

The output of the command will be written to the command line, and to a report file in the JSON format. The report can be found within the ``output`` folder under the respective path of the artifact that was passed to the command.  (See :ref:`Output Files Guide <output_files_guide>`). In this case, Macaron created a report file: ``output/reports/npm/semver/semver.source.json``, which contains the repository and commit that was found.

To open the report and view the contents, you can use the following:

.. code-block:: shell

  open output/reports/npm/semver/semver.source.json

Inside you will find the ``repo`` and ``commit`` properties have been populated with ``https://github.com/npm/node-semver`` and ``eb1380b1ecd74f6572831294d55ef4537dfe1a2a`` respectively. As this is a GitHub repository, Macaron also creates a URL that leads directly to the reported commit, found under the ``url`` property.

If the repository for an artifact is already known, the ``find-source`` command can be given it to save looking it up again. To do this, the command changes to:

.. code-block:: shell

    ./run_macaron.sh find-source -purl pkg:npm/semver@7.6.2 -rp https://github.com/npm/node-semver

.. note:: If you are unfamiliar with PackageURLs (purl), see this link: `PURLs <https://github.com/package-url/purl-spec>`_.

********************
Execution with Clone
********************

For the case where cloning the repository is desirable, perhaps because further use of the contents are planned, Macaron requires this to be specified in a custom ``ini`` configuration file that is passed as input. See `How to change the default configuration </pages/using#change-config>`_ for more details. Within the configuration file the following option should be set:

.. code-block:: ini

    [repofinder]
    find_source_should_clone = True

Then Macaron can be run with:

.. code-block:: shell

      ./run_macaron.sh -dp <path-to-modified-default.ini> find-source -purl pkg:npm/semver@7.6.2
