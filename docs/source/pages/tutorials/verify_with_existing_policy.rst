==============================================================
Verify with an existing example policy using --existing-policy
==============================================================

This short tutorial shows how to use the ``--existing-policy`` flag with the ``verify-policy`` subcommand to run one of the example (predefined) policies that ship with Macaron.

--------
Use case
--------

Use ``--existing-policy`` when you want to run one of the built-in example policies by name instead of providing a local policy file with ``--file``. Example policies are useful for quick checks or automated examples/tests.

-------
Example
-------

Run the ``malware-detection`` example policy against a package URL:

.. code-block:: shell

  ./run_macaron.sh analyze -purl pkg:pypi/django@5.0.6

.. note:: By default, Macaron clones the repositories and creates output files under the ``output`` directory. To understand the structure of this directory please see :ref:`Output Files Guide <output_files_guide>`.

.. code-block:: shell

    ./run_macaron.sh verify-policy \
      --database output/macaron.db \
      --existing-policy malware-detection \
      --package-url "pkg:pypi/django"

The result of this command should show that the policy succeeds with a zero exit code (if a policy fails to pass, Macaron returns a none-zero error code):

.. code-block:: shell

    Components Satisfy Policy
    1    pkg:pypi/django@5.0.6  check-component

    Components Violate Policy   None

    Passed Policies  check-component
    Failed Policies  None
    Policy Report    output/policy_report.json
    Verification Summary Attestation  output/vsa.intoto.jsonl
    Decode and Inspect the Content    cat output/vsa.intoto.jsonl | jq -r '.payload' | base64 -d | jq

-----------------
Related tutorials
-----------------

- :doc:`detect_malicious_package` — shows what the malware-detection policy does in this tutorial.
- :doc:`use_verification_summary_attestation` — how to consume an attestation
  produced by Macaron.
