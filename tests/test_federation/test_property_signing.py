"""Hypothesis property tests for the RFC 9421 Ed25519 signing substrate.

These pin the invariants the federation crypto layer must uphold (design of
record §P0.3): a freshly-signed request always verifies; any tamper to the body,
the key, the replay window, or the signature headers is rejected with a
``SignatureError`` rather than an uncaught exception.
"""

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from hypothesis import assume, given, settings
from hypothesis import strategies as st

import pytest

from app.federation.signing import (
    SignatureError,
    sign_request,
    verify_request,
)

_METHOD = "POST"
_URI = "https://harbor.example/federation/inbox"
_KEYID = "did:web:harbor.example#main-key"
_MAX_SKEW = 300

# Small bodies keep example generation cheap while still exercising the
# digest/signature path over arbitrary byte content (including empty).
_bodies = st.binary(min_size=0, max_size=64)
# Ed25519 timestamps live well inside the signed 64-bit space; keep them in a
# plausible epoch-seconds window so created/now arithmetic stays realistic.
_epochs = st.integers(min_value=1_600_000_000, max_value=2_000_000_000)


def _fresh_keys() -> tuple[Ed25519PrivateKey, object]:
    private_key = Ed25519PrivateKey.generate()
    return private_key, private_key.public_key()


@settings(max_examples=200)
@given(body=_bodies, created=_epochs, drift=st.integers(min_value=-_MAX_SKEW, max_value=_MAX_SKEW))
def test_sign_then_verify_always_roundtrips_within_skew(body, created, drift):
    """A freshly signed request verifies whenever ``now`` is within the skew."""
    private_key, public_key = _fresh_keys()
    headers = sign_request(private_key, _KEYID, _METHOD, _URI, body, created)
    verify_request(
        public_key,
        _METHOD,
        _URI,
        headers,
        body=body,
        max_skew_seconds=_MAX_SKEW,
        now=created + drift,
    )


@settings(max_examples=200)
@given(body=_bodies, created=_epochs, index=st.integers(min_value=0), flip=st.integers(min_value=1, max_value=255))
def test_flipping_any_body_byte_is_rejected(body, created, index, flip):
    """Mutating any byte of a non-empty body fails the content-digest check."""
    assume(len(body) > 0)
    private_key, public_key = _fresh_keys()
    headers = sign_request(private_key, _KEYID, _METHOD, _URI, body, created)

    pos = index % len(body)
    mutated = bytearray(body)
    mutated[pos] = mutated[pos] ^ flip  # guaranteed-different byte (flip != 0)
    tampered = bytes(mutated)
    assume(tampered != body)

    with pytest.raises(SignatureError):
        verify_request(
            public_key,
            _METHOD,
            _URI,
            headers,
            body=tampered,
            max_skew_seconds=_MAX_SKEW,
            now=created,
        )


@settings(max_examples=150)
@given(body=_bodies, created=_epochs)
def test_verifying_with_a_different_key_is_rejected(body, created):
    """A signature does not verify against an unrelated public key."""
    signer, _ = _fresh_keys()
    _, stranger_public = _fresh_keys()
    headers = sign_request(signer, _KEYID, _METHOD, _URI, body, created)

    with pytest.raises(SignatureError):
        verify_request(
            stranger_public,
            _METHOD,
            _URI,
            headers,
            body=body,
            max_skew_seconds=_MAX_SKEW,
            now=created,
        )


@settings(max_examples=200)
@given(body=_bodies, created=_epochs, overshoot=st.integers(min_value=1, max_value=10_000))
def test_created_outside_skew_is_rejected_at_the_boundary(body, created, overshoot):
    """Exactly ``== max_skew`` passes; one second beyond (either side) fails."""
    private_key, public_key = _fresh_keys()
    headers = sign_request(private_key, _KEYID, _METHOD, _URI, body, created)

    # Boundary: |now - created| == max_skew must still verify.
    verify_request(
        public_key, _METHOD, _URI, headers,
        body=body, max_skew_seconds=_MAX_SKEW, now=created + _MAX_SKEW,
    )
    verify_request(
        public_key, _METHOD, _URI, headers,
        body=body, max_skew_seconds=_MAX_SKEW, now=created - _MAX_SKEW,
    )

    # One past the window in either direction must be rejected.
    for now in (created + _MAX_SKEW + overshoot, created - _MAX_SKEW - overshoot):
        with pytest.raises(SignatureError):
            verify_request(
                public_key, _METHOD, _URI, headers,
                body=body, max_skew_seconds=_MAX_SKEW, now=now,
            )


@settings(max_examples=200)
@given(
    body=_bodies,
    created=_epochs,
    header_name=st.sampled_from(["Signature", "Content-Digest", "Signature-Input"]),
    corruption=st.sampled_from(["", "garbage", "sig1=:!!!notb64!!!:", "sig1=:YWJjZA==:", "x" * 80]),
)
def test_corrupting_a_signed_header_raises_signature_error_not_a_crash(
    body, created, header_name, corruption
):
    """Any corrupted signed header yields SignatureError, never an uncaught error."""
    private_key, public_key = _fresh_keys()
    headers = sign_request(private_key, _KEYID, _METHOD, _URI, body, created)
    headers[header_name] = corruption  # clobber one header with junk

    with pytest.raises(SignatureError):
        verify_request(
            public_key,
            _METHOD,
            _URI,
            headers,
            body=body,
            max_skew_seconds=_MAX_SKEW,
            now=created,
        )
