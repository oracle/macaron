# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Functions to base64 encode/decode the in-toto attestation payload."""

import base64
import json

from macaron.intoto.errors import DecodeIntotoAttestationError


def encode_payload(payload: dict) -> str:
    """Encode (base64 encoding) the payload of an in-toto attestation.

    For more details about the payload field, see:
        https://github.com/in-toto/attestation/blob/main/spec/v1/envelope.md#fields.

    Parameters
    ----------
    payload : dict
        The unencoded payload.

    Returns
    -------
    str
        The encoded payload.
    """
    return base64.b64encode(json.dumps(payload).encode()).decode("ascii")


def decode_payload(encoded_payload: str) -> dict:
    """Decode (base64 decoding) the payload of an in-toto attestation.

    For more details about the payload field, see:
        https://github.com/in-toto/attestation/blob/main/spec/v1/envelope.md#fields.

    Parameters
    ----------
    encoded_payload : str
        The encoded payload.

    Returns
    -------
    dict
        The decoded payload.

    Raises
    ------
    DecodeIntotoAttestationError
        If there is an error decoding the payload of an in-toto attestation.
    """
    try:
        decoded_string = base64.b64decode(encoded_payload)
    except UnicodeDecodeError as error:
        raise DecodeIntotoAttestationError("Cannot base64-decode the attestation payload.") from error

    try:
        json_payload = json.loads(decoded_string)
    except (json.JSONDecodeError, TypeError) as error:
        raise DecodeIntotoAttestationError(
            "Cannot deserialize the attestation payload as JSON.",
        ) from error

    if not isinstance(json_payload, dict):
        raise DecodeIntotoAttestationError("The provenance payload is not a JSON object.")

    return json_payload
