"""Task 2b (PR-B): the federation log append + checkpoint/proof builders (§6.2b).

DB-backed tests against the real ``federation_log`` table (created by
``init-scripts/16-federation-log.sql`` in fresh test DBs and by the migration in
existing DBs). The append's critical section is the spike-proven shape (P0.5
memo, GO): ``pg_advisory_xact_lock(KEY)`` scoped to ONLY
``SELECT COALESCE(MAX(sequence),0)+1 -> INSERT -> COMMIT`` — the resource commit
is never inside the lock. Dense sequence = Merkle leaf index.
"""

import hashlib
import os

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.federation import checkpoint, log, merkle
from app.federation.canonical import jcs_bytes

_CONTEXT = "https://hsds-federation.pantrypirateradio.org/profile"
_LICENSE = "sandia-ftgg-nc-os-1.0"
_ORIGIN = "did:web:example.org"
_SEED = bytes(range(32))


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


def _append(session, n: int = 1, start_loc: int = 0) -> list[int]:
    seqs = []
    for i in range(n):
        seq = log.append(
            session,
            activity_type="Update",
            federation_id=f"example.org:loc-{start_loc + i}",
            obj={"id": f"loc-{start_loc + i}", "name": f"Test Pantry {start_loc + i}"},
            origin_did=_ORIGIN,
            signing_key=_signing_key(),
            context=_CONTEXT,
            license=_LICENSE,
            published="2026-06-06T00:00:00Z",
        )
        seqs.append(seq)
    return seqs


def test_append_assigns_dense_sequences_and_stores_envelope(db_session) -> None:
    seqs = _append(db_session, 3)
    assert seqs == [1, 2, 3]
    rows = db_session.execute(
        text(
            "SELECT sequence, leaf_hash, type, federation_id, object_canonical,"
            " origin_did FROM federation_log ORDER BY sequence"
        )
    ).all()
    assert [r.sequence for r in rows] == [1, 2, 3]
    for row in rows:
        env = row.object_canonical
        # stored envelope's sequence matches the row's
        assert env["sequence"] == row.sequence
        assert env["license"] == _LICENSE
        # content address is exactly re-derivable from the stored envelope
        preimage = {k: v for k, v in env.items() if k not in ("id", "proof")}
        assert (
            "sha256:" + hashlib.sha256(jcs_bytes(preimage)).hexdigest()
            == env["id"]
            == row.leaf_hash
        )


def test_append_envelope_proof_verifies(db_session) -> None:
    from app.federation import envelope as envelope_mod

    _append(db_session, 1)
    env = db_session.execute(
        text("SELECT object_canonical FROM federation_log WHERE sequence = 1")
    ).scalar_one()
    assert envelope_mod.verify_envelope(env, _signing_key().public_key()) is True


def test_kill_switch_appends_nothing(db_session, monkeypatch) -> None:
    """§6.2d: FEDERATION_ENABLED=False makes append a hard no-op before any work."""
    from app.core.config import settings as live_settings

    monkeypatch.setattr(live_settings, "FEDERATION_ENABLED", False)
    seq = log.append(
        db_session,
        activity_type="Update",
        federation_id="example.org:loc-x",
        obj={"id": "loc-x"},
        origin_did=_ORIGIN,
        signing_key=_signing_key(),
        context=_CONTEXT,
        license=_LICENSE,
    )
    assert seq is None
    count = db_session.execute(text("SELECT COUNT(*) FROM federation_log")).scalar_one()
    assert count == 0


def test_safe_high_water(db_session) -> None:
    assert log.safe_high_water(db_session) == 0
    _append(db_session, 5)
    assert log.safe_high_water(db_session) == 5


def test_signed_checkpoint_verifies_and_matches_recomputed_root(db_session) -> None:
    _append(db_session, 4)
    note = log.signed_checkpoint(
        db_session,
        origin_did=_ORIGIN,
        signing_key=_signing_key(),
        timestamp="2026-06-06T00:00:00Z",
    )
    assert checkpoint.verify_note(note, _signing_key().public_key(), _ORIGIN) is True
    parsed = checkpoint.parse_checkpoint(note)
    assert parsed["origin"] == _ORIGIN
    assert parsed["tree_size"] == 4
    # independently recompute the RFC-6962 root over the stored leaf pre-images
    leaves = log.leaf_data(db_session, 4)
    assert parsed["root_hash"] == merkle.merkle_root(leaves)


def test_inclusion_proof_round_trip_from_db(db_session) -> None:
    _append(db_session, 5)
    leaves = log.leaf_data(db_session, 5)
    root = merkle.merkle_root(leaves)
    for seq in range(1, 6):
        proof = log.build_inclusion_proof(db_session, sequence=seq, tree_size=5)
        assert merkle.verify_inclusion(leaves[seq - 1], seq - 1, 5, proof, root)


def test_consistency_proof_round_trip_from_db(db_session) -> None:
    _append(db_session, 3)
    old_root = merkle.merkle_root(log.leaf_data(db_session, 3))
    _append(db_session, 4, start_loc=3)
    new_root = merkle.merkle_root(log.leaf_data(db_session, 7))
    proof = log.build_consistency_proof(db_session, first_size=3, second_size=7)
    assert merkle.verify_consistency(3, 7, proof, old_root, new_root)


def test_append_rejects_unknown_sizes(db_session) -> None:
    _append(db_session, 2)
    with pytest.raises(ValueError):
        log.build_inclusion_proof(db_session, sequence=3, tree_size=2)
    with pytest.raises(ValueError):
        log.build_consistency_proof(db_session, first_size=0, second_size=2)
    with pytest.raises(ValueError):
        log.build_consistency_proof(db_session, first_size=3, second_size=2)
