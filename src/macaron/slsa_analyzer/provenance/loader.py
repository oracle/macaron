# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the loaders for SLSA provenances."""

import base64
import configparser
import gzip
import json
import zlib
from urllib.parse import urlparse

from macaron.config.defaults import defaults
from macaron.slsa_analyzer.provenance.intoto import InTotoPayload, validate_intoto_payload
from macaron.slsa_analyzer.provenance.intoto.errors import LoadIntotoAttestationError, ValidateInTotoPayloadError
from macaron.util import JsonType, send_get_http_raw


def _try_read_url_link_file(file_content: bytes) -> str | None:
    parser = configparser.ConfigParser()
    try:
        parser.read_string(file_content.decode())
        return parser.get("InternetShortcut", "url", fallback=None)
    except (configparser.Error, UnicodeDecodeError):
        return None


def _download_url_file_content(url: str, url_link_hostname_allowlist: list[str]) -> bytes:
    hostname = urlparse(url).hostname
    if hostname is None or hostname == "":
        raise LoadIntotoAttestationError("Cannot resolve URL link file: invalid URL")
    if hostname not in url_link_hostname_allowlist:
        raise LoadIntotoAttestationError(
            "Cannot resolve URL link file: target hostname '" + hostname + "' is not in allowed hostnames."
        )

    # TODO download size limit?
    timeout = defaults.getint("downloads", "timeout", fallback=120)
    response = send_get_http_raw(url=url, headers=None, timeout=timeout)
    if response is None:
        raise LoadIntotoAttestationError("Cannot resolve URL link file: Failed to download file")
    if response.status_code != 200:
        raise LoadIntotoAttestationError(
            "Cannot resolve URL link file: Failed to download file, error " + str(response.status_code)
        )
    return response.content


def _load_provenance_file_content(
    file_content: bytes, url_link_hostname_allowlist: list[str], url_link_depth_limit: int = 5
) -> dict[str, JsonType]:
    url_link_depth = 0
    while url_link_depth <= url_link_depth_limit:
        url = _try_read_url_link_file(file_content)
        if url is None:
            break
        if url_link_depth == url_link_depth_limit:
            raise LoadIntotoAttestationError("Cannot resolve URL link file: depth limit exceeded")
        file_content = _download_url_file_content(url, url_link_hostname_allowlist)
        url_link_depth = url_link_depth + 1

    try:
        try:
            decompressed_file_content = gzip.decompress(file_content)
            provenance = json.loads(decompressed_file_content.decode())
        except (gzip.BadGzipFile, EOFError, zlib.error, configparser.NoOptionError):
            provenance = json.loads(file_content.decode())
    except (json.JSONDecodeError, TypeError) as error:
        raise LoadIntotoAttestationError(
            "Cannot deserialize the file content as JSON.",
        ) from error

    provenance_payload = provenance.get("payload", None)
    if not provenance_payload:
        raise LoadIntotoAttestationError(
            'Cannot find the "payload" field in the decoded provenance.',
        )

    try:
        decoded_payload = base64.b64decode(provenance_payload)
    except UnicodeDecodeError as error:
        raise LoadIntotoAttestationError("Cannot decode the payload.") from error

    try:
        json_payload = json.loads(decoded_payload)
    except (json.JSONDecodeError, TypeError) as error:
        raise LoadIntotoAttestationError(
            "Cannot deserialize the provenance payload as JSON.",
        ) from error

    if not isinstance(json_payload, dict):
        raise LoadIntotoAttestationError("The provenance payload is not a JSON object.")

    return json_payload


def load_provenance_file(filepath: str) -> dict[str, JsonType]:
    """Load a provenance file and obtain the payload.

    Inside a provenance file is a DSSE envelope containing a base64-encoded
    provenance JSON payload. See: https://github.com/secure-systems-lab/dsse.
    If the file is gzipped, it will be transparently decompressed.
    If the file is a URL file (Windows .url file format, i.e. an ini file with
    a "URL" field inside an "InternetShortcut" section), it will be transparently
    downloaded.

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
        with open(filepath, mode="rb") as file:
            file_content = file.read()
            return _load_provenance_file_content(
                file_content, defaults.get_list("slsa.verifier", "url_link_hostname_allowlist", fallback=[])
            )
    except OSError as error:
        raise LoadIntotoAttestationError("Cannot open file.") from error


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
