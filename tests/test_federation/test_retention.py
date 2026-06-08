"""Archive tiering + retention prune (P1 PR-D, Tasks 9-10) — the RED-tier core.

The verifiable log recomputes every checkpoint root and every inclusion/consistency
proof on demand from ``leaf_data()`` — the FULL ``preimage_canonical`` bytes for
sequences ``1..N`` (there is no persisted Merkle frontier). So a naive DELETE of
low-sequence rows would IMMEDIATELY break ``signed_checkpoint`` and every proof
spanning the trimmed range (``leaf_data`` raises unless it finds exactly
``tree_size`` contiguous rows). "Never destroy tree state" (design §6.2g) is
therefore satisfiable only by **archive-then-trim with leaf read-back**: the prune
writes each trimmed leaf's exact signed bytes to the archive tier BEFORE removing
it from the live Postgres window, and ``leaf_data`` transparently sources
below-floor leaves back from the archive — so root@N and proofs across the trim
boundary stay valid forever, while ``/export`` applies a 410 policy below the floor.

These tests pin that contract (DB-backed; all data fictional):
  * prune archives then trims; ``retention_horizon_sequence`` = MIN(survivors);
  * the checkpoint root@N is IDENTICAL before and after the trim (tree retained);
  * inclusion proofs for a TRIMMED leaf and a SURVIVING leaf both verify;
  * a consistency proof SPANNING the trim boundary verifies;
  * write-ahead: an archive-put failure leaves the live row intact (no loss/wedge);
  * the kill switch makes prune a no-op.
"""

from __future__ import annotations

import os

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.federation import log, merkle
from app.federation.retention import (
    ArchiveBackend,
    LocalFsArchiveBackend,
    prune_to_horizon,
)

_SEED = bytes(range(32))
_DID = "did:web:node.example"
_CONTEXT = "https://hsds-federation.pantrypirateradio.org/profile"
_LICENSE = "sandia-ftgg-nc-os-1.0"

# published_at stamps: sequences 1..3 are "old" (beyond a 30-day SLA from _NOW),
# 4..5 are recent. The prune cutoff = _NOW - 30d trims the 1..3 prefix.
_OLD = "2026-01-01T00:00:00Z"
_RECENT = "2026-06-06T00:00:00Z"
_NOW = "2026-06-08T00:00:00Z"


def _key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(_SEED)


@pytest.fixture()
def db_session(monkeypatch, tmp_path):
    from app.core.config import settings as live

    monkeypatch.setattr(live, "FEDERATION_ENABLED", True)
    # Point the log's archive read-back at a temp local-fs tier so leaf_data can
    # source below-floor leaves after a trim (the dev realization of §6.2g).
    monkeypatch.setattr(live, "FEDERATION_ARCHIVE_PATH", str(tmp_path), raising=False)
    url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    engine = create_engine(url)
    session = sessionmaker(bind=engine)()
    session.execute(text("TRUNCATE federation_log"))
    session.commit()
    yield session
    session.rollback()
    session.execute(text("TRUNCATE federation_log"))
    session.commit()
    session.close()
    engine.dispose()


def _append(session, i: int, published: str) -> int:
    return log.append(
        session,
        activity_type="Update",
        federation_id=f"node.example:loc-{i}",
        obj={"id": f"loc-{i}", "name": f"Pantry {i}"},
        origin_did=_DID,
        signing_key=_key(),
        context=_CONTEXT,
        license=_LICENSE,
        published=published,
    )


def _seed_five(session) -> None:
    """5 appended activities: 1..3 old (trimmable), 4..5 recent (survivors)."""
    for i in range(1, 4):
        _append(session, i, _OLD)
    for i in range(4, 6):
        _append(session, i, _RECENT)


def _backend(session) -> LocalFsArchiveBackend:
    from app.core.config import settings

    return LocalFsArchiveBackend(settings.FEDERATION_ARCHIVE_PATH)


def test_localfs_backend_roundtrips_preimage_bytes(tmp_path) -> None:
    backend: ArchiveBackend = LocalFsArchiveBackend(str(tmp_path))
    assert backend.has(7) is False
    backend.put(7, b'{"sequence":7}')
    assert backend.has(7) is True
    assert backend.get(7) == b'{"sequence":7}'


