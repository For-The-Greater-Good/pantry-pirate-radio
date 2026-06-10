"""Slice W (PR rewrite): the activity envelope on top of W3C eddsa-jcs-2022.

The bespoke ``proof.type="ed25519-jcs-2026"`` (base64 signature over the preimage
bytes) is replaced by the W3C Data Integrity ``eddsa-jcs-2022`` cryptosuite
(``proof.type="DataIntegrityProof"``, ``cryptosuite="eddsa-jcs-2022"``,
multibase-base58btc ``proofValue``). The content-address ``id`` is UNCHANGED —
``id = "sha256:"+hex(sha256(jcs_bytes(envelope ∖ {id,proof})))`` — load-bearing
across the Merkle log / proofs / archive (Slice W "proof-independence").

Properties carried over from the old proof: preimage excludes id+proof;
license-in-band rides the SIGNED document; the pinned worked ``id``; verify
round-trip; object-tamper rejection; forgery-with-recomputed-id rejection; wrong
key; malformed envelope; key-order-independent id; determinism. The base64
malleability suite is replaced by proofValue multibase strictness. NEW hardening:
cryptosuite allowlist; verificationMethod↔actor binding (review R9); proofPurpose
pin; @context match; third-party re-sign; created default; I-JSON integer bound.

The DI document scope is the envelope ∖ {proof} (id INCLUDED) so an off-the-shelf
DI verifier strips only ``proof``; the content address is still computed over
envelope ∖ {id,proof}.
"""

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

# The content address is proof-FORMAT-INDEPENDENT, so the worked id from P1 stays
# byte-identical through the proof rewrite (Slice W proof-independence invariant).
_EXPECTED_ID = "sha256:0d7f0a2d0aefdf9d2c51e135aca90ce9e27a642683cb8ecdb87431bbb30bcaba"


def _key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(_SEED)


def _finalize(**overrides):
    pre = envelope.build_preimage(**{**_ARGS, **overrides})
    return envelope.finalize(pre, _key())


# --- preimage / content-address invariants (UNCHANGED across the proof rewrite) -
def test_preimage_excludes_id_and_proof() -> None:
    pre = envelope.build_preimage(**_ARGS)
    assert "id" not in pre and "proof" not in pre
    assert {"federation_id", "attributedTo", "origin"} <= set(pre)
    assert "federation_id" not in pre["object"]


def test_id_is_sha256_of_preimage_jcs() -> None:
    pre = envelope.build_preimage(**_ARGS)
    env = envelope.finalize(pre, _key())
    assert env["id"] == "sha256:" + hashlib.sha256(jcs_bytes(pre)).hexdigest()


def test_content_address_pinned_unchanged_by_proof_rewrite() -> None:
    """Proof-independence: the worked content address is byte-identical to P1 even
    though the proof format changed (the Merkle log / proofs / archive depend on
    this being stable)."""
    env = _finalize()
    assert env["id"] == _EXPECTED_ID


def test_key_order_independent_id() -> None:
    """JCS makes builder field-emission order irrelevant to the content address."""
    env1 = _finalize()
    reordered = dict(reversed(list(envelope.build_preimage(**_ARGS).items())))
    env2 = envelope.finalize(reordered, _key())
    assert env1["id"] == env2["id"]
    assert env1["proof"]["proofValue"] == env2["proof"]["proofValue"]


def test_determinism_identical_envelopes() -> None:
    """RFC 8032 Ed25519 is deterministic and created defaults to published, so two
    finalizations of the same logical envelope are byte-identical."""
    assert _finalize() == _finalize()


# --- proof shape (W3C Data Integrity eddsa-jcs-2022) ----------------------------
def test_proof_has_data_integrity_shape() -> None:
    env = _finalize()
    proof = env["proof"]
    assert set(proof) == {
        "@context",
        "type",
        "cryptosuite",
        "created",
        "verificationMethod",
        "proofPurpose",
        "proofValue",
    }
    assert proof["type"] == "DataIntegrityProof"
    assert proof["cryptosuite"] == "eddsa-jcs-2022"
    assert proof["verificationMethod"] == "did:web:example.org#main-key"
    assert proof["proofPurpose"] == "assertionMethod"
    # The proof copies the document's @context (scalar string here).
    assert proof["@context"] == env["@context"] == _CONTEXT
    assert isinstance(proof["proofValue"], str) and proof["proofValue"].startswith("z")


