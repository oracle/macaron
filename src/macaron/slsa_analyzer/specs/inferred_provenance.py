# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the inferred SLSA provenance spec."""


from macaron.slsa_analyzer.provenance.intoto import v01


class Provenance:
    """This class implements the inferred SLSA provenance."""

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
                "buildConfig": {},
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
