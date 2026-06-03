"""Tests for scripts/backfill_null_org_from_record_version.py.

Recovers organization_id for NULL-org canonical locations from the latest
record_version snapshot. These run against the real Postgres test DB (mirrors
tests/test_dedupe_near_duplicate_locations.py)."""

from __future__ import annotations

import json
import uuid
from collections.abc import Generator

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

# Top-level tests/conftest provides the async db_session; we need the sync one.
from tests.fixtures.db import db_session_sync as db_session  # noqa: F401

from scripts.backfill_null_org_from_record_version import (
    ensure_audit_table,
    fill_org,
    find_candidates,
    total_null_org_canonical,
    undo_run,
)


@pytest.fixture
def clean_tables(
    db_session: Session,  # noqa: F811
) -> Generator[Session, None, None]:
    """Wipe the tables this backfill touches before each test."""
    db_session.execute(text("TRUNCATE TABLE record_version CASCADE"))
    db_session.execute(text("TRUNCATE TABLE location CASCADE"))
    db_session.execute(text("TRUNCATE TABLE organization CASCADE"))
    db_session.commit()
    ensure_audit_table(db_session)
    db_session.execute(text("TRUNCATE TABLE org_backfill_audit"))
    db_session.commit()
    yield db_session


def _seed_org(db: Session, org_id: str, name: str = "Org") -> str:
    db.execute(
        text(
            """
            INSERT INTO organization (id, name, description)
            VALUES (:id, :name, 'backfill-test org')
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {"id": org_id, "name": name},
    )
    return org_id


def _seed_location(
    db: Session,
    *,
    loc_id: str,
    org_id: str | None,
    is_canonical: bool = True,
    verified_by: str | None = None,
) -> None:
    db.execute(
        text(
            """
            INSERT INTO location (
                id, organization_id, name, latitude, longitude,
                location_type, validation_status, confidence_score,
                is_canonical, verified_by
            )
            VALUES (:id, :org, 'Pantry', 40.0, -75.0,
                    'physical', 'verified', 70, :canon, :verified_by)
            """
        ),
        {
            "id": loc_id,
            "org": org_id,
            "canon": is_canonical,
            "verified_by": verified_by,
        },
    )


def _seed_version(
    db: Session,
    *,
    loc_id: str,
    version_num: int,
    org_in_data: str | None,
) -> None:
    """Insert one record_version row for a location, optionally carrying an
    organization_id in its data jsonb."""
    data: dict[str, object] = {"name": "Pantry"}
    if org_in_data is not None:
        data["organization_id"] = org_in_data
    db.execute(
        text(
            """
            INSERT INTO record_version (
                id, record_id, record_type, version_num, data, created_by
            )
            VALUES (:id, :rid, 'location', :ver, CAST(:data AS jsonb), 'reconciler')
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "rid": loc_id,
            "ver": version_num,
            "data": json.dumps(data),
        },
    )


def _org_of(db: Session, loc_id: str) -> str | None:
    row = db.execute(
        text("SELECT organization_id FROM location WHERE id = :id"),
        {"id": loc_id},
    ).first()
    return str(row[0]) if row and row[0] else None


class TestFindCandidates:
    def test_recoverable_null_org_is_a_candidate(self, clean_tables: Session) -> None:
        db = clean_tables
        org = _seed_org(db, str(uuid.uuid4()))
        loc = str(uuid.uuid4())
        _seed_location(db, loc_id=loc, org_id=None)
        _seed_version(db, loc_id=loc, version_num=1, org_in_data=org)
        db.commit()

        cands = find_candidates(db)
        assert len(cands) == 1
        assert cands[0]["location_id"] == loc
        assert cands[0]["recovered_org_id"] == org
        assert cands[0]["source_version_num"] == 1

    def test_picks_latest_version_org(self, clean_tables: Session) -> None:
        db = clean_tables
        org_a = _seed_org(db, str(uuid.uuid4()), "A")
        org_b = _seed_org(db, str(uuid.uuid4()), "B")
        loc = str(uuid.uuid4())
        _seed_location(db, loc_id=loc, org_id=None)
        _seed_version(db, loc_id=loc, version_num=1, org_in_data=org_a)
        _seed_version(db, loc_id=loc, version_num=2, org_in_data=org_b)
        db.commit()

        cands = find_candidates(db)
        assert len(cands) == 1
        # Highest version_num wins.
        assert cands[0]["recovered_org_id"] == org_b
        assert cands[0]["source_version_num"] == 2

    def test_no_version_with_org_excluded(self, clean_tables: Session) -> None:
        db = clean_tables
        loc = str(uuid.uuid4())
        _seed_location(db, loc_id=loc, org_id=None)
        _seed_version(db, loc_id=loc, version_num=1, org_in_data=None)
        db.commit()

        assert find_candidates(db) == []

    def test_org_no_longer_exists_excluded(self, clean_tables: Session) -> None:
        db = clean_tables
        loc = str(uuid.uuid4())
        _seed_location(db, loc_id=loc, org_id=None)
        # Version references an org id that was never inserted (stale FK).
        _seed_version(db, loc_id=loc, version_num=1, org_in_data=str(uuid.uuid4()))
        db.commit()

        assert find_candidates(db) == []

    def test_human_verified_excluded(self, clean_tables: Session) -> None:
        db = clean_tables
        org = _seed_org(db, str(uuid.uuid4()))
        loc = str(uuid.uuid4())
        _seed_location(db, loc_id=loc, org_id=None, verified_by="admin")
        _seed_version(db, loc_id=loc, version_num=1, org_in_data=org)
        db.commit()

        assert find_candidates(db) == []

    def test_noncanonical_excluded(self, clean_tables: Session) -> None:
        db = clean_tables
        org = _seed_org(db, str(uuid.uuid4()))
        loc = str(uuid.uuid4())
        _seed_location(db, loc_id=loc, org_id=None, is_canonical=False)
        _seed_version(db, loc_id=loc, version_num=1, org_in_data=org)
        db.commit()

        assert find_candidates(db) == []

    def test_already_has_org_excluded(self, clean_tables: Session) -> None:
        db = clean_tables
        org = _seed_org(db, str(uuid.uuid4()))
        loc = str(uuid.uuid4())
        _seed_location(db, loc_id=loc, org_id=org)  # already linked
        _seed_version(db, loc_id=loc, version_num=1, org_in_data=org)
        db.commit()

        assert find_candidates(db) == []
        assert total_null_org_canonical(db) == 0