def test_constants_renamed_to_data_integrity() -> None:
    assert envelope.PROOF_TYPE == "DataIntegrityProof"
    assert envelope.CRYPTOSUITE == "eddsa-jcs-2022"


# --- created handling ------------------------------------------------------------
def test_created_defaults_to_published() -> None:
    """Determinism: with no explicit ``created`` the proof's created defaults to the
    envelope's ``published`` so re-signing reproduces identical bytes."""
    env = _finalize()
    assert env["proof"]["created"] == _ARGS["published"]


def test_explicit_created_is_honored() -> None:
    pre = envelope.build_preimage(**_ARGS)
    env = envelope.finalize(pre, _key(), created="2030-01-01T00:00:00Z")
    assert env["proof"]["created"] == "2030-01-01T00:00:00Z"
    # A different created changes the signed proof config -> a different proofValue.
    assert env["proof"]["proofValue"] != _finalize()["proof"]["proofValue"]


# --- verify round-trip + integrity ----------------------------------------------
def test_verify_round_trip() -> None:
    assert envelope.verify_envelope(_finalize(), _key().public_key()) is True


def test_license_is_inside_the_signed_document() -> None:
    """License-in-band: relicensing after signing breaks both the content address
    and the DI proof."""
    pre = envelope.build_preimage(**_ARGS)
    assert pre["license"] == "sandia-ftgg-nc-os-1.0"
    env = envelope.finalize(pre, _key())
    relicensed = {**env, "license": "CC0-1.0"}
    assert envelope.verify_envelope(relicensed, _key().public_key()) is False


def test_verify_rejects_object_tamper_without_resigning() -> None:
    env = _finalize()
    tampered = {**env, "object": {**env["object"], "name": "Evil Pantry"}}
    assert envelope.verify_envelope(tampered, _key().public_key()) is False


def test_verify_rejects_forgery_even_with_recomputed_id() -> None:
    """Attacker edits the object AND recomputes a valid content address, but cannot
    re-sign without the private key -> the DI proof fails."""
    env = _finalize()
    forged_pre = {k: v for k, v in env.items() if k not in ("id", "proof")}
    forged_pre["object"] = {**forged_pre["object"], "name": "Evil Pantry"}
    forged = {
        **forged_pre,
        "id": "sha256:" + hashlib.sha256(jcs_bytes(forged_pre)).hexdigest(),
        "proof": env["proof"],  # stale signature over the ORIGINAL document
    }
    assert envelope.verify_envelope(forged, _key().public_key()) is False


def test_verify_rejects_wrong_key() -> None:
    env = _finalize()
    other = Ed25519PrivateKey.from_private_bytes(bytes([1]) * 32)
    assert envelope.verify_envelope(env, other.public_key()) is False


def test_verify_rejects_malformed_envelope() -> None:
    assert envelope.verify_envelope({"id": "sha256:x"}, _key().public_key()) is False
    assert envelope.verify_envelope({}, _key().public_key()) is False
    assert envelope.verify_envelope("not-a-dict", _key().public_key()) is False


# --- proofValue multibase strictness (replaces the base64 malleability suite) ---
def test_verify_rejects_non_z_multibase_prefix() -> None:
    """A proofValue that is not base58btc-multibase ('z' prefix) must NOT verify."""
    env = _finalize()
    pub = _key().public_key()
    assert envelope.verify_envelope(env, pub) is True  # baseline
    pv = env["proof"]["proofValue"]
    for bad in (pv[1:], "u" + pv[1:], "x" + pv[1:], pv[1:] + "="):
        env["proof"]["proofValue"] = bad
        assert envelope.verify_envelope(env, pub) is False, bad


def test_verify_rejects_invalid_base58_chars() -> None:
    """base58btc excludes 0, O, I, l (and all non-alphabet bytes): a proofValue with
    such a character must be rejected at decode, not silently coerced."""
    env = _finalize()
    pub = _key().public_key()
    pv = env["proof"]["proofValue"]
    for junk in ("0", "O", "I", "l", "+", "/", " "):
        env["proof"]["proofValue"] = "z" + junk + pv[1:]
        assert envelope.verify_envelope(env, pub) is False, junk


