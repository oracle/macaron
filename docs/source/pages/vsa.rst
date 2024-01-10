=================================
Verification Summary Attestations
=================================

.. _vsa:

Macaron generates Verification Summary Attestations (VSAs) as part of its verification to communicate the fact that "some software component has been verified against a policy".

The concept of VSA in Macaron largely follows the concept of VSA in `SLSA <https://slsa.dev/spec/v1.0/verification_summary>`_ and `in-toto <https://github.com/in-toto/attestation/blob/main/spec/predicates/vsa.md>`_.


---------
Use cases
---------

The use cases of Macaron VSAs includes, but not limited to:

- **Enabling delegated verification**: This allows software consumers to make use of verification results from another party.
- **Caching verification results**: It could be expensive or inconvenient to run a full Macaron verification in certain circumstances. A VSA helps with caching and reusing verification results.


------
Schema
------

.. Type references
.. _PackageURL: https://github.com/package-url/purl-spec
.. _Envelope: https://github.com/in-toto/attestation/blob/main/spec/v1/envelope.md
.. _TypeURI: https://github.com/in-toto/attestation/blob/main/spec/v1/field_types.md#TypeURI
.. _Timestamp: https://github.com/in-toto/attestation/blob/main/spec/v1/field_types.md#timestamp
.. _ResourceURI: https://github.com/in-toto/attestation/blob/main/spec/v1/field_types.md#ResourceURI
.. _ResourceDescriptor: https://github.com/in-toto/attestation/blob/main/spec/v1/resource_descriptor.md
.. _SlsaResult: https://slsa.dev/spec/v1.0/verification_summary#slsaresult

Following in-toto attestation schema, the outermost layer if a Macaron-generated VSA is a `DSSE envelope <https://github.com/in-toto/attestation/blob/main/spec/v1/envelope.md>`_ containing a base64-encoded ``payload`` of type `in-toto Statement <https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md>`_.

The following is the schema of the Statement layer:


.. code-block:: js+jinja

    {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [
            {
                "uri": {{ PackageURL of the software component being verified }},
            }
        ],
        "predicateType": "https://slsa.dev/verification_summary/v1",
        "predicate": {
            "verifier": {
                "id": "https://github.com/oracle/macaron",
                "version": {
                    "macaron": {{ Macaron version }}
                }
            },
            "timeVerified": {{ The timestamp of when the verification happened }},
            "resourceUri": {{ PackageURL of the software component being verified }},
            "policy": {
                "content": {{ Datalog policy applies to the software component being verified }}
            },
            "verificationResult": {{ Either "PASSED" or "FAILED" }},
            "verifiedLevels": []
        }
    }



* ``_type``: string (`TypeURI`_)
    Identifier for the schema of the Statement layer. This follows `in-toto v1 Statement layer schema <https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md>`_ and is always ``https://in-toto.io/Statement/v1``.

* ``subject``: array of `ResourceDescriptor`_ objects
    Subjects of the VSA. Each entry is a software component being verified by Macaron.

    *Note: In the current version of Macaron, this field only contains one single software component, identified by a `PackageURL`_.*

* ``predicateType``: string (`TypeURI`_)
    Identifier for the type of the Predicate. For Macaron-generated VSAs, this is always ``https://slsa.dev/verification_summary/v1``.

* ``predicate``: object
    The Predicate of the attestation, providing information about the verification.

* ``predicate.verifier``: object
    Information about the tool running the verification, which is Macaron.

* ``predicate.verifier.id``: string (`TypeURI`_)
    The identifier for Macaron.

* ``predicate.timeVerified``: string (`Timestamp`_)
    The timestamp of when the verification happened.

* ``predicate.resourceUri``: string (`ResourceURI`_)
    URI identifying the resource associated with the software component being verified.

    *Note: In the current version of Macaron, the value of this field is similar to the `PackageURL`_ identifying the only subject software component of the VSA.*

* ``policy``: object
    Details about the policy that the subject software component was verified against.

* ``policy.content``: string
    The Souffle datalog policy used for verification, in plain text.

* ``verificationResult``: string, either ``"PASSED"`` or ``"FAILED"``
    The verification result. The result of ``"PASSED"`` means the subject software component conforms to the policy.

* ``verificationResult``: array (`SlsaResult`_), required
    Indicates the highest level of each SLSA track verified for the software component (and not its dependencies), or “FAILED” if policy verification failed.

    *Note: For the current version of Macaron, this is left empty.*


-------
Example
-------


The following is an example payload (Statement layer) of a Macaron VSA generated from verification on the `slsa-verifier <https://github.com/slsa-framework/slsa-verifier>`_ repository.

.. code-block:: json

    {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [
            {
                "uri": "pkg:github.com/slsa-framework/slsa-verifier@7e1e47d7d793930ab0082c15c2b971fdb53a3c95"
            }
        ],
        "predicateType": "https://slsa.dev/verification_summary/v1",
        "predicate": {
            "verifier": {
                "id": "https://github.com/oracle/macaron",
                "version": {
                    "macaron": "0.6.0"
                }
            },
            "timeVerified": "2024-01-04T11:13:03.496399Z",
            "resourceUri": "pkg:github.com/slsa-framework/slsa-verifier@7e1e47d7d793930ab0082c15c2b971fdb53a3c95",
            "policy": {
                "content": "#include \"prelude.dl\"\n\nPolicy(\"slsa_verifier_policy\", component_id, \"Policy for SLSA Verifier\") :-\n  check_passed(component_id, \"mcn_build_as_code_1\"),\n  check_passed(component_id, \"mcn_provenance_level_three_1\"),\n  check_passed(component_id, \"mcn_provenance_available_1\").\n\napply_policy_to(\"slsa_verifier_policy\", component_id) :-\n  is_repo(\n    _,  // repo_id\n    \"github.com/slsa-framework/slsa-verifier\",\n    component_id\n  ).\n"
            },
            "verificationResult": "PASSED",
            "verifiedLevels": []
        }
    }

This VSA communicates that the subject software component ``"pkg:github.com/slsa-framework/slsa-verifier@7e1e47d7d793930ab0082c15c2b971fdb53a3c95"`` passed the following policy in the ``policy.content`` field:

.. code-block:: prolog

    #include "prelude.dl"

    Policy("slsa_verifier_policy", component_id, "Policy for SLSA Verifier") :-
      check_passed(component_id, "mcn_build_as_code_1"),
      check_passed(component_id, "mcn_provenance_level_three_1"),
      check_passed(component_id, "mcn_provenance_available_1").

    apply_policy_to("slsa_verifier_policy", component_id) :-
      is_repo(
        _,  // repo_id
        "github.com/slsa-framework/slsa-verifier",
        component_id
      ).

This policy enforces the subject software component to pass 3 Macaron checks:

* ``mcn_build_as_code_1``
* ``mcn_provenance_level_three_1``
* ``mcn_provenance_available_1``

For more details on using the Macaron VSA generation feature and inspecting the resulting VSA, please refer to the :ref:`Output File Guide <output_files_guide>`.
