"""API-1 regression guard: HSDS location read paths default to visible rows.

The audit found that ``LocationRepository`` served soft-deleted duplicates
(``is_canonical=FALSE``) and ``validation_status='rejected'`` rows on the public
HSDS API (``/locations`` etc.), because neither the repository nor the endpoints
applied any canonical/validation predicate. In production this exposed 11,376
rows that every other surface (map/PTF/export) hides.

These tests lock in the fix: the location read paths must default to
``is_canonical = TRUE AND validation_status != 'rejected'`` and must skip that
filter only when ``include_hidden=True`` is explicitly passed (admin/debug).
"""

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.database.models import LocationModel
from app.database.repositories import LocationRepository


def _sql(query) -> str:
    """Compile a SQLAlchemy statement to a lowercase SQL string."""
    return str(
        query.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": False},
        )
    ).lower()


class _CapturingSession:
    """Async session stub that records the last statement passed to execute()."""

    def __init__(self) -> None:
        self.captured = None
        self.execute = AsyncMock(side_effect=self._execute)

    async def _execute(self, statement, *args, **kwargs):
        self.captured = statement
        result = Mock()
        scalars = Mock()
        scalars.all.return_value = []
        result.scalars.return_value = scalars
        result.scalar_one_or_none.return_value = None
        result.scalar.return_value = 0
        return result


def test_location_model_maps_is_canonical():
    """is_canonical exists in the DB but was unmapped on the ORM model."""
    assert hasattr(LocationModel, "is_canonical")


# The visibility predicate renders (postgresql dialect) as
#   location.is_canonical IS true AND
#   (location.validation_status IS NULL OR location.validation_status != ...)
# We assert on the WHERE-clause phrasing, not the bare column name, because the
# mapped column also appears in the SELECT list regardless of filtering.
_CANONICAL_PRED = "is_canonical is true"
_REJECTED_PRED = "validation_status is null"


@pytest.mark.asyncio
async def test_get_all_defaults_to_canonical_non_rejected():
    session = _CapturingSession()
    repo = LocationRepository(session)
    await repo.get_all()
    sql = _sql(session.captured)
    assert _CANONICAL_PRED in sql
    assert _REJECTED_PRED in sql


@pytest.mark.asyncio
async def test_get_all_include_hidden_skips_filter():
    session = _CapturingSession()
    repo = LocationRepository(session)
    await repo.get_all(include_hidden=True)
    sql = _sql(session.captured)
    assert _CANONICAL_PRED not in sql
    assert _REJECTED_PRED not in sql


@pytest.mark.asyncio
async def test_get_by_id_defaults_to_canonical_non_rejected():
    session = _CapturingSession()
    repo = LocationRepository(session)
    await repo.get_by_id(uuid4())
    sql = _sql(session.captured)
    assert _CANONICAL_PRED in sql


@pytest.mark.asyncio
async def test_get_by_id_include_hidden_returns_any_row():
    session = _CapturingSession()
    repo = LocationRepository(session)
    await repo.get_by_id(uuid4(), include_hidden=True)
    sql = _sql(session.captured)
    assert _CANONICAL_PRED not in sql


@pytest.mark.asyncio
async def test_count_defaults_to_canonical_non_rejected():
    """count() must match get_all() filtering or pagination totals are wrong."""
    session = _CapturingSession()
    repo = LocationRepository(session)
    await repo.count()
    sql = _sql(session.captured)
    assert _CANONICAL_PRED in sql
    assert _REJECTED_PRED in sql


@pytest.mark.asyncio
async def test_bbox_and_radius_default_to_visible():
    from app.models.hsds.query import GeoBoundingBox, GeoPoint

    session = _CapturingSession()
    repo = LocationRepository(session)
    await repo.count_by_bbox(
        GeoBoundingBox(
            min_latitude=40.0,
            max_latitude=41.0,
            min_longitude=-74.0,
            max_longitude=-73.0,
        )
    )
    assert _CANONICAL_PRED in _sql(session.captured)

    await repo.count_by_radius(GeoPoint(latitude=40.0, longitude=-73.5), 5.0)
    assert _CANONICAL_PRED in _sql(session.captured)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_repository_hides_noncanonical_and_rejected_end_to_end(db_session):
    """End-to-end: seed canonical / non-canonical / rejected rows against the
    real test DB and prove the repository returns only the visible one.

    This is the production behavior that removes the ~11,376 leaked rows: a
    soft-deleted duplicate (is_canonical=FALSE) and a rejected row must not be
    returned by default, and must be retrievable only via include_hidden=True.
    """
    from sqlalchemy import text

    org_id = str(uuid4())
    visible_id = str(uuid4())
    duplicate_id = str(uuid4())
    rejected_id = str(uuid4())

    await db_session.execute(
        text(
            "INSERT INTO organization (id, name, description) "
            "VALUES (:id, :name, :desc)"
        ),
        {"id": org_id, "name": "API-1 Visibility Org", "desc": "API-1 seed org"},
    )
    seed = [
        (visible_id, "Visible Pantry", "needs_review", True),
        (duplicate_id, "Soft-deleted Duplicate", "needs_review", False),
        (rejected_id, "Rejected Pantry", "rejected", True),
    ]
    for loc_id, name, status, canonical in seed:
        await db_session.execute(
            text(
                """
                INSERT INTO location (
                    id, organization_id, name, latitude, longitude,
                    location_type, validation_status, confidence_score,
                    is_canonical
                )
                VALUES (
                    :id, :org, :name, 40.0, -74.0,
                    'physical', :status, 70, :canonical
                )
                """
            ),
            {
                "id": loc_id,
                "org": org_id,
                "name": name,
                "status": status,
                "canonical": canonical,
            },
        )
    await db_session.flush()

    repo = LocationRepository(db_session)

    # Default: only the canonical, non-rejected row of this org is returned.
    returned = await repo.get_all(filters={"organization_id": org_id}, limit=1000)
    returned_ids = {str(loc.id) for loc in returned}
    assert visible_id in returned_ids
    assert duplicate_id not in returned_ids
    assert rejected_id not in returned_ids

    # count() agrees with get_all() so pagination totals are correct.
    assert await repo.count(filters={"organization_id": org_id}) == 1

    # get_by_id hides the soft-deleted duplicate and the rejected row…
    assert await repo.get_by_id(uuid4_from(duplicate_id)) is None
    assert await repo.get_by_id(uuid4_from(rejected_id)) is None
    assert await repo.get_by_id(uuid4_from(visible_id)) is not None

    # …but include_hidden=True opts back into every row (admin/debug).
    assert (
        await repo.get_by_id(uuid4_from(duplicate_id), include_hidden=True) is not None
    )
    hidden_all = await repo.get_all(
        filters={"organization_id": org_id}, limit=1000, include_hidden=True
    )
    assert len(hidden_all) == 3


def uuid4_from(value: str):
    """Local helper: parse a string UUID (kept near its single use site)."""
    from uuid import UUID

    return UUID(value)