def test_verify_rejects_wrong_decoded_length() -> None:
    """A proofValue decoding to other than exactly 64 bytes (an Ed25519 sig) is
    rejected before the verifier."""
    from app.federation.identity import _b58encode

    env = _finalize()
    pub = _key().public_key()
    for nbytes in (0, 1, 63, 65, 128):
        env["proof"]["proofValue"] = "z" + _b58encode(b"\x00" * nbytes)
        assert envelope.verify_envelope(env, pub) is False, nbytes


# The byte-for-byte old (P1) ed25519-jcs-2026 signature over the worked preimage
# (seed 0x00..1f), copied verbatim from the pre-rewrite envelope_proof.json vector.
# Using the REAL signature (not junk) proves the new verifier rejects on FORMAT, not
# because the signature is malformed — even a cryptographically-valid old proof fails.
_OLD_FORMAT_SIGNATURE = "L0DOrx5ghYakAs6SFy3dedYh1+m4EpirerHbZzrfzUv5RSvMoujcMgwjSmSOXgbGTmmj2r7Ob4Pv0XMttQgxDA=="


def test_verify_rejects_old_format_proof_object() -> None:
    """An envelope carrying the OLD bespoke proof object ({type:'ed25519-jcs-2026',
    verificationMethod, signature}) must NOT verify under the new DI verifier — the
    cryptosuite/type closed allowlist refuses it even with its genuine signature."""
    env = _finalize()
    pub = _key().public_key()
    env["proof"] = {
        "type": "ed25519-jcs-2026",
        "verificationMethod": "did:web:example.org#main-key",
        "signature": _OLD_FORMAT_SIGNATURE,
    }
    assert envelope.verify_envelope(env, pub) is False


# --- cryptosuite allowlist ------------------------------------------------------
def test_verify_rejects_bogus_cryptosuite() -> None:
    """The cryptosuite is a closed allowlist: a different (even real W3C) suite or
    junk must NOT verify, even with an otherwise-valid signature."""
    env = _finalize()
    pub = _key().public_key()
    for suite in ("eddsa-rdfc-2022", "ecdsa-jcs-2019", "junk", ""):
        e = {**env, "proof": {**env["proof"], "cryptosuite": suite}}
        assert envelope.verify_envelope(e, pub) is False, suite


def test_verify_rejects_wrong_proof_type() -> None:
    env = _finalize()
    pub = _key().public_key()
    e = {**env, "proof": {**env["proof"], "type": "Ed25519Signature2020"}}
    assert envelope.verify_envelope(e, pub) is False


# --- verificationMethod ↔ actor binding (review R9) -----------------------------
def test_verify_rejects_vm_did_not_equal_actor() -> None:
    """The verificationMethod's DID part MUST equal the envelope actor. A vm naming a
    different DID is rejected even if its proof is otherwise structurally valid."""
    env = _finalize()
    pub = _key().public_key()
    e = {
        **env,
        "proof": {
            **env["proof"],
            "verificationMethod": "did:web:evil.example#main-key",
        },
    }
    assert envelope.verify_envelope(e, pub) is False


def test_verify_rejects_vm_without_fragment() -> None:
    """verificationMethod must be '<DID>#<fragment>' with a non-empty fragment."""
    env = _finalize()
    pub = _key().public_key()
    for vm in ("did:web:example.org", "did:web:example.org#", "#main-key", "not-a-vm"):
        e = {**env, "proof": {**env["proof"], "verificationMethod": vm}}
        assert envelope.verify_envelope(e, pub) is False, vm


def test_third_party_resign_with_own_did_is_rejected_under_origin_key() -> None:
    """A relay/attacker re-signs the SAME preimage with its OWN key. The vm still
    binds to the ORIGIN's actor (build_preimage left actor = did:web:example.org),
    so the actor↔vm check passes and the SOLE reason verify fails is that the caller
    resolves the key from the ORIGIN — the verifier never trusts a key derived from
    the envelope's vm. Isolating the key-resolution property: do NOT also flip the vm
    (that would let the actor-binding check mask the key mismatch)."""
    pre = envelope.build_preimage(**_ARGS)  # actor = did:web:example.org (the origin)
    attacker = Ed25519PrivateKey.from_private_bytes(bytes([9]) * 32)
    forged = envelope.finalize(pre, attacker)  # structurally valid, attacker-signed
    # vm is still "did:web:example.org#main-key" (passes actor binding) — the proof is
    # internally consistent under the ATTACKER's key but must NOT verify under origin's.
    assert forged["proof"]["verificationMethod"] == "did:web:example.org#main-key"
    assert envelope.verify_envelope(forged, attacker.public_key()) is True  # attacker's
    origin_pub = _key().public_key()  # the ORIGIN's resolved key (caller-supplied)
    assert envelope.verify_envelope(forged, origin_pub) is False


