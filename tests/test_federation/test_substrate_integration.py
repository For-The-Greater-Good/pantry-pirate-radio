"""End-to-end federation substrate integration test (P1 PR-B, design §6.2a/b).

This is THE peer's-eye-view test. Everything else in ``tests/test_federation/``
cross-checks a module against the same helpers that produced its data; this test
proves the stronger property the whole substrate exists for:

    A remote peer, holding ONLY the wire artifacts — the stored
    ``object_canonical`` envelopes, the two signed-note checkpoint strings, and
    the publisher's Ed25519 public key — can independently re-derive every leaf
    pre-image, verify every object signature, recompute the RFC-6962 root, and
    confirm both *inclusion* (every record is in the tree the checkpoint commits
    to) and *consistency* (checkpoint B's tree is an append-only extension of
    checkpoint A's tree). A forged record cannot be smuggled in undetected.

The "independent verifier" deliberately leans on ONLY the pure crypto in
``app.federation.{envelope,merkle,checkpoint,canonical}`` plus stdlib hashlib —
NEVER ``log.leaf_data`` / ``log.signed_checkpoint`` internals — for the
re-derivation and verification. The two proof *generators*
(``log.build_inclusion_proof`` / ``log.build_consistency_proof``) are the
server-side endpoints a peer would query over the wire, so using their output is
faithful to the real protocol; the proofs are *checked* with the independent
``merkle.verify_*`` primitives against roots the verifier recomputed itself.

DB-backed: drives the real ``federation_log`` table, TRUNCATE-isolated exactly
like ``tests/test_federation/test_log_append.py``. Fictional data only.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.federation import checkpoint, envelope, log, merkle
from app.federation.canonical import jcs_bytes

_CONTEXT = "https://hsds-federation.pantrypirateradio.org/profile"
_LICENSE = "sandia-ftgg-nc-os-1.0"
_ORIGIN = "did:web:pantry.example.org"
_SEED = bytes(range(1, 33))  # fixed, deterministic, fictional Ed25519 seed
_PUBLISHED = "2026-06-06T00:00:00Z"

#: A realistic, fictional mix of activities: several federation_ids, a Delete.
_ACTIVITIES: list[dict[str, Any]] = [
    {
        "type": "Update",
        "fid": "pantry.example.org:loc-1",
        "obj": {"id": "loc-1", "name": "Harbor Light Food Pantry"},
    },
    {
        "type": "Update",
        "fid": "pantry.example.org:loc-2",
        "obj": {"id": "loc-2", "name": "Northside Community Larder"},
    },
    {
        "type": "Update",
        "fid": "pantry.example.org:loc-3",
        "obj": {"id": "loc-3", "name": "Riverbend Meals Program"},
    },
    {
        "type": "Update",
        "fid": "pantry.example.org:loc-4",
        "obj": {"id": "loc-4", "name": "Old Mill Pantry"},
    },
    {
        "type": "Update",
        "fid": "pantry.example.org:loc-5",
        "obj": {"id": "loc-5", "name": "Greenfield Share Shelf"},
    },
    {"type": "Delete", "fid": "pantry.example.org:loc-2", "obj": {"id": "loc-2"}},
    {
        "type": "Update",
        "fid": "pantry.example.org:loc-6",
        "obj": {"id": "loc-6", "name": "Seaside Helping Hands"},
    },
    # ---- batch boundary (checkpoint A) sits after sequence 7 ----
    {
        "type": "Update",
        "fid": "pantry.example.org:loc-7",
        "obj": {"id": "loc-7", "name": "Maple Street Food Bank"},
    },
    {
        "type": "Update",
        "fid": "pantry.example.org:loc-8",
        "obj": {"id": "loc-8", "name": "Lakeview Outreach Kitchen"},
    },
    {"type": "Delete", "fid": "pantry.example.org:loc-4", "obj": {"id": "loc-4"}},
    {
        "type": "Update",
        "fid": "pantry.example.org:loc-1",
        "obj": {"id": "loc-1", "name": "Harbor Light Food Pantry (Annex)"},
    },
    {
        "type": "Update",
        "fid": "pantry.example.org:loc-9",
        "obj": {"id": "loc-9", "name": "Pinewood Mutual Aid"},
    },
]

_BATCH_A = 7  # checkpoint A is taken after these many appends
_TOTAL = len(_ACTIVITIES)  # checkpoint B is taken at the end (12)


def _signing_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(_SEED)


@pytest.fixture()
def db_session():
    url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    engine = create_engine(url)
    maker = sessionmaker(bind=engine)
    session = maker()
    session.execute(text("TRUNCATE federation_log"))
    session.commit()
    yield session
    session.rollback()
    session.execute(text("TRUNCATE federation_log"))
    session.commit()
    session.close()
    engine.dispose()


def _append_activity(session, spec: dict[str, Any]) -> int:
    return log.append(
        session,
        activity_type=spec["type"],
        federation_id=spec["fid"],
        obj=spec["obj"],
        origin_did=_ORIGIN,
        signing_key=_signing_key(),
        context=_CONTEXT,
        license=_LICENSE,
        published=_PUBLISHED,
    )


# --- the independent, peer's-eye verifier ------------------------------------
#
# Uses ONLY wire artifacts (stored envelopes + note strings + public key) and
# the pure crypto primitives. NEVER log.leaf_data / log.signed_checkpoint.


def _read_envelopes(session, upto: int) -> list[dict[str, Any]]:
    """The raw stored ``object_canonical`` envelopes for sequences 1..upto."""
    rows = session.execute(
        text(
            "SELECT sequence, object_canonical FROM federation_log"
            " WHERE sequence <= :n ORDER BY sequence"
        ),
        {"n": upto},
    ).all()
    return [row.object_canonical for row in rows]


def _independent_leaf_preimage_bytes(env: dict[str, Any]) -> bytes:
    """Re-derive the RFC-6962 leaf data the exact way a remote verifier does:
    strip ``id``/``proof`` from the wire envelope and JCS-canonicalize."""
    preimage = {k: v for k, v in env.items() if k not in ("id", "proof")}
    return jcs_bytes(preimage)


def _independent_root(envelopes: list[dict[str, Any]]) -> bytes:
    """Recompute the RFC-6962 root from wire envelopes alone."""
    return merkle.merkle_root(
        [_independent_leaf_preimage_bytes(env) for env in envelopes]
    )


def _verify_object_integrity(env: dict[str, Any], public_key: Ed25519PublicKey) -> None:
    """Every envelope: signature verifies AND content-address id is reproducible
    AND it equals the SHA-256 of the independently-derived pre-image."""
    assert envelope.verify_envelope(env, public_key) is True
    leaf_bytes = _independent_leaf_preimage_bytes(env)
    recomputed_id = "sha256:" + hashlib.sha256(leaf_bytes).hexdigest()
    assert recomputed_id == env["id"]


# --- the test ----------------------------------------------------------------


@pytest.mark.integration
def test_remote_peer_can_independently_verify_the_substrate(db_session) -> None:
    """Append two batches, checkpoint each, then verify the whole chain the way a
    peer holding only wire artifacts would (envelopes + 2 notes + public key)."""
    public_key = _signing_key().public_key()

    # 1. Append batch one, take checkpoint A over the size-7 prefix.
    for spec in _ACTIVITIES[:_BATCH_A]:
        _append_activity(db_session, spec)
    note_a = log.signed_checkpoint(
        db_session,
        origin_did=_ORIGIN,
        signing_key=_signing_key(),
        timestamp=_PUBLISHED,
    )

    # 2. Append batch two, take checkpoint B over the full size-12 prefix.
    for spec in _ACTIVITIES[_BATCH_A:]:
        _append_activity(db_session, spec)
    note_b = log.signed_checkpoint(
        db_session,
        origin_did=_ORIGIN,
        signing_key=_signing_key(),
        timestamp=_PUBLISHED,
    )

    # ===== EVERYTHING BELOW USES ONLY WIRE ARTIFACTS =========================

    # 3. The peer verifies both checkpoint notes (C2SP signed note) and parses
    #    them WITHOUT trusting any server-side state.
    assert checkpoint.verify_note(note_a, public_key, _ORIGIN) is True
    assert checkpoint.verify_note(note_b, public_key, _ORIGIN) is True
    parsed_a = checkpoint.parse_checkpoint(note_a)
    parsed_b = checkpoint.parse_checkpoint(note_b)
    assert parsed_a is not None and parsed_b is not None
    assert parsed_a["origin"] == parsed_b["origin"] == _ORIGIN
    assert parsed_a["tree_size"] == _BATCH_A
    assert parsed_b["tree_size"] == _TOTAL

    # 4. Pull the wire envelopes and verify object integrity for EVERY record.
    envelopes_b = _read_envelopes(db_session, _TOTAL)
    assert len(envelopes_b) == _TOTAL
    for env in envelopes_b:
        _verify_object_integrity(env, public_key)
    # The Delete activities are present in the log (real mix, not all Updates).
    assert sum(1 for e in envelopes_b if e["type"] == "Delete") == 2

    # 5. Independently recompute the RFC-6962 root from wire envelopes alone and
    #    assert it equals the root each checkpoint committed to.
    envelopes_a = _read_envelopes(db_session, _BATCH_A)
    root_a = _independent_root(envelopes_a)
    root_b = _independent_root(envelopes_b)
    assert root_a == parsed_a["root_hash"]
    assert root_b == parsed_b["root_hash"]

    # 6. Inclusion: for EVERY sequence, request the server's audit path and
    #    verify it against the peer-recomputed root_b (NOT a server-claimed one).
    for seq in range(1, _TOTAL + 1):
        proof = log.build_inclusion_proof(db_session, sequence=seq, tree_size=_TOTAL)
        leaf_bytes = _independent_leaf_preimage_bytes(envelopes_b[seq - 1])
        assert merkle.verify_inclusion(
            leaf_bytes, seq - 1, _TOTAL, proof, root_b
        ), f"inclusion failed for sequence {seq}"

    # 7. Consistency: checkpoint B's tree extends checkpoint A's tree, proven
    #    between the two peer-recomputed roots.
    consistency = log.build_consistency_proof(
        db_session, first_size=_BATCH_A, second_size=_TOTAL
    )
    assert (
        merkle.verify_consistency(_BATCH_A, _TOTAL, consistency, root_a, root_b) is True
    )

    # 8. NEGATIVE — a forged record breaks the chain. The peer holds the
    #    wire envelopes; an attacker swaps one out for a forged one (re-signed
    #    with a DIFFERENT key, so verify_envelope catches it AND the recomputed
    #    root diverges from the checkpoint).
    attacker_key = Ed25519PrivateKey.from_private_bytes(bytes(range(33, 65)))
    forged_preimage = envelope.build_preimage(
        context=_CONTEXT,
        activity_type="Update",
        actor=_ORIGIN,
        attributed_to=_ORIGIN,
        origin=_ORIGIN,
        federation_id="pantry.example.org:loc-666",
        obj={"id": "loc-666", "name": "Phantom Pantry (forged)"},
        sequence=3,
        published=_PUBLISHED,
        license=_LICENSE,
    )
    forged_env = envelope.finalize(forged_preimage, attacker_key)
    # 8a. Object integrity rejects the forgery under the real publisher key.
    assert envelope.verify_envelope(forged_env, public_key) is False
    # 8b. Splicing the forgery into the leaf set yields a root that does NOT
    #     match the signed checkpoint B — tampering is provable, not alleged.
    tampered = list(envelopes_b)
    tampered[2] = forged_env  # replace sequence 3
    tampered_root = _independent_root(tampered)
    assert tampered_root != parsed_b["root_hash"]
    # 8c. A consistency proof from A to the tampered tree fails.
    assert (
        merkle.verify_consistency(_BATCH_A, _TOTAL, consistency, root_a, tampered_root)
        is False
    )


@pytest.mark.integration
def test_kill_switch_freezes_the_substrate_mid_stream(db_session, monkeypatch) -> None:
    """§6.2d kill switch interplay with the substrate: once FEDERATION_ENABLED
    flips False mid-stream, appends no-op and the tree/checkpoints taken after
    are byte-identical to the pre-flip head (no silent corruption)."""
    from app.core.config import settings as live_settings

    public_key = _signing_key().public_key()

    # Append a few activities with the switch ON.
    for spec in _ACTIVITIES[:4]:
        seq = _append_activity(db_session, spec)
        assert seq is not None
    note_before = log.signed_checkpoint(
        db_session,
        origin_did=_ORIGIN,
        signing_key=_signing_key(),
        timestamp=_PUBLISHED,
    )
    parsed_before = checkpoint.parse_checkpoint(note_before)
    assert parsed_before is not None
    assert parsed_before["tree_size"] == 4
    root_before = _independent_root(_read_envelopes(db_session, 4))
    assert root_before == parsed_before["root_hash"]

    # Flip the kill switch; subsequent appends must be hard no-ops.
    monkeypatch.setattr(live_settings, "FEDERATION_ENABLED", False)
    for spec in _ACTIVITIES[4:]:
        assert _append_activity(db_session, spec) is None

    # The committed prefix is unchanged: count, head, root, and a checkpoint
    # taken now all match the pre-flip state exactly.
    count = db_session.execute(text("SELECT COUNT(*) FROM federation_log")).scalar_one()
    assert count == 4
    assert log.safe_high_water(db_session) == 4
    note_after = log.signed_checkpoint(
        db_session,
        origin_did=_ORIGIN,
        signing_key=_signing_key(),
        timestamp=_PUBLISHED,
    )
    parsed_after = checkpoint.parse_checkpoint(note_after)
    assert parsed_after is not None
    assert parsed_after["tree_size"] == 4
    assert parsed_after["root_hash"] == parsed_before["root_hash"]
    # The note text is byte-identical (same size, same root, same timestamp).
    assert note_after == note_before
    # And every surviving envelope still verifies under the publisher key.
    for env in _read_envelopes(db_session, 4):
        assert envelope.verify_envelope(env, public_key) is True
