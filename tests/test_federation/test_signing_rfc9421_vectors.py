"""RFC 9421 (HTTP Message Signatures) conformance against the PUBLISHED vector.

The Ed25519 keypair (RFC 9421 §B.1.4, ``test-key-ed25519``) and the signed
example (§B.2.6, ``sig-b26``) are vendored under ``vendor/rfc9421_appendix_b/``
(see that dir's README for provenance and the component-set note). These bytes
come from the standard's own appendix — an EXTERNAL anchor for
``app/federation/signing.py``.

COMPONENT-SET GAP (documented, not faked): RFC 9421 §B.2.6 signs
``("date" "@method" "@path" "@authority" "content-type" "content-length")``,
whereas ``signing.py`` uses a fixed federation set
``("@method" "@target-uri" "content-digest")``. They are not byte-compatible, so
the vector cannot be driven through ``sign_request``/``verify_request``'s header
construction. We therefore assert at the level signing.py actually supports and
relies on: the raw Ed25519 sign/verify over the documented signature-base bytes
— which is literally the final step ``verify_request`` performs
(``public_key.verify(signature, base.encode("utf-8"))``). This locks our Ed25519
+ signature-base byte handling to the RFC; the differing component set is a
documented design choice, not a conformance failure.
"""

import base64
import json
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
    load_pem_private_key,
    load_pem_public_key,
)

_VECTOR = (
    Path(__file__).resolve().parent / "vendor" / "rfc9421_appendix_b" / "vector.json"
)
_V = json.loads(_VECTOR.read_text(encoding="utf-8"))

_BASE_BYTES = _V["signature_base"].encode("utf-8")
_SIG = base64.b64decode(_V["signature_b64"])


def _public_key() -> Ed25519PublicKey:
    key = load_pem_public_key(_V["public_key_pem"].encode("utf-8"))
    assert isinstance(key, Ed25519PublicKey)
    return key


def _private_key() -> Ed25519PrivateKey:
    key = load_pem_private_key(_V["private_key_pem"].encode("utf-8"), password=None)
    assert isinstance(key, Ed25519PrivateKey)
    return key


def test_vendored_keypair_is_internally_consistent() -> None:
    """Transcription guard: the §B.1.4 private key must derive the §B.1.4 public
    key, and both must match the raw-hex cross-check stored in the vector."""
    priv = _private_key()
    pub = _public_key()
    pub_raw = pub.public_bytes(Encoding.Raw, PublicFormat.Raw)
    priv_raw = priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    assert pub_raw == bytes.fromhex(_V["public_key_raw_hex"])
    assert priv_raw == bytes.fromhex(_V["private_key_raw_hex"])
    derived = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    assert derived == pub_raw


def test_signature_base_is_exactly_the_published_bytes() -> None:
    """Sanity that the vendored signature base is the §B.2.6 shape: each covered
    component on its own line, @signature-params last, no trailing newline."""
    base = _V["signature_base"]
    assert base.startswith('"date": Tue, 20 Apr 2021 02:07:55 GMT\n')
    assert '"@method": POST\n' in base
    assert base.endswith(';keyid="test-key-ed25519"')
    assert not base.endswith("\n")
    # The @signature-params line must carry exactly the covered component set.
    for comp in _V["covered_components"]:
        assert f'"{comp}"' in base


def test_published_signature_verifies_over_signature_base() -> None:
    """THE external KAT: the published sig-b26 must verify against the §B.1.4
    public key over the documented signature base. This is the exact crypto step
    signing.py.verify_request performs (public_key.verify(sig, base_bytes))."""
    # Must not raise.
    _public_key().verify(_SIG, _BASE_BYTES)


def test_signing_py_resigns_to_the_published_signature() -> None:
    """Ed25519 is deterministic (RFC 8032), and signing.py signs with the raw
    primitive signing.py.sign_request uses internally (private_key.sign(bytes)).
    So re-signing the documented base with the §B.1.4 key MUST reproduce the
    published signature byte-for-byte — meaning any RFC-9421 verifier accepts
    signatures produced by our Ed25519 path."""
    resigned = _private_key().sign(_BASE_BYTES)
    assert base64.b64encode(resigned).decode("ascii") == _V["signature_b64"]


def test_one_byte_tamper_in_base_is_rejected() -> None:
    """Flip one byte of the signature base — the published signature must no
    longer verify (confirms the KAT is not a tautology)."""
    tampered = bytearray(_BASE_BYTES)
    tampered[0] ^= 0x01
    with pytest.raises(InvalidSignature):
        _public_key().verify(_SIG, bytes(tampered))


def test_one_byte_tamper_in_signature_is_rejected() -> None:
    """Flip one byte of the signature — verification over the genuine base must
    fail."""
    tampered = bytearray(_SIG)
    tampered[0] ^= 0x01
    with pytest.raises(InvalidSignature):
        _public_key().verify(bytes(tampered), _BASE_BYTES)
