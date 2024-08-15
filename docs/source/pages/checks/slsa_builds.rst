.. Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
.. Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

.. _slsa_builds:

=================
SLSA Build Levels
=================

SLSA Build Levels report on various security aspects of a project, to provide a score that represents its overall trustworthiness and completeness.
See `SLSA Levels <https://slsa.dev/spec/v1.0/levels>`_.

Macaron's :class:`Provenance verified <macaron.slsa_analyzer.checks.provenance_verified_check.ProvenanceVerifiedCheck>` check uses the criteria of SLSA Build Levels to output a result that matches the correct level for a given artifact.

- Build Level 0: There is no provenance for the artifact.
- Build Level 1: There is provenance for the artifact but it cannot be verified.
- Build Level 2: There is provenance for the artifact, and it has been verified.
- Build Level 3: There is provenance for the artifact, it has been verified, and the build service isolates provenance generation in the control plane from the untrusted build process.

.. note :: Build Level 4 is not included in the check.
