"""Tests for Tightbeam search functionality."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.tightbeam.services import TightbeamService


class TestTightbeamSearch:
    """Test search service methods."""

    @pytest.fixture
    def mock_session(self):
        session = MagicMock(spec=AsyncSession)
        session.execute = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_session):
        return TightbeamService(mock_session)

    @pytest.mark.asyncio
    async def test_search_returns_empty(self, service, mock_session):
        """Search with no matches returns empty results."""
        # Count query returns 0
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        # Data query returns empty
        data_result = MagicMock()
        data_result.fetchall.return_value = []

        mock_session.execute = AsyncMock(side_effect=[count_result, data_result])

        result = await service.search(q="nonexistent")
        assert result.total == 0
        assert len(result.results) == 0

    @pytest.mark.asyncio
    async def test_search_with_name_filter(self, service, mock_session):
        """Search by name returns matching locations."""
        count_result = MagicMock()
        count_result.scalar.return_value = 1

        row = MagicMock()
        row.id = "loc-001"
        row.name = "Test Food Bank"
        row.organization_name = "Test Org"
        row.address_1 = "123 Main St"
        row.city = "Newark"
        row.state = "NJ"
        row.postal_code = "07102"
        row.latitude = 40.7128
        row.longitude = -74.006
        row.phone = "555-123-4567"
        row.email = "info@example.com"
        row.website = "https://example.org"
        row.description = "A food bank"
        row.confidence_score = 85
        row.validation_status = "verified"

        data_result = MagicMock()
        data_result.fetchall.return_value = [row]

        mock_session.execute = AsyncMock(side_effect=[count_result, data_result])

        result = await service.search(name="Food Bank")
        assert result.total == 1
        assert result.results[0].name == "Test Food Bank"
        assert result.results[0].city == "Newark"

    @pytest.mark.asyncio
    async def test_search_excludes_rejected_by_default(self, service, mock_session):
        """Search should exclude rejected locations by default."""
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        data_result = MagicMock()
        data_result.fetchall.return_value = []

        mock_session.execute = AsyncMock(side_effect=[count_result, data_result])

        await service.search(q="food")

        # Verify the SQL contains rejection filter
        call_args = mock_session.execute.call_args_list[0]
        sql_text = str(call_args[0][0])
        assert "rejected" in sql_text.lower()

    @pytest.mark.asyncio
    async def test_search_includes_rejected_when_requested(self, service, mock_session):
        """Search with include_rejected=True should not filter rejected."""
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        data_result = MagicMock()
        data_result.fetchall.return_value = []

        mock_session.execute = AsyncMock(side_effect=[count_result, data_result])

        await service.search(include_rejected=True)

        # With no other filters and include_rejected=True, WHERE should be TRUE
        call_args = mock_session.execute.call_args_list[0]
        sql_text = str(call_args[0][0])
        assert "TRUE" in sql_text

    @pytest.mark.asyncio
    async def test_search_pagination(self, service, mock_session):
        """Search respects limit and offset parameters."""
        count_result = MagicMock()
        count_result.scalar.return_value = 50
        data_result = MagicMock()
        data_result.fetchall.return_value = []

        mock_session.execute = AsyncMock(side_effect=[count_result, data_result])

        result = await service.search(q="food", limit=10, offset=20)
        assert result.limit == 10
        assert result.offset == 20
        assert result.total == 50

    @pytest.mark.asyncio
    async def test_search_multi_field(self, service, mock_session):
        """Search with multiple filters applies all conditions."""
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        data_result = MagicMock()
        data_result.fetchall.return_value = []

        mock_session.execute = AsyncMock(side_effect=[count_result, data_result])

        await service.search(city="Newark", state="NJ", zip_code="07102")

        call_args = mock_session.execute.call_args_list[0]
        sql_text = str(call_args[0][0])
        assert "city" in sql_text.lower()
        assert "state_province" in sql_text.lower()
        assert "postal_code" in sql_text.lower()
