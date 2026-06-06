"""Task 2b (PR-B): activity envelope id + Ed25519 proof (design §6.2a, §8.1).

Pinned (spec-pinning workflow): both the content-address ``id`` and the ``proof``
signature are computed over ONE buffer — ``jcs_bytes(envelope without id+proof)``
— so a verifier strips both, canonicalizes once, and reuses that buffer for
``sha256 == id`` and ``ed25519.verify``.

The known-answer vector below is reproducible by any conformant peer: SHA-256 is
fixed, JCS is now RFC-8785-conformant (vendored cyberphone suite), and Ed25519
(RFC 8032) is deterministic — a fixed seed + fixed pre-image yields a fixed
signature. So pinning ``id`` and ``signature`` here is an interop contract, not a
self-graded value.
"""

import base64
import hashlib

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.federation import envelope
from app.federation.canonical import jcs_bytes

# Fixed Ed25519 seed 0x00..0x1f (reproducible) + the spec-pinned worked envelope.
_SEED = bytes(range(32))
_CONTEXT = "https://hsds-federation.pantrypirateradio.org/profile"
_ARGS = dict(
    context=_CONTEXT,
    activity_type="Update",
    actor="did:web:example.org",
    attributed_to="did:web:example.org",
    origin="did:web:example.org",
    federation_id="example.org:abc-123",
    obj={
        "id": "loc-1",
        "latitude": 40.7128,
        "longitude": -74.006,
        "name": "Test Pantry",
    },
    sequence=1,
    published="2026-06-05T00:00:00Z",
    license="sandia-ftgg-nc-os-1.0",
)
_EXPECTED_ID = "sha256:0d7f0a2d0aefdf9d2c51e135aca90ce9e27a642683cb8ecdb87431bbb30bcaba"
_EXPECTED_SIG = "L0DOrx5ghYakAs6SFy3dedYh1+m4EpirerHbZzrfzUv5RSvMoujcMgwjSmSOXgbGTmmj2r7Ob4Pv0XMttQgxDA=="


def _key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(_SEED)


def test_preimage_excludes_id_and_proof() -> None:
    pre = envelope.build_preimage(**_ARGS)
    assert "id" not in pre and "proof" not in pre
    # envelope-only identity fields live at the top level, never inside object
    assert {"federation_id", "attributedTo", "origin"} <= set(pre)
    assert "federation_id" not in pre["object"]


def test_license_is_inside_the_signed_preimage() -> None:
    """License-in-band (mesh-resilience decision, 2026-06-06): the license rides
    in the SIGNED pre-image, so a relayed/archived object carries a signed,
    DID-attributed license paper trail even detached from its feed. Changing it
    after signing breaks both the content address and the proof."""
    pre = envelope.build_preimage(**_ARGS)
    assert pre["license"] == "sandia-ftgg-nc-os-1.0"
    env = envelope.finalize(pre, _key())
    stripped = {**env, "license": "CC0-1.0"}  # relicense attempt, stale proof
    assert envelope.verify_envelope(stripped, _key().public_key()) is False


@pytest.mark.interop_pending  # pins envelope field set + PROOF_TYPE + license-in-band + int/published serialization (INTEROP_PENDING.md rows 1-4,6)
def test_finalize_matches_pinned_known_answer() -> None:
    env = envelope.finalize(envelope.build_preimage(**_ARGS), _key())
    assert env["id"] == _EXPECTED_ID
    assert env["proof"]["type"] == "ed25519-jcs-2026"
    assert env["proof"]["verificationMethod"] == "did:web:example.org#main-key"
    assert env["proof"]["signature"] == _EXPECTED_SIG


def test_id_is_sha256_of_preimage_jcs() -> None:
    pre = envelope.build_preimage(**_ARGS)
    env = envelope.finalize(pre, _key())
    assert env["id"] == "sha256:" + hashlib.sha256(jcs_bytes(pre)).hexdigest()


def test_verify_round_trip() -> None:
    env = envelope.finalize(envelope.build_preimage(**_ARGS), _key())
    assert envelope.verify_envelope(env, _key().public_key()) is True


def test_verify_rejects_object_tamper_without_resigning() -> None:
    """Tampering the object but keeping the old id+proof breaks the content address."""
    env = envelope.finalize(envelope.build_preimage(**_ARGS), _key())
    tampered = {**env, "object": {**env["object"], "name": "Evil Pantry"}}
    assert envelope.verify_envelope(tampered, _key().public_key()) is False


def test_verify_rejects_forgery_even_with_recomputed_id() -> None:
    """Attacker edits the object AND recomputes a valid content address, but cannot
    re-sign without the private key -> the Ed25519 proof fails."""
    env = envelope.finalize(envelope.build_preimage(**_ARGS), _key())
    forged_pre = {k: v for k, v in env.items() if k not in ("id", "proof")}
    forged_pre["object"] = {**forged_pre["object"], "name": "Evil Pantry"}
    forged = {
        **forged_pre,
        "id": "sha256:" + hashlib.sha256(jcs_bytes(forged_pre)).hexdigest(),
        "proof": env["proof"],  # stale signature over the ORIGINAL bytes
    }
    assert envelope.verify_envelope(forged, _key().public_key()) is False


