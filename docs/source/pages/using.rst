.. Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
.. Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

.. _using-macaron:

=============
Using Macaron
=============

.. note:: The instructions below assume that you have setup you environment correctly to run Macaron (if not, please refer to :ref:`Installation Guide <installation-guide>`).

.. _analyze-command:

.. contents:: :local:

----------------------------------------
Analyzing an artifact with a PURL string
----------------------------------------

Macaron can analyze an artifact to determine its supply chain security posture. To analyze an artifact, you need to provide the PURL identifier of the artifact:

 .. code-block::

  pkg:<package_type>/<artifact_details>

Where ``artifact_details`` varies based on the provided ``package_type``. Examples for those currently supported by Macaron are as follows:

.. list-table:: Examples of PURL strings for artifacts.
   :widths: 50 50
   :header-rows: 1

   * - Package Type
     - PURL String
   * - Maven (Java)
     - ``pkg:maven/org.apache.xmlgraphics/batik-anim@1.9.1``
   * - PyPi (Python)
     - ``pkg:pypi/django@1.11.1``
   * - Cargo (Rust)
     - ``pkg:cargo/rand@0.7.2``
   * - NuGet (.Net)
     - ``pkg:nuget/EnterpriseLibrary.Common@6.0.1304``
   * - NPM (NodeJS)
     - ``pkg:npm/@angular/animation@12.3.1``

For more detailed information on converting a given artifact into a PURL, see `PURL Specification <https://github.com/package-url/purl-spec/blob/master/PURL-SPECIFICATION.rst>`_ and `PURL Types <https://github.com/package-url/purl-spec/blob/master/PURL-TYPES.rst>`_


To run Macaron on an artifact, we use the following command:

.. code-block:: shell

  ./run_macaron.sh analyze -purl <artifact-purl>

Macaron can also analyze the package's dependencies. Please see :ref:`automate-deps-resolution`.

''''''''''''''''''''''''''''''''''''''
Automated repository and commit finder
''''''''''''''''''''''''''''''''''''''

Macaron is capable of automatically determining the repository and exact commit that match a given artifact. For repository URLs, this is achieved through examination of SCM meta data found within artifact POM files (for Java), or use of Google's Open Source Insights API (for other languages). For commits, Macaron will attempt to match repository tags with the artifact version being sought, thereby requiring that the repository supports and uses tags on commits that were used for releases.

By default, Macaron will try to discover the corresponding repository of an artifact unless it is already provided as input (as shown `later <#analyze-repo>`_). To disable or otherwise configure this behavior, or others, a custom ``.ini`` file should be passed to Macaron during execution. See `How to change the default configuration <#change-config>`_ for more details.

For example, under the ``repofinder`` header, three options exist: ``find_repos``, ``use_open_source_insights``, and ``redirect_urls``:

- ``find_repos`` (Values: True or False) - Enables or disables the Repository Finding feature.
- ``use_open_source_insights`` (Values: True or False) - Enables or disables use of Google's Open Source Insights API.
- ``redirect_urls`` (Values: List of URLs) - These are URLs that are known to redirect to actual repository URLs.

To turn off the automatic source repo finding feature, change the following section in the configuration ``ini`` file:

.. code-block:: ini

    [repofinder]
    find_repos = False

Within the configuration file under the ``repofinder.java`` header, three options exist: ``artifact_repositories``, ``repo_pom_paths``, ``find_parents``. These options behave as follows:

- ``artifact_repositories`` (Values: List of URLs) - Determines the remote artifact repositories to attempt to retrieve dependency information from.
- ``repo_pom_paths`` (Values: List of POM tags) - Determines where to search for repository information in the POM files. E.g. scm.url.
- ``find_parents`` (Values: True or False) - When enabled, the Repository Finding feature will also search for repository URLs in parents POM files of the current dependency.

.. note:: Dependency related configurations like ``artifact_repositories`` or ``find_parents`` can affect  :ref:`Macaron automatic dependency resolution <automate-deps-resolution>`.

.. note:: Finding repositories requires at least one remote call, adding some additional overhead to an analysis run.

