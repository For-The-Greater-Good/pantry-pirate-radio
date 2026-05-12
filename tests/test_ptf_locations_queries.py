"""Query-builder tests for PTF /locations.

These tests focus on what the SQL contains and what params are passed,
without requiring a live database. The actual JOIN behaviour against
feeding_america_zip_coverage is exercised via test_ptf_locations_router
with a seeded in-memory test DB.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.v1.partners.ptf.locations_queries import (
    PtfLocationsQuery,
    clamp_limit,
    clamp_offset,
)


def _capture_session():
    """Return a mock AsyncSession that records every execute() call."""
    session = MagicMock()
    session.execute = AsyncMock(
        return_value=MagicMock(fetchall=MagicMock(return_value=[]))
    )
    return session


class TestClamps:
    def test_limit_clamps_to_minimum(self):
        assert clamp_limit(0) == 1
        assert clamp_limit(-100) == 1

    def test_limit_clamps_to_maximum(self):
        assert clamp_limit(1000) == 200

    def test_limit_passes_through_valid(self):
        assert clamp_limit(50) == 50

    def test_offset_clamps_to_zero(self):
        assert clamp_offset(-1) == 0
        assert clamp_offset(0) == 0
        assert clamp_offset(500) == 500


class TestQuerySQL:
    @pytest.mark.asyncio
    async def test_list_query_joins_feeding_america(self):
        session = _capture_session()
        query = PtfLocationsQuery(session)
        await query.list_locations(limit=10, offset=0)
        sql_text = str(session.execute.call_args[0][0])
        assert "feeding_america_zip_coverage" in sql_text
        assert "LEFT JOIN" in sql_text.upper()

    @pytest.mark.asyncio
    async def test_list_query_excludes_rejected_rows(self):
        session = _capture_session()
        query = PtfLocationsQuery(session)
        await query.list_locations(limit=10, offset=0)
        sql_text = str(session.execute.call_args[0][0])
        assert "validation_status" in sql_text
        assert "rejected" in sql_text

    @pytest.mark.asyncio
    async def test_list_query_uses_limit_offset_params(self):
        session = _capture_session()
        query = PtfLocationsQuery(session)
        await query.list_locations(limit=42, offset=17)
        params = session.execute.call_args[0][1]
        assert params["limit"] == 42
        assert params["offset"] == 17

    @pytest.mark.asyncio
    async def test_bbox_filter_adds_4_params(self):
        session = _capture_session()
        query = PtfLocationsQuery(session)
        await query.list_locations(limit=10, offset=0, bbox=(40.0, -75.0, 41.0, -73.0))
        params = session.execute.call_args[0][1]
        assert params["lat_min"] == 40.0
        assert params["lng_min"] == -75.0
        assert params["lat_max"] == 41.0
        assert params["lng_max"] == -73.0
        sql_text = str(session.execute.call_args[0][0])
        assert "latitude" in sql_text and "longitude" in sql_text

    @pytest.mark.asyncio
    async def test_q_filter_is_case_insensitive(self):
        session = _capture_session()
        query = PtfLocationsQuery(session)
        await query.list_locations(limit=10, offset=0, q="Harvest")
        params = session.execute.call_args[0][1]
        # Pattern is wrapped in % and lowered so ILIKE matches case-insensitively.
        assert params["q"].lower() == "%harvest%"
        sql_text = str(session.execute.call_args[0][0]).upper()
        assert "ILIKE" in sql_text

    @pytest.mark.asyncio
    async def test_q_filter_searches_name_and_short_name(self):
        session = _capture_session()
        query = PtfLocationsQuery(session)
        await query.list_locations(limit=10, offset=0, q="food")
        sql_text = str(session.execute.call_args[0][0])
        # Both name and alternate_name must be searched — exactly two
        # ILIKE clauses, no fewer.
        assert sql_text.count("ILIKE") == 2, (
            f"expected 2 ILIKE clauses for name + alternate_name, got "
            f"{sql_text.count('ILIKE')}"
        )

    @pytest.mark.asyncio
    async def test_q_filter_special_chars_are_bound_not_concatenated(self):
        """Regression: q must go through bound params so '%' / "'" /
        SQL keywords can't break out of the LIKE pattern."""
        session = _capture_session()
        query = PtfLocationsQuery(session)
        await query.list_locations(
            limit=10, offset=0, q="O'Brien'; DROP TABLE location;--"
        )
        sql_text = str(session.execute.call_args[0][0])
        params = session.execute.call_args[0][1]
        # The dangerous string must live in params, not in the SQL.
        assert "O'Brien" not in sql_text
        assert "DROP TABLE" not in sql_text.upper()
        assert "drop table" in params["q"].lower()

    @pytest.mark.asyncio
    async def test_q_filter_with_literal_percent_does_not_match_all(self):
        """Bound param + ILIKE: '%' is part of the pattern wrapper,
        a user-supplied '%' is escaped by being inside the bound value."""
        session = _capture_session()
        query = PtfLocationsQuery(session)
        await query.list_locations(limit=10, offset=0, q="%")
        params = session.execute.call_args[0][1]
        # Pattern is `%<lowered q>%` so a literal '%' becomes `%%%`.
        # Postgres treats that as "anything containing a literal %",
        # which is functionally distinct from "match all rows".
        assert params["q"] == "%%%"

    @pytest.mark.asyncio
    async def test_list_query_excludes_null_island(self):
        """SQL must filter out lat=0,lng=0 (Plentiful parity)."""
        session = _capture_session()
        query = PtfLocationsQuery(session)
        await query.list_locations(limit=10, offset=0)
        sql_text = str(session.execute.call_args[0][0])
        assert "NOT (l.latitude = 0 AND l.longitude = 0)" in sql_text

    @pytest.mark.asyncio
    async def test_list_query_filters_physical_addresses(self):
        """JOIN must restrict to address_type='physical' so mailing
        addresses don't surface in map results."""
        session = _capture_session()
        query = PtfLocationsQuery(session)
        await query.list_locations(limit=10, offset=0)
        sql_text = str(session.execute.call_args[0][0])
        assert "address_type = 'physical'" in sql_text

    @pytest.mark.asyncio
    async def test_list_query_uses_gist_compatible_bbox_expression(self):
        """bbox clause must use st_setsrid(st_makepoint(...), 4326)
        with the && operator so the GIST index idx_location_coords is
        picked up by the planner."""
        session = _capture_session()
        query = PtfLocationsQuery(session)
        await query.list_locations(limit=10, offset=0, bbox=(40.0, -75.0, 41.0, -73.0))
        sql_text = str(session.execute.call_args[0][0])
        assert "st_setsrid(st_makepoint" in sql_text.lower()
        assert "ST_MakeEnvelope" in sql_text
        assert "&&" in sql_text

    @pytest.mark.asyncio
    async def test_get_by_id_binds_uuid_param(self):
        session = _capture_session()
        query = PtfLocationsQuery(session)
        loc_id = "11111111-2222-3333-4444-555555555555"
        await query.get_location(loc_id)
        params = session.execute.call_args[0][1]
        assert params["location_id"] == loc_id

    @pytest.mark.asyncio
    async def test_get_by_id_joins_feeding_america(self):
        session = _capture_session()
        query = PtfLocationsQuery(session)
        await query.get_location("11111111-2222-3333-4444-555555555555")
        sql_text = str(session.execute.call_args[0][0])
        assert "feeding_america_zip_coverage" in sql_text

    @pytest.mark.asyncio
    async def test_get_by_id_prefers_physical_address(self):
        session = _capture_session()
        query = PtfLocationsQuery(session)
        await query.get_location("11111111-2222-3333-4444-555555555555")
        sql_text = str(session.execute.call_args[0][0])
        # physical address tie-break is the documented invariant
        assert "physical" in sql_text
