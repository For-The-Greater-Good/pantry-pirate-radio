"""Tests for PTF partner sync service."""

import pytest
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.partners.ptf.services import PtfSyncService


def _make_row(**kwargs):
    """Create a mock DB row with attribute access."""
    row = MagicMock()
    for k, v in kwargs.items():
        setattr(row, k, v)
    row.configure_mock(**kwargs)
    return row


def _location_row(**overrides):
    """Create a standard location row with defaults."""
    defaults = {
        "id": "loc-001",
        "name": "Test Food Bank",
        "description": "Provides food assistance",
        "latitude": 40.7128,
        "longitude": -74.0060,
        "confidence_score": 85,
        "updated_at": datetime(2026, 3, 6, 12, 0, 0, tzinfo=UTC),
        "organization_id": "org-001",
        "org_name": "Test Org",
        "org_description": "An org",
        "email": "info@example.com",
        "org_website": "https://example.org",
        "address_1": "123 Test St",
        "address_2": None,
        "city": "Newark",
        "state_province": "NJ",
        "postal_code": "07102",
    }
    defaults.update(overrides)
    return _make_row(**defaults)


def _mock_execute_factory(
    main_rows=None,
    count_value=0,
    etag_updated=None,
    phone_rows=None,
    schedule_rows=None,
    service_rows=None,
    source_rows=None,
    capture_list=None,
):
    """Build a mock execute side effect with proper query dispatch.

    The key challenge: both count and main queries contain ST_ClusterDBSCAN.
    We distinguish them by checking for 'SELECT COUNT(*) FROM winners' (count)
    vs 'SELECT w_loc.id' (main data query).
    """
    if main_rows is None:
        main_rows = []
    if etag_updated is None:
        etag_updated = datetime(2026, 3, 6, tzinfo=UTC)

    main_result = MagicMock()
    main_result.fetchall.return_value = main_rows

    count_result = MagicMock()
    count_result.scalar_one.return_value = count_value

    etag_result = MagicMock()
    etag_result.fetchone.return_value = _make_row(
        max_updated=etag_updated, total=count_value
    )

    phone_result = MagicMock()
    phone_result.fetchall.return_value = phone_rows or []

    schedule_result = MagicMock()
    schedule_result.fetchall.return_value = schedule_rows or []

    service_result = MagicMock()
    service_result.fetchall.return_value = service_rows or []

    source_result = MagicMock()
    source_result.fetchall.return_value = source_rows or []

    empty_result = MagicMock()
    empty_result.fetchall.return_value = []

    async def mock_execute(*args, **kwargs):
        query_str = str(args[0])
        if capture_list is not None:
            capture_list.append(query_str)

        # ETag query (no ST_ClusterDBSCAN, has MAX)
        if "MAX(" in query_str and "ST_ClusterDBSCAN" not in query_str:
            return etag_result
        # Count query (has ST_ClusterDBSCAN AND COUNT(*) FROM winners)
        if "COUNT(*) FROM winners" in query_str:
            return count_result
        # Main data query (has ST_ClusterDBSCAN but selects w_loc.id)
        if "ST_ClusterDBSCAN" in query_str and "w_loc.id" in query_str:
            return main_result
        # Batch queries
        if "FROM phone" in query_str:
            return phone_result
        if "FROM schedule" in query_str:
            return schedule_result
        if "service_at_location" in query_str and "schedule" not in query_str:
            return service_result
        if "location_source" in query_str:
            return source_result
        return empty_result

    return mock_execute


