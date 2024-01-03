# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Tests for functions to base64 encode/decode the in-toto attestation payload."""


from string import printable

from hypothesis import given
from hypothesis import strategies as st

from macaron.intoto.encoder_decoder import decode_payload, encode_payload
from macaron.util import JsonType

json_values = st.recursive(
    st.none() | st.booleans() | st.floats(allow_nan=False, allow_infinity=False) | st.text(printable),
    lambda children: st.lists(children) | st.dictionaries(st.text(printable), children),
    max_leaves=3,
)
json_payloads = st.dictionaries(st.text(printable), json_values)


@given(json_payload_before=json_payloads)
def test_round_trip(json_payload_before: dict[str, JsonType]) -> None:
    """Test the round-trip property of the `encode_payload` and the `decode_payload` functions.

    After a round-trip of `encode_payload` and `decode_payload`, we should get the original payload.
    """
    encoded = encode_payload(json_payload_before)
    json_payload_after = decode_payload(encoded)
    assert json_payload_before == json_payload_after
