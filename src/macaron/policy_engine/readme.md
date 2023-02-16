Macaron Policy Engine
-----------------------

This module is used to enforce policy requirements using the output of Macaron's analysis.

It has two modes of operation:

1. When running macaron in `analyze` mode, pass `-po policyfile.dl` and it will enforce the policy on the analyzed
   repositories.
2. Independently, by running `macaron.policy_engine`, and passing it a database file from historical analyses.

```
usage: policy_engine [-h] -d DATABASE [-f FILE] [-s] [-v] [-l LOG_PATH]

options:
  -h, --help            show this help message and exit
  -d DATABASE, --database DATABASE
                        Database path
  -f FILE, --file FILE  Replace policy file
  -s, --show-prelude    Show policy prelude
  -v, --verbose         Enable verbose logging
  -l LOG_PATH, --log-path LOG_PATH
                        Log file path
```

Writing Policies
----------------

Policies are written using [Souffle datalog](policies.md),
some example policies can be found [here: ./examples](examples).

To import the facts from the database, or Macaron, policies must begin with the line `#include "prelude.dl"`.
This imports the automatically generated datalog statements to import the facts.

This includes

1. `.decl`, and `.input` statements to load facts from the database
2. Rules to derive helper relations from these facts
3. The relations needed to define Policies so that macaron can understand the results
4. Some simple pre-written Policies

These can be found in the folder [prelude/](prelude). The automatically generated rules can be found by running
`macaron.policy_engine -d database.db -s`.

A policy consists of two statements, a definition clause and an enforcement clause. For example, to write a policy that
requires that the repository has verified authenticated provenance we can write:

```c
Policy("auth-provenance", repositoryid, "") :- check_passed(repositoryid, "mcn_provenance_level_three_1").
```

Then to actually enforce this policy on some repositories we write:

```c
apply_policy_to("auth-provenance", repo) :- is_repo(repo, _).
```

This rule applies the policy to every repository.

When being evaluated in the context of a macaron analysis this means every repository analysed in that macaron
invocation. When being evaluated independently on a database, this means every repository in the database.


When we evaluate this policy with, for example

```sh
python -m macaron.policy_engine -d output/macaron.db -f src/macaron/policy_engine/examples/simple_example.dl
```

We get

1. The list of all repositories where the relation `Policy(policyid, repoid)` does not exist
2. The list of all repositories where the relation `Policy(policyid, repoid)` exists
3. The list of policy ids where there exists a repository where the policy does not pass
4. The list of policy ids where there _does not_ exist a repository where the policy does not pass

```
repo_violates_policy
repo_satisfies_policy
    ['1', 'slsa-framework/slsa-verifier', 'auth-provenance']
    ['2', 'slsa-framework/slsa-verifier', 'auth-provenance']
    ['3', 'slsa-framework/slsa-verifier', 'auth-provenance']
    ['4', 'slsa-framework/slsa-verifier', 'auth-provenance']
passed_policies
    ['auth-provenance']
failed_policies
```

For the implementation of this see [prelude/policy.dl](prelude/policy.dl).

The presence of any row in the `failed_policies` relation means policy failure, and the policy engine will exit non-zero.
