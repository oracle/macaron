# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the loaders for SLSA provenances."""

import gzip
import json
import zlib

from macaron.intoto import InTotoPayload, validate_intoto_payload
from macaron.intoto.encoder_decoder import decode_payload
from macaron.intoto.errors import DecodeIntotoAttestationError, LoadIntotoAttestationError, ValidateInTotoPayloadError
from macaron.util import JsonType


def load_provenance_file(filepath: str) -> dict[str, JsonType]:
    """Load a provenance file and obtain the payload.

    Inside a provenance file is a DSSE envelope containing a base64-encoded
    provenance JSON payload. See: https://github.com/secure-systems-lab/dsse.
    If the file is gzipped, it will be transparently decompressed.

    Parameters
    ----------
    filepath : str
        Path to the provenance file.

    Returns
    -------
    dict[str, JsonType]
        The provenance JSON payload.

    Raises
    ------
    LoadIntotoAttestationError
        If there is an error loading the provenance JSON payload.
    """
    try:
        try:
            with gzip.open(filepath, mode="rt", encoding="utf-8") as file:
                provenance = json.load(file)
        except (gzip.BadGzipFile, EOFError, zlib.error):
            with open(filepath, encoding="utf-8") as file:
                provenance = json.load(file)
    except (OSError, json.JSONDecodeError, TypeError) as error:
        raise LoadIntotoAttestationError(
            "Cannot deserialize the file content as JSON.",
        ) from error

    provenance_payload = provenance.get("payload", None)
    if not provenance_payload:
        raise LoadIntotoAttestationError(
            'Cannot find the "payload" field in the decoded provenance.',
        )

    try:
        json_payload = decode_payload(provenance_payload)
    except DecodeIntotoAttestationError as err:
        raise LoadIntotoAttestationError("Cannot decode the attestation payload") from err

    return json_payload


def load_provenance_payload(filepath: str) -> InTotoPayload:
    """Load, verify, and construct an in-toto payload.

    Parameters
    ----------
    filepath : str
        Absolute path to the provenance file.

    Returns
    -------
    InTotoPayload
        The in-toto payload.

    Raises
    ------
    LoadIntotoAttestationError
        If there is an error while loading and verifying the provenance payload.
    """
    try:
        payload_json = load_provenance_file(filepath)
    except LoadIntotoAttestationError as error:
        raise error

    try:
        return validate_intoto_payload(payload_json)
    except ValidateInTotoPayloadError as error:
        raise LoadIntotoAttestationError("Failed to deserialize the payload.") from error
