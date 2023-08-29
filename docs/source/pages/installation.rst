.. Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
.. Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

.. _installation-guide:

==================
Installation Guide
==================

-------------
Prerequisites
-------------
- Installations of ``wget`` or ``curl`` and ``bash`` must be available and on the path.
- Docker (or docker equivalent for your host OS) must be installed, with a docker command line equivalent to Docker 17.06 (Oracle Container Runtime 19.03) and the user should be a member of the operating system group ``docker`` (to run Docker in `rootless mode <https://docs.docker.com/engine/security/rootless/>`_).

.. _download-macaron:

--------
Download
--------

Macaron is currently distributed as a Docker image. We provide a bash script ``run_macaron.sh`` to easily download and run it.

.. note:: When run, Macaron will create output files inside the current directory where ``run_macaron.sh`` is run.

Download the ``run_macaron.sh`` script and make it executable by running the commands (replace ``tag`` with the version you want or ``main`` for the latest version):

.. code-block:: shell

  curl -O https://raw.githubusercontent.com/oracle/macaron/<tag>/scripts/release_scripts/run_macaron.sh
  chmod +x run_macaron.sh

----------------------------------------
Verify that the installation is complete
----------------------------------------

To verify your setup, go to the directory containing the downloaded ``run_macaron.sh`` script and run this command in order to print out the help message for Macaron:

.. code-block:: shell

  ./run_macaron.sh --help


.. note:: In the first execution, this script will download the Macaron Docker image from ``ghcr.io/oracle/macaron`` which can take some time. However, the next time you run it, the docker image available on your local host will be used.

.. note:: By default, ``latest`` is used as the tag for the downloaded image. You can choose a specific tag by assigning the environment variable ``MACARON_IMAGE_TAG``. For example to run Macaron v0.1.0 run: ``MACARON_IMAGE_TAG=v0.1.0 && ./run_macaron.sh --help``

.. _prepare-github-token:

---------------------------
Prepare GitHub access token
---------------------------

A GitHub access token is **always** required when using the **analyze** command (see example below) of Macaron as it may query information from GitHub API about public repositories. More information on this analyze command is can be found in :ref:`Using Macaron <using-macaron>`.

.. code-block:: shell

  ./run_macaron.sh analyze <rest_of_arguments>

To obtain a GitHub access token, please see the official instructions `here <https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token>`_.

Ideally, the GitHub token must have **read** permissions for the repositories that you want to analyze:

- Every `fine-grained personal-access token <https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token#creating-a-fine-grained-personal-access-token>`_ should have read permission to public GitHub repositories. However, if you are analyzing a private repository, please select it in the ``Repository Access section``.
- For `classic personal-access token <https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token#creating-a-personal-access-token-classic>`_, the ``repo.public_repo`` scope must be selected. Please select the whole ``repo`` scope if you are running the analysis against private repositories.

After generating a GitHub personal-access token, please store its value in an environment variable called ``GITHUB_TOKEN``. This environment variable will be read by Macaron for its **analyze** command.

Now that you have successfully downloaded and installed Macaron, please refer to :ref:`Using Macaron <using-macaron>` for the instructions on how to use Macaron.

.. _proxy_configuration:

-------------------
Proxy Configuration
-------------------

Make sure your system proxy is correctly set. These environment variables are read from the host machine and set in the Macaron container automatically.

.. code-block:: shell

   $ export {http,https,ftp}_proxy=http://www-example-proxy:80
   $ export no_proxy=localhost,127.0.0.1

In order to connect to the registry on behalf of the Docker client, the Docker daemon service needs the proxies in order to download images:

.. code-block:: shell
   :caption:    /etc/systemd/system/docker.service.d/http-proxy.conf
   :name: docker-proxy-conf-proxies

   [Service]
   Environment="HTTP_PROXY=http://wwww-example-proxy:80/"
   Environment="http_proxy=http://www-example-proxy:80/"
   Environment="HTTPS_PROXY=http://www-example-proxy:80/"
   Environment="https_proxy=http://www-example-proxy:80/"

The line below shows an example to exclude the proxy intercept:

.. code-block:: shell
   :caption:    /etc/systemd/system/docker.service.d/http-proxy.conf
   :name: docker-proxy-conf-no-proxy

   Environment="NO_PROXY=localhost,127.0.0.1"

.. note:: If you update ``/etc/systemd/system/docker.service.d/http-proxy.conf``, you need to reload the daemon and restart the docker service to apply changes.

.. code-block:: shell

  sudo systemctl daemon-reload
  sudo systemctl restart docker.service

You can run the following command to make sure the proxy settings are updated:

.. code-block:: shell

  sudo systemctl show --property=Environment docker

'''''''''''''''''''''''''''''''
Maven and Gradle proxy settings
'''''''''''''''''''''''''''''''

Maven and Gradle do not use the system proxy settings. If the target software component (repository)
is using either of these build tools, make sure to set up the following environment variables:

.. code-block:: shell

  export MAVEN_OPTS="-Dhttp.proxyHost=wwww-example-proxy -Dhttp.proxyPort=80 -Dhttps.proxyHost=wwww-example-proxy -Dhttps.proxyPort=80"
  export GRADLE_OPTS="-Dhttp.proxyHost=wwww-example-proxy -Dhttp.proxyPort=80 -Dhttps.proxyHost=wwww-example-proxy -Dhttps.proxyPort=80"

In addition, Macaron uses the global settings files for Maven and Gradle if present on the host machine and copies them to
the Docker container. You can set up your proxy settings in the following files:

* ``~/.m2/settings.xml``
* ``~/.gradle/gradle.properties``

See the `Maven <https://maven.apache.org/settings.html#proxies>`_ and `Gradle <https://docs.gradle.org/current/userguide/build_environment.html#sec:accessing_the_web_via_a_proxy>`_ documentations for more information on setting up proxies.
