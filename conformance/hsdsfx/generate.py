#!/usr/bin/env python3
"""Regenerate the HSDS-FX canonical conformance vectors from the reference impl.

The corpus is the published source of truth, but it is GENERATED (not hand-copied)
from ``app.federation`` so it can never silently drift from what the node actually
signs — the failure that invalidated three successive PR-B ``id`` literals (the
license-in-band change). Run with ``--check`` in CI to fail on any uncommitted
drift between the committed corpus and the live reference implementation.

This is a dev/CI tool, not part of the portable suite — it is the ONE place under
``conformance/hsdsfx/`` permitted to import ``app`` (it is excluded from the
portability gate's corpus glob by being explicitly listed; see the gate). For
Slice 1 it emits the three envelope areas. Later slices extend ``_AREAS``.

Usage:
    python conformance/hsdsfx/generate.py           # write the manifests
    python conformance/hsdsfx/generate.py --check   # exit 1 if any manifest drifted
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from app.federation import envelope as env_mod

_VECTORS = Path(__file__).resolve().parent / "vectors"

# The canonical worked envelope (fixed seed 0x00..0x1f; license-in-band; the live
# wire form the reference impl signs). This is THE pinned interop-pending vector.
_SEED = bytes(range(32))
_SEED_HEX = _SEED.hex()
_CONTEXT = "https://hsds-federation.pantrypirateradio.org/profile"


def _pubkey_hex() -> str:
    pub = Ed25519PrivateKey.from_private_bytes(_SEED).public_key()
    return pub.public_bytes(Encoding.Raw, PublicFormat.Raw).hex()


def _worked_preimage() -> dict:
    """The canonical worked envelope pre-image (fixed seed 0x00..0x1f; license
    in-band; the live wire form the reference impl signs) — THE pinned
    interop-pending vector. Explicit kwargs (not a ``**dict`` spread) so the typed
    ``build_preimage`` signature is honored."""
    return env_mod.build_preimage(
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


def _gen_content_address() -> dict:
    pre = _worked_preimage()
    env_id = env_mod.content_address(pre)
    return {
        "area": "envelope_content_address",
        "spec": "HSDS-FX/§8.1",
        "reference_impl": "app/federation/envelope.py:content_address",
        "interop_status": "interop_pending",
        "derives_from": "INTEROP_PENDING.md rows 1-6 (envelope wire shape, pinned by fiat)",
        "vectors": [
            {
                "id": "env-id-001",
                "op": "content_address",
                "description": "Canonical worked envelope (license-in-band, fixed seed 0x00..0x1f): content address = 'sha256:'+hex(sha256(JCS(preimage))).",
                "input": {"preimage": pre},
                "expected": env_id,
                "must_reject": False,
                "interop_pending": True,
                "interop_row": 3,
            }
        ],
    }


def _gen_proof() -> dict:
    pre = _worked_preimage()
    key = Ed25519PrivateKey.from_private_bytes(_SEED)
    env, _ = env_mod.finalize_with_bytes(dict(pre), key)
    sig = env["proof"]["signature"]
    raw = base64.b64decode(sig, validate=True)
    return {
        "area": "envelope_proof",
        "spec": "HSDS-FX/§6.2a,§8.1",
        "reference_impl": "app/federation/envelope.py:finalize_with_bytes",
        "interop_status": "interop_pending",
        "derives_from": "INTEROP_PENDING.md rows 1-4 (proof.type + signature over JCS bytes)",
        "vectors": [
            {
                "id": "env-proof-001",
                "op": "sign_envelope",
                "description": "Ed25519-over-JCS proof for the worked envelope; signature is canonical base64-std over the same bytes the content address commits to. Deterministic (RFC 8032) — any impl with the seed reproduces it.",
                "input": {"seed_hex": _SEED_HEX, "preimage": pre},
                "expected": {"type": "ed25519-jcs-2026", "signature": sig},
                "must_reject": False,
                "interop_pending": True,
                "interop_row": 4,
            },
            {
                "id": "env-proof-noncanonical-b64-001",
                "op": "verify_envelope",
                "description": "Non-canonical base64 of the SAME 64 signature bytes (final-quantum padding bits flipped) MUST be rejected by verify (signature non-malleability, envelope.py:153-166).",
                "input": {
                    "envelope": _verify_envelope_with_sig(
                        pre, key, _noncanonical_b64(raw)
                    ),
                    "pubkey_hex": _pubkey_hex(),
                },
                "must_reject": True,
            },
        ],
    }


def _gen_assembly() -> dict:
    pre = _worked_preimage()
    key = Ed25519PrivateKey.from_private_bytes(_SEED)
    env, _ = env_mod.finalize_with_bytes(dict(pre), key)
    pub = _pubkey_hex()
    # A relicensed copy keeping the original (stale) proof must NOT verify
    # (license is inside the signed bytes — §8.1 license-in-band).
    relicensed = dict(env)
    relicensed_obj = dict(pre)
    relicensed_obj["license"] = "CC-BY-4.0"
    relicensed = {**relicensed_obj, "id": env["id"], "proof": env["proof"]}
    # Stripped-license copy keeping the original proof must NOT verify.
    stripped = {k: v for k, v in env.items() if k != "license"}
    return {
        "area": "envelope_assembly",
        "spec": "HSDS-FX/§8.1",
        "reference_impl": "app/federation/envelope.py:verify_envelope",
        "interop_status": "interop_pending",
        "derives_from": "INTEROP_PENDING.md rows 1-6 (10-key field set; license-in-band; placement)",
        "vectors": [
            {
                "id": "env-assembly-verify-001",
                "op": "verify_envelope",
                "description": "The full worked envelope verifies under the origin public key (10-key field set incl. license; federation_id/attributedTo/origin/license at the envelope top level, never inside object).",
                "input": {"envelope": env, "pubkey_hex": pub},
                "expected": True,
                "must_reject": False,
                "interop_pending": True,
                "interop_row": 3,
            },
            {
                "id": "env-assembly-relicense-001",
                "op": "verify_envelope",
                "description": "Relicensed object (CC-BY-4.0) with the original proof MUST fail verify — license is inside the signed pre-image.",
                "input": {"envelope": relicensed, "pubkey_hex": pub},
                "must_reject": True,
            },
            {
                "id": "env-assembly-license-stripped-001",
                "op": "verify_envelope",
                "description": "License key removed with the original proof MUST fail verify — the signed bytes no longer match.",
                "input": {"envelope": stripped, "pubkey_hex": pub},
                "must_reject": True,
            },
        ],
    }


def _noncanonical_b64(raw: bytes) -> str:
    """A non-canonical base64 of the EXACT 64 bytes (flip the final-quantum pad bits).
    64 bytes -> 88 chars ending 'xx=='; char[85] carries 2 significant + 4 pad bits,
    so several distinct strings decode to the same bytes — the malleability the
    verifier must reject."""
    canonical = base64.b64encode(raw).decode("ascii")
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    for c in alphabet:
        variant = canonical[:85] + c + "=="
        if variant != canonical and base64.b64decode(variant, validate=True) == raw:
            return variant
    raise RuntimeError("no non-canonical base64 variant found")


def _verify_envelope_with_sig(pre: dict, key: Ed25519PrivateKey, sig_b64: str) -> dict:
    env, _ = env_mod.finalize_with_bytes(dict(pre), key)
    env = dict(env)
    env["proof"] = {**env["proof"], "signature": sig_b64}
    return env


# --- checkpoint area (Slice 2) --------------------------------------------------
# The C2SP signed-note FORMAT is externally anchored to the Go golang.org/x/mod/
# sumdb/note PeterNeumann KAT (a genuinely different implementation); the HSDS-FX
# CHECKPOINT BODY composition (origin/size/base64(root)/Timestamp) is PPR-canonical
# (interop_pending). The manifest carries both, honestly flagged per vector.

# The Go sumdb/note reference vector (verbatim from test_checkpoint.py / the Go
# source) — the external anchor for the note wire format.
_GO_VERIFIER_KEY = "PeterNeumann+c74f20a3+ARpc2QcUPDhMQegwxbzhKqiBfsVkmqq/LDE4izWy10TW"
_GO_SIGNER_KEY = (
    "PRIVATE+KEY+PeterNeumann+c74f20a3+AYEKFALVFGyNhPJEMzD1QIDr+Y7hfZx09iUvxdXHKDFz"
)
_GO_TEXT = (
    "If you think cryptography is the answer to your problem,\n"
    "then you don't know what your problem is.\n"
)
_GO_SIG_BLOB = "x08go/ZJkuBS9UG/SffcvIAQxVBtiFupLLr8pAcElZInNIuGUgYN1FFYC2pZSNXgKvqfqdngotpRZb6KE6RyyBwJnAM="
_GO_NOTE = _GO_TEXT + "\n" + "— PeterNeumann " + _GO_SIG_BLOB + "\n"


def _go_seed_hex() -> str:
    # maxsplit 4 — the base64 portion itself contains an embedded '+'.
    decoded = base64.b64decode(_GO_SIGNER_KEY.split("+", 4)[4])
    assert decoded[0] == 1  # algEd25519
    return decoded[1:].hex()


def _go_pubkey_hex() -> str:
    decoded = base64.b64decode(_GO_VERIFIER_KEY.split("+", 2)[2])
    assert decoded[0] == 1
    return decoded[1:].hex()


_CP_ORIGIN = "did:web:node.example"
_CP_ROOT_HEX = bytes(range(32)).hex()
_CP_TS = "2026-06-06T00:00:00Z"
_CP_SIZE = 4


def _gen_checkpoint() -> dict:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from app.federation import checkpoint as cp

    # Anchored: reproduce the Go sumdb/note PeterNeumann note byte-for-byte.
    go_key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(_go_seed_hex()))
    go_note = cp.sign_note(_GO_TEXT.encode("utf-8"), "PeterNeumann", go_key)
    assert go_note == _GO_NOTE, "Go note KAT drifted"

    # Interop-pending: the HSDS-FX checkpoint body + full signed checkpoint.
    key = Ed25519PrivateKey.from_private_bytes(_SEED)
    body = cp.checkpoint_body(
        _CP_ORIGIN, _CP_SIZE, bytes.fromhex(_CP_ROOT_HEX), _CP_TS
    ).decode("utf-8")
    note = cp.build_checkpoint(
        origin=_CP_ORIGIN,
        tree_size=_CP_SIZE,
        root_hash=bytes.fromhex(_CP_ROOT_HEX),
        timestamp=_CP_TS,
        signing_key=key,
    )
    tampered = note.replace(f"\n{_CP_SIZE}\n", f"\n{_CP_SIZE + 1}\n")  # forge size

    return {
        "area": "checkpoint",
        "spec": "HSDS-FX/§6.2b",
        "reference_impl": "app/federation/checkpoint.py",
        "interop_status": "interop_pending",
        "derives_from": "note format: Go sumdb/note KAT (anchored); body: INTEROP_PENDING.md (PPR checkpoint shape)",
        "vectors": [
            {
                "id": "cp-note-go-kat-001",
                "op": "encode_note",
                "description": "ANCHORED: the C2SP signed-note wire format reproduces the Go golang.org/x/mod/sumdb/note PeterNeumann KAT byte-for-byte (em-dash sig line, keyID4||sig blob, trailing newline).",
                "input": {
                    "seed_hex": _go_seed_hex(),
                    "text": _GO_TEXT,
                    "key_name": "PeterNeumann",
                },
                "expected": go_note,
                "must_reject": False,
                "interop_pending": False,
            },
            {
                "id": "cp-body-001",
                "op": "checkpoint_body",
                "description": "The HSDS-FX checkpoint body composition: origin / tree_size / base64(root) / 'Timestamp: <ts>', each newline-terminated incl. the last (signed).",
                "input": {
                    "origin": _CP_ORIGIN,
                    "tree_size": _CP_SIZE,
                    "root_hex": _CP_ROOT_HEX,
                    "timestamp": _CP_TS,
                },
                "expected": body,
                "must_reject": False,
                "interop_pending": True,
            },
            {
                "id": "cp-encode-001",
                "op": "encode_checkpoint",
                "description": "A full signed checkpoint note over the body, key_name = origin DID.",
                "input": {
                    "seed_hex": _SEED_HEX,
                    "origin": _CP_ORIGIN,
                    "tree_size": _CP_SIZE,
                    "root_hex": _CP_ROOT_HEX,
                    "timestamp": _CP_TS,
                },
                "expected": note,
                "must_reject": False,
                "interop_pending": True,
            },
            {
                "id": "cp-parse-001",
                "op": "parse_checkpoint",
                "description": "Parse a checkpoint note back to (origin, tree_size, root_hex, timestamp).",
                "input": {"note": note},
                "expected": {
                    "origin": _CP_ORIGIN,
                    "tree_size": _CP_SIZE,
                    "root_hex": _CP_ROOT_HEX,
                    "timestamp": _CP_TS,
                },
                "must_reject": False,
                "interop_pending": True,
            },
            {
                "id": "cp-verify-001",
                "op": "verify_note",
                "description": "The genuine checkpoint note verifies under the origin public key + key_name.",
                "input": {
                    "note": note,
                    "pubkey_hex": _pubkey_hex(),
                    "key_name": _CP_ORIGIN,
                },
                "expected": True,
                "must_reject": False,
                "interop_pending": True,
            },
            {
                "id": "cp-verify-tamper-size-001",
                "op": "verify_note",
                "description": "A tree_size-forged note MUST fail verify — size is inside the signed body.",
                "input": {
                    "note": tampered,
                    "pubkey_hex": _pubkey_hex(),
                    "key_name": _CP_ORIGIN,
                },
                "must_reject": True,
            },
        ],
    }


# --- export_wire area (Slice 3) -------------------------------------------------
# A frozen 3-leaf log: each /export row's inclusion proof verifies against the
# checkpoint root. The RFC-6962 proof/root BYTES are ANCHORED (transparency-dev
# vendored suite); the row composition (envelope + inclusion_proof; leaf =
# JCS(envelope minus id+proof), NOT the content-address id) is exercised live in
# Level 2. Here we certify the verify_inclusion op over a fixed tree.


def _frozen_leaves() -> list[bytes]:
    """Three JCS pre-image leaves for a fixed 3-activity log (deterministic)."""
    from app.federation.canonical import jcs_bytes

    leaves = []
    for i in range(3):
        pre = env_mod.build_preimage(
            context=_CONTEXT,
            activity_type="Update",
            actor="did:web:example.org",
            attributed_to="did:web:example.org",
            origin="did:web:example.org",
            federation_id=f"example.org:loc-{i}",
            obj={"id": f"loc-{i}", "name": f"Pantry {i}"},
            sequence=i + 1,
            published="2026-06-05T00:00:00Z",
            license="sandia-ftgg-nc-os-1.0",
        )
        leaves.append(jcs_bytes(pre))
    return leaves


def _gen_export_wire() -> dict:
    from app.federation import merkle

    leaves = _frozen_leaves()
    n = len(leaves)
    root_hex = merkle.merkle_root(leaves).hex()
    vectors = []
    for m in range(n):
        proof_hex = [h.hex() for h in merkle.inclusion_proof(leaves, m)]
        vectors.append(
            {
                "id": f"export-incl-{m + 1:03d}",
                "op": "verify_inclusion",
                "description": f"ANCHORED (RFC-6962): the inclusion proof for export row sequence {m + 1} verifies against the checkpoint root of the frozen size-{n} tree. leaf_data = JCS(envelope minus id+proof), NOT the content-address.",
                "input": {
                    "leaf_data_hex": leaves[m].hex(),
                    "m": m,
                    "n": n,
                    "proof_hex": proof_hex,
                    "root_hex": root_hex,
                },
                "expected": True,
                "must_reject": False,
                "interop_pending": False,
            }
        )
    # Negative: a proof from the wrong index must not verify against the root.
    vectors.append(
        {
            "id": "export-incl-wrong-index-001",
            "op": "verify_inclusion",
            "description": "An inclusion proof for index 0 presented at index 1 MUST fail (RFC-6962 soundness).",
            "input": {
                "leaf_data_hex": leaves[1].hex(),
                "m": 1,
                "n": n,
                "proof_hex": [h.hex() for h in merkle.inclusion_proof(leaves, 0)],
                "root_hex": root_hex,
            },
            "must_reject": True,
        }
    )
    return {
        "area": "export_wire",
        "spec": "HSDS-FX/§6.3",
        "reference_impl": "app/federation/merkle.py:verify_inclusion; app/federation/log.py:read_export",
        "interop_status": "anchored",
        "derives_from": "vendor/rfc6962_transparency_dev (Merkle proof/root bytes)",
        "vectors": vectors,
    }


_AREAS = {
    "envelope_content_address.json": _gen_content_address,
    "envelope_proof.json": _gen_proof,
    "envelope_assembly.json": _gen_assembly,
    "checkpoint.json": _gen_checkpoint,
    "export_wire.json": _gen_export_wire,
}


def _serialize(manifest: dict) -> str:
    return json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def main(check: bool) -> int:
    _VECTORS.mkdir(parents=True, exist_ok=True)
    drift = []
    for filename, gen in _AREAS.items():
        path = _VECTORS / filename
        new = _serialize(gen())
        if check:
            old = path.read_text(encoding="utf-8") if path.exists() else ""
            if old != new:
                drift.append(filename)
        else:
            path.write_text(new, encoding="utf-8")
    if check:
        if drift:
            print(
                "HSDS-FX corpus DRIFT — regenerate (python conformance/hsdsfx/generate.py):"
            )
            for f in drift:
                print(f"  - {f}")
            return 1
        print("HSDS-FX corpus matches the reference implementation.")
        return 0
    print(f"Wrote {len(_AREAS)} HSDS-FX vector manifests to {_VECTORS}")
    return 0


if __name__ == "__main__":
    sys.exit(main("--check" in sys.argv))