class TestFillOrg:
    def test_fill_sets_org_and_writes_audit(self, clean_tables: Session) -> None:
        db = clean_tables
        org = _seed_org(db, str(uuid.uuid4()))
        loc = str(uuid.uuid4())
        _seed_location(db, loc_id=loc, org_id=None)
        _seed_version(db, loc_id=loc, version_num=1, org_in_data=org)
        db.commit()

        run_id = str(uuid.uuid4())
        cand = find_candidates(db)[0]
        changed = fill_org(db, cand, run_id)
        db.commit()

        assert changed is True
        assert _org_of(db, loc) == org
        audit = db.execute(
            text(
                """
                SELECT location_id, old_organization_id, new_organization_id, action
                FROM org_backfill_audit WHERE run_id = :rid
                """
            ),
            {"rid": run_id},
        ).fetchall()
        assert len(audit) == 1
        assert str(audit[0].location_id) == loc
        assert audit[0].old_organization_id is None
        assert str(audit[0].new_organization_id) == org
        assert audit[0].action == "org_fill"

    def test_fill_guard_skips_row_that_gained_org(self, clean_tables: Session) -> None:
        db = clean_tables
        org = _seed_org(db, str(uuid.uuid4()))
        other = _seed_org(db, str(uuid.uuid4()), "Other")
        loc = str(uuid.uuid4())
        _seed_location(db, loc_id=loc, org_id=None)
        _seed_version(db, loc_id=loc, version_num=1, org_in_data=org)
        db.commit()
        cand = find_candidates(db)[0]

        # Simulate a concurrent writer linking the org before we apply.
        db.execute(
            text("UPDATE location SET organization_id = :o WHERE id = :id"),
            {"o": other, "id": loc},
        )
        db.commit()

        changed = fill_org(db, cand, str(uuid.uuid4()))
        db.commit()
        assert changed is False
        assert _org_of(db, loc) == other  # untouched

    def test_fill_guard_skips_human_verified(self, clean_tables: Session) -> None:
        db = clean_tables
        org = _seed_org(db, str(uuid.uuid4()))
        loc = str(uuid.uuid4())
        # Candidate selection would exclude this, but fill_org's own guard is
        # defense-in-depth — verify it independently.
        _seed_location(db, loc_id=loc, org_id=None, verified_by="claimed")
        db.commit()

        cand = {
            "location_id": loc,
            "recovered_org_id": org,
            "source_version_num": 1,
        }
        changed = fill_org(db, cand, str(uuid.uuid4()))
        db.commit()
        assert changed is False
        assert _org_of(db, loc) is None


