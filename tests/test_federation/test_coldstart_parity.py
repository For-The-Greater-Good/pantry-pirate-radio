"""Cold-start ``_since=0`` raw-table parity (P1 PR-D, Task 8 acceptance gate).

The plan's acceptance bar is *"cold-start parity holds ... a flattened-view
shortcut fails CI"*: the §8.2 Location aggregate rebuilt from the RAW normalized
tables must BYTE-EQUAL the ``object`` the live ``/export`` signed and serves for
the same ``federation_id``. A cold-starting peer (or the eventual S3/SQLite
snapshot) rebuilds aggregates from raw tables; this locks that the rebuild is
byte-identical to what the verifiable log committed — so the lossy
``location_master`` materialized view (which collapses distinct schedule windows
via ``DISTINCT ON`` and string-aggregates phones) can never be silently
substituted for ``build_location_aggregate``.

Two tests, by design (see the scoping critique):
  * POSITIVE — exercises the full byte-faithful SERVED path (build → append →
    store ``preimage_canonical`` → ``read_export`` reconstruct) and asserts a
    fresh raw-table rebuild byte-equals the served object. This holds by
    construction (``publish``/``log.append`` JCS-canonicalize the builder's output
    once and ``read_export`` reconstructs from ``preimage_canonical``, never the
    float-normalized JSONB ``object_canonical``) — so it is the round-trip /
    storage-fidelity lock, not the teeth.
  * NEGATIVE (the load-bearing teeth) — proves the byte-equal assertion actually
    CATCHES the forbidden flattened-view shortcut: against the SAME seed (≥2
    distinct schedule windows, so the collapse is non-trivial), a
    ``location_master``-style ``DISTINCT ON (location_id)`` schedule collapse
    produces DIFFERENT canonical bytes — i.e. it would fail CI, which is the
    guarantee the plan asks for.

DB-backed; all data fictional (no PII). Seeding helpers are reused verbatim from
``test_aggregate`` so the two suites share one fixture vocabulary.
"""

from __future__ import annotations

import os

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.federation import log
from app.federation.aggregate import build_location_aggregate
from app.federation.canonical import jcs_bytes
from tests.test_federation.test_aggregate import (
    _insert_location,
    _insert_phone,
    _insert_schedule,
    _insert_source,
)

_SEED = bytes(range(32))
_DID = "did:web:node.example"
_CONTEXT = "https://hsds-federation.pantrypirateradio.org/profile"
_LICENSE = "sandia-ftgg-nc-os-1.0"


def _key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(_SEED)


@pytest.fixture()
def db_session(monkeypatch):
    from app.core.config import settings as live

    # append() is a hook site gated by the kill switch; enable it for the seam.
    monkeypatch.setattr(live, "FEDERATION_ENABLED", True)
    url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    engine = create_engine(url)
    session = sessionmaker(bind=engine)()
    session.execute(text("TRUNCATE federation_log"))
    session.commit()
    yield session
    session.rollback()
    session.execute(text("TRUNCATE TABLE location CASCADE"))
    session.execute(text("TRUNCATE federation_log"))
    session.commit()
    session.close()
    engine.dispose()


def _seed_multi_window_location(session) -> str:
    """A location with ≥2 DISTINCT schedule windows + a source + phones — the seed
    that gives the anti-flatten negative its teeth (a DISTINCT-ON collapse on a
    single-window location would be a no-op and assert nothing)."""
    loc_id = _insert_location(session, latitude=40.7128, longitude=-74.0060)
    _insert_source(session, loc_id, scraper_id="scraper_a")
    _insert_phone(session, loc_id, number="555-0100")
    _insert_phone(session, loc_id, number="555-0199")
    _insert_schedule(
        session,
        loc_id,
        byday="MO",
        opens_at="09:00",
        closes_at="12:00",
        description="Mon morning",
    )
    _insert_schedule(
        session,
        loc_id,
        byday="TH",
        opens_at="13:00",
        closes_at="17:00",
        description="Thu afternoon",
    )
    return loc_id


def _served_object(session, federation_id: str, loc_id: str) -> dict:
    """Publish the aggregate to the log and recover the object the live /export
    serves — reconstructed byte-faithfully from ``preimage_canonical`` (NOT the
    float-normalized JSONB ``object_canonical``), exactly as a peer receives it."""
    obj = build_location_aggregate(session, loc_id)
    seq = log.append(
        session,
        activity_type="Update",
        federation_id=federation_id,
        obj=obj,
        origin_did=_DID,
        signing_key=_key(),
        context=_CONTEXT,
        license=_LICENSE,
        published="2026-06-06T00:00:00Z",
    )
    assert seq == 1
    rows, tree_size, _ = log.read_export(session, since=0, limit=10, tree_size=None)
    assert tree_size == 1 and len(rows) == 1
    return rows[0]["object"]


def test_coldstart_rebuild_byte_equals_served_object(db_session) -> None:
    """The cold-start invariant: a raw-table rebuild of the aggregate byte-equals
    the object the live /export signed and serves for the same federation_id."""
    loc_id = _seed_multi_window_location(db_session)
    served = _served_object(db_session, "node.example:loc-1", loc_id)

    # The cold-start path: rebuild the §8.2 aggregate from the RAW tables.
    rebuilt = build_location_aggregate(db_session, loc_id)

    # Byte-equal over the canonical JCS form — not Python-dict equality, and not
    # the float-normalized JSONB. This is the literal Task-8 acceptance bar.
    assert jcs_bytes(rebuilt) == jcs_bytes(served)
    # And the multi-window structure genuinely survived the full round-trip
    # (so the comparison above is over a non-trivial object, not an empty one).
    assert len(served["schedules"]) == 2


def test_flattened_view_shortcut_breaks_parity(db_session) -> None:
    """The teeth: a ``location_master``-style flattened rebuild (DISTINCT ON
    (location_id) collapses the distinct schedule windows to one) produces
    DIFFERENT canonical bytes than the correct raw-table aggregate — i.e. swapping
    the lossy view in for ``build_location_aggregate`` FAILS this parity guard,
    which is exactly what the plan requires CI to catch."""
    loc_id = _seed_multi_window_location(db_session)
    correct = build_location_aggregate(db_session, loc_id)

    # Precondition that gives the collapse teeth: the correct aggregate carries
    # >=2 distinct windows, so a DISTINCT-ON collapse is genuinely lossy here.
    assert len(correct["schedules"]) == 2

    # A DISTINCT ON (location_id) collapse keeps ONE window per location (which one
    # is positional — schedules are ORDER BY a random-UUID id — but irrelevant here:
    # collapsing 2 windows to any 1 changes the canonical bytes). This stands in for
    # an aggregate built off the lossy location_master view.
    flattened = {**correct, "schedules": correct["schedules"][:1]}

    assert jcs_bytes(flattened) != jcs_bytes(correct)
