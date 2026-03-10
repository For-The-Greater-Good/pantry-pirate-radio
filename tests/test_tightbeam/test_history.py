"""Tests for Tightbeam audit history functionality."""

import pytest
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.tightbeam.services import TightbeamService


class TestTightbeamHistory:
    """Test history/audit trail service methods."""

    @pytest.fixture
    def mock_session(self):
        session = MagicMock(spec=AsyncSession)
        session.execute = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_session):
        return TightbeamService(mock_session)

    @pytest.mark.asyncio
    async def test_history_nonexistent_location(self, service, mock_session):
        """History for nonexistent location returns None."""
        check_result = MagicMock()
        check_result.fetchone.return_value = None
        mock_session.execute = AsyncMock(return_value=check_result)

        result = await service.get_history("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_history_empty(self, service, mock_session):
        """History for location with no changes returns empty entries."""
        check_result = MagicMock()
        check_result.fetchone.return_value = MagicMock(id="loc-001")

        count_result = MagicMock()
        count_result.scalar.return_value = 0

        data_result = MagicMock()
        data_result.fetchall.return_value = []

        mock_session.execute = AsyncMock(
            side_effect=[check_result, count_result, data_result]
        )

        result = await service.get_history("loc-001")
        assert result is not None
        assert result.location_id == "loc-001"
        assert result.total == 0
        assert len(result.entries) == 0

    @pytest.mark.asyncio
    async def test_history_with_entries(self, service, mock_session):
        """History returns audit entries in reverse chronological order."""
        check_result = MagicMock()
        check_result.fetchone.return_value = MagicMock(id="loc-001")

        count_result = MagicMock()
        count_result.scalar.return_value = 2

        now = datetime.now(UTC)
        entry1 = MagicMock()
        entry1.id = "audit-002"
        entry1.location_id = "loc-001"
        entry1.action = "update"
        entry1.changed_fields = ["name"]
        entry1.previous_values = {"name": "Old"}
        entry1.new_values = {"name": "New"}
        entry1.api_key_id = "key-001"
        entry1.api_key_name = "slackbot"
        entry1.source_ip = "10.0.0.1"
        entry1.user_agent = "SlackBot/1.0"
        entry1.caller_context = {"slack_user_id": "U123"}
        entry1.created_at = now

        entry2 = MagicMock()
        entry2.id = "audit-001"
        entry2.location_id = "loc-001"
        entry2.action = "soft_delete"
        entry2.changed_fields = ["validation_status"]
        entry2.previous_values = {"validation_status": None}
        entry2.new_values = {"validation_status": "rejected"}
        entry2.api_key_id = "key-001"
        entry2.api_key_name = "admin"
        entry2.source_ip = "10.0.0.2"
        entry2.user_agent = "AdminApp/1.0"
        entry2.caller_context = None
        entry2.created_at = now

        data_result = MagicMock()
        data_result.fetchall.return_value = [entry1, entry2]

        mock_session.execute = AsyncMock(
            side_effect=[check_result, count_result, data_result]
        )

        result = await service.get_history("loc-001")
        assert result is not None
        assert result.total == 2
        assert len(result.entries) == 2
        assert result.entries[0].action == "update"
        assert result.entries[1].action == "soft_delete"

    @pytest.mark.asyncio
    async def test_history_pagination(self, service, mock_session):
        """History respects limit and offset."""
        check_result = MagicMock()
        check_result.fetchone.return_value = MagicMock(id="loc-001")

        count_result = MagicMock()
        count_result.scalar.return_value = 100

        data_result = MagicMock()
        data_result.fetchall.return_value = []

        mock_session.execute = AsyncMock(
            side_effect=[check_result, count_result, data_result]
        )

        result = await service.get_history("loc-001", limit=10, offset=20)
        assert result is not None
        assert result.total == 100

    @pytest.mark.asyncio
    async def test_history_provenance_fields(self, service, mock_session):
        """History entries include full provenance fields."""
        check_result = MagicMock()
        check_result.fetchone.return_value = MagicMock(id="loc-001")

        count_result = MagicMock()
        count_result.scalar.return_value = 1

        entry = MagicMock()
        entry.id = "audit-001"
        entry.location_id = "loc-001"
        entry.action = "update"
        entry.changed_fields = ["name", "address_1"]
        entry.previous_values = {"name": "Old", "address_1": "123 Old St"}
        entry.new_values = {"name": "New", "address_1": "456 New St"}
        entry.api_key_id = "key-001"
        entry.api_key_name = "slackbot"
        entry.source_ip = "10.0.0.1"
        entry.user_agent = "SlackBot/1.0"
        entry.caller_context = {
            "slack_user_id": "U123",
            "slack_channel_id": "C456",
            "slack_team_id": "T789",
        }
        entry.created_at = datetime.now(UTC)

        data_result = MagicMock()
        data_result.fetchall.return_value = [entry]

        mock_session.execute = AsyncMock(
            side_effect=[check_result, count_result, data_result]
        )

        result = await service.get_history("loc-001")
        assert result.entries[0].api_key_name == "slackbot"
        assert result.entries[0].caller_context["slack_user_id"] == "U123"
        assert result.entries[0].caller_context["slack_team_id"] == "T789"