class TestUndo:
    def _fill_one(self, db: Session) -> tuple[str, str, str]:
        org = _seed_org(db, str(uuid.uuid4()))
        loc = str(uuid.uuid4())
        _seed_location(db, loc_id=loc, org_id=None)
        _seed_version(db, loc_id=loc, version_num=1, org_in_data=org)
        db.commit()
        run_id = str(uuid.uuid4())
        fill_org(db, find_candidates(db)[0], run_id)
        db.commit()
        return run_id, loc, org

    def test_undo_renulls_filled_rows(self, clean_tables: Session) -> None:
        db = clean_tables
        run_id, loc, org = self._fill_one(db)
        assert _org_of(db, loc) == org

        reverted = undo_run(db, run_id, apply=True)
        db.commit()
        assert reverted == 1
        assert _org_of(db, loc) is None

    def test_undo_dry_run_changes_nothing(self, clean_tables: Session) -> None:
        db = clean_tables
        run_id, loc, org = self._fill_one(db)

        reverted = undo_run(db, run_id, apply=False)
        db.rollback()
        assert reverted == 1  # would-revert count
        assert _org_of(db, loc) == org  # unchanged

    def test_undo_skips_if_human_curated_after_fill(
        self, clean_tables: Session
    ) -> None:
        db = clean_tables
        run_id, loc, org = self._fill_one(db)
        # A human curates the row after the backfill.
        db.execute(
            text("UPDATE location SET verified_by = 'admin' WHERE id = :id"),
            {"id": loc},
        )
        db.commit()

        reverted = undo_run(db, run_id, apply=True)
        db.commit()
        assert reverted == 0
        assert _org_of(db, loc) == org  # human-curated row preserved

    def test_undo_skips_if_org_changed_after_fill(self, clean_tables: Session) -> None:
        db = clean_tables
        run_id, loc, _org = self._fill_one(db)
        other = _seed_org(db, str(uuid.uuid4()), "Other")
        db.execute(
            text("UPDATE location SET organization_id = :o WHERE id = :id"),
            {"o": other, "id": loc},
        )
        db.commit()

        reverted = undo_run(db, run_id, apply=True)
        db.commit()
        assert reverted == 0
        assert _org_of(db, loc) == other  # not clobbered back to NULL

    def test_undo_writes_undo_audit_row(self, clean_tables: Session) -> None:
        db = clean_tables
        run_id, loc, org = self._fill_one(db)
        undo_run(db, run_id, apply=True)
        db.commit()

        row = db.execute(
            text(
                """
                SELECT location_id, old_organization_id, new_organization_id
                FROM org_backfill_audit
                WHERE run_id = :rid AND action = 'undo'
                """
            ),
            {"rid": run_id},
        ).fetchall()
        assert len(row) == 1
        assert str(row[0].location_id) == loc
        # By design the undo audit row records old==new==the reverted org.
        assert str(row[0].old_organization_id) == org
        assert str(row[0].new_organization_id) == org

    def test_undo_unknown_run_id_is_noop(self, clean_tables: Session) -> None:
        db = clean_tables
        _run_id, loc, org = self._fill_one(db)
        reverted = undo_run(db, str(uuid.uuid4()), apply=True)  # never used
        db.commit()
        assert reverted == 0
        assert _org_of(db, loc) == org  # the real fill untouched

    def test_undo_only_affects_its_own_run(self, clean_tables: Session) -> None:
        db = clean_tables
        run_a, loc_a, org_a = self._fill_one(db)
        run_b, loc_b, org_b = self._fill_one(db)

        reverted = undo_run(db, run_a, apply=True)
        db.commit()
        assert reverted == 1
        assert _org_of(db, loc_a) is None  # run A reverted
        assert _org_of(db, loc_b) == org_b  # run B untouched


class TestStableOrderAndCap:
    """The --max-rows staged rollout relies on find_candidates returning a
    stable id order so a re-run with the same cap touches the same rows."""

    def test_candidates_returned_in_stable_id_order(
        self, clean_tables: Session
    ) -> None:
        db = clean_tables
        # Controlled, sortable ids so the ORDER BY l.id contract is assertable.
        ids = [f"00000000-0000-0000-0000-0000000000{n:02d}" for n in (3, 1, 2)]
        for i in ids:
            org = _seed_org(db, str(uuid.uuid4()))
            _seed_location(db, loc_id=i, org_id=None)
            _seed_version(db, loc_id=i, version_num=1, org_in_data=org)
        db.commit()

        cands = find_candidates(db)
        returned = [c["location_id"] for c in cands]
        assert returned == sorted(ids)  # deterministic ascending id order
        # The --max-rows 2 slice is the first 2 in that stable order.
        assert returned[:2] == sorted(ids)[:2]


class TestFreshnessPreflight:
    def test_freshness_false_when_no_recent_version(
        self, clean_tables: Session
    ) -> None:
        from scripts.backfill_null_org_from_record_version import (
            check_haarrrvest_freshness,
        )

        db = clean_tables  # record_version truncated by the fixture
        assert check_haarrrvest_freshness(db) is False

    def test_freshness_true_with_recent_version(self, clean_tables: Session) -> None:
        from scripts.backfill_null_org_from_record_version import (
            check_haarrrvest_freshness,
        )

        db = clean_tables
        # A freshly-inserted record_version (created_at defaults to NOW()).
        _seed_version(db, loc_id=str(uuid.uuid4()), version_num=1, org_in_data=None)
        db.commit()
        assert check_haarrrvest_freshness(db) is True
