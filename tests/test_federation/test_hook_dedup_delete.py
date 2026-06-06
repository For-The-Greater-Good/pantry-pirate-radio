"""PR-C Task 5: the dedup-script soft-delete -> federation ``Delete`` (Tombstone)
hook with survivor-chain-resolved ``redirectTo`` (§6.2e, §9).

Tests ``publish_location_delete`` (chain resolution + Tombstone shape + kill
switch) and the ``dedupe_near_duplicate_locations.soft_delete_duplicate`` wiring.
DB-backed; all data fictional.
"""

import base64
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.federation.publish import publish_location_delete
from scripts.dedupe_near_duplicate_locations import (
    ensure_audit_table,
    soft_delete_duplicate,
)

_SEED = bytes(range(32))
_DID = "did:web:node.example"
_HOST = "node.example"


@pytest.fixture()
def db_session():
    from app.core.config import settings

    url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    engine = create_engine(url)
    session = sessionmaker(bind=engine)()
    ensure_audit_table(session)
    session.execute(text("TRUNCATE federation_log"))
    session.execute(text("TRUNCATE dedup_run_audit"))
    session.execute(text("TRUNCATE TABLE location CASCADE"))
    session.commit()
    yield session
    session.rollback()
    session.execute(text("TRUNCATE federation_log"))
    session.execute(text("TRUNCATE dedup_run_audit"))
    session.execute(text("TRUNCATE TABLE location CASCADE"))
    session.commit()
    session.close()
    engine.dispose()


@pytest.fixture()
def configured(monkeypatch):
    from app.core.config import settings as live

    monkeypatch.setattr(live, "FEDERATION_ENABLED", True)
    monkeypatch.setattr(live, "FEDERATION_DID", _DID)
    monkeypatch.setattr(live, "FEDERATION_DOMAIN", None)
    monkeypatch.setattr(
        live, "FEDERATION_SIGNING_KEY", base64.b64encode(_SEED).decode("ascii")
    )
    return live


def _insert_location(session, *, is_canonical: bool) -> str:
    loc_id = str(uuid.uuid4())
    session.execute(
        text(
            """
            INSERT INTO location (id, name, latitude, longitude, location_type,
                                  is_canonical, created_at, updated_at)
            VALUES (:id, 'Fictional Pantry', 40.7, -74.0, 'physical',
                    :canon, NOW(), NOW())
            """
        ),
        {"id": loc_id, "canon": is_canonical},
    )
    session.commit()
    return loc_id


def _audit_soft_delete(session, dead: str, survivor: str) -> None:
    session.execute(
        text(
            """
            INSERT INTO dedup_run_audit
                (run_id, cluster_id, survivor_id, duplicate_id, table_name,
                 row_id, action, old_value, new_value)
            VALUES (:run, 'c', :surv, :dead, 'location', :dead, 'soft_delete',
                    '{}'::jsonb, '{}'::jsonb)
            """
        ),
        {"run": str(uuid.uuid4()), "surv": survivor, "dead": dead},
    )
    session.commit()


def _delete_rows(session):
    return session.execute(
        text(
            "SELECT federation_id, object_canonical FROM federation_log"
            " WHERE type = 'Delete' ORDER BY sequence"
        )
    ).all()


def test_soft_delete_emits_delete_with_resolved_redirect(db_session, configured):
    """dead_a -> survivor_b -> survivor_c (terminal canonical). The Delete for
    dead_a must redirectTo c's federation_id (terminal), not b's."""
    dead_a = _insert_location(db_session, is_canonical=False)
    surv_b = _insert_location(db_session, is_canonical=False)
    surv_c = _insert_location(db_session, is_canonical=True)
    _audit_soft_delete(db_session, dead_a, surv_b)
    _audit_soft_delete(db_session, surv_b, surv_c)

    seq = publish_location_delete(
        db_session, dead_location_id=dead_a, survivor_location_id=surv_b
    )
    assert seq is not None
    rows = _delete_rows(db_session)
    assert len(rows) == 1
    obj = rows[0].object_canonical["object"]
    assert obj["type"] == "Tombstone"
    assert obj["federation_id"] == f"{_HOST}:{dead_a}"
    assert obj["redirectTo"] == f"{_HOST}:{surv_c}"  # terminal, not b


def test_redirect_null_when_terminal_not_canonical(db_session, configured):
    """If the survivor chain ends at a non-canonical row, redirectTo is null."""
    dead = _insert_location(db_session, is_canonical=False)
    surv = _insert_location(db_session, is_canonical=False)  # not canonical
    seq = publish_location_delete(
        db_session, dead_location_id=dead, survivor_location_id=surv
    )
    assert seq is not None
    obj = _delete_rows(db_session)[0].object_canonical["object"]
    assert obj["redirectTo"] is None


