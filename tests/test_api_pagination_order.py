"""API-6 regression guard: paginated repository reads have a stable ORDER BY.

Without a deterministic ORDER BY, Postgres may return rows in a different
physical order between requests, so OFFSET/LIMIT can silently skip or duplicate
rows across pages of the HSDS list endpoints. Every paginated repository read
now orders by the primary key (appended as a tiebreaker where an upstream
order_by such as distance already exists).
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database.repositories import (
    LocationRepository,
    OrganizationRepository,
    ServiceRepository,
)
from app.models.hsds.query import GeoBoundingBox

pytestmark = pytest.mark.integration


def _sql(query) -> str:
    return str(
        query.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": False}
        )
    ).lower()


class _CapturingSession:
    def __init__(self) -> None:
        self.captured = None

    async def execute(self, statement, *args, **kwargs):
        self.captured = statement
        from unittest.mock import Mock

        result = Mock()
        scalars = Mock()
        scalars.all.return_value = []
        result.scalars.return_value = scalars
        return result


@pytest.mark.asyncio
async def test_location_get_all_orders_by_id():
    session = _CapturingSession()
    await LocationRepository(session).get_all()
    assert "order by location.id" in _sql(session.captured)


@pytest.mark.asyncio
async def test_location_bbox_orders_by_id():
    session = _CapturingSession()
    await LocationRepository(session).get_locations_by_bbox(
        GeoBoundingBox(
            min_latitude=40.0,
            max_latitude=41.0,
            min_longitude=-74.0,
            max_longitude=-73.0,
        )
    )
    assert "order by location.id" in _sql(session.captured)


@pytest.mark.asyncio
async def test_org_and_service_get_all_order_by_id():
    for repo_cls, table in (
        (OrganizationRepository, "organization"),
        (ServiceRepository, "service"),
    ):
        session = _CapturingSession()
        await repo_cls(session).get_all()
        assert f"order by {table}.id" in _sql(session.captured)


@pytest_asyncio.fixture
async def five_locations(db_session: AsyncSession):
    org_id = str(uuid.uuid4())
    await db_session.execute(
        text(
            "INSERT INTO organization (id, name, description) "
            "VALUES (:id, :name, :desc)"
        ),
        {"id": org_id, "name": "Pagination Org", "desc": "API-6 seed"},
    )
    ids = sorted(str(uuid.uuid4()) for _ in range(5))
    for i, loc_id in enumerate(ids):
        await db_session.execute(
            text(
                """
                INSERT INTO location (
                    id, organization_id, name, latitude, longitude,
                    location_type, validation_status, confidence_score,
                    is_canonical
                )
                VALUES (:id, :org, :name, 40.0, -74.0,
                        'physical', 'needs_review', 70, TRUE)
                """
            ),
            {"id": loc_id, "org": org_id, "name": f"Pantry {i}"},
        )
    await db_session.flush()
    return org_id, set(ids)


@pytest.mark.asyncio
async def test_pagination_covers_every_row_exactly_once(db_session, five_locations):
    org_id, expected_ids = five_locations
    repo = LocationRepository(db_session)

    seen: list[str] = []
    for page in range(3):  # limit 2 over 5 rows -> pages of 2,2,1
        rows = await repo.get_all(
            skip=page * 2, limit=2, filters={"organization_id": org_id}
        )
        seen.extend(str(r.id) for r in rows)

    # No duplicates across pages, and every seeded row appears exactly once.
    assert len(seen) == len(set(seen)) == 5
    assert set(seen) == expected_ids
