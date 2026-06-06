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
                "description": "Ed25519-over-JCS proof for the worked envelope; signature is canonical base64-std over the same bytes the content address commits to. Deterministic (RFC 8032) — any impl with the seed reproduces it.",
                "input": {"seed_hex": _SEED_HEX, "preimage": pre},
                "expected": {"type": "ed25519-jcs-2026", "signature": sig},
                "must_reject": False,
                "interop_pending": True,
                "interop_row": 4,
            },
            {
                "id": "env-proof-noncanonical-b64-001",
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
                "description": "The full worked envelope verifies under the origin public key (10-key field set incl. license; federation_id/attributedTo/origin/license at the envelope top level, never inside object).",
                "input": {"envelope": env, "pubkey_hex": pub},
                "expected": True,
                "must_reject": False,
                "interop_pending": True,
                "interop_row": 3,
            },
            {
                "id": "env-assembly-relicense-001",
                "description": "Relicensed object (CC-BY-4.0) with the original proof MUST fail verify — license is inside the signed pre-image.",
                "input": {"envelope": relicensed, "pubkey_hex": pub},
                "must_reject": True,
            },
            {
                "id": "env-assembly-license-stripped-001",
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


_AREAS = {
    "envelope_content_address.json": _gen_content_address,
    "envelope_proof.json": _gen_proof,
    "envelope_assembly.json": _gen_assembly,
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