def test_verify_rejects_wrong_key() -> None:
    env = envelope.finalize(envelope.build_preimage(**_ARGS), _key())
    other = Ed25519PrivateKey.from_private_bytes(bytes([1]) * 32)
    assert envelope.verify_envelope(env, other.public_key()) is False


def test_verify_rejects_malformed_envelope() -> None:
    assert envelope.verify_envelope({"id": "sha256:x"}, _key().public_key()) is False
    assert envelope.verify_envelope({}, _key().public_key()) is False


def test_key_order_independent_id() -> None:
    """JCS makes builder field-emission order irrelevant to the content address."""
    env1 = envelope.finalize(envelope.build_preimage(**_ARGS), _key())
    reordered = dict(reversed(list(envelope.build_preimage(**_ARGS).items())))
    env2 = envelope.finalize(reordered, _key())
    assert env1["id"] == env2["id"]
    assert env1["proof"]["signature"] == env2["proof"]["signature"]


# --- Signature non-malleability (RED-tier Gauntlet finding: CRYPTO #1).
# Python's base64.b64decode is lenient by default — it silently strips
# non-alphabet characters (including embedded garbage) and tolerates surrounding
# whitespace. A signature field is part of the wire form; two distinct byte
# strings that both verify True is a malleability defect. verify_envelope must
# bind the signature to the EXACT 64-byte Ed25519 value.


def test_verify_rejects_whitespace_wrapped_signature() -> None:
    """A signature with surrounding/internal whitespace must NOT verify."""
    env = envelope.finalize(envelope.build_preimage(**_ARGS), _key())
    pub = _key().public_key()
    assert envelope.verify_envelope(env, pub) is True  # baseline
    sig = env["proof"]["signature"]
    for mutated in (f"  {sig}  ", f"\n{sig}\n", sig[:10] + "\n" + sig[10:]):
        env["proof"]["signature"] = mutated
        assert (
            envelope.verify_envelope(env, pub) is False
        ), f"whitespace-wrapped signature verified True: {mutated!r}"


def test_verify_rejects_garbage_injected_signature() -> None:
    """Non-alphabet garbage spliced into the base64 must NOT verify."""
    env = envelope.finalize(envelope.build_preimage(**_ARGS), _key())
    pub = _key().public_key()
    sig = env["proof"]["signature"]
    # Inject characters outside the standard base64 alphabet that the lenient
    # decoder would otherwise silently discard.
    for junk in ("!", "@@@", "\x00", "----"):
        env["proof"]["signature"] = sig[:8] + junk + sig[8:]
        assert (
            envelope.verify_envelope(env, pub) is False
        ), f"garbage-injected signature verified True: {junk!r}"


def test_verify_rejects_non_canonical_base64_signature() -> None:
    """A non-canonical base64 of the SAME 64 bytes (final-quantum padding bits
    flipped) must NOT verify — closes the residual malleability the second
    Gauntlet found (~16 wire strings decoding to one signature)."""
    env = envelope.finalize(envelope.build_preimage(**_ARGS), _key())
    pub = _key().public_key()
    canonical = env["proof"]["signature"]
    sig_bytes = base64.b64decode(canonical, validate=True)
    # 64 bytes -> 88 chars ending "xx=="; canonical[85] holds 2 sig bits + 4 pad.
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    non_canonical = [
        canonical[:85] + c + "=="
        for c in alphabet
        if (canonical[:85] + c + "==") != canonical
        and base64.b64decode(canonical[:85] + c + "==", validate=True) == sig_bytes
    ]
    assert non_canonical, "expected at least one non-canonical encoding to exist"
    for variant in non_canonical:
        env["proof"]["signature"] = variant
        assert (
            envelope.verify_envelope(env, pub) is False
        ), f"non-canonical signature verified True: {variant!r}"
    # The canonical form still verifies.
    env["proof"]["signature"] = canonical
    assert envelope.verify_envelope(env, pub) is True


def test_verify_rejects_wrong_length_signature() -> None:
    """A validly-base64 value that does not decode to exactly 64 bytes is rejected
    before reaching the Ed25519 verifier."""
    env = envelope.finalize(envelope.build_preimage(**_ARGS), _key())
    pub = _key().public_key()
    # 63 bytes and 65 bytes, both clean base64.
    for nbytes in (0, 1, 63, 65, 128):
        env["proof"]["signature"] = base64.b64encode(b"\x00" * nbytes).decode("ascii")
        assert (
            envelope.verify_envelope(env, pub) is False
        ), f"{nbytes}-byte signature verified True"
