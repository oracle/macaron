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

- **Caching verification results**: It could be expensive or inconvenient to run a full Macaron verification in certain circumstances. A VSA helps with caching and reusing verification results.
- **Enabling delegated verification**: This allows software consumers to make use of verification results from another party.


------
Schema
------

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
            "timeVerified": "2024-01-04T11:13:03.496399Z",
            "resourceUri": {{ PackageURL of the software component being verified }},
            "policy": {
                "content": {{ Datalog policy applies to the software component being verified }}
            },
            "verificationResult": {{ Either "PASSED" or "FAILED" }},
            "verifiedLevels": []
        }
    }


-------
Example
-------

The following is an example of Macaron VSA generated from verification on the `slsa-verifier <https://github.com/slsa-framework/slsa-verifier>`_ repository.


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

For more details on using the Macaron VSA generation feature, please refer to the :ref:`Output File Guide <output_files_guide>`.
