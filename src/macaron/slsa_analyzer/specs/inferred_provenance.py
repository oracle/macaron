# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the inferred SLSA provenance spec."""


from macaron.intoto import v01


class Provenance:
    """This class implements the inferred SLSA provenance.

    This inferred provenance implementation follows the SLSA v0.2 provenance schema.
    See https://slsa.dev/spec/v0.2/provenance
    """

    def __init__(self) -> None:
        """Initialize instance."""
        self.payload: v01.InTotoV01Statement = {
            "_type": "https://in-toto.io/Statement/v0.1",
            "subject": [],
            "predicateType": "https://slsa.dev/provenance/v0.2",
            "predicate": {
                "builder": {"id": "<URI>"},
                "buildType": "<URI>",
                "invocation": {
                    "configSource": {"uri": "<URI>", "digest": {"sha1": "<STING>"}, "entryPoint": "<STRING>"},
                    "parameters": {},
                    "environment": {},
                },
                "buildConfig": {
                    # This is an arbitrary JSON object with a schema defined by buildType.
                    # We set these fields for GitHubActionsWorkflow buildType.
                    # Note that some checks might consume these values.
                    "jobID": "<STRING>",
                    "stepID": "<STRING>",
                },
                "metadata": {
                    "buildInvocationId": "<STRING>",
                    "buildStartedOn": "<TIMESTAMP>",
                    "buildFinishedOn": "<TIMESTAMP>",
                    "completeness": {"parameters": "false", "environment": "false", "materials": "false"},
                    "reproducible": "false",
                },
                "materials": [{"uri": "<URI>", "digest": {}}],
            },
        }