# --- proofPurpose pin -----------------------------------------------------------
def test_verify_rejects_non_assertion_proof_purpose() -> None:
    env = _finalize()
    pub = _key().public_key()
    for purpose in ("authentication", "keyAgreement", ""):
        e = {**env, "proof": {**env["proof"], "proofPurpose": purpose}}
        assert envelope.verify_envelope(e, pub) is False, purpose


# --- @context match -------------------------------------------------------------
def test_verify_rejects_proof_context_mismatch() -> None:
    """If the proof carries an @context it must match the document's (scalar==scalar
    for our envelopes); a mismatched proof @context is rejected."""
    env = _finalize()
    pub = _key().public_key()
    e = {**env, "proof": {**env["proof"], "@context": "https://evil.example/profile"}}
    assert envelope.verify_envelope(e, pub) is False


# --- I-JSON integer bound (RFC 7493 §2.2) ---------------------------------------
def test_finalize_raises_on_oversize_integer() -> None:
    """An int field with |v| > 2^53-1 anywhere in the envelope violates the I-JSON
    interoperable integer range; finalize/build must raise ValueError, not emit a
    silently-divergent (double-based-JCS-incompatible) envelope."""
    with pytest.raises(ValueError):
        envelope.finalize(
            envelope.build_preimage(
                **{**_ARGS, "obj": {"id": "loc-1", "capacity": 2**53}}
            ),
            _key(),
        )


def test_verify_rejects_hand_built_envelope_with_oversize_integer() -> None:
    """A hand-built envelope whose object carries an oversize int is rejected by
    verify_envelope (defense in depth; verify returns False, never raises). Per the
    wire-freeze design: sign a valid envelope, splice the oversized int in, and
    recompute NOTHING — verify must refuse the spliced document. (The id/signature
    are intentionally stale; the I-JSON guard is a hard gate regardless, so a peer
    cannot smuggle a >2^53 int past a double-based-JCS reader.)"""
    pre = envelope.build_preimage(**{**_ARGS, "obj": {"id": "loc-1", "capacity": 5}})
    env = envelope.finalize(pre, _key())
    tampered = {**env, "object": {**env["object"], "capacity": 2**53}}
    assert envelope.verify_envelope(tampered, _key().public_key()) is False


def test_int_at_i_json_boundary_is_accepted() -> None:
    """2^53-1 is the max safe I-JSON integer and must be accepted (round-trips)."""
    pre = envelope.build_preimage(
        **{**_ARGS, "obj": {"id": "loc-1", "capacity": 2**53 - 1}}
    )
    env = envelope.finalize(pre, _key())
    assert envelope.verify_envelope(env, _key().public_key()) is True


# --- ISOLATING mutation-killing tests (Gauntlet M3/M4) --------------------------
# The existing allowlist / vm-binding negatives reject for a SECOND reason too (a
# changed cryptosuite/type alters the proofConfig hash so the signature also fails;
# the third-party-resign vector rejects via wrong-key). These tests forge a proof
# whose Ed25519 signature GENUINELY verifies for the (bad) proofConfig under the
# ORIGIN key, so the allowlist / vm-binding check is the SOLE reason verify fails —
# they survive a mutant that deletes that check unless it is independently load-bearing.


def _sign_over_proof_config(proof_config, di_document, signing_key) -> dict:
    """Sign ``di_document`` under a CALLER-CHOSEN ``proof_config`` (which may carry a
    bad cryptosuite/type/verificationMethod) so the produced proof's signature
    genuinely verifies for THAT config — the only way to isolate a non-signature
    guard. Mirrors ``di_proof.create_proof``'s hash order (config FIRST)."""
    from app.federation.canonical import jcs_bytes
    from app.federation.identity import b58btc_encode

    config_hash = hashlib.sha256(jcs_bytes(proof_config)).digest()
    doc_hash = hashlib.sha256(jcs_bytes(di_document)).digest()
    signature = signing_key.sign(config_hash + doc_hash)
    return {**proof_config, "proofValue": "z" + b58btc_encode(signature)}


