.. Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
.. Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

.. _gen-vsa_tutorial:

=========================================
Generate Verification Summary Attestation
=========================================


This tutorial walks through how Macaron can be used to generate Verification Summary Attestation (VSA).

For more information about VSAs, please refer to the :ref:`Verification Summary Attestation page<vsa>`.


* https://slsa.dev/spec/v1.0/verification_summary
* https://security.googleblog.com/2022/04/how-to-slsa-part-1-basics.html

.. note::

    At the moment, this feature only supports a limited number of artifact and provenance types. Please refer to the :ref:`notes-on-using-the-feature` section for more information.


--------
Use case
--------

Imagine you are the producer of an artifact. You want consumers of this artifact to be able to verify it. In order to simplify the verification process, you can use Macaron to verify the artifact prior to publishing it to consumers and generate a Verification Summary Attestation (VSA), thus allowing for delegated verification on consumers' side if they trust you as a verifier. For easy access to the generated VSA on consumers' side, it can be published alongside the artifact, for example.

As you are the producer of the artifact, you also have access to the provenance attesting to the build.

As a tool, Macaron can support this particular use case quite well. Given a provenance of a build as input, Macaron can then analyze different aspects of the build, verify the data gathered against a Datalog policy, and generate VSA attesting to artifacts produced by the build.


-------
Example
-------

Let's say you are the author of the Maven artifact `<https://repo1.maven.org/maven2/io/micronaut/openapi/micronaut-openapi/6.8.0/micronaut-openapi-6.8.0-javadoc.jar>`_, which can be identified with the PackageURL ``pkg:maven/io.micronaut.openapi/micronaut-openapi@6.8.0?type=jar``. You used `Witness <https://github.com/in-toto/witness>`_ to generate a build provenance file ``multiple.intoto.jsonl``. In addition, for security purposes, you also want to enforce certain properties of the build based on the content of the provenance through :ref:`CUE expectation <pages/using:Verifying provenance expectations in CUE language>`, specified in a ``expectation.cue`` file.

In order to verify the artifact with Macaron, you can follow the following steps:

- **Step 1**: Provide Macaron with the provenance file, the PackageURL identifying the artifact, and the CUE expectation file.

.. code-block:: shell

  ./run_macaron.sh analyze \
        --package-url pkg:maven/io.micronaut.openapi/micronaut-openapi@6.8.0?type=jar \
        --provenance-file multiple.intoto.jsonl \
        --provenance-expectation expectation.cue \
        --skip-deps

.. note::

    If your build produces more than one artifact, you can use the same command once for each artifact and substitute in the appropriate PURL for the respective artifact.


- **Step 2**: Compose a policy to verify the artifact against. The following is a sample policy enforcing the two checks ``mcn_version_control_system_1`` and ``mcn_provenance_expectation_1`` passing for the artifact. Let's put this policy in a file ``policy.dl``.

.. code-block:: prolog

    #include "prelude.dl"

    Policy("producer-policy", component_id, "Poducer policy for micronaut-openapi.") :-
        check_passed(component_id, "mcn_version_control_system_1"),
        check_passed(component_id, "mcn_provenance_expectation_1").

    apply_policy_to("has-hosted-build", component_id) :-
        is_component(component_id, "pkg:maven/io.micronaut.openapi/micronaut-openapi@6.8.0?type=jar").

- **Step 3**: Verify the artifact against the policy file.

.. code-block:: shell

  ./run_macaron.sh verify-policy --file policy.dl

After step 3, if the artifact satisfies the policy, there will be a VSA file generated in the output directory at ``output/vsa.intoto.jsonl``. You can inspect the payload of this VSA using the following command:

.. code-block:: bash

    cat output/vsa.intoto.jsonl | jq -r '.payload' | base64 -d | jq


If you inspect the payload of this file, you can expect the content of the file to be as follows:

.. code-block:: json

    {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [
            {
                "uri": "pkg:maven/io.micronaut.openapi/micronaut-openapi@6.8.0?type=jar",
                "digest": {
                    "sha256": "..."  // The SHA256 digest of the file
                }
            },
        ],
        "predicateType": "https://slsa.dev/verification_summary/v1",
        "predicate": {
            "verifier": {
                "id": "https://github.com/oracle/macaron",
                "version": {
                    "macaron": "0.10.0"
                }
            },
            "timeVerified": "2024-04-12T07:37:29.364898+00:00",
            "resourceUri": "pkg:maven/io.micronaut.openapi/micronaut-openapi@6.8.0",
            "policy": {
                "content": "...",  // The policy in plain text
            },
            "verificationResult": "PASSED",
            "verifiedLevels": []
        }
    }


.. _notes-on-using-the-feature:

--------------------------
Notes on using the feature
--------------------------

As of version ``v0.10.0`` of Macaron, the following are supported:

* Artifacts:

  * Maven artifacts: there are 4 specific artifact types being supported: ``jar``, ``pom``, ``java-doc``, and ``java-source``. Please refer to the `Maven reference <https://maven.apache.org/ref/3.9.6/maven-core/artifact-handlers.html>`_ for more information.

* Provenances: Witness provenances.

Support for other artifact types and provenance types will be added in the later versions of Macaron.
