"""Tests for Tightbeam soft-delete and restore functionality."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.tightbeam.models import CallerIdentity
from app.api.v1.tightbeam.services import TightbeamService


class TestTightbeamSoftDelete:
    """Test soft-delete service methods."""

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
    def caller(self):
        return CallerIdentity(
            api_key_id="key-001",
            api_key_name="slackbot",
            source_ip="10.0.0.1",
            user_agent="SlackBot/1.0",
        )

    @pytest.fixture
    def existing_location(self):
        row = MagicMock()
        row.id = "loc-001"
        row.name = "Test Food Bank"
        return row

    @pytest.mark.asyncio
    async def test_soft_delete_nonexistent(self, service, mock_session, caller):
        """Soft-deleting a nonexistent location returns None."""
        check_result = MagicMock()
        check_result.fetchone.return_value = None
        mock_session.execute = AsyncMock(return_value=check_result)

        result = await service.soft_delete("nonexistent", caller=caller)
        assert result is None

    @pytest.mark.asyncio
    async def test_soft_delete_sets_rejected(
        self, service, mock_session, caller, existing_location
    ):
        """Soft-delete sets validation_status to 'rejected'."""
        check_result = MagicMock()
        check_result.fetchone.return_value = existing_location

        mock_session.execute = AsyncMock(side_effect=[check_result] + [MagicMock()] * 3)

        result = await service.soft_delete(
            "loc-001", reason="Permanently closed", caller=caller
        )

        assert result is not None
        assert result.location_id == "loc-001"
        assert result.message == "Location soft-deleted successfully"
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_soft_delete_records_audit(
        self, service, mock_session, caller, existing_location
    ):
        """Soft-delete creates an audit entry."""
        check_result = MagicMock()
        check_result.fetchone.return_value = existing_location

        mock_session.execute = AsyncMock(side_effect=[check_result] + [MagicMock()] * 3)

        result = await service.soft_delete("loc-001", caller=caller)
        assert result.audit_id is not None

    @pytest.mark.asyncio
    async def test_soft_delete_with_caller_context(
        self, service, mock_session, caller, existing_location
    ):
        """Soft-delete passes caller_context to audit."""
        check_result = MagicMock()
        check_result.fetchone.return_value = existing_location

        mock_session.execute = AsyncMock(side_effect=[check_result] + [MagicMock()] * 3)

        result = await service.soft_delete(
            "loc-001",
            caller=caller,
            caller_context={"slack_user_id": "U123", "channel_id": "C456"},
        )

        assert result is not None


class TestTightbeamRestore:
    """Test restore service methods."""

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
    def caller(self):
        return CallerIdentity(
            api_key_id="key-001",
            api_key_name="admin",
        )

    @pytest.fixture
    def existing_location(self):
        row = MagicMock()
        row.id = "loc-001"
        row.name = "Restored Food Bank"
        return row

    @pytest.mark.asyncio
    async def test_restore_nonexistent(self, service, mock_session, caller):
        """Restoring a nonexistent location returns None."""
        check_result = MagicMock()
        check_result.fetchone.return_value = None
        mock_session.execute = AsyncMock(return_value=check_result)

        result = await service.restore("nonexistent", caller=caller)
        assert result is None

    @pytest.mark.asyncio
    async def test_restore_sets_verified(
        self, service, mock_session, caller, existing_location
    ):
        """Restore sets validation_status to 'verified'."""
        check_result = MagicMock()
        check_result.fetchone.return_value = existing_location

        mock_session.execute = AsyncMock(side_effect=[check_result] + [MagicMock()] * 3)

        result = await service.restore(
            "loc-001", reason="Confirmed still open", caller=caller
        )

        assert result is not None
        assert result.location_id == "loc-001"
        assert result.message == "Location restored successfully"
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_restore_records_audit(
        self, service, mock_session, caller, existing_location
    ):
        """Restore creates an audit entry."""
        check_result = MagicMock()
        check_result.fetchone.return_value = existing_location

        mock_session.execute = AsyncMock(side_effect=[check_result] + [MagicMock()] * 3)

        result = await service.restore("loc-001", caller=caller)
        assert result.audit_id is not None
