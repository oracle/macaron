Policies
=======

This directory contains policy resources used by Macaron. Policies in this folder are packaged as templates that the verify-policy command can use.

Common files and conventions
---------------------------
- `*.dl.template` - datalog policy templates.
- `*.description` - short descriptions that explain the policy's intent.
- `*.cue.template` - CUE-based expectation templates used by the GDK.

Example policies are exposed to the user via Macaron commands `verify-policy --existing-policy <policy-name>`.
