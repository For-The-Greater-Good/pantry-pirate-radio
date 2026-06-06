"""Task 2b (PR-B, RED rank-1): dense-sequence append under REAL concurrency.

The P0.5 spike proved (GO) that ``pg_advisory_xact_lock`` scoped to ONLY
``SELECT MAX(sequence)+1 -> INSERT -> COMMIT`` yields gapless, duplicate-free,
skip-free sequences under independent OS processes, without globally serializing
the callers' resource work. These tests re-prove both properties against the
committed implementation (smaller N than the spike for CI friendliness; the
property, not the throughput, is what is asserted).
"""

import multiprocessing
import os
import time

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

_CONTEXT = "https://hsds-federation.pantrypirateradio.org/profile"
_LICENSE = "sandia-ftgg-nc-os-1.0"
_ORIGIN = "did:web:example.org"


def _db_url() -> str:
    return os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")


def _truncate() -> None:
    engine = create_engine(_db_url())
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE federation_log"))
    engine.dispose()


def _worker_append(
    worker_id: int, count: int, resource_sleep: float
) -> tuple[float, float]:
    """Run in a SEPARATE OS process: own engine/connection, append `count` rows.

    ``resource_sleep`` simulates the reconciler's per-resource commit happening
    OUTSIDE the append lock (once per worker, before the appends). Returns the
    (start, end) CLOCK_MONOTONIC timestamps of the resource+append phase —
    system-wide on Linux, so comparable across processes; the caller measures
    the overlapped execution window from these, excluding spawn/import startup.
    """
    from app.federation import log  # re-import under spawn

    engine = create_engine(_db_url())
    maker = sessionmaker(bind=engine)
    session = maker()
    key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    start = time.monotonic()
    if resource_sleep:
        time.sleep(resource_sleep)  # the non-serialized resource step
    for i in range(count):
        seq = log.append(
            session,
            activity_type="Update",
            federation_id=f"example.org:w{worker_id}-{i}",
            obj={"id": f"w{worker_id}-{i}", "name": "Test Pantry"},
            origin_did=_ORIGIN,
            signing_key=key,
            context=_CONTEXT,
            license=_LICENSE,
            published="2026-06-06T00:00:00Z",
        )
        assert seq is not None
    end = time.monotonic()
    session.close()
    engine.dispose()
    return start, end


@pytest.fixture(autouse=True)
def _clean_table():
    _truncate()
    yield
    _truncate()


def test_concurrent_appends_are_gapless_and_duplicate_free() -> None:
    """8 independent OS processes x 25 appends -> sequences exactly 1..200."""
    workers, per_worker = 8, 25
    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(workers) as pool:
        pool.starmap(_worker_append, [(w, per_worker, 0.0) for w in range(workers)])
    engine = create_engine(_db_url())
    with engine.connect() as conn:
        seqs = [
            r[0]
            for r in conn.execute(
                text("SELECT sequence FROM federation_log ORDER BY sequence")
            )
        ]
    engine.dispose()
    total = workers * per_worker
    assert len(seqs) == total
    assert seqs == list(range(1, total + 1))  # dense, gapless, no duplicates


def test_resource_work_is_not_globally_serialized() -> None:
    """8 workers each doing a 0.2s resource step + 1 append overlap: the span
    max(end)-min(start) is roughly one step, not 8 x 0.2s — only the tiny
    append serializes. Measured from worker-reported CLOCK_MONOTONIC stamps so
    spawn/import startup cost is excluded."""
    workers = 8
    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(workers) as pool:
        spans = pool.starmap(_worker_append, [(w, 1, 0.2) for w in range(workers)])
    window = max(end for _, end in spans) - min(start for start, _ in spans)
    serialized_lower_bound = workers * 0.2  # 1.6s if resource steps serialized
    assert window < serialized_lower_bound * 0.75, (
        f"overlap window {window:.2f}s suggests resource steps are being "
        f"serialized (serialized bound {serialized_lower_bound:.1f}s)"
    )
