.. Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
.. Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

.. _using-macaron:

=============
Using Macaron
=============

.. note:: The instructions below assume that you have setup you environment correctly to run Macaron (if not, please refer to :ref:`Installation Guide <installation-guide>`).

.. _analyze-action:

.. contents:: :local:

----------------------------------
Analyzing a source code repository
----------------------------------

^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Analyzing a public Github repository
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Macaron can analyze a Github public repository (and potentially the repositories of it dependencies) to determine its SLSA posture following the specification of `SLSA v0.1 <https://slsa.dev/spec/v0.1/>`_.

To run Macaron on a Github public repository, we use the following command:

.. code-block:: shell

  ./run_macaron.sh analyze -rp <repo_path>

With ``repo_path`` being the remote path to your target repository.

By default, Macaron will analyze the latest commit of the default branch. However, you could specify the branch and commit digest to run the analysis against:

.. code-block:: shell

  ./run_macaron.sh analyze -rp <repo_path> -b <branch_name> -d <digest>

For example, to analyze the SLSA posture of `micronaut-core <https://github.com/micronaut-projects/micronaut-core>`_ at branch 4.0.x and commit ``82d115b4901d10226552ac67b0a10978cd5bc603`` we could use the following command:

.. code-block:: shell

  ./run_macaron.sh analyze -rp https://github.com/micronaut-projects/micronaut-core -b 4.0.x -d 82d115b4901d10226552ac67b0a10978cd5bc603

.. note:: Macaron automatically detects and analyzes **direct** dependencies for Java Maven and Gradle projects. This process might take a while and can be skipped by using the ``--skip-deps`` option.

Take the same example as above, to disable analyzing `micronaut-core <https://github.com/micronaut-projects/micronaut-core>`_ direct dependencies, we could use the following command:

.. code-block:: shell

  ./run_macaron.sh analyze -rp https://github.com/micronaut-projects/micronaut-core -b 4.0.x -d 82d115b4901d10226552ac67b0a10978cd5bc603 --skip-deps

.. note:: By default, Macaron would generate report files into the ``output`` directory in the current workspace. To understand the structure of this directory please see :ref:`Output Files Guide <output_files_guide>`.

With the example above, the generated output reports can be seen here:

- `micronaut-core.html <../_static/examples/micronaut-projects/micronaut-core/analyze_with_repo_path/micronaut-core.html>`__
- `micronaut-core.json <../_static/examples/micronaut-projects/micronaut-core/analyze_with_repo_path/micronaut-core.json>`__

^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Analyzing a GitLab repository
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Macaron supports analyzing GitLab repositories, whether they are hosted on `gitlab.com <https://gitlab.com>`_ or on your self-hosted GitLab instance. The set up in these two cases are a little bit different.

""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
Analyzing a repository on `gitlab.com <https://gitlab.com>`_
""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""

Analyzing a public repository on `gitlab.com <https://gitlab.com>`_ is quite similar to analyzing a public GitHub repository -- you just need to pass a proper GitLab repository URL to ``macaron analyze``.

To analyze a private repository hosted on ``gitlab.com``, you need to obtain a GitLab access token having at least the ``read_repository`` permission and store it into the ``MCN_GITLAB_TOKEN`` environment variable. For more detailed instructions, see `GitLab documentation <https://docs.gitlab.com/ee/user/profile/personal_access_tokens.html#create-a-personal-access-token>`_.

"""""""""""""""""""""""""""""""""""""""""""""""""""""""
Analyzing a repository on a self-hosted GitLab instance
"""""""""""""""""""""""""""""""""""""""""""""""""""""""

To analyze a repository on a self-hosted GitLab instance, you need to do the following:

- Add the following ``[git_service.gitlab.self_hosted]`` section into your ``.ini`` config. In the default .ini configuration (generated using ``macaron dump-default`` -- :ref:`see instructions <action_dump_defaults>`), there is already this section commented out. You can start by un-commenting this section and modifying the ``domain`` value with the domain of your self-hosted GitLab instance.

.. code-block:: ini

    # Access to a self-hosted GitLab instance (e.g. your organization's self-hosted GitLab instance).
    # If this section is enabled, an access token must be provided through the ``MCN_SELF_HOSTED_GITLAB_TOKEN`` environment variable.
    # The `read_repository` permission is required for this token.
    [git_service.gitlab.self_hosted]
    domain = internal.gitlab.org

