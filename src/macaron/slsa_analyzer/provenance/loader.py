# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the loaders for SLSA provenances."""

import base64
import json
from typing import Any

from macaron.errors import ProvenanceLoadError
from macaron.util import JsonType


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


def load_provenance(filepath: str) -> dict[str, JsonType]:
    """Load a provenance JSON payload.

    Inside a provenance file is a DSSE envelope containing a base64-encoded
    provenance JSON payload. See: https://github.com/secure-systems-lab/dsse.

    Returns
    -------
    dict[str, JsonType]
        The provenance JSON payload.

    Raises
    ------
    ProvenanceLoadError
        If there is an error loading the provenance JSON payload.
    """
    try:
        with open(filepath, encoding="utf-8") as file:
            provenance = json.load(file)
    except (json.JSONDecodeError, TypeError) as error:
        raise ProvenanceLoadError(
            "Cannot deserialize the file content as JSON.",
        ) from error

    provenance_payload = provenance.get("payload", None)
    if not provenance_payload:
        raise ProvenanceLoadError(
            'Cannot find the "payload" field in the decoded provenance.',
        )

    try:
        decoded_payload = base64.b64decode(provenance_payload)
    except UnicodeDecodeError as error:
        raise ProvenanceLoadError("Cannot decode the payload.") from error

    try:
        json_payload = json.loads(decoded_payload)
    except (json.JSONDecodeError, TypeError) as error:
        raise ProvenanceLoadError(
            "Cannot deserialize the provenance payload as JSON.",
        ) from error

    if not isinstance(json_payload, dict):
        raise ProvenanceLoadError("The provenance payload is not a JSON object.")

    return json_payload