def test_allowlist_is_independently_load_bearing_for_cryptosuite() -> None:
    """M3: a proof VALIDLY SIGNED over a proofConfig with cryptosuite='eddsa-rdfc-2022'
    (everything else valid) MUST be rejected SOLELY by the closed allowlist — the
    signature itself verifies for that config, so this kills a mutant deleting the
    cryptosuite check (confirmed: stubbing the allowlist to pass made this verify True).
    """
    env = _finalize()
    di_document = {k: v for k, v in env.items() if k != "proof"}
    proof = env["proof"]
    bad_config = {k: v for k, v in proof.items() if k != "proofValue"}
    bad_config["cryptosuite"] = "eddsa-rdfc-2022"
    forged_proof = _sign_over_proof_config(bad_config, di_document, _key())
    forged = {**di_document, "proof": forged_proof}
    # The signature genuinely verifies for the (bad) config — only the allowlist rejects.
    assert envelope.verify_envelope(forged, _key().public_key()) is False


def test_allowlist_is_independently_load_bearing_for_proof_type() -> None:
    """M3: same isolation for proof.type — a validly-signed proof whose type is
    'Ed25519Signature2020' (not 'DataIntegrityProof') is rejected SOLELY by the
    type allowlist, not by a signature mismatch."""
    env = _finalize()
    di_document = {k: v for k, v in env.items() if k != "proof"}
    proof = env["proof"]
    bad_config = {k: v for k, v in proof.items() if k != "proofValue"}
    bad_config["type"] = "Ed25519Signature2020"
    forged_proof = _sign_over_proof_config(bad_config, di_document, _key())
    forged = {**di_document, "proof": forged_proof}
    assert envelope.verify_envelope(forged, _key().public_key()) is False


def test_vm_binding_is_independently_load_bearing() -> None:
    """M4: the SAME origin key signs a proofConfig whose verificationMethod DID !=
    actor (vm='did:web:other.example#main-key', actor='did:web:example.org'). The
    signature verifies under the origin key, so ONLY _vm_binds_actor rejects — kills
    a mutant deleting the binding (confirmed: stubbing _vm_binds_actor to True made
    this verify True)."""
    env = _finalize()
    assert env["actor"] == "did:web:example.org"
    di_document = {k: v for k, v in env.items() if k != "proof"}
    proof = env["proof"]
    bad_config = {k: v for k, v in proof.items() if k != "proofValue"}
    bad_config["verificationMethod"] = "did:web:other.example#main-key"
    forged_proof = _sign_over_proof_config(bad_config, di_document, _key())
    forged = {**di_document, "proof": forged_proof}
    # Signature verifies under the origin key; only the vm->actor binding rejects.
    assert envelope.verify_envelope(forged, _key().public_key()) is False


# --- _vm_binds_actor empty-actor edge (F7 / INFO) -------------------------------
def test_vm_binds_actor_rejects_empty_actor() -> None:
    """An empty actor paired with a fragment-only vm ('#main-key' -> empty did_part
    == '' == actor) must NOT bind — a real envelope actor is always a non-empty DID."""
    assert envelope._vm_binds_actor("#main-key", "") is False
    assert envelope._vm_binds_actor("did:web:example.org#main-key", "") is False
    # Sanity: a real binding still holds.
    assert (
        envelope._vm_binds_actor("did:web:example.org#main-key", "did:web:example.org")
        is True
    )


# --- RecursionError totality (F6 / L2) ------------------------------------------
def test_verify_envelope_is_total_on_pathologically_deep_nesting() -> None:
    """verify_envelope is documented TOTAL: a dict nested past the recursion limit
    makes _i_json_ok (and jcs_bytes) hit RecursionError; verify must return False,
    never propagate the raise."""
    import sys

    env = _finalize()
    deep: dict = {}
    cursor = deep
    for _ in range(sys.getrecursionlimit() + 100):
        nxt: dict = {}
        cursor["x"] = nxt
        cursor = nxt
    tampered = {**env, "object": deep}
    # Must not raise RecursionError.
    assert envelope.verify_envelope(tampered, _key().public_key()) is False
