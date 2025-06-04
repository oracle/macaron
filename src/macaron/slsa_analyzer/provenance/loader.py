# Copyright (c) 2022 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the loaders for SLSA provenances."""

import base64
import configparser
import gzip
import json
import logging
import zlib
from urllib.parse import urlparse

from cryptography import x509
from cryptography.x509 import DuplicateExtension, UnsupportedGeneralNameType

from macaron.config.defaults import defaults
from macaron.json_tools import JsonType, json_extract
from macaron.slsa_analyzer.provenance.intoto import InTotoPayload, validate_intoto_payload
from macaron.slsa_analyzer.provenance.intoto.errors import LoadIntotoAttestationError, ValidateInTotoPayloadError
from macaron.slsa_analyzer.specs.pypi_certificate_predicate import PyPICertificatePredicate
from macaron.util import send_get_http_raw

logger: logging.Logger = logging.getLogger(__name__)


# See: https://github.com/sigstore/fulcio/blob/main/docs/oid-info.md
_OID_IDS = {
    "1.3.6.1.4.1.57264.1.12": "source_repo",
    "1.3.6.1.4.1.57264.1.13": "source_digest",
    "1.3.6.1.4.1.57264.1.18": "workflow",
    "1.3.6.1.4.1.57264.1.21": "invocation",
}


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
            decoded_file_content = decompressed_file_content.decode()
            return decode_provenance(json.loads(decoded_file_content))
        except (gzip.BadGzipFile, EOFError, zlib.error):
            decoded_file_content = file_content.decode()
            return decode_provenance(json.loads(decoded_file_content))
    except (json.JSONDecodeError, TypeError, UnicodeDecodeError) as error:
        raise LoadIntotoAttestationError(
            "Cannot deserialize the file content as JSON.",
        ) from error


def decode_provenance(provenance: dict) -> dict[str, JsonType]:
    """Find and decode the provenance payload.

    Parameters
    ----------
    provenance: dict
        The contents of the provenance from which the payload will be decoded.

    Returns
    -------
    The decoded payload.

    Raises
    ------
    LoadIntotoAttestationError
        If the payload could not be decoded.
    """
    # The GitHub Attestation stores the DSSE envelope in `dsseEnvelope` property.
    dsse_envelope = provenance.get("dsseEnvelope", None)
    if dsse_envelope:
        provenance_payload = dsse_envelope.get("payload", None)
        logger.debug("Found dsseEnvelope property in the provenance.")
    else:
        # Some provenances, such as Witness may not include the DSSE envelope `dsseEnvelope`
        # property but contain its value directly.
        provenance_payload = provenance.get("payload", None)
    if not provenance_payload:
        # PyPI Attestation.
        provenance_payload = json_extract(provenance, ["envelope", "statement"], str)
    if not provenance_payload:
        # GitHub Attestation.
        # TODO Check if old method (above) actually works.
        provenance_payload = json_extract(provenance, ["bundle", "dsseEnvelope", "payload"], str)
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
        raise LoadIntotoAttestationError("Cannot deserialize the provenance payload as JSON.") from error

    if not isinstance(json_payload, dict):
        raise LoadIntotoAttestationError("The provenance payload is not a JSON object.")

    predicate_type = json_extract(json_payload, ["predicateType"], str)
    if not predicate_type:
        raise LoadIntotoAttestationError("The payload is missing a predicate type.")

    predicate = json_extract(json_payload, ["predicate"], dict)
    if predicate:
        if predicate_type == "https://docs.pypi.org/attestations/publish/v1":
            raise LoadIntotoAttestationError("PyPI attestation should not have a predicate.")
        return json_payload

    if predicate_type != "https://docs.pypi.org/attestations/publish/v1":
        raise LoadIntotoAttestationError(f"The payload predicate type '{predicate_type}' requires a predicate.")

    # For provenance without a predicate (e.g. PyPI), try to use the provenance certificate instead.
    raw_certificate = json_extract(provenance, ["verification_material", "certificate"], str)
    if not raw_certificate:
        raise LoadIntotoAttestationError("Failed to extract certificate data.")
    try:
        decoded_certificate = base64.b64decode(raw_certificate)
        certificate_predicate = get_x509_der_certificate_values(decoded_certificate)
    except UnicodeDecodeError as error:
        raise LoadIntotoAttestationError("Cannot decode the payload.") from error
    except ValueError as error:
        logger.debug(error)
        raise LoadIntotoAttestationError("Error parsing certificate.") from error

    json_payload["predicate"] = certificate_predicate.build_predicate()
    return json_payload


