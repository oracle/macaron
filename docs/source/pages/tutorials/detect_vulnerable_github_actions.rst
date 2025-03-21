.. Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
.. Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

.. _detect-vuln-gh-actions:

=======================================
How to detect vulnerable GitHub Actions
=======================================

This tutorial explains how to use a check in Macaron that detects vulnerable third-party GitHub Actions. This check is important for preventing security issues in your CI/CD pipeline, especially in light of recent incidents, such as vulnerabilities discovered in popular GitHub Actions like `tj-actions/changed-files <https://www.cve.org/CVERecord?id=CVE-2025-30066>`_, and `reviewdog/action-setup <https://www.cve.org/CVERecord?id=CVE-2025-30154>`_.

We will guide you on how to enable and use this check to enhance the security of your development pipeline.

For more information on other features of Macaron, please refer to the :ref:`documentation here <index>`.

.. contents:: :local:

------------
Introduction
------------

In March 2025, CISA (Cybersecurity and Infrastructure Security Agency) issued an `alert <https://www.cisa.gov/news-events/alerts/2025/03/18/supply-chain-compromise-third-party-github-action-cve-2025-30066>`_ about a critical supply chain attack affecting third-party GitHub Actions. The incidents, identified as `CVE-2025-30066 <https://www.cve.org/CVERecord?id=CVE-2025-30066>`_ and `CVE-2025-30154 <https://www.cve.org/CVERecord?id=CVE-2025-30154>`_, targeted the widely used GitHub Actions ``tj-actions/changed-files`` and ``reviewdog/action-setup``, respectively. These actions were compromised, allowing attackers to manipulate CI/CD pipelines and potentially inject malicious code into repositories.

Macaron now includes a check for detecting vulnerable third-party GitHub Actions that are used in repositories, preventing the potential misuse of these actions.

-------------------------------------------
The Check: Detect Vulnerable GitHub Actions
-------------------------------------------

Macaron's check, ``mcn_githubactions_vulnerabilities_1`` identifies third-party GitHub Actions and reports any known vulnerabilities associated with the versions used in your repository.


**Key Features of this Check:**

- **Vulnerability Detection**: It scans the repository’s workflow files and checks for any known vulnerabilities in the GitHub Actions used.
- **Version Checks**: It verifies the versions of the GitHub Actions being used, comparing them against a list of known vulnerabilities.
- **Security Prevention**: Helps prevent security breaches by ensuring that your workflows are free from compromised actions.
- **Continuous Monitoring**: As GitHub Actions are updated, you can enforce a policy to continuously track and address emerging threats, ensuring that your security posture remains up-to-date.

-----------------------------------------------------------
How to Use the GitHub Actions Vulnerability Detection Check
-----------------------------------------------------------

******************************
Installation and Prerequisites
******************************

Skip this section if you already know how to install Macaron.

.. toggle::

    Please follow the instructions :ref:`here <installation-guide>`. In summary, you need:

        * Docker
        * the ``run_macaron.sh``  script to run the Macaron image.
        * sqlite3

    .. note:: At the moment, Docker alternatives (e.g. podman) are not supported.


    You also need to provide Macaron with a GitHub token through the ``GITHUB_TOKEN``  environment variable.

    To obtain a GitHub Token:

    * Go to ``GitHub settings`` → ``Developer Settings`` (at the bottom of the left side pane) → ``Personal Access Tokens`` → ``Fine-grained personal access tokens`` → ``Generate new token``. Give your token a name and an expiry period.
    * Under ``"Repository access"``, choosing ``"Public Repositories (read-only)"`` should be good enough in most cases.

    Now you should be good to run Macaron. For more details, see the documentation :ref:`here <prepare-github-token>`.

***************
Running Macaron
***************

To use the GitHub Actions Vulnerability Detection check in Macaron, you can either provide the repository URL or use the :term:`PURL` of the package. Macaron will automatically resolve the repository if you choose the PURL approach. For more details, refer to the :ref:`CLI options<analyze-command-cli>` of the ``analyze`` command.

+++++++++++++++++++++++++
Using the Repository Path
+++++++++++++++++++++++++

As an example, we will check if the https://github.com/apache/logging-log4j2 repository calls any vulnerable GitHub Actions. First, execute the ``analyze`` command as follows:

.. code-block:: shell

  ./run_macaron.sh analyze -rp https://github.com/apache/logging-log4j2

Next, ensure that the ``mcn_githubactions_vulnerabilities_1`` check passes for the repository. You can create a simple policy like the one below and store it in a file (e.g., ``check_github_actions_vuln.dl``):

.. code-block:: prolog

  Policy("github_actions_vulns", component_id, "GitHub Actions Vulnerability Detection") :-
    check_passed(component_id, "mcn_githubactions_vulnerabilities_1").

  apply_policy_to("github_actions_vulns", component_id) :-
    is_repo_url(component_id, "https://github.com/apache/logging-log4j2").

Run the ``verify-policy`` command to check if the ``mcn_githubactions_vulnerabilities_1`` check is successful.