- Obtain a GitLab access token having at least the ``read_repository`` permission and store it into the ``MCN_SELF_HOSTED_GITLAB_TOKEN`` environment variable. For more detailed instructions, see `GitLab documentation <https://docs.gitlab.com/ee/user/profile/personal_access_tokens.html#create-a-personal-access-token>`_.

-------------------------------------------------
Verifying provenance expectations in CUE language
-------------------------------------------------

When a project generates SLSA provenances, you can add a build expectation in the form of a
`Configure Unify Execute (CUE) <https://cuelang.org/>`_ policy to check the content of provenances. For instance, the expectation
can specify the accepted GitHub Actions workflows that trigger a build, which can prevent using artifacts built from attackers
workflows.

.. code-block:: shell

  ./run_macaron.sh analyze -pe micronaut-core.cue -rp https://github.com/micronaut-projects/micronaut-core -b 4.0.x -d 82d115b4901d10226552ac67b0a10978cd5bc603 --skip-deps

where ``micronaut-core.cue`` file can contain:

.. code-block:: javascript

  {
    target: "micronaut-projects/micronaut-core",
    predicate: {
        invocation: {
            configSource: {
                uri: =~"^git\\+https://github.com/micronaut-projects/micronaut-core@refs/tags/v[0-9]+.[0-9]+.[0-9]+$"
                entryPoint: ".github/workflows/release.yml"
            }
        }
    }
  }

.. note::
  The provenance expectation is verified via the ``provenance_expectation`` check in Macaron. You can see the result of this check in the HTML or JSON report and see if the provenance found by Macaron meets the expectation CUE file.

----------------------
Analyzing with an SBOM
----------------------

Macaron can run the analysis against an existing SBOM in `CycloneDX <https://cyclonedx.org/>`_ which contains all the necessary information of the dependencies of a target repository. In this case, the dependencies will not be resolved automatically.

CycloneDX provides open-source SBOM generators for different types of project (e.g Maven, Gradle, etc). For instructions on generating a CycloneDX SBOM for your project, see `CycloneDX documentation <https://github.com/CycloneDX>`_.

For example, with `micronaut-core <https://github.com/micronaut-projects/micronaut-core>`_ at branch 4.0.x commit ``82d115b4901d10226552ac67b0a10978cd5bc603``, using the `CycloneDX Gradle plugin <https://github.com/CycloneDX/cyclonedx-gradle-plugin>`_ would give us the following `SBOM <../_static/examples/micronaut-projects/micronaut-core/analyze_with_sbom/sbom.json>`_.

To run the analysis against that SBOM, run this command:

..
  TODO: Remove the -rp path after https://github.com/oracle/macaron/issues/108 is merged.

.. code-block:: shell

  ./run_macaron.sh analyze -rp https://github.com/micronaut-projects/micronaut-core -sbom <path_to_sbom>

With ``path_to_sbom`` is the path to the SBOM you want to use.

With the example above, the generated output reports can be seen here:

- `micronaut-core.html <../_static/examples/micronaut-projects/micronaut-core/analyze_with_sbom/micronaut-core.html>`__
- `micronaut-core.json <../_static/examples/micronaut-projects/micronaut-core/analyze_with_sbom/micronaut-core.json>`__

'''''''''''''''''''''''''''
Analyzing more dependencies
'''''''''''''''''''''''''''

In some cases the dependencies that Macaron discovers lack a direct connection to a repository for it to analyze. To improve results in these instances, the Repository Finding feature can be enabled. This feature makes use of a dependency's identifying information that can be found using the package registries located on the Internet.

.. note:: The Repository Finding feature currently only works for Java projects via SCM meta data found within artifact POM files.

This feature is enabled by default. To disable, or configure its behaviour in other ways, a custom ``defaults.ini`` should be passed to Macaron during execution.

See :ref:`dump-defaults <action_dump_defaults>`, the CLI command to dump the default configurations in ``defaults.ini``. After making changes, see :ref:`analyze <analyze-action-cli>` CLI command for the option to pass the modified ``defaults.ini`` file.

Within the configuration file under the ``repofinder.java`` header, five options exist: ``find_repos``, ``artifact_repositories``, ``repo_pom_paths``, ``find_parents``, ``artifact_ignore_list``. These options behave as follows:

- ``find_repos`` (Values: True or False) - Enables or disables the Repository Finding feature.
- ``artifact_repositories`` (Values: List of URLs) - Determines the remote artifact repositories to attempt to retrieve dependency information from.
- ``repo_pom_paths`` (Values: List of POM tags) - Determines where to search for repository information in the POM files. E.g. scm.url.
- ``find_parents`` (Values: True or False) - When enabled, the Repository Finding feature will also search for repository URLs in parents POM files of the current dependency.
- ``artifact_ignore_list`` (Values: List of GAs) - The Repository Finding feature will skip any artifact in this list. Format is "GroupId":"ArtifactId". E.g. org.apache.maven:maven

.. note:: Finding repositories requires at least one remote call, adding some additional overhead to an analysis run.

An example configuration file for utilising this feature:

.. code-block:: ini

    [repofinder.java]
    find_repos = True
    artifact_repositories = https://repo.maven.apache.org/maven2
    repo_pom_paths =
        scm.url
        scm.connection
        scm.developerConnection
    find_parents = True
    artifact_ignore_list =
        org.apache.maven:maven

-------------------------------------
Analyzing a locally cloned repository
-------------------------------------

If you have a local repository that you want to analyze, Macaron also supports running the analysis against a local repository.

Assume that the dir tree at the local repository has the following components:

.. code-block:: shell

  boo
  ├── foo
  │   └── target

We can run Macaron against the local repository at ``target`` by using this command:

.. code-block:: shell

  ./run_macaron.sh -lr path/to/boo/foo analyze -rp target <rest_of_args>

With ``rest_of_args`` being the arguments to the ``analyze`` command (e.g. ``-b``, ``-d`` or ``--skip-deps`` similar to two previous examples)

The ``-lr`` flag configure Macaron to looks into ``path/to/boo/foo`` for local repositories. For more information, please see :ref:`Command Line Usage <cli-usage>`.

.. note:: If ``-lr`` is not provided, Macaron will looks inside ``<working_directory>/output/git_repos/local_repos/`` whenever you provide a local path to ``-rp``.

-------------------------
Running the policy engine
-------------------------

Macaron's policy engine accepts policies specified in `Datalog <https://en.wikipedia.org/wiki/Datalog>`_. An example policy
can verify if a project and all its dependencies pass certain checks. We use `Soufflé <https://souffle-lang.github.io/index.html>`_
as the Datalog engine in Macaron. Once you run the checks on a target project as described :ref:`here <analyze-action>`,
the check results will be stored in ``macaron.db`` in the output directory. We can pass the check results to the policy
engine and provide a Datalog policy file to be enforced by the policy engine.

We use `Micronaut MuShop <https://github.com/oracle-quickstart/oci-micronaut>`_ project as a case study to show how to run the policy engine.
Micronaut MuShop is a cloud-native microservices example for Oracle Cloud Infrastructure. When we run Macaron on the Micronaut MuShop GitHub
project, it automatically finds the project’s dependencies and runs checks for the top-level project and dependencies
independently. For example, the build service check, as defined in SLSA, analyzes the CI configurations to determine if its artifacts are built
using a build service. Another example is the check that determines whether a SLSA provenance document is available for an artifact. If so, it
verifies whether the provenance document attests to the produced artifacts. For the Micronaut MuShop project, Macaron identifies 48 dependencies
that map to 24 unique repositories and generates an HTML report that summarizes the check results.

Now we can run the policy engine over these results and enforce a policy:

.. code-block:: shell

  ./run_macaron.sh verify-policy -o outputs -d outputs/macaron.db --file oci-micronaut.dl

In this example, the Datalog policy file is provided in `oci-micronaut.dl <../_static/examples/oracle-quickstart/oci-micronaut/policies/oci-micronaut.dl>`__.
This example policy can verify if the Micronaut MuShop project and all its dependencies pass the ``build_service`` check
and the Micronaut provenance documents meets the expectation provided as a `CUE file <../_static/examples/micronaut-projects/micronaut-core/policies/micronaut-core.cue>`__.

Thanks to Datalog’s expressive language model, it’s easy to add exception rules if certain dependencies do not meet a
requirement. For example, `the Mysql Connector/J <https://slsa.dev/spec/v0.1/requirements#build-service>`_ dependency in
the Micronaut MuShop project does not pass the ``build_service`` check, but can be manually investigated and exempted if trusted. Overall, policies expressed in Datalog can be
enforced by Macaron as part of your CI/CD pipeline to detect regressions or unexpected behavior.
