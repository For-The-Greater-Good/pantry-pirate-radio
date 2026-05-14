"""Router tests for PTF /locations endpoints.

Tests the FastAPI handler functions directly with a mocked query layer
(matches the pattern in test_ptf_router.py). Asserts response shape,
auth-free access, validation, and FA enrichment routing.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.partners.ptf.locations_router import (
    _BBOX_MIN_SIZE_DEG,
    _pad_bbox_to_min,
    get_ptf_location,
    list_ptf_locations,
)


def _row(**overrides):
    base = {
        "id": str(uuid4()),
        "name": "Test Pantry",
        "short_name": None,
        "description": None,
        "latitude": 40.0,
        "longitude": -74.0,
        "organization_id": None,
        "org_name": None,
        "org_description": None,
        "org_email": None,
        "org_website": None,
        "address_1": "1 Main St",
        "address_2": None,
        "city": "Newark",
        "state_province": "NJ",
        "postal_code": "07102",
        "phone_number": None,
        "fa_org_id": None,
        "fa_org_name": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class TestListEndpoint:
    @pytest.mark.asyncio
    async def test_returns_array_not_envelope(self):
        session = MagicMock(spec=AsyncSession)
        with patch(
            "app.api.v1.partners.ptf.locations_router.PtfLocationsQuery"
        ) as MockQuery:
            mock_q = MagicMock()
            mock_q.list_locations = AsyncMock(return_value=[_row(), _row()])
            MockQuery.return_value = mock_q

            result = await list_ptf_locations(
                response=MagicMock(headers={}),
                limit=50,
                offset=0,
                lat1=None,
                lng1=None,
                lat2=None,
                lng2=None,
                q=None,
                session=session,
            )

        assert isinstance(result, list)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_respects_limit_and_offset(self):
        session = MagicMock(spec=AsyncSession)
        with patch(
            "app.api.v1.partners.ptf.locations_router.PtfLocationsQuery"
        ) as MockQuery:
            mock_q = MagicMock()
            mock_q.list_locations = AsyncMock(return_value=[])
            MockQuery.return_value = mock_q

            await list_ptf_locations(
                response=MagicMock(headers={}),
                limit=5,
                offset=10,
                lat1=None,
                lng1=None,
                lat2=None,
                lng2=None,
                q=None,
                session=session,
            )
            mock_q.list_locations.assert_awaited_once()
            kwargs = mock_q.list_locations.await_args.kwargs
            assert kwargs["limit"] == 5
            assert kwargs["offset"] == 10

    @pytest.mark.asyncio
    async def test_bbox_passed_through(self):
        session = MagicMock(spec=AsyncSession)
        with patch(
            "app.api.v1.partners.ptf.locations_router.PtfLocationsQuery"
        ) as MockQuery:
            mock_q = MagicMock()
            mock_q.list_locations = AsyncMock(return_value=[])
            MockQuery.return_value = mock_q

            await list_ptf_locations(
                response=MagicMock(headers={}),
                limit=50,
                offset=0,
                lat1=40.0,
                lng1=-75.0,
                lat2=41.0,
                lng2=-73.0,
                q=None,
                session=session,
            )
            kwargs = mock_q.list_locations.await_args.kwargs
            # 1° x 2° is well above the 3-mile floor, so it passes through
            # unchanged (modulo the min/max normalization, which is a
            # no-op here since the values are already ordered).
            assert kwargs["bbox"] == (40.0, -75.0, 41.0, -73.0)

    @pytest.mark.asyncio
    async def test_tiny_bbox_padded_to_min(self):
        """A pin-tight zoom (<3 mi on a side) must be expanded around its
        center before the SQL runs, so neighboring pins don't drop off
        the response as the client zooms in."""
        session = MagicMock(spec=AsyncSession)
        with patch(
            "app.api.v1.partners.ptf.locations_router.PtfLocationsQuery"
        ) as MockQuery:
            mock_q = MagicMock()
            mock_q.list_locations = AsyncMock(return_value=[])
            MockQuery.return_value = mock_q

            # 0.001° x 0.001° — well under the floor.
            await list_ptf_locations(
                response=MagicMock(headers={}),
                limit=50,
                offset=0,
                lat1=40.7580,
                lng1=-73.9858,
                lat2=40.7585,
                lng2=-73.9853,
                q=None,
                session=session,
            )
            kwargs = mock_q.list_locations.await_args.kwargs
            padded = kwargs["bbox"]
            # Side lengths must now meet the floor.
            assert padded[2] - padded[0] >= _BBOX_MIN_SIZE_DEG - 1e-9
            assert padded[3] - padded[1] >= _BBOX_MIN_SIZE_DEG - 1e-9
            # Centered on the original center.
            assert padded[0] + padded[2] == pytest.approx(40.7580 + 40.7585)
            assert padded[1] + padded[3] == pytest.approx(-73.9858 + -73.9853)

    @pytest.mark.asyncio
    async def test_inverted_bbox_is_normalized(self):
        """Swapped corners (lat2 < lat1) must yield a valid envelope, not
        an inverted one. The query layer assumes min/max are correctly
        ordered."""
        session = MagicMock(spec=AsyncSession)
        with patch(
            "app.api.v1.partners.ptf.locations_router.PtfLocationsQuery"
        ) as MockQuery:
            mock_q = MagicMock()
            mock_q.list_locations = AsyncMock(return_value=[])
            MockQuery.return_value = mock_q

            await list_ptf_locations(
                response=MagicMock(headers={}),
                limit=50,
                offset=0,
                lat1=41.0,
                lng1=-73.0,
                lat2=40.0,
                lng2=-75.0,
                q=None,
                session=session,
            )
            kwargs = mock_q.list_locations.await_args.kwargs
            lat_min, lng_min, lat_max, lng_max = kwargs["bbox"]
            assert lat_min < lat_max
            assert lng_min < lng_max

    @pytest.mark.asyncio
    async def test_limit_500_accepted(self):
        """Max page size widened to 500 so a 3-mile-padded urban viewport
        can return all pins in one call."""
        session = MagicMock(spec=AsyncSession)
        with patch(
            "app.api.v1.partners.ptf.locations_router.PtfLocationsQuery"
        ) as MockQuery:
            mock_q = MagicMock()
            mock_q.list_locations = AsyncMock(return_value=[])
            MockQuery.return_value = mock_q

            await list_ptf_locations(
                response=MagicMock(headers={}),
                limit=500,
                offset=0,
                lat1=None,
                lng1=None,
                lat2=None,
                lng2=None,
                q=None,
                session=session,
            )
            kwargs = mock_q.list_locations.await_args.kwargs
            assert kwargs["limit"] == 500

    @pytest.mark.asyncio
    async def test_partial_bbox_rejected(self):
        session = MagicMock(spec=AsyncSession)
        with pytest.raises(HTTPException) as ei:
            await list_ptf_locations(
                response=MagicMock(headers={}),
                limit=50,
                offset=0,
                lat1=40.0,
                lng1=None,
                lat2=41.0,
                lng2=-73.0,
                q=None,
                session=session,
            )
        assert ei.value.status_code == 422

    @pytest.mark.asyncio
    async def test_q_filter_passed_through(self):
        session = MagicMock(spec=AsyncSession)
        with patch(
            "app.api.v1.partners.ptf.locations_router.PtfLocationsQuery"
        ) as MockQuery:
            mock_q = MagicMock()
            mock_q.list_locations = AsyncMock(return_value=[])
            MockQuery.return_value = mock_q

            await list_ptf_locations(
                response=MagicMock(headers={}),
                limit=50,
                offset=0,
                lat1=None,
                lng1=None,
                lat2=None,
                lng2=None,
                q="Harvest",
                session=session,
            )
            kwargs = mock_q.list_locations.await_args.kwargs
            assert kwargs["q"] == "Harvest"

    @pytest.mark.asyncio
    async def test_fa_enrichment_populated_when_zip_matches(self):
        session = MagicMock(spec=AsyncSession)
        with patch(
            "app.api.v1.partners.ptf.locations_router.PtfLocationsQuery"
        ) as MockQuery:
            mock_q = MagicMock()
            mock_q.list_locations = AsyncMock(
                return_value=[
                    _row(fa_org_id=58, fa_org_name="Community Foodbank of New Jersey")
                ]
            )
            MockQuery.return_value = mock_q

            result = await list_ptf_locations(
                response=MagicMock(headers={}),
                limit=50,
                offset=0,
                lat1=None,
                lng1=None,
                lat2=None,
                lng2=None,
                q=None,
                session=session,
            )
        assert result[0].feeding_america_food_bank is not None
        assert result[0].feeding_america_food_bank.id == 58

    @pytest.mark.asyncio
    async def test_fa_null_when_no_zip_match(self):
        session = MagicMock(spec=AsyncSession)
        with patch(
            "app.api.v1.partners.ptf.locations_router.PtfLocationsQuery"
        ) as MockQuery:
            mock_q = MagicMock()
            mock_q.list_locations = AsyncMock(return_value=[_row()])
            MockQuery.return_value = mock_q

            result = await list_ptf_locations(
                response=MagicMock(headers={}),
                limit=50,
                offset=0,
                lat1=None,
                lng1=None,
                lat2=None,
                lng2=None,
                q=None,
                session=session,
            )
        assert result[0].feeding_america_food_bank is None


class TestDetailEndpoint:
    @pytest.mark.asyncio
    async def test_returns_detail_for_known_id(self):
        session = MagicMock(spec=AsyncSession)
        loc_id = str(uuid4())
        with patch(
            "app.api.v1.partners.ptf.locations_router.PtfLocationsQuery"
        ) as MockQuery:
            mock_q = MagicMock()
            mock_q.get_location = AsyncMock(return_value=_row(id=loc_id))
            mock_q.get_schedules = AsyncMock(return_value=[])
            MockQuery.return_value = mock_q

            result = await get_ptf_location(
                location_id=loc_id,
                response=MagicMock(headers={}),
                session=session,
            )
        assert result.id == loc_id

    @pytest.mark.asyncio
    async def test_404_for_unknown_id(self):
        session = MagicMock(spec=AsyncSession)
        with patch(
            "app.api.v1.partners.ptf.locations_router.PtfLocationsQuery"
        ) as MockQuery:
            mock_q = MagicMock()
            mock_q.get_location = AsyncMock(return_value=None)
            MockQuery.return_value = mock_q

            with pytest.raises(HTTPException) as ei:
                await get_ptf_location(
                    location_id="00000000-0000-0000-0000-000000000000",
                    response=MagicMock(headers={}),
                    session=session,
                )
            assert ei.value.status_code == 404


class TestPadBboxToMin:
    """Direct unit tests for the bbox-padding helper."""

    def test_large_bbox_unchanged(self):
        bbox = (40.0, -75.0, 41.0, -73.0)
        assert _pad_bbox_to_min(bbox) == bbox

    def test_tiny_bbox_padded(self):
        bbox = (40.7580, -73.9858, 40.7585, -73.9853)
        padded = _pad_bbox_to_min(bbox)
        assert padded[2] - padded[0] == pytest.approx(_BBOX_MIN_SIZE_DEG)
        assert padded[3] - padded[1] == pytest.approx(_BBOX_MIN_SIZE_DEG)

    def test_padding_centered(self):
        bbox = (45.0, -100.0, 45.001, -99.999)
        padded = _pad_bbox_to_min(bbox)
        assert (padded[0] + padded[2]) / 2 == pytest.approx(45.0005)
        assert (padded[1] + padded[3]) / 2 == pytest.approx(-99.9995)

    def test_only_one_axis_under_floor(self):
        # Lat span 0.01 (under floor), lng span 1.0 (above floor).
        bbox = (45.0, -100.0, 45.01, -99.0)
        padded = _pad_bbox_to_min(bbox)
        # Lat padded.
        assert padded[2] - padded[0] == pytest.approx(_BBOX_MIN_SIZE_DEG)
        # Lng untouched.
        assert padded[1] == pytest.approx(-100.0)
        assert padded[3] == pytest.approx(-99.0)

    def test_inverted_lat_normalized(self):
        bbox = (41.0, -75.0, 40.0, -73.0)  # lat1 > lat2
        lat_min, lng_min, lat_max, lng_max = _pad_bbox_to_min(bbox)
        assert lat_min < lat_max

    def test_inverted_lng_normalized(self):
        bbox = (40.0, -73.0, 41.0, -75.0)  # lng1 > lng2
        lat_min, lng_min, lat_max, lng_max = _pad_bbox_to_min(bbox)
        assert lng_min < lng_max


class TestRouterMounting:
    """Confirms the router is wired up so HTTP requests hit it."""

    def test_router_has_list_route(self):
        from app.api.v1.partners.ptf.router import router

        paths = {r.path for r in router.routes}
        assert "/partners/ptf/locations" in paths

    def test_router_has_detail_route(self):
        from app.api.v1.partners.ptf.router import router

        paths = {r.path for r in router.routes}
        assert "/partners/ptf/locations/{location_id}" in paths

    def test_locations_routes_have_no_auth_dependency(self):
        """A regression guard against accidentally adding an auth dep.

        Hard-asserts `dependant` exists rather than falling back to a
        MagicMock (which would silently pass and make this test useless).
        """
        from app.api.v1.partners.ptf.router import router

        locations_routes = [
            r for r in router.routes if "/locations" in getattr(r, "path", "")
        ]
        assert len(locations_routes) >= 2, "list and detail routes must exist"
        for route in locations_routes:
            assert hasattr(
                route, "dependant"
            ), f"route {route.path} has no dependant; can't audit auth"
            for dep in route.dependant.dependencies or []:
                name = getattr(dep.call, "__name__", "")
                assert (
                    "auth" not in name.lower()
                ), f"Auth dependency leaked into PTF locations endpoint: {name}"