.. code-block:: shell

  ./run_macaron.sh verify-policy --database ./output/macaron.db --file ./check_github_actions_vuln.dl

++++++++++++++
Using the PURL
++++++++++++++

Alternatively, run the ``analyze`` command with the PURL of a package:

.. code-block:: shell

  ./run_macaron.sh analyze -purl pkg:maven/org.apache.logging.log4j/log4j-core@3.0.0-beta3

Then, ensure that the ``mcn_githubactions_vulnerabilities_1`` check passes for the component. You can create a similar policy to the one shown earlier and store it in a file (e.g., ``check_github_actions_vuln.dl``):

.. code-block:: prolog

  Policy("github_actions_vulns", component_id, "GitHub Actions Vulnerability Detection") :-
    check_passed(component_id, "mcn_githubactions_vulnerabilities_1").

  apply_policy_to("github_actions_vulns", component_id) :-
    is_component(component_id, purl),
    match("pkg:maven/org.apache.logging.log4j/log4j-core@.*", purl).

Run the ``verify-policy`` command to verify that the check passes:

.. code-block:: shell

  ./run_macaron.sh verify-policy --database ./output/macaron.db --file ./check_github_actions_vuln.dl

******************
Review the Results
******************

Macaron stores the results in a local database and generates HTML and JSON reports. If the ``verify-policy`` step fails, you can retrieve detailed information about the vulnerable repositories from the database. For a quick overview, refer to the HTML report located in the ``output/reports`` directory, such as:

- ``output/reports/github_com/apache/logging-log4j2/logging-log4j2.html`` (for repository path analysis)
- ``output/reports/maven/org_apache_logging_log4j/log4j-core/log4j-core.html`` (for PURL analysis)

For comprehensive results, query the local database with the following command:

.. code-block:: shell

  sqlite3 -json output/macaron.db "SELECT * FROM github_actions_vulnerabilities_check;" | jq

.. code-block:: json

  [
    {
      "id": 1,
      "vulnerability_urls": "[\"https://osv.dev/vulnerability/GHSA-mrrh-fwg8-r2c3\"]",
      "github_actions_id": "tj-actions/changed-files",
      "github_actions_version": "v41",
      "caller_workflow": "https://github.com/OWNER/REPO/blob/4d59c62f42b7f5c08e31f6eb401a4e35355fe077/.github/workflows/workflow.yml"
    }
  ]

**Output Breakdown:**

- **id**: Unique identifier for this specific report in the database.
- **vulnerability_urls**: List of URLs pointing to published vulnerability advisories for the identified GitHub Action.
- **github_actions_id**: The identifier of the vulnerable GitHub Action, formatted as ``OWNER/REPO``.
- **github_actions_version**: The version of the GitHub Action that contains the vulnerability.
- **caller_workflow**: URL to the GitHub workflow file that is calling the affected action.

The output is machine-readable, making it suitable for further analysis, automation, or integration with other security tools.

.. note::

  The ``OWNER`` and ``REPO`` in the ``caller_workflow`` field are anonymized to protect the privacy of the repository being analyzed.

**********
Mitigation
**********

To mitigate the vulnerability, review the advisory linked in the ``vulnerability_urls`` field and identify the patched version of the GitHub Action. Follow security best practices by pinning the vulnerable action to a fixed version, using the commit SHA for the patched version. This ensures that security updates are incorporated while maintaining the stability of your workflow.

For example, to pin the ``tj-actions/changed-files`` action to a specific version:

.. code-block:: yaml

  uses: tj-actions/changed-files@823fcebdb31bb35fdf2229d9f769b400309430d0 # v46.0.3

Refer to GitHub's security hardening guide for more information on managing third-party actions securely: `GitHub Security <https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions#using-third-party-actions>`_.

---------------------
Why This is Important
---------------------

In the aftermath of the supply chain compromise in March 2025, securing your CI/CD pipeline is more important than ever. GitHub Actions are widely used to automate development processes, but relying on third-party actions that could be compromised poses a significant risk.

By using the ``mcn_githubactions_vulnerabilities_1`` check in Macaron, you can proactively secure your repositories. It helps identify and mitigate risks early in the development process, ensuring that your workflows are running trusted and secure actions.

As third-party libraries and tools continue to grow in popularity, security risks from supply chain attacks will only increase. Regularly checking for vulnerabilities in the GitHub Actions used in your projects is an essential step toward maintaining a secure development environment.

----------
Conclusion
----------

In this tutorial, we've shown you how to use Macaron to detect vulnerable third-party GitHub Actions in your repository. By integrating this check into your pipeline, you can prevent security breaches caused by compromised or vulnerable actions. This is especially important following the recent `CVE-2025-30066 <https://www.cve.org/CVERecord?id=CVE-2025-30066>`_ report, which highlights the need for robust security measures in CI/CD pipelines.

Make sure to stay up to date with Macaron’s security checks to protect your project from emerging threats.

For more information about using Macaron and other checks, please refer to the full list of our checks: :ref:`here <index>`.
