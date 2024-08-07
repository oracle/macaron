.. Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
.. Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

.. _detect-malicious-package:

----------------------------
Detecting malicious packages
----------------------------

In this tutorial we show how to use Macaron to find malicious packages. Imagine you have found a Python package and you would like to add this as a dependency to your project, but you are not sure whether you can trust the maintainers or not. You can run Macaron to see if it can detect any malicious behavior. Note that Macaron is an analysis tool and can either miss a malicious behavior or report a false positive. So, while we encourage you to use Macaron, you might still need to triage the results manually.

.. list-table::
   :widths: 25
   :header-rows: 1

   * - Supported packages
   * - Python packages (PyPI)

.. contents:: :local:


**********
Background
**********

Detecting malicious behavior in open-source software has been a focus for the `Open Source Security Foundation <https://github.com/ossf>`_ (OpenSSF) community in recent years. One significant initiative is :term:`SLSA`, which offers practical recommendations to enhance the integrity of software packages and infrastructure. Macaron is designed to detect poorly maintained or malicious packages by implementing checks inspired by the SLSA specification. However, some forms of attacks currently fall outside the scope of SLSA version 1—notably, SLSA doesn't address the issue of malicious maintainers. Our primary goal is to make it more difficult for malicious actors to compromise critical supply chains and infrastructure. To achieve this, we're developing new methods to detect when maintainers of open source projects are untrustworthy and deliberately spread malware.

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

***********
Run Macaron
***********

In this tutorial, we run Macaron on the ``django`` Python package as an example with and without its dependencies to check malicious behavior and apply a policy to fail if the corresponding check fails.


'''''''''''''''''''''''''''''''''''''
Analyzing django without dependencies
'''''''''''''''''''''''''''''''''''''

First, we need to run the ``analyze`` command of Macaron to run a number of :ref:`checks <checks>` on the ``django`` package. In this tutorial, we are interested in the results of the ``mcn_detect_malicious_metadata_1``. Check :ref:`this tutorial <include_exclude_checks>` if you would like to exclude other checks.

.. code-block:: shell

  ./run_macaron.sh analyze -purl pkg:pypi/django@5.0.6 --skip-deps

.. note:: By default, Macaron clones the repositories and creates output files under the ``output`` directory. To understand the structure of this directory please see :ref:`Output Files Guide <output_files_guide>`.

.. code-block:: shell

  open output/reports/pypi/django/django.html

.. _fig_django-malware-check:

.. figure:: ../../_static/images/tutorial_django_5.0.6_detect_malicious_metadata_check.png
   :alt: Check ``mcn_detect_malicious_metadata_1`` result for ``django@5.0.6``
   :align: center

|

The image above shows the result of the ``mcn_detect_malicious_metadata_1`` check for ``django@5.0.6``. The check has passed, which means this package is not malicious. If a package is malicious, this check fails, and if the ecosystem is not supported, the check returns ``UKNOWN``. You can also see the result of individual heuristics applied in this check under the ``Justification`` column.

Now we can write a policy to enforce that all versions of ``django`` pass the ``mcn_detect_malicious_metadata_1`` check. The policy will be enforced against the ``analyze`` command run outputs cached in the local database at ``output/macaron.db``.

.. code-block:: shell

  ./run_macaron.sh verify-policy --database output/macaron.db --file policy.dl

Where the policy looks like below:

.. code-block:: prolog

  #include "prelude.dl"

  Policy("check-django", component_id, "Check django artifacts.") :-
      check_passed(component_id, "mcn_detect_malicious_metadata_1").


  apply_policy_to("check-django", component_id) :-
      is_component(component_id, purl),
      match("pkg:pypi/django@.*", purl).

Note that the ``match`` constraint applies a regex and can be expanded to enforce the ``mcn_detect_malicious_metadata_1`` check to pass on all Python packages analyzed so far by Macaron:

.. code-block:: prolog

  apply_policy_to("check-django", component_id) :-
      is_component(component_id, purl),
      match("pkg:pypi.*", purl).

''''''''''''''''''''''''''''''''''
Analyzing django with dependencies
''''''''''''''''''''''''''''''''''

Macaron supports analyzing dependencies of a package and runs the same set of checks on the dependencies as the main target package. To analyze the dependencies of ``django@5.0.6`` Python package, you can either :ref:`generate an SBOM <python-sbom>` yourself or :ref:`point Macaron to a virtual environment <python-venv-deps>` where ``django`` is installed.


Let's assume ``/tmp/.django_venv`` is the virtual environment where ``django@5.0.6`` is installed. Run Macaron as follows to analyze ``django`` and its dependencies.

.. code-block:: shell

  ./run_macaron.sh analyze -purl pkg:pypi/django@5.0.6 --python-venv "/tmp/.django_venv"


By default Macaron only checks the direct dependencies. To turn on recursive dependency analysis, add the following to the ``configurations.ini`` file:

.. code-block:: ini

  [dependency.resolver]
  recursive = True

And pass that to the ``analyze`` command:

.. code-block:: shell

  ./run_macaron.sh --defaults-path configurations.ini analyze -purl pkg:pypi/django@5.0.6 --python-venv "/tmp/.django_venv"

To learn more about changing configurations see :ref:`here <change-config>`.

Now we can enforce the policy below to ensure that the ``mcn_detect_malicious_metadata_1`` check always passes on ``django`` and its dependencies and none of the dependencies have malicious behavior.

.. code-block:: prolog

  #include "prelude.dl"

  Policy("check-dependencies", component_id, "Check the dependencies of django.") :-
    is_component(component_id, _),
    transitive_dependency(component_id, dependency),
    check_passed(dependency, "mcn_detect_malicious_metadata_1").

  apply_policy_to("check-dependencies", component_id) :-
      is_component(component_id, purl),
      match("pkg:pypi.*", purl).

***********
Future Work
***********

We are actively working on the malware detection analysis in Macaron to improve the precision and support more ecosystems. An upcoming feature is a more advanced source code analysis. Stay tuned and feel free to contribute to improve this check.
