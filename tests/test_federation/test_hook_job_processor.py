"""PR-C Task 4: the reconciler matched/new-Location commit -> federation ``Update``
hook (echo-suppressed, kill-switch-guarded, publish-gated, fail-soft).

Tests the guarded ``app.federation.publish.publish_location_update`` directly (the
shared hook logic) plus the ``LocationCommitHandler`` wiring via a minimally
constructed handler (``object.__new__`` — the full handler needs job-scoped
collaborators a unit test should not assemble). DB-backed; all data fictional.
"""

import base64
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.federation import publish
from app.federation.publish import publish_location_update

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
def configured(monkeypatch):
    from app.core.config import settings as live

    monkeypatch.setattr(live, "FEDERATION_ENABLED", True)
    monkeypatch.setattr(live, "FEDERATION_DID", _DID)
    monkeypatch.setattr(live, "FEDERATION_DOMAIN", None)  # host derives from DID
    monkeypatch.setattr(
        live, "FEDERATION_SIGNING_KEY", base64.b64encode(_SEED).decode("ascii")
    )
    return live


def _insert_location(session, *, is_canonical: bool = True) -> str:
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


def _log_rows(session):
    return session.execute(
        text("SELECT type, federation_id FROM federation_log ORDER BY sequence")
    ).all()


def test_ppr_origin_commit_appends_update(db_session, configured):
    loc_id = _insert_location(db_session)
    seq = publish_location_update(db_session, loc_id, source_type="scraper")
    assert seq == 1
    rows = _log_rows(db_session)
    assert len(rows) == 1
    assert rows[0].type == "Update"
    assert rows[0].federation_id == f"node.example:{loc_id}"


def test_pure_federated_commit_appends_nothing(db_session, configured):
    """Echo suppression (§10): a commit sourced from a federated peer is a re-echo."""
    loc_id = _insert_location(db_session)
    assert (
        publish_location_update(db_session, loc_id, source_type="federated_node")
        is None
    )
    assert _log_rows(db_session) == []


def test_killswitch_off_appends_nothing(db_session, configured, monkeypatch):
    from app.core.config import settings as live

    monkeypatch.setattr(live, "FEDERATION_ENABLED", False)
    loc_id = _insert_location(db_session)
    assert publish_location_update(db_session, loc_id, source_type="scraper") is None
    assert _log_rows(db_session) == []


def test_no_identity_appends_nothing(db_session, configured, monkeypatch):
    from app.core.config import settings as live

    monkeypatch.setattr(live, "FEDERATION_DID", None)
    loc_id = _insert_location(db_session)
    assert publish_location_update(db_session, loc_id, source_type="scraper") is None
    assert _log_rows(db_session) == []


def test_non_canonical_location_not_published(db_session, configured):
    """Publish gate: a soft-deleted (is_canonical=FALSE) row is not published."""
    loc_id = _insert_location(db_session, is_canonical=False)
    assert publish_location_update(db_session, loc_id, source_type="scraper") is None
    assert _log_rows(db_session) == []


def test_missing_location_is_fail_soft(db_session, configured):
    """A federation failure must never raise into the reconciler (Principle XI)."""
    missing = str(uuid.uuid4())
    _insert_location(db_session)  # the gate query needs the table populated/empty-safe
    assert publish_location_update(db_session, missing, source_type="scraper") is None


def test_handler_wiring_publishes_for_non_submarine(db_session, configured):
    """LocationCommitHandler._publish_federation_update appends for a non-submarine
    commit (verifies the hook is wired at the commit site)."""
    from app.reconciler.location_commit import LocationCommitHandler

    loc_id = _insert_location(db_session)
    handler = object.__new__(LocationCommitHandler)
    handler.db = db_session
    handler.metadata = {"source_type": "scraper"}
    handler._publish_federation_update(uuid.UUID(loc_id))
    rows = _log_rows(db_session)
    assert len(rows) == 1 and rows[0].type == "Update"


def test_handler_wiring_echo_suppressed(db_session, configured):
    """The handler passes source_type through, so a federated job is echo-suppressed."""
    from app.reconciler.location_commit import LocationCommitHandler

    loc_id = _insert_location(db_session)
    handler = object.__new__(LocationCommitHandler)
    handler.db = db_session
    handler.metadata = {"source_type": publish.FEDERATED_SOURCE_TYPE}
    handler._publish_federation_update(uuid.UUID(loc_id))
    assert _log_rows(db_session) == []


def test_submarine_source_publishes_update(db_session, configured):
    """PR-C Task 6: a submarine enrichment commit (PPR-origin) publishes an Update
    — submarine is not echo-suppressed (source_type != federated_node)."""
    from app.reconciler.location_commit import LocationCommitHandler

    loc_id = _insert_location(db_session)
    handler = object.__new__(LocationCommitHandler)
    handler.db = db_session
    handler.metadata = {"scraper_id": "submarine", "source_type": "submarine"}
    handler._publish_federation_update(uuid.UUID(loc_id))
    rows = _log_rows(db_session)
    assert len(rows) == 1 and rows[0].type == "Update"
