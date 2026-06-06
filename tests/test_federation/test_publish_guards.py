"""Guard / branch coverage for app.federation.publish + the log read helpers.

These exercise the negative/guard paths the RED-tier bar (constitution v1.7.1)
and the per-file 95% federation coverage floor require: every early-return guard,
the fail-soft except branches, and the empty/edge read-path returns. DB-backed;
all data fictional.
"""

import base64
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.federation import log, publish

_SEED = bytes(range(32))
_DID = "did:web:node.example"


@pytest.fixture()
def db_session():
    from app.core.config import settings

    url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    engine = create_engine(url)
    session = sessionmaker(bind=engine)()
    session.execute(text("TRUNCATE federation_log"))
    session.execute(text("TRUNCATE TABLE location CASCADE"))
    session.commit()
    yield session
    session.rollback()
    session.execute(text("TRUNCATE federation_log"))
    session.execute(text("TRUNCATE TABLE location CASCADE"))
    session.commit()
    session.close()
    engine.dispose()


@pytest.fixture()
def enabled(monkeypatch):
    from app.core.config import settings as live

    monkeypatch.setattr(live, "FEDERATION_ENABLED", True)
    monkeypatch.setattr(live, "FEDERATION_DID", _DID)
    monkeypatch.setattr(live, "FEDERATION_DOMAIN", None)
    monkeypatch.setattr(
        live, "FEDERATION_SIGNING_KEY", base64.b64encode(_SEED).decode("ascii")
    )
    return live


def _loc(session, *, is_canonical=True) -> str:
    loc_id = str(uuid.uuid4())
    session.execute(
        text(
            "INSERT INTO location (id, name, latitude, longitude, location_type,"
            " is_canonical, created_at, updated_at) VALUES (:id, 'X', 40.7, -74.0,"
            " 'physical', :c, NOW(), NOW())"
        ),
        {"id": loc_id, "c": is_canonical},
    )
    session.commit()
    return loc_id


# --- _node_host (line 44: FEDERATION_DOMAIN wins) ---------------------------
def test_node_host_uses_federation_domain(monkeypatch):
    from app.core.config import settings as live

    monkeypatch.setattr(live, "FEDERATION_DOMAIN", "override.example")
    monkeypatch.setattr(live, "FEDERATION_DID", _DID)
    assert publish._node_host() == "override.example"


def test_node_host_none_for_non_didweb(monkeypatch):
    from app.core.config import settings as live

    monkeypatch.setattr(live, "FEDERATION_DOMAIN", None)
    monkeypatch.setattr(live, "FEDERATION_DID", "did:key:zABC")  # not did:web
    assert publish._node_host() is None


# --- _append guard branches (69/71/74/78) ----------------------------------
def test_append_returns_none_without_did(db_session, monkeypatch):
    from app.core.config import settings as live

    monkeypatch.setattr(live, "FEDERATION_ENABLED", True)
    monkeypatch.setattr(live, "FEDERATION_DID", None)
    assert (
        publish._append(db_session, activity_type="Update", federation_id="x", obj={})
        is None
    )


def test_append_returns_none_when_host_unresolvable(db_session, monkeypatch):
    from app.core.config import settings as live

    monkeypatch.setattr(live, "FEDERATION_ENABLED", True)
    monkeypatch.setattr(live, "FEDERATION_DID", "did:key:zABC")  # no host
    monkeypatch.setattr(live, "FEDERATION_DOMAIN", None)
    assert (
        publish._append(db_session, activity_type="Update", federation_id="x", obj={})
        is None
    )


def test_append_returns_none_with_no_signing_key(db_session, monkeypatch):
    from app.core.config import settings as live

    monkeypatch.setattr(live, "FEDERATION_ENABLED", True)
    monkeypatch.setattr(live, "FEDERATION_DID", _DID)
    monkeypatch.setattr(live, "FEDERATION_DOMAIN", None)
    monkeypatch.setattr(live, "FEDERATION_SIGNING_KEY", None)
    assert (
        publish._append(db_session, activity_type="Update", federation_id="x", obj={})
        is None
    )


# --- publish_location_update except branch (126-132) -----------------------
def test_update_fail_soft_when_aggregate_raises(db_session, enabled, monkeypatch):
    loc = _loc(db_session)

    def _boom(*a, **k):
        raise RuntimeError("aggregate exploded")

    monkeypatch.setattr(publish, "build_location_aggregate", _boom)
    assert (
        publish.publish_location_update(db_session, loc, source_type="scraper") is None
    )
    assert db_session.execute(text("SELECT 1")).scalar() == 1  # session recovered


# --- _load_soft_delete_chain missing table (148) ---------------------------
def test_load_chain_tolerates_missing_audit_table(db_session):
    sp = db_session.begin_nested()
    try:
        db_session.execute(text("DROP TABLE IF EXISTS dedup_run_audit"))
        assert publish._load_soft_delete_chain(db_session) == {}
    finally:
        sp.rollback()  # restore the table for other tests


# --- _resolve_terminal_survivor terminal=None branch (202) -----------------
def test_delete_null_redirect_when_no_chain_and_no_survivor(db_session, enabled):
    dead = _loc(db_session, is_canonical=False)  # not in any audit chain
    seq = publish.publish_location_delete(
        db_session, dead_location_id=dead, survivor_location_id=None
    )
    assert seq is not None
    rows = db_session.execute(
        text("SELECT object_canonical FROM federation_log WHERE type='Delete'")
    ).all()
    assert rows[0].object_canonical["object"]["redirectTo"] is None


# --- publish_location_delete guards (239 kill switch, 246 no identity) ------
def test_delete_killswitch_off(db_session, enabled, monkeypatch):
    from app.core.config import settings as live

    monkeypatch.setattr(live, "FEDERATION_ENABLED", False)
    dead = _loc(db_session, is_canonical=False)
    assert (
        publish.publish_location_delete(
            db_session, dead_location_id=dead, survivor_location_id=None
        )
        is None
    )


def test_delete_no_identity(db_session, enabled, monkeypatch):
    from app.core.config import settings as live

    monkeypatch.setattr(live, "FEDERATION_DID", None)
    dead = _loc(db_session, is_canonical=False)
    assert (
        publish.publish_location_delete(
            db_session, dead_location_id=dead, survivor_location_id=None
        )
        is None
    )


# --- publish_pending_deletes empty early-return (286) ----------------------
def test_pending_deletes_empty_is_noop(db_session, enabled):
    publish.publish_pending_deletes(db_session, [])  # must not raise / no-op


# --- log read-helper edge returns (log.py 273/275/312) ---------------------
def test_read_export_tree_size_beyond_head_raises(db_session, enabled):
    log.append(
        db_session,
        activity_type="Update",
        federation_id="node.example:a",
        obj={"id": "a"},
        origin_did=_DID,
        signing_key=__import__(
            "cryptography.hazmat.primitives.asymmetric.ed25519",
            fromlist=["Ed25519PrivateKey"],
        ).Ed25519PrivateKey.from_private_bytes(_SEED),
        context="https://hsds-federation.pantrypirateradio.org/profile",
        license="sandia-ftgg-nc-os-1.0",
        published="2026-06-06T00:00:00Z",
    )
    with pytest.raises(ValueError):
        log.read_export(db_session, since=0, limit=10, tree_size=99)


def test_read_export_empty_log(db_session):
    assert log.read_export(db_session, since=0, limit=10) == ([], 0, None)


def test_read_history_empty_log(db_session):
    assert log.read_history(db_session, "node.example:none") == ([], 0)
