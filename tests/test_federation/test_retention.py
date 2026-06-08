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
    # Seed where the entrypoint + router read: settings.DATABASE_URL (test-aware
    # under pytest), so the prune entrypoint's own session hits the seeded DB.
    url = live.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
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


def test_leaf_data_rejects_a_hole_above_the_floor(db_session):
    """Defense-in-depth: a hole IN the live suffix (live rows still present below it —
    live-table corruption, since the prune only trims a prefix) must RAISE, not be
    backfilled from a possibly-stale archive copy (which would yield a wrong,
    silently-accepted root)."""
    _seed_five(db_session)
    # No prune: floor is 1. Punch a hole at sequence 3 (live 1,2 remain below it).
    db_session.execute(text("DELETE FROM federation_log WHERE sequence = 3"))
    db_session.commit()
    with pytest.raises(ValueError, match="hole at sequence 3"):
        log.leaf_data(db_session, 5)


def test_s3_backend_has_reraises_transient_error_but_404_is_absent():
    """S3ArchiveBackend.has must treat ONLY a real 404 as 'absent'; a transient
    error must propagate (retryable), never be mistaken for permanent leaf loss."""
    from botocore.exceptions import ClientError

    from app.federation.retention import S3ArchiveBackend

    backend = S3ArchiveBackend.__new__(S3ArchiveBackend)
    backend._bucket = "b"
    backend._prefix = "p"

    class _FakeS3:
        def __init__(self, code, status):
            self._code, self._status = code, status

        def head_object(self, **_):
            raise ClientError(
                {
                    "Error": {"Code": self._code},
                    "ResponseMetadata": {"HTTPStatusCode": self._status},
                },
                "HeadObject",
            )

    backend._s3 = _FakeS3("404", 404)
    assert backend.has(1) is False
    backend._s3 = _FakeS3("ThrottlingException", 503)
    with pytest.raises(ClientError):
        backend.has(1)


def test_prune_entrypoint_refuses_without_an_archive_backend(db_session, monkeypatch):
    """The bouy/Lambda prune entrypoint REFUSES (exit 1, no trim) when no archive
    tier is configured — trimming without archiving first would destroy tree state."""
    from app.core.config import settings as live
    from app.federation.__main__ import _prune

    monkeypatch.setattr(live, "FEDERATION_ARCHIVE_BACKEND", "file")
    monkeypatch.setattr(live, "FEDERATION_ARCHIVE_PATH", None, raising=False)
    _seed_five(db_session)
    assert _prune() == 1
    assert log.live_window_floor(db_session) == 1  # nothing trimmed


def test_prune_entrypoint_archives_and_trims(db_session, monkeypatch):
    """The entrypoint wires resolve_archive_backend + FEDERATION_RETENTION_DAYS into
    prune_to_horizon end-to-end (the Docker worker path)."""
    from app.core.config import settings as live
    from app.federation.__main__ import _prune

    monkeypatch.setattr(live, "FEDERATION_RETENTION_DAYS", 30)
    _seed_five(db_session)
    assert _prune() == 0
    assert log.live_window_floor(db_session) == 4


def test_prune_now_defaults_to_wall_clock(db_session):
    """now=None uses datetime.now(); with a 30-day SLA the 2026-01-01 leaves are
    over-SLA against the real clock and get archived+trimmed."""
    _seed_five(db_session)
    result = prune_to_horizon(
        db_session, backend=_backend(db_session), retention_days=30
    )
    assert result.archived_count == 3
    assert log.live_window_floor(db_session) == 4


def test_prune_first_put_failure_archives_nothing_and_does_not_delete(db_session):
    """If the FIRST candidate's archive-put fails, `archived` is empty: no DELETE
    runs, the live window is untouched (the `if archived:` empty branch)."""
    _seed_five(db_session)

    class _AlwaysFail:
        def put(self, sequence, preimage):
            raise OSError("archive down")

        def get(self, sequence):  # pragma: no cover - not reached
            raise KeyError(sequence)

        def has(self, sequence):  # pragma: no cover - not reached
            return False

    result = prune_to_horizon(
        db_session, backend=_AlwaysFail(), retention_days=30, now=_NOW
    )
    assert result.archived_count == 0
    assert log.live_window_floor(db_session) == 1  # nothing deleted


def test_main_prune_dispatch_and_no_command(db_session, monkeypatch):
    """`python -m app.federation prune` dispatches to _prune; no subcommand -> help+1."""
    import sys

    from app.federation import __main__ as fed_main

    monkeypatch.setattr(sys, "argv", ["prog", "prune"])
    assert fed_main.main() == 0  # prune ran (db_session has an archive path configured)
    monkeypatch.setattr(sys, "argv", ["prog"])
    assert fed_main.main() == 1  # no command -> print_help, exit 1


def test_prune_lambda_handler_ok_and_raises(db_session, monkeypatch):
    """The EventBridge handler returns ok on success and RAISES on a non-zero exit
    (so the Principle-XIV Errors alarm fires) — same _prune as the bouy worker."""
    from app.core.config import settings as live
    from app.federation.prune_lambda import handler

    monkeypatch.setattr(live, "FEDERATION_RETENTION_DAYS", 30)
    _seed_five(db_session)
    assert handler({}, None) == {"status": "ok"}
    assert log.live_window_floor(db_session) == 4

    # No archive tier -> _prune returns 1 -> handler raises (alarm fires).
    monkeypatch.setattr(live, "FEDERATION_ARCHIVE_PATH", None, raising=False)
    with pytest.raises(RuntimeError, match="federation prune failed"):
        handler({}, None)


def test_s3_backend_put_get_has_roundtrip(monkeypatch):
    """S3ArchiveBackend put/get/has against a faked boto3 client (no AWS)."""
    import boto3

    from app.federation.retention import S3ArchiveBackend

    store: dict[str, bytes] = {}

    class _Body:
        def __init__(self, b: bytes) -> None:
            self._b = b

        def read(self) -> bytes:
            return self._b

    class _FakeS3:
        def put_object(self, Bucket, Key, Body):
            store[Key] = Body

        def get_object(self, Bucket, Key):
            return {"Body": _Body(store[Key])}

        def head_object(self, Bucket, Key):
            if Key not in store:
                from botocore.exceptions import ClientError

                raise ClientError({"Error": {"Code": "404"}}, "HeadObject")

    monkeypatch.setattr(boto3, "client", lambda service: _FakeS3())
    backend = S3ArchiveBackend("bucket", "pref")
    assert backend.has(9) is False
    backend.put(9, b"signed-leaf-9")
    assert backend.has(9) is True
    assert backend.get(9) == b"signed-leaf-9"


def test_resolve_archive_backend_selects_s3_or_none(monkeypatch):
    import boto3

    from app.core.config import settings as live
    from app.federation import retention
    from app.federation.retention import S3ArchiveBackend

    monkeypatch.setattr(boto3, "client", lambda service: object())
    monkeypatch.setattr(live, "FEDERATION_ARCHIVE_BACKEND", "s3")
    monkeypatch.setattr(
        live, "FEDERATION_ARCHIVE_S3_BUCKET", "my-bucket", raising=False
    )
    assert isinstance(retention.resolve_archive_backend(), S3ArchiveBackend)
    # s3 selected but no bucket -> None (never a half-configured backend).
    monkeypatch.setattr(live, "FEDERATION_ARCHIVE_S3_BUCKET", None, raising=False)
    assert retention.resolve_archive_backend() is None