.. note:: Google's Open Source Insights API is currently used to find repositories for: Python, Rust, .Net, NodeJS

An example configuration file for utilising this feature:

.. code-block:: ini

    [repofinder]
    find_repos = True
    use_open_source_insights = True
    redirect_urls =
        gitbox.apache.org
        git-wip-us.apache.org

    [repofinder.java]
    artifact_repositories = https://repo.maven.apache.org/maven2
    repo_pom_paths =
        scm.url
        scm.connection
        scm.developerConnection
    find_parents = True

.. _analyze-repo:

----------------------------------
Analyzing a source code repository
----------------------------------

''''''''''''''''''''''''''''''''''''
Analyzing a public GitHub repository
''''''''''''''''''''''''''''''''''''

Macaron can also analyze a public GitHub repository.

To run Macaron on a GitHub public repository, we use the following command:

.. code-block:: shell

  ./run_macaron.sh analyze -rp <repo_path>

With ``repo_path`` being the remote path to your target repository.

By default, Macaron will analyze the latest commit of the default branch. However, you could specify the branch and commit digest to run the analysis against:

.. code-block:: shell

  ./run_macaron.sh analyze -rp <repo_path> -b <branch_name> -d <digest>

For example, to analyze the SLSA posture of `micronaut-core <https://github.com/micronaut-projects/micronaut-core>`_ at branch 4.0.x and commit ``82d115b4901d10226552ac67b0a10978cd5bc603`` we could use the following command:

.. code-block:: shell

  ./run_macaron.sh analyze -rp https://github.com/micronaut-projects/micronaut-core -b 4.0.x -d 82d115b4901d10226552ac67b0a10978cd5bc603

.. note:: By default, Macaron would generate report files into the ``output`` directory in the current working directory. To understand the structure of this directory please see :ref:`Output Files Guide <output_files_guide>`.

With the example above, the generated output reports can be seen here:

- `micronaut-core.html <../_static/examples/micronaut-projects/micronaut-core/analyze_with_repo_path/micronaut-core.html>`__
- `micronaut-core.json <../_static/examples/micronaut-projects/micronaut-core/analyze_with_repo_path/micronaut-core.json>`__

'''''''''''''''''''''''''''''
Analyzing a GitLab repository
'''''''''''''''''''''''''''''

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

- Add the following ``[git_service.gitlab.self_hosted]`` section into your ``.ini`` config. In the default .ini configuration (generated using ``macaron dump-default`` -- :ref:`see instructions <action_dump_defaults>`), there is already this section commented out. You can start by un-commenting this section and modifying the ``hostname`` value with the hostname of your self-hosted GitLab instance.

.. code-block:: ini

    # Access to a self-hosted GitLab instance (e.g. your organization's self-hosted GitLab instance).
    # If this section is enabled, an access token must be provided through the ``MCN_SELF_HOSTED_GITLAB_TOKEN`` environment variable.
    # The `read_repository` permission is required for this token.
    [git_service.gitlab.self_hosted]
    hostname = internal.gitlab.org

- Obtain a GitLab access token having at least the ``read_repository`` permission and store it into the ``MCN_SELF_HOSTED_GITLAB_TOKEN`` environment variable. For more detailed instructions, see `GitLab documentation <https://docs.gitlab.com/ee/user/profile/personal_access_tokens.html#create-a-personal-access-token>`_.

''''''''''''''''''''''''''''''''''''''''''''''''''''
Providing a PURL string instead of a repository path
''''''''''''''''''''''''''''''''''''''''''''''''''''

Instead of providing the repository path to analyze a software component, you can use a `PURL <https://github.com/package-url/purl-spec/blob/master/PURL-SPECIFICATION.rst>`_. string for the target git repository.

To simplify the examples, we use the same configurations as above if needed (e.g., for the self-hosted GitLab instances). The PURL string for a git repository should have the following format:

.. code-block::

  pkg:<git_service_hostname>/<organization>/<name>

The list below shows examples for the corresponding PURL strings for different git repositories:

.. list-table:: Examples of PURL strings for git repositories.
   :widths: 50 50
   :header-rows: 1

   * - Repository path
     - PURL string
   * - ``https://github.com/micronaut-projects/micronaut-core``
     - Both ``pkg:github/micronaut-projects/micronaut-core`` and ``pkg:github.com/micronaut-projects/micronaut-core`` are applicable as ``github`` is a pre-defined type as mentioned `here <https://github.com/package-url/purl-spec/blob/master/PURL-TYPES.rst>`_.
   * - ``https://bitbucket.org/snakeyaml/snakeyaml``
     - Both ``pkg:github/micronaut-projects/micronaut-core`` and ``pkg:github.com/micronaut-projects/micronaut-core`` are applicable as ``bitbucket`` is a pre-defined type as mentioned `here <https://github.com/package-url/purl-spec/blob/master/PURL-TYPES.rst>`_.
   * - ``https://internal.gitlab.com/foo/bar``
     - ``pkg:internal.gitlab.com/foo/bar``
   * - ``https://gitlab.com/gitlab-org/gitlab``
     - ``pkg:gitlab.com/gitlab-org/gitlab``

Run the analysis using the PURL string as follows:

.. code-block:: shell

  ./run_macaron.sh analyze -purl <purl_string>

You can also provide the PURL string together with the repository path. In this case, the PURL string will be used as the unique identifier for the analysis target. If providing a PURL with a version, providing the repository path as well is sufficient for analysis to take place. If providing a PURL without a version, the branch and digest must also be provided alongside the repository path. Examples of both use cases follow.

Analyzing a PURL (with an included version) and a repository path:

.. code-block:: shell

  ./run_macaron.sh analyze -purl <purl_string_with_version> -rp <repo_path>

Analyzing a PURL (without an included version) and a repository path (with a digest and branch):

.. code-block:: shell

  ./run_macaron.sh analyze -purl <purl_string> -rp <repo_path> -b <branch> -d <digest>

-------------------------------------------------
Verifying provenance expectations in CUE language
-------------------------------------------------

When a project generates provenances, you can add a build expectation in the form of a
`Configure Unify Execute (CUE) <https://cuelang.org/>`_ policy to check the content of provenances. For instance, the expectation
can specify the accepted GitHub Actions workflows that trigger a build, which can prevent using artifacts built from attackers
workflows.

.. code-block:: shell

  ./run_macaron.sh analyze -pe micronaut-core.cue -rp https://github.com/micronaut-projects/micronaut-core -b 4.0.x -d 82d115b4901d10226552ac67b0a10978cd5bc603

where ``micronaut-core.cue`` file can contain:

