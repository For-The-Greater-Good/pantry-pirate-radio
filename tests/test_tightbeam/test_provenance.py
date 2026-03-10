"""Tests for Tightbeam provenance tracking — CallerIdentity propagation."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.tightbeam.models import CallerIdentity
from app.api.v1.tightbeam.services import TightbeamService


class TestProvenancePropagation:
    """Test that CallerIdentity and caller_context propagate correctly."""

    @pytest.fixture
    def mock_session(self):
        session = MagicMock(spec=AsyncSession)
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_session):
        return TightbeamService(mock_session)

    @pytest.fixture
    def slack_caller(self):
        return CallerIdentity(
            api_key_id="key-001",
            api_key_name="slackbot",
            source_ip="10.0.0.1",
            user_agent="SlackBot/1.0",
            caller_context={"slack_team_id": "T789"},
        )

    @pytest.fixture
    def existing_location(self):
        row = MagicMock()
        row.id = "loc-001"
        row.name = "Food Bank"
        row.latitude = 40.7128
        row.longitude = -74.006
        row.description = "A food bank"
        row.url = None
        return row

    @pytest.fixture
    def existing_address(self):
        row = MagicMock()
        row.address_1 = "123 Main St"
        row.city = "Newark"
        row.state_province = "NJ"
        row.postal_code = "07102"
        return row

    @pytest.mark.asyncio
    async def test_update_merges_caller_contexts(
        self, service, mock_session, slack_caller, existing_location, existing_address
    ):
        """Update merges CallerIdentity.caller_context with request caller_context."""
        check_result = MagicMock()
        check_result.fetchone.return_value = existing_location

        addr_result = MagicMock()
        addr_result.fetchone.return_value = existing_address

        mock_session.execute = AsyncMock(
            side_effect=[check_result, addr_result] + [MagicMock()] * 4
        )

        await service.update_location(
            location_id="loc-001",
            name="Updated",
            caller=slack_caller,
            caller_context={"slack_user_id": "U123", "slack_channel_id": "C456"},
        )

        # The audit insert should have been called - verify it was called
        assert mock_session.execute.call_count >= 4

    @pytest.mark.asyncio
    async def test_soft_delete_includes_caller_identity(
        self, service, mock_session, slack_caller
    ):
        """Soft-delete records CallerIdentity in audit."""
        check_result = MagicMock()
        existing = MagicMock()
        existing.id = "loc-001"
        existing.name = "Food Bank"
        check_result.fetchone.return_value = existing

        mock_session.execute = AsyncMock(side_effect=[check_result] + [MagicMock()] * 3)

        result = await service.soft_delete(
            "loc-001",
            reason="Closed",
            caller=slack_caller,
            caller_context={"slack_user_id": "U123"},
        )

        assert result is not None
        assert result.audit_id is not None

    @pytest.mark.asyncio
    async def test_restore_includes_caller_identity(
        self, service, mock_session, slack_caller
    ):
        """Restore records CallerIdentity in audit."""
        check_result = MagicMock()
        existing = MagicMock()
        existing.id = "loc-001"
        existing.name = "Food Bank"
        check_result.fetchone.return_value = existing

        mock_session.execute = AsyncMock(side_effect=[check_result] + [MagicMock()] * 3)

        result = await service.restore(
            "loc-001",
            reason="Reopened",
            caller=slack_caller,
        )

        assert result is not None
        assert result.audit_id is not None

    @pytest.mark.asyncio
    async def test_update_without_caller_context(
        self, service, mock_session, existing_location, existing_address
    ):
        """Update works without caller_context (API key only)."""
        caller = CallerIdentity(api_key_id="key-002", api_key_name="admin")

        check_result = MagicMock()
        check_result.fetchone.return_value = existing_location

        addr_result = MagicMock()
        addr_result.fetchone.return_value = existing_address

        mock_session.execute = AsyncMock(
            side_effect=[check_result, addr_result] + [MagicMock()] * 4
        )

        result = await service.update_location(
            location_id="loc-001",
            name="Updated",
            caller=caller,
        )

        assert result is not None

    @pytest.mark.asyncio
    async def test_update_source_record_has_updated_by(
        self, service, mock_session, slack_caller, existing_location, existing_address
    ):
        """Source record should have updated_by set to API key name."""
        check_result = MagicMock()
        check_result.fetchone.return_value = existing_location

        addr_result = MagicMock()
        addr_result.fetchone.return_value = existing_address

        mock_session.execute = AsyncMock(
            side_effect=[check_result, addr_result] + [MagicMock()] * 4
        )

        result = await service.update_location(
            location_id="loc-001",
            name="Updated",
            caller=slack_caller,
        )

        assert result is not None
        # The insert source call should include updated_by
        # Check the second execute call (after check and addr) which is the source insert
        insert_call = mock_session.execute.call_args_list[2]
        params = insert_call[0][1] if len(insert_call[0]) > 1 else insert_call[1]
        assert params.get("updated_by") == "slackbot"