def get_x509_der_certificate_values(x509_der_certificate: bytes) -> PyPICertificatePredicate:
    """Retrieve the values of interest from an x509 certificate in the form of a predicate.

    The passed certificate should be following the DER specification.
    See https://peps.python.org/pep-0740/#provenance-objects.


    Parameters
    ----------
    x509_der_certificate: bytes
        The certificate bytes.

    Returns
    -------
    PyPICertificatePredicate
        A predicate created from the extracted values.

    Raises
    ------
    ValueError
        If the values could not be extracted.

    """
    certificate = x509.load_der_x509_certificate(x509_der_certificate)
    certificate_claims = {}
    try:
        extensions = certificate.extensions
    except (DuplicateExtension, UnsupportedGeneralNameType) as error:
        raise ValueError("Certificate extension error:") from error

    for extension in extensions:
        if extension.oid.dotted_string not in _OID_IDS:
            continue

        # These extensions should be of the UnrecognizedExtension type.
        # See: https://cryptography.io/en/latest/x509/reference/#cryptography.x509.UnrecognizedExtension
        claim_name = _OID_IDS[extension.oid.dotted_string]

        # Values are DER encoded UTF-8 strings. Removing the first two bytes seems to be sufficient.
        value: str = extension.value.value[2:].decode("UTF-8")
        if claim_name == "source_digest" and len(value) != 40:
            # Expect a 40 character hex value.
            raise ValueError(f"Digest is not 40 characters long: {value}. Original: {extension.value.value}")
        if claim_name != "source_digest" and not value.startswith("http"):
            # Expect a URL with scheme.
            raise ValueError(f"URL has invalid scheme: {value}. Original: {extension.value.value}")

        # Accept value.
        certificate_claims[claim_name] = value

    # Expect all values to have been found.
    if len(certificate_claims) != len(_OID_IDS):
        raise ValueError(f"Missing certificate claim(s). Found {len(certificate_claims)} of {len(_OID_IDS)}")

    # Apply final formatting.
    workflow = certificate_claims["workflow"]
    workflow = workflow.replace(certificate_claims["source_repo"] + "/", "")
    if "@" in workflow:
        workflow = workflow[: workflow.index("@")]
    certificate_claims["workflow"] = workflow

    if "/attempts" in certificate_claims["invocation"]:
        certificate_claims["invocation"] = certificate_claims["invocation"][
            : certificate_claims["invocation"].index("/attempts")
        ]

    return PyPICertificatePredicate(
        certificate_claims["source_repo"],
        certificate_claims["source_digest"],
        certificate_claims["workflow"],
        certificate_claims["invocation"],
    )


def load_provenance_file(filepath: str) -> dict[str, JsonType]:
    """Load a provenance file and obtain the payload.

    Inside a provenance file is a DSSE envelope containing a base64-encoded
    provenance JSON payload. See: https://github.com/secure-systems-lab/dsse.
    If the file is gzipped, it will be transparently decompressed.
    If the file is a URL file (Windows .url file format, i.e. an ini file with
    a "URL" field inside an "InternetShortcut" section), it will be transparently
    downloaded.

    Note: We have observed that GitHub provenances store the DSSE envelope using the
    `dsseEnvelope` property in the bundle. The bundle also includes Sigstore verification
    material, such as `publicKey` and `x509CertificateChain`. However, provenances generated by
    Witness and SLSA GitHub generator store the DSSE envelope content only.
    This function supports both types of provenances. See the Sigstore bundle schema, which is
    used in GitHub provenances:
    https://github.com/sigstore/protobuf-specs/blob/2bfc122984e8c30fc83f5892b2947af7d113b411/gen/jsonschema/schemas/Bundle.schema.json

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