class TestPtfSyncService:
    """Test the PtfSyncService orchestration."""

    @pytest.fixture
    def mock_session(self):
        return MagicMock(spec=AsyncSession)

    @pytest.fixture
    def service(self, mock_session):
        return PtfSyncService(mock_session)

    @pytest.mark.asyncio
    async def test_sync_returns_correct_structure(self, service, mock_session):
        """Verify response has meta and organizations keys."""
        mock_session.execute = AsyncMock(
            side_effect=_mock_execute_factory(
                main_rows=[_location_row()], count_value=1
            )
        )

        result = await service.sync(page_size=100)

        assert "meta" in result
        assert "organizations" in result
        assert result["meta"]["returned"] == 1
        assert result["meta"]["data_version"] == "1.0"

    @pytest.mark.asyncio
    async def test_phone_normalization_in_sync(self, service, mock_session):
        """Verify phones are normalized to integers."""
        mock_session.execute = AsyncMock(
            side_effect=_mock_execute_factory(
                main_rows=[_location_row()],
                count_value=1,
                phone_rows=[
                    _make_row(
                        location_id="loc-001",
                        organization_id="org-001",
                        number="(555) 123-4567",
                        type="voice",
                        extension=None,
                        description=None,
                    )
                ],
            )
        )

        result = await service.sync(page_size=100)
        org = result["organizations"][0]
        assert org.phone == "5551234567"

    @pytest.mark.asyncio
    async def test_nyc_excluded_by_sql(self, service, mock_session):
        """NYC locations should be excluded by the SQL WHERE clause."""
        captured = []
        mock_session.execute = AsyncMock(
            side_effect=_mock_execute_factory(capture_list=captured)
        )

        await service.sync(page_size=100)

        # Both count and main queries contain the NYC exclusion
        cluster_queries = [q for q in captured if "ST_ClusterDBSCAN" in q]
        assert len(cluster_queries) >= 1
        for q in cluster_queries:
            assert "BROOKLYN" in q.upper()
            assert "MANHATTAN" in q.upper()

    @pytest.mark.asyncio
    async def test_junk_website_filtered(self, service, mock_session):
        """Dropbox/GDrive URLs should be filtered out."""
        mock_session.execute = AsyncMock(
            side_effect=_mock_execute_factory(
                main_rows=[
                    _location_row(org_website="https://drive.google.com/file/d/abc")
                ],
                count_value=1,
            )
        )

        result = await service.sync(page_size=100)
        org = result["organizations"][0]
        assert org.website is None

    @pytest.mark.asyncio
    async def test_pagination_has_more(self, service, mock_session):
        """has_more=True when page_size results returned."""
        locs = [_location_row(id=f"loc-{i}") for i in range(10)]
        mock_session.execute = AsyncMock(
            side_effect=_mock_execute_factory(main_rows=locs, count_value=50)
        )

        result = await service.sync(page_size=10)
        assert result["meta"]["has_more"] is True
        assert result["meta"]["cursor"] is not None
        assert result["meta"]["total_available"] == 50

    @pytest.mark.asyncio
    async def test_timezone_mapping(self, service, mock_session):
        """State should be mapped to IANA timezone."""
        mock_session.execute = AsyncMock(
            side_effect=_mock_execute_factory(
                main_rows=[_location_row(state_province="CA")],
                count_value=1,
            )
        )

        result = await service.sync(page_size=100)
        org = result["organizations"][0]
        assert org.timezone == "America/Los_Angeles"

    @pytest.mark.asyncio
    async def test_sources_humanized(self, service, mock_session):
        """Scraper IDs should be humanized in data_sources."""
        mock_session.execute = AsyncMock(
            side_effect=_mock_execute_factory(
                main_rows=[_location_row()],
                count_value=1,
                source_rows=[
                    _make_row(
                        location_id="loc-001",
                        scraper_id="capital_area_food_bank_dc",
                    )
                ],
            )
        )

        result = await service.sync(page_size=100)
        org = result["organizations"][0]
        assert "Capital Area Food Bank DC" in org.data_sources


class TestCursorEncoding:
    """Test cursor encode/decode roundtrip."""

    def test_roundtrip(self):
        from app.api.v1.partners.ptf.services import _encode_cursor, _decode_cursor

        cursor = _encode_cursor(85, "loc-001")
        conf, loc_id = _decode_cursor(cursor)
        assert conf == 85
        assert loc_id == "loc-001"

    def test_decode_none(self):
        from app.api.v1.partners.ptf.services import _decode_cursor

        assert _decode_cursor(None) == (None, None)

    def test_decode_invalid_raises_value_error(self):
        from app.api.v1.partners.ptf.services import _decode_cursor

        with pytest.raises(ValueError, match="Malformed pagination cursor"):
            _decode_cursor("not-valid-base64!!!")