def test_prune_archives_then_trims_and_sets_horizon(db_session) -> None:
    _seed_five(db_session)
    result = prune_to_horizon(
        db_session, backend=_backend(db_session), retention_days=30, now=_NOW
    )
    assert result.archived_count == 3
    assert result.retention_horizon_sequence == 4
    # The live window now starts at sequence 4; 1..3 are archived (retrievable).
    assert log.live_window_floor(db_session) == 4
    backend = _backend(db_session)
    for seq in (1, 2, 3):
        assert backend.has(seq)


def test_checkpoint_root_identical_before_and_after_trim(db_session) -> None:
    """Tree state retained: the size-5 Merkle root is byte-identical after the
    prune, so the signed checkpoint over the same prefix is unchanged."""
    _seed_five(db_session)
    root_before = merkle.merkle_root(log.leaf_data(db_session, 5))
    note_before = log.signed_checkpoint(
        db_session, origin_did=_DID, signing_key=_key(), timestamp=_NOW
    )

    prune_to_horizon(
        db_session, backend=_backend(db_session), retention_days=30, now=_NOW
    )

    # leaf_data must transparently read 1..3 back from the archive -> same leaves.
    root_after = merkle.merkle_root(log.leaf_data(db_session, 5))
    note_after = log.signed_checkpoint(
        db_session, origin_did=_DID, signing_key=_key(), timestamp=_NOW
    )
    assert root_after == root_before
    assert note_after == note_before


def test_inclusion_proofs_verify_for_trimmed_and_surviving_leaves(db_session) -> None:
    _seed_five(db_session)
    leaves_before = log.leaf_data(db_session, 5)
    root = merkle.merkle_root(leaves_before)
    prune_to_horizon(
        db_session, backend=_backend(db_session), retention_days=30, now=_NOW
    )
    # A trimmed leaf (seq 2 -> index 1) and a surviving leaf (seq 5 -> index 4).
    for seq in (2, 5):
        proof = log.build_inclusion_proof(db_session, sequence=seq, tree_size=5)
        leaf = log.leaf_data(db_session, 5)[seq - 1]
        assert merkle.verify_inclusion(leaf, seq - 1, 5, proof, root)


def test_consistency_proof_spanning_the_trim_boundary_verifies(db_session) -> None:
    """A consumer holding checkpoint@3 (now BELOW the floor of 4) can still verify
    consistency 3->5 — the append-only guarantee survives the trim."""
    _seed_five(db_session)
    root3 = merkle.merkle_root(log.leaf_data(db_session, 3))
    root5 = merkle.merkle_root(log.leaf_data(db_session, 5))
    prune_to_horizon(
        db_session, backend=_backend(db_session), retention_days=30, now=_NOW
    )
    proof = log.build_consistency_proof(db_session, first_size=3, second_size=5)
    assert merkle.verify_consistency(3, 5, proof, root3, root5)


def test_archive_put_failure_skips_the_delete(db_session) -> None:
    """Write-ahead: if archiving a leaf fails, that leaf's live row is NOT deleted
    (no leaf loss, no wedge) — the floor does not advance past the failure."""
    _seed_five(db_session)

    class _FailOnSeq2:
        def __init__(self, real: ArchiveBackend) -> None:
            self._real = real

        def put(self, sequence: int, preimage: bytes) -> None:
            if sequence == 2:
                raise OSError("simulated archive outage")
            self._real.put(sequence, preimage)

        def get(self, sequence: int) -> bytes:
            return self._real.get(sequence)

        def has(self, sequence: int) -> bool:
            return self._real.has(sequence)

    result = prune_to_horizon(
        db_session,
        backend=_FailOnSeq2(_backend(db_session)),
        retention_days=30,
        now=_NOW,
    )
    # Only seq 1 archived+trimmed before the seq-2 failure halted the contiguous prune.
    assert result.archived_count == 1
    assert log.live_window_floor(db_session) == 2
    # No gap: every live leaf 2..5 is present, and seq 1 is retrievable from archive.
    assert len(log.leaf_data(db_session, 5)) == 5


def test_prune_is_a_noop_when_federation_disabled(db_session, monkeypatch) -> None:
    from app.core.config import settings as live

    # Seed while enabled (append is itself gated), then disable and prune.
    _seed_five(db_session)
    monkeypatch.setattr(live, "FEDERATION_ENABLED", False)
    result = prune_to_horizon(
        db_session, backend=_backend(db_session), retention_days=30, now=_NOW
    )
    assert result.archived_count == 0
    assert log.live_window_floor(db_session) == 1
