#!/usr/bin/env python3
"""Regenerate the HSDS-FX canonical conformance vectors from the reference impl.

The corpus is the published source of truth, but it is GENERATED (not hand-copied)
from ``app.federation`` so it can never silently drift from what the node actually
signs — the failure that invalidated three successive PR-B ``id`` literals (the
license-in-band change). Run with ``--check`` in CI to fail on any uncommitted
drift between the committed corpus and the live reference implementation.

This is a dev/CI tool, not part of the portable suite — it is the ONE place under
``conformance/hsdsfx/`` permitted to import ``app``. It lives in
``conformance/hsdsfx/`` (the PARENT of ``vectors/``); the portability gate scopes
its pure-data check to the ``vectors/`` subdir only, so this file is outside that
scope by directory layout (not by an allowlist). ``--check`` is **closed-world**:
it fails on any ``vectors/*.json`` the generator does not produce, so a
hand-authored manifest cannot slip past the drift gate (the runner globs every
``*.json``). ``_AREAS`` is the full set of emitted areas.

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

from app.federation import di_proof as di_mod
from app.federation import envelope as env_mod

_VECTORS = Path(__file__).resolve().parent / "vectors"
# Vendored upstream conformance suites — the external anchors. Reading expected
# bytes FROM here (never re-authoring them) is what makes an "anchored" area honest.
_VENDOR = Path(__file__).resolve().parents[2] / "tests" / "test_federation" / "vendor"

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


# A SECOND fixed seed, distinct from _SEED, for the "third-party re-sign" reject
# vector: a genuine eddsa-jcs-2022 proof produced by a DIFFERENT key (and a
# did:web:evil.example verificationMethod) that MUST NOT verify under the ORIGIN's
# public key. Deterministic so the corpus stays byte-stable.
_EVIL_SEED = bytes(range(32, 64))
#: The retired ed25519-jcs-2026 signature for the worked envelope (byte-copied from
#: the pre-Slice-W envelope_proof.json git history) — the must_reject "old format"
#: vector proves a verifier rejects the retired proof shape even with a valid old sig.
_RETIRED_SIG_B64 = "L0DOrx5ghYakAs6SFy3dedYh1+m4EpirerHbZzrfzUv5RSvMoujcMgwjSmSOXgbGTmmj2r7Ob4Pv0XMttQgxDA=="


def _gen_proof() -> dict:
    pre = _worked_preimage()
    key = Ed25519PrivateKey.from_private_bytes(_SEED)
    env, _ = env_mod.finalize_with_bytes(dict(pre), key)
    proof = env["proof"]
    pub = _pubkey_hex()

    # (a) bogus cryptosuite — the original (valid) signature under a cryptosuite the
    #     closed allowlist rejects. Catches a verifier that ignores cryptosuite.
    bad_cryptosuite = dict(env)
    bad_cryptosuite["proof"] = {**proof, "cryptosuite": "eddsa-rdfc-2022"}
    # (b) third-party re-sign — a GENUINE eddsa-jcs-2022 proof over the same DI
    #     document made by a DIFFERENT key, claiming did:web:evil.example. Verified
    #     under the ORIGIN pubkey it fails on BOTH the vm-DID binding (evil != actor)
    #     AND the wrong key — the substitution attack the binding defends against.
    evil_key = Ed25519PrivateKey.from_private_bytes(_EVIL_SEED)
    evil_env, _ = env_mod.finalize_with_bytes(dict(pre), evil_key)
    evil_env = dict(evil_env)
    evil_env["proof"] = di_mod.create_proof(
        {k: v for k, v in evil_env.items() if k != "proof"},
        signing_key=evil_key,
        verification_method="did:web:evil.example#main-key",
        proof_purpose="assertionMethod",
        created=pre["published"],
    )
    # (c) wrong proofPurpose — a GENUINE origin-signed proof whose proofPurpose is
    #     'authentication'; the signature is valid, so ONLY the purpose check fires.
    purpose_env = dict(env)
    purpose_env["proof"] = di_mod.create_proof(
        {k: v for k, v in env.items() if k != "proof"},
        signing_key=key,
        verification_method=proof["verificationMethod"],
        proof_purpose="authentication",
        created=pre["published"],
    )
    # (d) proofValue without the "z" multibase prefix — strict decode rejects it.
    no_prefix = dict(env)
    no_prefix["proof"] = {
        **proof,
        "proofValue": proof["proofValue"].removeprefix("z"),
    }
    # (e) the RETIRED ed25519-jcs-2026 proof object (a valid OLD-format base64 sig)
    #     MUST be rejected — the format is gone (closed type/cryptosuite allowlist).
    old_format = dict(env)
    old_format["proof"] = {
        "type": "ed25519-jcs-2026",
        "verificationMethod": proof["verificationMethod"],
        "signature": _RETIRED_SIG_B64,
    }
    return {
        "area": "envelope_proof",
        "spec": "HSDS-FX/§6.2a,§8.1 (vc-di-eddsa eddsa-jcs-2022)",
        "reference_impl": "app/federation/envelope.py:finalize_with_bytes",
        "interop_status": "interop_pending",
        "derives_from": "INTEROP_PENDING.md rows 1-4 (W3C DataIntegrityProof eddsa-jcs-2022: type + cryptosuite + verificationMethod + proofValue over the DI document)",
        "vectors": [
            {
                "id": "env-proof-001",
                "op": "sign_envelope",
                "description": "W3C Data Integrity eddsa-jcs-2022 proof for the worked envelope; the FULL proof object (@context copied from the document, type=DataIntegrityProof, cryptosuite=eddsa-jcs-2022, created=published, verificationMethod, proofPurpose=assertionMethod, proofValue) is pinned byte-for-byte. proofValue is multibase base58btc ('z'-prefixed) over the 64-byte Ed25519 signature on SHA256(JCS(proofConfig)) || SHA256(JCS(document)) (proof config FIRST), the DI document being the envelope minus proof (id included). created defaults to published, so the proof is deterministic (RFC 8032) — any impl with the seed reproduces it.",
                "input": {"seed_hex": _SEED_HEX, "preimage": pre},
                "expected": proof,
                "must_reject": False,
                "interop_pending": True,
                "interop_row": 4,
            },
            {
                "id": "env-proof-bad-cryptosuite-001",
                "op": "verify_envelope",
                "description": "A proof carrying the original (valid) signature but cryptosuite='eddsa-rdfc-2022' MUST be rejected — the type/cryptosuite pair is a CLOSED allowlist {DataIntegrityProof, eddsa-jcs-2022}; an unrecognised cryptosuite is not accepted even with a genuine signature.",
                "input": {"envelope": bad_cryptosuite, "pubkey_hex": pub},
                "must_reject": True,
            },
            {
                "id": "env-proof-third-party-resign-001",
                "op": "verify_envelope",
                "description": "A genuine eddsa-jcs-2022 proof over the SAME DI document, but produced by a DIFFERENT key and claiming verificationMethod did:web:evil.example#main-key, verified under the ORIGIN public key MUST be rejected — it fails BOTH the verificationMethod-to-actor binding (the DID part != envelope.actor) AND the Ed25519 check under the origin key. This is the key-substitution attack the binding closes (review R9).",
                "input": {"envelope": evil_env, "pubkey_hex": pub},
                "must_reject": True,
            },
            {
                "id": "env-proof-wrong-purpose-001",
                "op": "verify_envelope",
                "description": "A genuine origin-signed proof whose proofPurpose='authentication' (not 'assertionMethod') MUST be rejected — an assertion of data provenance requires the assertionMethod purpose; the signature itself is valid so only the purpose check fires.",
                "input": {"envelope": purpose_env, "pubkey_hex": pub},
                "must_reject": True,
            },
            {
                "id": "env-proof-no-multibase-prefix-001",
                "op": "verify_envelope",
                "description": "A proofValue missing the 'z' base58btc multibase prefix MUST be rejected — proofValue is strict-multibase ('z' + base58btc(64-byte sig)); a bare base58 string is not a valid multibase value (vc-di-eddsa §3.3.6).",
                "input": {"envelope": no_prefix, "pubkey_hex": pub},
                "must_reject": True,
            },
            {
                "id": "env-proof-retired-format-001",
                "op": "verify_envelope",
                "description": "The RETIRED ed25519-jcs-2026 proof object (proof.type='ed25519-jcs-2026' with a valid old base64 'signature' field, no cryptosuite/proofValue/proofPurpose) MUST be rejected — the bespoke pre-Slice-W proof format is gone; only the W3C DataIntegrityProof eddsa-jcs-2022 shape is accepted. The signature is a genuine old-format signature, so the rejection is by FORMAT, not a bad signature: the first check to fire is the proofPurpose pin (the retired object carries no proofPurpose), and the closed type/cryptosuite allowlist independently refuses the retired type even were a purpose spliced in.",
                "input": {"envelope": old_format, "pubkey_hex": pub},
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


# --- checkpoint area (Slice 2) --------------------------------------------------
# The C2SP signed-note FORMAT is externally anchored to the Go golang.org/x/mod/
# sumdb/note PeterNeumann KAT (a genuinely different implementation); the HSDS-FX
# CHECKPOINT BODY composition (origin/size/base64(root)/Timestamp) is PPR-canonical
# (interop_pending). The manifest carries both, honestly flagged per vector.

# The Go sumdb/note reference vector — the external anchor for the note wire
# format. Loaded FROM the vendored suite (not re-authored inline) so the "anchored"
# claim is honest and machine-checkable: vendor/c2sp_sumdb_note/ pins the upstream
# source URL + commit + license (constitution III).
_GO_KAT = json.loads(
    (_VENDOR / "c2sp_sumdb_note" / "vectors.json").read_text(encoding="utf-8")
)
_GO_VERIFIER_KEY = _GO_KAT["verifier_key"]
_GO_SIGNER_KEY = _GO_KAT["signer_key"]
_GO_TEXT = _GO_KAT["text"]
_GO_NOTE = _GO_KAT["signed_note"]


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
# checkpoint root. INTEROP_PENDING — the root/proof BYTES here are computed by
# app.federation.merkle over PPR-NATIVE /export leaves (leaf = JCS(envelope minus
# id+proof), NOT the content-address id), so they are self-derived, not vendored.
# The RFC-6962 inclusion ALGORITHM is anchored separately and honestly by the
# `merkle_inclusion` area (vendored transparency-dev bytes) + test_merkle_rfc6962_
# vectors.py. This area certifies the PPR /export ROW COMPOSITION over a fixed tree;
# only a second independent impl (#558/#565) finally settles the leaf definition.


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
                "description": f"INTEROP_PENDING (PPR /export row composition): the inclusion proof for export row sequence {m + 1} verifies against the checkpoint root of the frozen size-{n} tree. leaf_data = JCS(envelope minus id+proof), NOT the content-address — a PPR-native reading. The root/proof BYTES are app.federation.merkle self-derivations over these leaves (the RFC-6962 algorithm itself is anchored in the merkle_inclusion area).",
                "input": {
                    "leaf_data_hex": leaves[m].hex(),
                    "m": m,
                    "n": n,
                    "proof_hex": proof_hex,
                    "root_hex": root_hex,
                },
                "expected": True,
                "must_reject": False,
                "interop_pending": True,
                "interop_row": 8,
            }
        )
    # Negative: a proof from the wrong index must not verify against the root.
    vectors.append(
        {
            "id": "export-incl-wrong-index-001",
            "op": "verify_inclusion",
            "description": "An inclusion proof for index 0 presented at index 1 MUST fail (RFC-6962 soundness over the PPR /export tree).",
            "input": {
                "leaf_data_hex": leaves[1].hex(),
                "m": 1,
                "n": n,
                "proof_hex": [h.hex() for h in merkle.inclusion_proof(leaves, 0)],
                "root_hex": root_hex,
            },
            "must_reject": True,
            "interop_pending": True,
            "interop_row": 8,
        }
    )
    return {
        "area": "export_wire",
        "spec": "HSDS-FX/§6.3",
        "reference_impl": "app/federation/merkle.py:verify_inclusion; app/federation/log.py:read_export",
        "interop_status": "interop_pending",
        "derives_from": "INTEROP_PENDING.md row 8 (the /export row shape + leaf=JCS(envelope minus id+proof)); the RFC-6962 inclusion algorithm is anchored in the merkle_inclusion area",
        "vectors": vectors,
    }


# --- merkle_inclusion area (Slice 3 remediation) --------------------------------
# GENUINELY ANCHORED: the RFC-6962 inclusion proofs are read VERBATIM from the
# vendored transparency-dev suite (independent Go implementation). This is the
# honest external anchor for the verify_inclusion op — and unlike export_wire it
# carries teeth for the load-bearing ROOT-EQUALITY check (a verifier that only
# reconstructs the path but skips comparing to the claimed root fails the
# wrong-root / tampered-proof negatives).


def _flip_hex(h: str) -> str:
    """Change the first nibble of a hex string to a different hex digit (still valid
    hex, same length) — used to corrupt a vendored proof element for a teeth vector."""
    first = "0" if h[0].lower() != "0" else "1"
    return first + h[1:]


def _gen_merkle_inclusion() -> dict:
    suite = json.loads(
        (_VENDOR / "rfc6962_transparency_dev" / "vectors.json").read_text(
            encoding="utf-8"
        )
    )
    proofs = suite["inclusion_proofs"]
    vectors = []
    for k, ip in enumerate(proofs, start=1):
        vectors.append(
            {
                "id": f"merkle-incl-{k:03d}",
                "op": "verify_inclusion",
                "description": (
                    f"ANCHORED (RFC-6962, transparency-dev {ip['source']}): leaf "
                    f"{ip['leaf_index']} of the size-{ip['tree_size']} tree verifies "
                    "against the published root. Proof/root/leaf bytes are vendored "
                    "verbatim — a genuinely external anchor, not self-derived."
                ),
                "input": {
                    "leaf_data_hex": ip["leaf_input_hex"],
                    "m": ip["leaf_index"],
                    "n": ip["tree_size"],
                    "proof_hex": ip["proof_hex"],
                    "root_hex": ip["root_hex"],
                },
                "expected": True,
                "must_reject": False,
                "interop_pending": False,
            }
        )
    good = proofs[0]
    # (a) a valid proof checked against a DIFFERENT root MUST fail — forces the
    #     RFC-6962 root-equality comparison, not just path reconstruction.
    vectors.append(
        {
            "id": "merkle-incl-wrong-root-001",
            "op": "verify_inclusion",
            "description": (
                "A valid vendored proof checked against a DIFFERENT (empty-tree) root "
                "MUST fail — this is the load-bearing root comparison an impl could "
                "otherwise skip while still reconstructing the audit path."
            ),
            "input": {
                "leaf_data_hex": good["leaf_input_hex"],
                "m": good["leaf_index"],
                "n": good["tree_size"],
                "proof_hex": good["proof_hex"],
                "root_hex": suite["empty_root_hex"],
            },
            "must_reject": True,
        }
    )
    # (b) a proof with one hash byte flipped MUST fail — proof integrity.
    tampered = list(good["proof_hex"])
    tampered[0] = _flip_hex(tampered[0])
    vectors.append(
        {
            "id": "merkle-incl-tampered-proof-001",
            "op": "verify_inclusion",
            "description": (
                "A vendored proof with a single flipped nibble in its first hash MUST "
                "fail (proof integrity / collision resistance)."
            ),
            "input": {
                "leaf_data_hex": good["leaf_input_hex"],
                "m": good["leaf_index"],
                "n": good["tree_size"],
                "proof_hex": tampered,
                "root_hex": good["root_hex"],
            },
            "must_reject": True,
        }
    )
    return {
        "area": "merkle_inclusion",
        "spec": "HSDS-FX/§6.2b,§6.3 (RFC-6962 inclusion)",
        "reference_impl": "app/federation/merkle.py:verify_inclusion",
        "interop_status": "anchored",
        "derives_from": "vendor/rfc6962_transparency_dev (inclusion proofs, verbatim)",
        "vectors": vectors,
    }


# --- consistency_proof area (Slice 8) -------------------------------------------
# GENUINELY ANCHORED (mirrors merkle_inclusion): RFC-6962 consistency proofs read
# VERBATIM from the vendored transparency-dev suite. This anchors the "the new log
# head is an APPEND-ONLY extension of the one I last saw" check (§6.2b) — the
# property that makes a rewritten / forked / truncated history PROVABLE, not merely
# alleged. Carries the root-equality teeth (wrong-second-root, tampered-proof).


def _gen_consistency_proof() -> dict:
    suite = json.loads(
        (_VENDOR / "rfc6962_transparency_dev" / "vectors.json").read_text(
            encoding="utf-8"
        )
    )
    proofs = suite["consistency_proofs"]
    vectors = []
    for k, cp in enumerate(proofs, start=1):
        vectors.append(
            {
                "id": f"consistency-{k:03d}",
                "op": "verify_consistency",
                "description": (
                    f"ANCHORED (RFC-6962, transparency-dev {cp['source']}): the "
                    f"size-{cp['second_size']} tree is a proven append-only extension "
                    f"of the size-{cp['first_size']} tree. Proof/root bytes are "
                    "vendored verbatim — a genuinely external anchor."
                ),
                "input": {
                    "first_size": cp["first_size"],
                    "second_size": cp["second_size"],
                    "proof_hex": cp["proof_hex"],
                    "first_root_hex": cp["first_root_hex"],
                    "second_root_hex": cp["second_root_hex"],
                },
                "expected": True,
                "must_reject": False,
                "interop_pending": False,
            }
        )
    good = proofs[0]
    # (a) a valid proof checked against a DIFFERENT second root MUST fail — the
    #     load-bearing equality (a forked/rewritten head reconstructs a different root).
    vectors.append(
        {
            "id": "consistency-wrong-second-root-001",
            "op": "verify_consistency",
            "description": (
                "A valid vendored consistency proof checked against a DIFFERENT "
                "(empty-tree) second root MUST fail — a rewritten/forked head cannot "
                "reconstruct the claimed root."
            ),
            "input": {
                "first_size": good["first_size"],
                "second_size": good["second_size"],
                "proof_hex": good["proof_hex"],
                "first_root_hex": good["first_root_hex"],
                "second_root_hex": suite["empty_root_hex"],
            },
            "must_reject": True,
        }
    )
    # (b) a proof with one hash byte flipped MUST fail — proof integrity.
    tampered = list(good["proof_hex"])
    tampered[0] = _flip_hex(tampered[0])
    vectors.append(
        {
            "id": "consistency-tampered-proof-001",
            "op": "verify_consistency",
            "description": (
                "A vendored consistency proof with a single flipped nibble in its "
                "first hash MUST fail (proof integrity)."
            ),
            "input": {
                "first_size": good["first_size"],
                "second_size": good["second_size"],
                "proof_hex": tampered,
                "first_root_hex": good["first_root_hex"],
                "second_root_hex": good["second_root_hex"],
            },
            "must_reject": True,
        }
    )
    return {
        "area": "consistency_proof",
        "spec": "HSDS-FX/§6.2b (RFC-6962 consistency)",
        "reference_impl": "app/federation/merkle.py:verify_consistency",
        "interop_status": "anchored",
        "derives_from": "vendor/rfc6962_transparency_dev (consistency proofs, verbatim)",
        "vectors": vectors,
    }


# --- federation_id grammar area (Slice 4) ---------------------------------------
# INTEROP_PENDING: the federation_id = <host> ":" <internal-id> composition is a
# PPR-native canonical reading (design §135) with no upstream conformance suite —
# RFC 3986 anchors the percent/case MECHANICS but not the two-field grammar. The
# normalize op is STRING-returning, so a must_reject vector passes only on a raise.

_FEDID_ACCEPT = [
    (
        "fedid-host-lower-001",
        "Example.ORG:abc-123",
        "Host ASCII-lowercased (§135 'host lowercasing' / RFC 3986 §6.2.2.1); all-unreserved internal-id unchanged.",
    ),
    (
        "fedid-host-lower-002",
        "STRASSE.example.org:x",
        "str.lower() (NOT casefold): STRASSE -> strasse, a host distinct from the rejected non-ASCII 'straße' — no peer-shadow collision.",
    ),
    (
        "fedid-trailing-dot-001",
        "example.org.:abc-123",
        "Single trailing FQDN-root dot stripped (§135 'trailing-dot strip' / RFC 4343).",
    ),
    (
        "fedid-worked-001",
        "northjerseyfoodbank.org:abc-123",
        "The §8.1 worked wire example — already canonical (identity).",
    ),
    (
        "fedid-decode-unreserved-001",
        "example.org:abc%2D123",
        "%2D ('-' unreserved) DECODED per RFC 3986 §6.2.2.2 — equals the literal-hyphen form.",
    ),
    (
        "fedid-decode-unreserved-002",
        "example.org:%41BC",
        "%41 ('A' unreserved) decoded; %41BC == ABC (safe collapse of one octet's spellings).",
    ),
    (
        "fedid-reserved-colon-001",
        "example.org:abc%3adef",
        "%3a (':' RESERVED) kept encoded, hex UPPERCASED to %3A (§6.2.2.1) — never decoded to a raw delimiter.",
    ),
    (
        "fedid-reserved-slash-001",
        "example.org:abc%2fdef",
        "%2f ('/' reserved) kept encoded, hex uppercased.",
    ),
    (
        "fedid-pct-utf8-001",
        "example.org:caf%c3%a9",
        "A properly percent-encoded UTF-8 internal-id octet stays encoded, hex uppercased.",
    ),
    (
        "fedid-alabel-host-001",
        "xn--mnchen-3ya.example:loc-1",
        "A pre-encoded xn-- A-label host is an opaque ASCII reg-name (no IDNA decode in v1).",
    ),
    (
        "fedid-uuid-identity-001",
        "example.org:550e8400-e29b-41d4-a716-446655440000",
        "A uuid4 internal-id is pure-unreserved -> identity (backward-compat with every value the repo emits today).",
    ),
]
_FEDID_REJECT = [
    (
        "fedid-no-colon-001",
        "x",
        "No delimiter colon — not a federation_id (§135 requires host ':' internal-id).",
    ),
    (
        "fedid-empty-host-001",
        ":abc-123",
        "Empty <publisher-host> — no authority to scope the id.",
    ),
    (
        "fedid-empty-id-001",
        "example.org:",
        "Empty <internal-id> — identifies no Location (production is 1*(...)).",
    ),
    (
        "fedid-bad-pct-001",
        "example.org:abc%2g3",
        "Malformed percent-escape ('g' is not a hex digit; RFC 3986 §2.1).",
    ),
    (
        "fedid-bad-pct-002",
        "example.org:%4",
        "Truncated percent-escape ('%' needs two HEXDIG).",
    ),
    (
        "fedid-nonascii-host-001",
        "münchen.example:loc-1",
        "Non-ASCII (U-label) host — v1 rejects; publishers pre-encode to xn-- A-labels.",
    ),
    (
        "fedid-pct-host-001",
        "ex%41mple.org:x",
        "Percent-encoding in the HOST — the host is ASCII LDH+dot only, never pct-encoded.",
    ),
    (
        "fedid-raw-colon-001",
        "example.org:loc:666",
        "Raw embedded ':' in the internal-id (must arrive as %3A) — rejected, not silently re-encoded (collision-safe).",
    ),
    (
        "fedid-pasted-did-001",
        "did:web:example.org:abc-123",
        "A full did:web DID pasted as the id: the internal-id carries raw colons -> reject.",
    ),
    (
        "fedid-raw-slash-001",
        "example.org:a/b",
        "Raw reserved '/' in the internal-id (must arrive as %2F).",
    ),
    (
        "fedid-whitespace-001",
        "  example.org:x  ",
        "Surrounding whitespace — not silently trimmed (a trim would let 'x' and ' x' collide).",
    ),
    (
        "fedid-host-dot-only-001",
        ".:abc-123",
        "Host is only a dot — empty after the single trailing-dot strip.",
    ),
    (
        "fedid-host-empty-label-001",
        "a..b.example:x",
        "Empty DNS label between dots (RFC 1035 labels are 1*).",
    ),
]


def _gen_federation_id() -> dict:
    from app.federation.grammar import normalize_federation_id

    vectors = []
    for vid, raw, desc in _FEDID_ACCEPT:
        vectors.append(
            {
                "id": vid,
                "op": "normalize_federation_id",
                "description": desc,
                "input": {"federation_id": raw},
                "expected": normalize_federation_id(raw),
                "must_reject": False,
                "interop_pending": True,
                "interop_row": 7,
            }
        )
    for vid, raw, desc in _FEDID_REJECT:
        try:  # generator self-check — a reject input MUST raise in the ref impl
            normalize_federation_id(raw)
        except ValueError:
            pass
        else:
            raise AssertionError(
                f"reject vector {vid} was accepted by the reference impl"
            )
        vectors.append(
            {
                "id": vid,
                "op": "normalize_federation_id",
                "description": desc,
                "input": {"federation_id": raw},
                "must_reject": True,
                "interop_pending": True,
                "interop_row": 7,
            }
        )
    return {
        "area": "federation_id",
        "spec": "HSDS-FX/§8.x (design §135 grammar)",
        "reference_impl": "app/federation/grammar.py:normalize_federation_id",
        "interop_status": "interop_pending",
        "derives_from": "INTEROP_PENDING.md row 7 (federation_id = <host>:<internal-id>, split-on-first-colon; host ASCII-lower + trailing-dot strip; internal-id RFC 3986 §6.2.2-normalized)",
        "vectors": vectors,
    }


# --- jcs area (Slice 5) ---------------------------------------------------------
# GENUINELY ANCHORED: the RFC 8785 JCS canonicalization vectors are read VERBATIM
# from the vendored cyberphone suite (the spec author's own conformance vectors —
# the one that caught the #555 UTF-16 key-ordering defect). canonicalize is the
# highest-divergence-risk primitive in the whole spec, so anchoring it directly
# (not just transitively via the envelope content-address) is the point of this
# slice. Accept-only KATs (canonicalize is a producer op, like content_address).

_JCS_NAMES = ["arrays", "french", "structures", "unicode", "values", "weird"]


def _gen_jcs() -> dict:
    from app.federation.canonical import jcs_bytes

    suite_dir = _VENDOR / "jcs_rfc8785"
    vectors = []
    for name in _JCS_NAMES:
        inp = json.loads(
            (suite_dir / "input" / f"{name}.json").read_text(encoding="utf-8")
        )
        expected_bytes = (suite_dir / "output" / f"{name}.json").read_bytes()
        # Self-check: the reference impl must reproduce the vendored output verbatim
        # (mirrors test_canonical_official_vectors.py) — drift here is a real defect.
        if jcs_bytes(inp) != expected_bytes:
            raise AssertionError(
                f"jcs reference impl diverges from vendored output: {name}"
            )
        vectors.append(
            {
                "id": f"jcs-{name}-001",
                "op": "canonicalize",
                "description": (
                    f"ANCHORED (RFC 8785, cyberphone '{name}' vector): JCS-canonicalize "
                    "the input to the published byte-exact output (hex). The vendored "
                    "output bytes are the anchor; the impl must reproduce them."
                ),
                "input": {"value": inp},
                "expected": expected_bytes.hex(),
                "must_reject": False,
                "interop_pending": False,
            }
        )
    return {
        "area": "jcs",
        "spec": "HSDS-FX/§6.1 (RFC 8785 JCS canonicalization)",
        "reference_impl": "app/federation/canonical.py:jcs_bytes",
        "interop_status": "anchored",
        "derives_from": "vendor/jcs_rfc8785 (RFC 8785 official cyberphone vectors, verbatim)",
        "vectors": vectors,
    }


# --- activity_verbs area (Slice 6) ----------------------------------------------
# INTEROP_PENDING: the verb wire semantics (Update/Announce/Delete authority +
# Tombstone shape) are a PPR-native reading (no external anchor) — settled only by
# the P2 two-node loop. validate_activity is a boolean verify op (reject vectors pass
# on False/raise). Stateless wire rules ONLY; ingest policy (allow-list, sequence,
# corroboration, merge) is deferred to P2.

_ACT_A = "did:web:a.example"
_ACT_B = "did:web:b.example"
_ACT_OBJ = {"id": "loc-1", "name": "Test Pantry"}


def _act_env(verb, actor, attributed_to, origin, obj, federation_id="a.example:loc-1"):
    return {
        "@context": _CONTEXT,
        "type": verb,
        "actor": actor,
        "attributedTo": attributed_to,
        "origin": origin,
        "federation_id": federation_id,
        "object": obj,
        "published": "2026-06-07T00:00:00Z",
        "sequence": 1,
        "license": "sandia-ftgg-nc-os-1.0",
    }


def _tomb(federation_id="a.example:dead", redirect="a.example:survivor", **extra):
    obj = {"type": "Tombstone", "federation_id": federation_id, "redirectTo": redirect}
    obj.update(extra)
    return obj


_ACT_ACCEPT = [
    (
        "act-update-own-001",
        _act_env("Update", _ACT_A, _ACT_A, _ACT_A, _ACT_OBJ),
        "Update own-authority: actor==attributedTo==origin; non-empty object.",
    ),
    (
        "act-announce-distinct-001",
        _act_env("Announce", _ACT_B, _ACT_A, _ACT_A, _ACT_OBJ),
        "Announce relays a DISTINCT origin: actor=announcer, attributedTo==origin (the corroborated authority), origin!=actor.",
    ),
    (
        "act-delete-survivor-001",
        _act_env("Delete", _ACT_A, _ACT_A, _ACT_A, _tomb()),
        "Delete: object=Tombstone{type,federation_id,redirectTo=<survivor>}; actor==attributedTo==origin.",
    ),
    (
        "act-delete-null-redirect-001",
        _act_env("Delete", _ACT_A, _ACT_A, _ACT_A, _tomb(redirect=None)),
        "Delete with no survivor: redirectTo present and null.",
    ),
    (
        "act-tombstone-extra-key-ignored-001",
        _act_env("Delete", _ACT_A, _ACT_A, _ACT_A, _tomb(reason="duplicate")),
        "§8.4 forward-compat: an UNKNOWN extra key on the Tombstone object is IGNORED (accepted), not rejected.",
    ),
]
_ACT_REJECT = [
    (
        "act-update-actor-ne-attributedto-001",
        _act_env("Update", _ACT_A, _ACT_B, _ACT_A, _ACT_OBJ),
        "Update with actor!=attributedTo (§117 actor==attributedTo for Update/Delete).",
    ),
    (
        "act-update-origin-ne-actor-001",
        _act_env("Update", _ACT_A, _ACT_A, _ACT_B, _ACT_OBJ),
        "Update with origin!=actor — a relayed assertion must use Announce (Update is own-authority).",
    ),
    (
        "act-delete-actor-ne-attributedto-001",
        _act_env("Delete", _ACT_A, _ACT_B, _ACT_A, _tomb()),
        "Delete with actor!=attributedTo (§117).",
    ),
    (
        "act-delete-origin-ne-actor-001",
        _act_env("Delete", _ACT_A, _ACT_A, _ACT_B, _tomb()),
        "Delete with origin!=actor (own-authority).",
    ),
    (
        "act-announce-origin-eq-actor-001",
        _act_env("Announce", _ACT_A, _ACT_A, _ACT_A, _ACT_OBJ),
        "Announce with origin==actor — a peer announcing its own data is an Update, not an Announce.",
    ),
    (
        "act-announce-attributedto-eq-actor-001",
        _act_env("Announce", _ACT_B, _ACT_B, _ACT_A, _ACT_OBJ),
        "Announce with attributedTo==actor!=origin — the data must be attributed to the corroborated origin (§12.1).",
    ),
    (
        "act-announce-missing-origin-001",
        _act_env("Announce", _ACT_B, _ACT_A, "", _ACT_OBJ),
        "Announce with empty origin — MUST carry the original origin (§160/§205).",
    ),
    (
        "act-verb-create-001",
        _act_env("Create", _ACT_A, _ACT_A, _ACT_A, _ACT_OBJ),
        "Unknown verb 'Create' — the verb set is closed at {Update,Announce,Delete}.",
    ),
    (
        "act-verb-flag-001",
        _act_env("Flag", _ACT_A, _ACT_A, _ACT_A, _ACT_OBJ),
        "'Flag' is reserved for a later phase, not a v1 verb.",
    ),
    (
        "act-verb-tombstone-as-verb-001",
        _act_env("Tombstone", _ACT_A, _ACT_A, _ACT_A, _ACT_OBJ),
        "'Tombstone' is an object type, never an envelope verb.",
    ),
    (
        "act-verb-lowercase-001",
        _act_env("update", _ACT_A, _ACT_A, _ACT_A, _ACT_OBJ),
        "Verb strings are case-sensitive: 'update' != 'Update'.",
    ),
    (
        "act-missing-actor-001",
        _act_env("Update", "", _ACT_A, _ACT_A, _ACT_OBJ),
        "Empty actor — actor/attributedTo/origin are required non-empty strings.",
    ),
    (
        "act-empty-fedid-001",
        _act_env("Update", _ACT_A, _ACT_A, _ACT_A, _ACT_OBJ, federation_id=""),
        "Empty top-level federation_id (shallow non-empty check; full grammar is its own area).",
    ),
    (
        "act-update-empty-object-001",
        _act_env("Update", _ACT_A, _ACT_A, _ACT_A, {}),
        "Update with an empty object — the object must be a non-empty dict.",
    ),
    (
        "act-tombstone-bad-type-001",
        _act_env(
            "Delete",
            _ACT_A,
            _ACT_A,
            _ACT_A,
            {"type": "Delete", "federation_id": "a.example:d", "redirectTo": None},
        ),
        "Delete whose object.type != 'Tombstone'.",
    ),
    (
        "act-tombstone-missing-redirect-001",
        _act_env(
            "Delete",
            _ACT_A,
            _ACT_A,
            _ACT_A,
            {"type": "Tombstone", "federation_id": "a.example:d"},
        ),
        "Tombstone missing the required redirectTo key (required even when null).",
    ),
    (
        "act-tombstone-redirect-nonstring-001",
        _act_env(
            "Delete",
            _ACT_A,
            _ACT_A,
            _ACT_A,
            {"type": "Tombstone", "federation_id": "a.example:d", "redirectTo": 123},
        ),
        "Tombstone redirectTo is a non-string, non-null value.",
    ),
    (
        "act-tombstone-empty-fedid-001",
        _act_env(
            "Delete",
            _ACT_A,
            _ACT_A,
            _ACT_A,
            {"type": "Tombstone", "federation_id": "", "redirectTo": None},
        ),
        "Tombstone with an empty federation_id.",
    ),
    (
        "act-announce-whitespace-origin-001",
        _act_env("Announce", _ACT_A, _ACT_A + " ", _ACT_A + " ", _ACT_OBJ),
        "Announce whose origin is its own actor plus a trailing space — a self-corroboration evasion of the byte-exact origin!=actor check; identity tokens are whitespace-free (§11.2).",
    ),
    (
        "act-whitespace-only-actor-001",
        _act_env("Update", " ", " ", " ", _ACT_OBJ),
        "Whitespace-only identity fields — non-empty but not a valid token.",
    ),
    (
        "act-unhashable-type-001",
        _act_env([], _ACT_A, _ACT_A, _ACT_A, _ACT_OBJ),
        "An unhashable (list) 'type' — the validator is total and rejects it, never raises.",
    ),
]


def _gen_activity_verbs() -> dict:
    from app.federation.activities import validate_activity

    vectors = []
    for vid, env, desc in _ACT_ACCEPT:
        if validate_activity(env) is not True:  # generator self-check
            raise AssertionError(
                f"accept vector {vid} not accepted by the reference impl"
            )
        vectors.append(
            {
                "id": vid,
                "op": "validate_activity",
                "description": desc,
                "input": {"envelope": env},
                "expected": True,
                "must_reject": False,
                "interop_pending": True,
                "interop_row": 9,
            }
        )
    for vid, env, desc in _ACT_REJECT:
        if validate_activity(env) is not False:  # generator self-check
            raise AssertionError(
                f"reject vector {vid} was accepted by the reference impl"
            )
        vectors.append(
            {
                "id": vid,
                "op": "validate_activity",
                "description": desc,
                "input": {"envelope": env},
                "must_reject": True,
                "interop_pending": True,
                "interop_row": 9,
            }
        )
    return {
        "area": "activity_verbs",
        "spec": "HSDS-FX/§8.x (verbs §117/§160/§204-206; Tombstone §160)",
        "reference_impl": "app/federation/activities.py:validate_activity",
        "interop_status": "interop_pending",
        "derives_from": "INTEROP_PENDING.md row 9 (Update/Announce/Delete authority relations + Tombstone shape; stateless wire only)",
        "vectors": vectors,
    }


_AREAS = {
    "envelope_content_address.json": _gen_content_address,
    "envelope_proof.json": _gen_proof,
    "envelope_assembly.json": _gen_assembly,
    "checkpoint.json": _gen_checkpoint,
    "export_wire.json": _gen_export_wire,
    "merkle_inclusion.json": _gen_merkle_inclusion,
    "consistency_proof.json": _gen_consistency_proof,
    "federation_id.json": _gen_federation_id,
    "jcs.json": _gen_jcs,
    "activity_verbs.json": _gen_activity_verbs,
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
    # Closed-world guard: the runner globs EVERY vectors/*.json, so an orphan file the
    # generator does not produce would be executed (and could be dishonestly labeled
    # "anchored") while sailing past a per-_AREAS-only drift check. Reconcile the two
    # sets so no hand-authored manifest can enter the corpus.
    on_disk = {p.name for p in _VECTORS.glob("*.json")}
    orphans = sorted(on_disk - set(_AREAS))
    if check:
        drift.extend(f"{f} (orphan — not produced by the generator)" for f in orphans)
        if drift:
            print(
                "HSDS-FX corpus DRIFT — regenerate (python conformance/hsdsfx/generate.py):"
            )
            for f in drift:
                print(f"  - {f}")
            return 1
        print("HSDS-FX corpus matches the reference implementation.")
        return 0
    for f in orphans:
        (_VECTORS / f).unlink()
        print(f"Removed orphan manifest {f} (not produced by the generator)")
    print(f"Wrote {len(_AREAS)} HSDS-FX vector manifests to {_VECTORS}")
    return 0


if __name__ == "__main__":
    sys.exit(main("--check" in sys.argv))