def test_killswitch_off_no_delete(db_session, configured, monkeypatch):
    from app.core.config import settings as live

    monkeypatch.setattr(live, "FEDERATION_ENABLED", False)
    dead = _insert_location(db_session, is_canonical=False)
    surv = _insert_location(db_session, is_canonical=True)
    assert (
        publish_location_delete(
            db_session, dead_location_id=dead, survivor_location_id=surv
        )
        is None
    )
    assert _delete_rows(db_session) == []


def test_soft_delete_collects_does_not_publish_inline(db_session, configured):
    """Gauntlet CRITICAL regression: soft_delete_duplicate must NOT publish inline
    (an inline append commits the session, folding the dedup run's savepoint and
    aborting the run). It COLLECTS the (dead, survivor) pair; publish_pending_
    deletes replays post-commit. Verified inside a begin_nested() that must
    SURVIVE the call (no folded transaction)."""
    from app.federation.publish import publish_pending_deletes

    survivor = _insert_location(db_session, is_canonical=True)
    dup = _insert_location(db_session, is_canonical=True)
    collected: list = []

    savepoint = db_session.begin_nested()
    rowcount = soft_delete_duplicate(
        db_session,
        dup,
        apply=True,
        run_id=str(uuid.uuid4()),
        cluster_id="cluster-1",
        survivor_id=survivor,
        federation_deletes=collected,
    )
    # The savepoint is still live — no inline append folded the transaction.
    savepoint.commit()

    assert rowcount == 1
    assert collected == [(dup, survivor)]  # collected, not published
    assert _delete_rows(db_session) == []  # nothing appended inline

    # Post-commit replay publishes the Delete with the resolved redirect.
    publish_pending_deletes(db_session, collected)
    rows = _delete_rows(db_session)
    assert len(rows) == 1
    obj = rows[0].object_canonical["object"]
    assert obj["type"] == "Tombstone"
    assert obj["federation_id"] == f"{_HOST}:{dup}"
    assert obj["redirectTo"] == f"{_HOST}:{survivor}"


def test_publish_failure_does_not_poison_caller_session(
    db_session, configured, monkeypatch
):
    """Gauntlet HIGH regression: a failed append must rollback so the caller's
    session stays usable (fail-soft must not leave an aborted transaction)."""
    from app.federation import publish as publish_mod

    dead = _insert_location(db_session, is_canonical=False)
    surv = _insert_location(db_session, is_canonical=True)

    def _boom(*a, **k):
        raise RuntimeError("append exploded")

    monkeypatch.setattr(publish_mod.log, "append", _boom)
    # Must not raise, must return None.
    assert (
        publish_location_delete(
            db_session, dead_location_id=dead, survivor_location_id=surv
        )
        is None
    )
    # The session is NOT poisoned — a subsequent query works.
    assert db_session.execute(text("SELECT 1")).scalar() == 1


def test_publish_location_delete_fail_soft_on_poisoned_session(db_session, configured):
    """Gauntlet round-2 MEDIUM regression: the is_canonical gate is inside the
    try/except, so a poisoned (aborted-transaction) session yields None — never a
    raise — honoring the documented 'Never raises' contract."""
    import contextlib

    dead = _insert_location(db_session, is_canonical=False)
    surv = _insert_location(db_session, is_canonical=True)
    with contextlib.suppress(Exception):  # poison: failing stmt, not rolled back
        db_session.execute(text("SELECT * FROM no_such_table_zzz"))
    assert (
        publish_location_delete(
            db_session, dead_location_id=dead, survivor_location_id=surv
        )
        is None
    )
    assert db_session.execute(text("SELECT 1")).scalar() == 1  # session recovered


def test_publish_pending_deletes_fail_soft_on_chain_error(
    db_session, configured, monkeypatch
):
    """Gauntlet round-2 MEDIUM regression: a failure loading the survivor chain
    must NOT crash the (already-committed) dedup run — publish_pending_deletes
    swallows it (honors 'Never raises')."""
    from app.federation import publish as publish_mod

    def _boom(*a, **k):
        raise RuntimeError("chain load exploded")

    monkeypatch.setattr(publish_mod, "_load_soft_delete_chain", _boom)
    # Must not raise.
    publish_mod.publish_pending_deletes(db_session, [(str(uuid.uuid4()), None)])
    assert db_session.execute(text("SELECT 1")).scalar() == 1


def test_dedup_script_dry_run_no_delete(db_session, configured):
    """Dry-run (apply=False) never emits a Delete."""
    survivor = _insert_location(db_session, is_canonical=True)
    dup = _insert_location(db_session, is_canonical=True)
    soft_delete_duplicate(
        db_session,
        dup,
        apply=False,
        run_id=str(uuid.uuid4()),
        cluster_id="cluster-1",
        survivor_id=survivor,
    )
    assert _delete_rows(db_session) == []