.. code-block:: javascript

  {
    target: "pkg:github.com/micronaut-projects/micronaut-core",
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

.. _automate-deps-resolution:

------------------------------------
Analyzing dependencies automatically
------------------------------------

Macaron supports automatically detecting and analyzing dependencies for certain types of projects (:ref:`supported_automatic_deps_resolution`). This feature is disabled by default and can be enabled with the CLI flag ``--deps-depth``.

The ``--deps-depth`` flag currently accepts these values:

* ``0``: Disable dependency resolution (Default).
* ``1``: Resolve and analyze direct dependencies.
* ``inf``: Resolve and analyze all transitive dependencies.

For example, to analyze `micronaut-core <https://github.com/micronaut-projects/micronaut-core>`_ and its **direct** dependencies, we could use the following command:

.. code-block:: shell

  ./run_macaron.sh analyze \
    -rp https://github.com/micronaut-projects/micronaut-core \
    -b 4.0.x \
    -d 82d115b4901d10226552ac67b0a10978cd5bc603 \
    --deps-depth=1

.. note:: This process might take a while. Alternatively, you can help Macaron by providing the dependencies information through : :ref:`an sbom <with-sbom>` or :ref:`a Python virtual environment <python-venv-deps>` (for Python packages only).

.. _with-sbom:

----------------------
Analyzing with an SBOM
----------------------

Macaron can run the analysis against an existing SBOM in `CycloneDX <https://cyclonedx.org/>`_ which contains all the necessary information of the dependencies of a target software component. In this case, the dependencies will not be resolved automatically.

CycloneDX provides open-source SBOM generators for different types of projects (e.g Maven, Gradle, etc). For instructions on generating a CycloneDX SBOM for your project, see `CycloneDX documentation <https://github.com/CycloneDX>`_.

'''''''''''''''''''''''
SBOM for Maven projects
'''''''''''''''''''''''

For example, let's analyze the dependencies of `pkg:maven/org.apache.maven/maven@3.9.7?type=pom <https://repo1.maven.org/maven2/org/apache/maven/maven/3.9.7/>`_, using the `SBOM <../_static/examples/apache/maven/analyze_with_sbom/sbom.json>`_ generated by `CycloneDX Maven plugin <https://github.com/CycloneDX/cyclonedx-maven-plugin>`_.

To run the analysis against that SBOM, run this command:

.. code-block:: shell

  ./run_macaron.sh analyze -purl pkg:maven/org.apache.maven/maven@3.9.7?type=pom -sbom <path_to_sbom> --deps-depth=inf

Where ``path_to_sbom`` is the path to the SBOM you want to use.

.. note:: Make sure to enable dependency resolution with ``--deps-depth``.

.. _python-sbom:

''''''''''''''''''''''''
SBOM for Python projects
''''''''''''''''''''''''

For Python projects, you can use `cyclonedx-py <https://github.com/CycloneDX/cyclonedx-python>`_ to generate the SBOM. First install the package in a virtual environment, and then use ``cyclonedx-py`` to generate an SBOM for it. Here is an example:

.. code-block:: shell

    python -m venv .django_venv # Create a virtual environment called .django_venv
    .django_venv/bin/pip install django==5.0.6 # Install the package in the virtual environment
    cyclonedx-py environment .django_venv --output-format json --outfile django_sbom.json # Generate the SBOM

Then run Macaron and pass the SBOM file as input:

.. code-block:: shell

  ./run_macaron.sh analyze -purl pkg:pypi/django@5.0.6 -sbom <path_to_django_sbom.json> --deps-depth=inf

''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''
Analyzing dependencies in the SBOM without the main software component
''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''

In the case where the repository URL of the main software component is not available (e.g. the repository is in a self-hosted git service instance where Macaron cannot access),
Macaron can still run the analysis on the dependencies listed in the SBOM.
To do that, you must first create a PURL to represent the main software component, e.g.,
``pkg:maven/private.apache.maven/maven@4.0.0-alpha-1-SNAPSHOT?type=pom``.

Then the analysis can be run as follows:

.. code-block:: shell

  ./run_macaron.sh analyze -purl pkg:maven/private.apache.maven/maven@4.0.0-alpha-1-SNAPSHOT?type=pom -sbom <path_to_sbom> --deps-depth=inf

Where ``path_to_sbom`` is the path to the SBOM you want to use.

.. _python-venv-deps:

-------------------------------------------------------
Analyzing dependencies using Python virtual environment
-------------------------------------------------------

Macaron can automatically identify and analyze the dependencies of a Python package if you provide the path to the virtual environment where the package is installed.

Let's say you want to analyze ``django@5.0.6`` and its dependencies. First create a virtual environment and install ``django@5.0.6``:

.. code-block:: shell

  python3.11 -m venv /tmp/.django_venv
  /tmp/.django_venv/bin/pip install django==5.0.6


Then run Macaron as follows:

.. code-block:: shell

  ./run_macaron.sh analyze -purl pkg:pypi/django@5.0.6 --python-venv "/tmp/.django_venv" --deps-depth=1

Where ``--python-venv`` is the path to virtual environment.

.. note:: Make sure to enable dependency resolution with ``--deps-depth``.

Alternatively, you can create an SBOM for the python package and provide it to Macaron as input as explained :ref:`here <with-sbom>`.

.. note:: We only support Python 3.11 for this feature of Macaron. Please make sure to install the package using this version of Python.


-----------------------------------------------
Analyzing a repository on the local file system
-----------------------------------------------

.. note::
  We assume that the ``origin`` remote exists in the cloned repository and checkout the relevant commits from ``origin`` only.

Macaron supports analyzing a repository on the local file system.

''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''
Analyzing a repository whose git service is not supported by Macaron
''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''

If the repository remote URL is from an unknown git service (see :ref:`Git Services <supported_git_services>` for a list of supported git services in Macaron), Macaron won't recognize it when analyzing the repository.

You would need to tell Macaron about that git service through the ``defaults.ini`` config.
For example, let's say you want to analyze a repository hosted at ``https://git.example.com/foo/target``. First, you need to create a ``defaults.ini`` file in the current working directory with the following content:

.. code-block:: ini

  [git_service.local_repo]
  hostname = git.example.com

In which ``hostname`` contains the hostname of the git service URL. In this example it is ``git.example.com``.

.. note::

  This ``defaults.ini`` section must only be used for analyzing a repository on the local file system. If the hostname has already been supported in other services, it doesn't need to be defined again here.

Assume that the dir tree at the current working directory has the following structure:

.. code-block:: shell

  boo
  ├── foo
  │   └── target

We can run Macaron against the local repository at ``target`` by using this command:

.. code-block:: shell

  ./run_macaron.sh --local-repos-path ./boo/foo --defaults-path ./defaults.ini analyze --repo-path target <rest_of_args>

With ``rest_of_args`` being the arguments to the ``analyze`` command (e.g. ``--branch/-b``, ``--digest/-d`` similar to two previous examples).

The ``--local-repos-path/-lr`` flag tells Macaron to look into ``./boo/foo`` for local repositories. For more information, please see :ref:`Command Line Usage <cli-usage>`.

.. note:: If ``--local-repos-path/-lr`` is not provided, Macaron will looks inside ``<current_working_directory>/output/git_repos/local_repos/`` whenever you provide a local path to ``--repo-path/-rp``.

'''''''''''''''''''''''''''''''''''''''''''''''''''''''
Analyzing a local repository with supported git service
'''''''''''''''''''''''''''''''''''''''''''''''''''''''

If the local repository you want to analyze has a remote origin hosted on a supported git service, you can run the analysis directly without having to prepare ``defaults.ini`` as above.

Assume that the dir tree at the current working directory has the following structure:

.. code-block:: shell

  boo
  ├── foo
  │   └── target

We can run Macaron against the local repository at ``target`` by using this command:

.. code-block:: shell

  ./run_macaron.sh --local-repos-path ./boo/foo analyze --repo-path target <rest_of_args>

With ``rest_of_args`` being the arguments to the ``analyze`` command (e.g. ``--branch/-b``, ``--digest/-d`` similar to two previous examples).

The ``--local-repos-path/-lr`` flag tells Macaron to look into ``./boo/foo`` for local repositories. For more information, please see :ref:`Command Line Usage <cli-usage>`.

.. note:: If ``--local-repos-path/-lr`` is not provided, Macaron will look inside ``<current_working_directory>/output/git_repos/local_repos/`` whenever you provide a local path to ``--repo-path/-rp``.

.. warning::
  Macaron by default analyzes the current state of the local repository. However, if the user provides a branch or commit hash as input, Macaron may reset the index and working tree of the repository to check out a specific commit.
  Therefore, any uncommitted changes in the repository need to be backed up to prevent loss (these include unstaged changes, staged changes and untracked files).
  However, Macaron will not modify the history of the repository.

-------------------------
Running the policy engine
-------------------------

Macaron's policy engine accepts policies specified in `Datalog <https://en.wikipedia.org/wiki/Datalog>`_. An example policy
can verify if a project and all its dependencies pass certain checks. We use `Soufflé <https://souffle-lang.github.io/index.html>`_
as the Datalog engine in Macaron. Once you run the checks on a target project as described :ref:`here <analyze-command>`,
the check results will be stored in ``macaron.db`` in the output directory. We pass the check results to the policy engine by providing the path to ``macaron.db`` together with a Datalog policy file to be validated by the policy engine.
In the Datalog policy file, we must specify the identifier for the target software component that interests us to validate the policy against. These are two ways to specify the target software component in the Datalog policy file:

#. Using the complete name of the target component (e.g. ``github.com/oracle-quickstart/oci-micronaut``)
#. Using the PURL string of the target component (e.g. ``pkg:github.com/oracle-quickstart/oci-micronaut@<commit_sha>``).

We use `Micronaut MuShop <https://github.com/oracle-quickstart/oci-micronaut>`_ project as a case study to show how to run the policy engine.
Micronaut MuShop is a cloud-native microservices example for Oracle Cloud Infrastructure. When we run Macaron on the Micronaut MuShop GitHub
project, it automatically finds the project’s dependencies and runs checks for the top-level project and dependencies
independently. For example, the build service check, as defined in SLSA, analyzes the CI configurations to determine if its artifacts are built
using a build service. Another example is the check that determines whether a SLSA provenance document is available for an artifact. If so, it
verifies whether the provenance document attests to the produced artifacts. For the Micronaut MuShop project, Macaron identifies 48 dependencies
that map to 24 unique repositories and generates an HTML report that summarizes the check results.

Now we can run the policy engine over these results and enforce a policy:

.. code-block:: shell

  ./run_macaron.sh verify-policy -o outputs -d outputs/macaron.db --file <policy_file>

In this example, the Datalog policy files for both ways (as mentioned previously) are provided in `oci-micronaut-repo.dl <../_static/examples/oracle-quickstart/oci-micronaut/policies/oci-micronaut-repo.dl>`__ and `oci-micronaut-purl.dl <../_static/examples/oracle-quickstart/oci-micronaut/policies/oci-micronaut-purl.dl>`__.

The differences between the two policy files can be observed below:

.. tabs::

  .. code-tab:: prolog Using repository complete name

    apply_policy_to("oci_micronaut_dependencies", repo_id) :- is_repo(repo_id, "github.com/oracle-quickstart/oci-micronaut", _).

  .. code-tab:: prolog Using PURL string

    apply_policy_to("oci_micronaut_dependencies", component_id) :- is_component(component_id, "<target_software_component_purl>").

The PURL string for the target software component is printed to the console by the :ref:`analyze command <analyze-command>`. For example:

.. code::

  > ./run_macaron.sh analyze -rp https://github.com/oracle-quickstart/oci-micronaut
  > ...
  > 2023-08-15 14:36:56,672 [INFO] The PURL string for the main target software component in this analysis is
  'pkg:github.com/oracle-quickstart/oci-micronaut@3ebe0c9520a25feeae983eac6eb956de7da29ead'.
  > 2023-08-15 14:36:56,672 [INFO] Analysis Completed!

This example policy can verify if the Micronaut MuShop project and all its dependencies pass the ``build_service`` check
and the Micronaut provenance documents meets the expectation provided as a `CUE file <../_static/examples/micronaut-projects/micronaut-core/policies/micronaut-core.cue>`__.

Thanks to Datalog's expressive language model, it's easy to add exception rules if certain dependencies do not meet a
requirement. For example, `the Mysql Connector/J <https://slsa.dev/spec/v0.1/requirements#build-service>`_ dependency in
the Micronaut MuShop project does not pass the ``build_service`` check, but can be manually investigated and exempted if trusted. Overall, policies expressed in Datalog can be
enforced by Macaron as part of your CI/CD pipeline to detect regressions or unexpected behavior.

.. _change-config:

-----------------------------------
Modifying the default configuration
-----------------------------------

See :ref:`dump-defaults <action_dump_defaults>`, the CLI command to dump the default configurations in ``defaults.ini``. After making changes, see :ref:`analyze <analyze-command-cli>` CLI command for the option to pass the modified ``defaults.ini`` file.

For example, to turn off the automatic source repo finding feature, change the following section in the configuration ``ini`` file:

.. code-block:: ini

    [repofinder]
    find_repos = False

Then run Macaron passing the modified configuration file:

.. code-block:: shell

      ./run_macaron.sh -dp <path-to-modified-default.ini> analyze -purl <artifact-purl>
