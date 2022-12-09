# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the loaders for SLSA provenances."""

import base64
import json
from typing import Any


class SLSAProvenanceError(Exception):
    """This error happens when the provenance cannot be loaded."""


class ProvPayloadLoader:
    """The loader for SLSA attestation files."""

    @classmethod
    def load(cls, path: str) -> Any:
        """Load a SLSA attestation file.

        This method returned the JSON deserialized ``Message``/``Statement`` section of the SLSA attestation.

        For more information on the terminology:
            - https://slsa.dev/attestation-model

        Parameters
        ----------
        path : str
            The path to the provenance file.

        Returns
        -------
        Any
            The JSON deserialized ``Message``/``Statement`` section of the SLSA attestation.

        Raises
        ------
        SLSAProvenanceError
            If there are errors when loading the file or decoding the content of the SLSA attestation.
        """
        try:
            with open(path, encoding="utf-8") as file:
                provenance = json.load(file)
                decoded_payload = base64.b64decode(provenance["payload"])
                return json.loads(decoded_payload)
        except json.JSONDecodeError as error:
            raise SLSAProvenanceError(f"Cannot deserialize the file content as JSON - {error}") from error
        except KeyError as error:
            raise SLSAProvenanceError(f"Cannot find the payload in the SLSA provenance - {error}") from error
        except UnicodeDecodeError as error:
            raise SLSAProvenanceError(
                f"Cannot decode the message content of the SLSA attestation - {error.reason}"
            ) from error
