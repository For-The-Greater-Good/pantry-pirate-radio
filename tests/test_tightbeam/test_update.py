"""Tests for Tightbeam update (append-only upsert) functionality."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.tightbeam.models import CallerIdentity
from app.api.v1.tightbeam.services import TightbeamService


class TestTightbeamUpdate:
    """Test update service methods."""

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
        row.name = "Old Food Bank"
        row.latitude = 40.7128
        row.longitude = -74.006
        row.description = "A food bank"
        row.url = "https://old.example.org"
        return row

    @pytest.fixture
    def existing_address(self):
        row = MagicMock()
        row.address_1 = "123 Old St"
        row.city = "Newark"
        row.state_province = "NJ"
        row.postal_code = "07102"
        return row

    @pytest.mark.asyncio
    async def test_update_nonexistent_location(self, service, mock_session, caller):
        """Updating a nonexistent location returns None."""
        check_result = MagicMock()
        check_result.fetchone.return_value = None
        mock_session.execute = AsyncMock(return_value=check_result)

        result = await service.update_location(
            location_id="nonexistent",
            name="New Name",
            caller=caller,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_update_creates_source_record(
        self, service, mock_session, caller, existing_location, existing_address
    ):
        """Update creates a new location_source row with human_update."""
        # Setup mock returns: check location, check address, insert source,
        # update location, audit, commit
        check_result = MagicMock()
        check_result.fetchone.return_value = existing_location

        addr_result = MagicMock()
        addr_result.fetchone.return_value = existing_address

        mock_session.execute = AsyncMock(
            side_effect=[check_result, addr_result]
            + [MagicMock()] * 4  # insert source, update loc, audit, etc.
        )

        result = await service.update_location(
            location_id="loc-001",
            name="Updated Food Bank",
            caller=caller,
        )

        assert result is not None
        assert result.location_id == "loc-001"
        assert result.source_id is not None
        assert result.audit_id is not None
        assert result.message == "Location updated successfully"

    @pytest.mark.asyncio
    async def test_update_records_audit(
        self, service, mock_session, caller, existing_location, existing_address
    ):
        """Update creates an audit entry with provenance."""
        check_result = MagicMock()
        check_result.fetchone.return_value = existing_location

        addr_result = MagicMock()
        addr_result.fetchone.return_value = existing_address

        mock_session.execute = AsyncMock(
            side_effect=[check_result, addr_result] + [MagicMock()] * 4
        )

        result = await service.update_location(
            location_id="loc-001",
            name="Updated Name",
            caller=caller,
            caller_context={"slack_user_id": "U123"},
        )

        assert result.audit_id is not None
        # Verify commit was called
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_with_address_fields(
        self, service, mock_session, caller, existing_location, existing_address
    ):
        """Update with address fields updates both location and address."""
        check_result = MagicMock()
        check_result.fetchone.return_value = existing_location

        addr_result = MagicMock()
        addr_result.fetchone.return_value = existing_address

        mock_session.execute = AsyncMock(
            side_effect=[check_result, addr_result]
            + [MagicMock()] * 5  # source, loc update, addr update, audit
        )

        result = await service.update_location(
            location_id="loc-001",
            address_1="456 New St",
            city="Boston",
            caller=caller,
        )

        assert result is not None
        # Should have more execute calls for address update
        assert mock_session.execute.call_count >= 4

    @pytest.mark.asyncio
    async def test_update_with_phone(
        self, service, mock_session, caller, existing_location, existing_address
    ):
        """Update with phone number looks up and updates phone."""
        check_result = MagicMock()
        check_result.fetchone.return_value = existing_location

        addr_result = MagicMock()
        addr_result.fetchone.return_value = existing_address

        phone_result = MagicMock()
        phone_row = MagicMock()
        phone_row.number = "555-000-0000"
        phone_result.fetchone.return_value = phone_row

        mock_session.execute = AsyncMock(
            side_effect=[check_result, addr_result, phone_result] + [MagicMock()] * 4
        )

        result = await service.update_location(
            location_id="loc-001",
            phone="555-999-9999",
            caller=caller,
        )

        assert result is not None
