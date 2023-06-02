=============
Verify Policy
=============

-----------
Description
-----------

Verify the analysis results against a Souffle Datalog policy.

-----
Usage
-----

.. code-block:: shell

    usage: ./run_macaron.sh verify-policy [-h] -d DATABASE -f FILE [-s]

-------
Options
-------

.. option:: -h, --help

    Show this help message and exit

.. option:: -d DATABASE, --database DATABASE

    Path to the database.

.. option:: -f FILE, --file FILE

    Path to the Datalog policy.

.. option:: -s, --show-prelude

    Show policy prelude.
