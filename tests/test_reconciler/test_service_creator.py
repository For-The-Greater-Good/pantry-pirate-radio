"""Tests for the service creation utilities."""

import uuid
from typing import Dict, Optional, Union
from unittest.mock import MagicMock, patch

import pytest
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import TextClause

from app.reconciler.service_creator import ServiceCreator


@pytest.fixture
def mock_db(mocker: MockerFixture) -> MagicMock:
    """Create a mock database session."""
    db = MagicMock(spec=Session)
    db.commit.return_value = None

    # Mock database result
    result = MagicMock()
    result.first.return_value = None
    db.execute.return_value = result

    return db


@pytest.fixture
def test_service_data() -> Dict[str, str]:
    """Create test service data."""
    return {
        "name": "Test Service",
        "description": "Test Description",
        "status": "active",
    }


@pytest.fixture
def test_phone_data() -> Dict[str, Union[str, int]]:
    """Create test phone data."""
    return {
        "number": "555-0123",
        "type": "voice",
        "extension": 123,
        "description": "Main line",
    }


@pytest.fixture
def test_schedule_data() -> Dict[str, str]:
    """Create test schedule data."""
    return {
        "freq": "WEEKLY",
        "wkst": "MO",
        "opens_at": "09:00",
        "closes_at": "17:00",
        "byday": "MO,TU,WE,TH,FR",
    }


def test_create_service(mock_db: MagicMock, test_service_data: Dict[str, str]) -> None:
    """Test creating a new service."""
    service_creator = ServiceCreator(mock_db)
    org_id = uuid.uuid4()

    # Mock version tracker
    with patch("app.reconciler.service_creator.VersionTracker") as mock_version_tracker:
        mock_tracker_instance = MagicMock()
        mock_version_tracker.return_value = mock_tracker_instance

        service_id = service_creator.create_service(
            test_service_data["name"],
            test_service_data["description"],
            org_id,
            {"source": "test"},
        )

        # Verify SQL execution
        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        assert isinstance(call_args[0][0], TextClause)
        assert call_args[0][1]["name"] == test_service_data["name"]
        assert call_args[0][1]["description"] == test_service_data["description"]
        assert call_args[0][1]["organization_id"] == str(org_id)

        # Verify version was created
        mock_tracker_instance.create_version.assert_called_once()
        version_call = mock_tracker_instance.create_version.call_args
        # Compare str representations to handle UUID vs string
        assert str(version_call[0][0]) == str(service_id)
        assert version_call[0][1] == "service"
        assert version_call[0][3] == "reconciler"


def test_create_service_at_location(mock_db: MagicMock) -> None:
    """Test creating a new service at location."""
    service_creator = ServiceCreator(mock_db)
    service_id = uuid.uuid4()
    location_id = uuid.uuid4()

    # Mock version tracker
    with patch("app.reconciler.service_creator.VersionTracker") as mock_version_tracker:
        mock_tracker_instance = MagicMock()
        mock_version_tracker.return_value = mock_tracker_instance

        sal_id = service_creator.create_service_at_location(
            service_id, location_id, "Test description", {"source": "test"}
        )

        # Verify SQL execution
        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        assert isinstance(call_args[0][0], TextClause)
        assert call_args[0][1]["service_id"] == str(service_id)
        assert call_args[0][1]["location_id"] == str(location_id)
        assert call_args[0][1]["description"] == "Test description"

        # Verify version was created
        mock_tracker_instance.create_version.assert_called_once()
        version_call = mock_tracker_instance.create_version.call_args
        # Compare str representations to handle UUID vs string
        assert str(version_call[0][0]) == str(sal_id)
        assert version_call[0][1] == "service_at_location"
        assert version_call[0][3] == "reconciler"


def test_create_phone(
    mock_db: MagicMock, test_phone_data: Dict[str, Union[str, Optional[int]]]
) -> None:
    """Test creating a new phone number."""
    service_creator = ServiceCreator(mock_db)
    service_id = uuid.uuid4()

    # Mock version tracker
    with patch("app.reconciler.service_creator.VersionTracker") as mock_version_tracker:
        mock_tracker_instance = MagicMock()
        mock_version_tracker.return_value = mock_tracker_instance

        phone_id = service_creator.create_phone(
            str(test_phone_data["number"]),
            str(test_phone_data["type"]),
            {"source": "test"},
            service_id=service_id,
            extension=123,  # Use literal value since we know it's always 123
            description=str(test_phone_data["description"]),
        )

        # Verify SQL execution
        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        assert isinstance(call_args[0][0], TextClause)
        assert call_args[0][1]["number"] == test_phone_data["number"]
        assert call_args[0][1]["type"] == test_phone_data["type"]
        assert call_args[0][1]["service_id"] == str(service_id)
        assert call_args[0][1]["extension"] == test_phone_data["extension"]
        assert call_args[0][1]["description"] == test_phone_data["description"]

        # Verify version was created
        mock_tracker_instance.create_version.assert_called_once()
        version_call = mock_tracker_instance.create_version.call_args
        # Compare str representations to handle UUID vs string
        assert str(version_call[0][0]) == str(phone_id)
        assert version_call[0][1] == "phone"
        assert version_call[0][3] == "reconciler"


def test_create_language(mock_db: MagicMock) -> None:
    """Test creating a new language."""
    service_creator = ServiceCreator(mock_db)
    service_id = uuid.uuid4()

    # Mock version tracker
    with patch("app.reconciler.service_creator.VersionTracker") as mock_version_tracker:
        mock_tracker_instance = MagicMock()
        mock_version_tracker.return_value = mock_tracker_instance

        language_id = service_creator.create_language(
            {"source": "test"}, name="English", code="en", service_id=service_id
        )

        # Verify SQL execution
        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        assert isinstance(call_args[0][0], TextClause)
        assert call_args[0][1]["name"] == "English"
        assert call_args[0][1]["code"] == "en"
        assert call_args[0][1]["service_id"] == str(service_id)

        # Verify version was created
        mock_tracker_instance.create_version.assert_called_once()
        version_call = mock_tracker_instance.create_version.call_args
        # Compare str representations to handle UUID vs string
        assert str(version_call[0][0]) == str(language_id)
        assert version_call[0][1] == "language"
        assert version_call[0][3] == "reconciler"


def test_process_service(mock_db: MagicMock, test_service_data: Dict[str, str]) -> None:
    """Test processing a service (match or create)."""
    service_creator = ServiceCreator(mock_db)
    org_id = uuid.uuid4()
    service_id = uuid.uuid4()

    # Mock database to return a match first
    result = MagicMock()
    # Mock row more directly using a tuple instead of MagicMock  
    # The query returns (id, is_new) where is_new indicates if it was newly created
    row = (str(service_id), False)  # False means it was found, not created
    result.first.return_value = row
    mock_db.execute.return_value = result

    # Mock MergeStrategy
    with patch("app.reconciler.service_creator.MergeStrategy") as mock_merge_strategy:
        mock_strategy_instance = MagicMock()
        mock_merge_strategy.return_value = mock_strategy_instance

        # Call process_service (should find a match)
        found_id, is_new = service_creator.process_service(
            test_service_data["name"],
            test_service_data["description"],
            org_id,
            {"source": "test", "scraper_id": "test_scraper"},
        )

        # Verify service was found and create_service_source was called
        assert found_id == service_id
        assert is_new is False
        # We expect multiple DB calls for the process_service flow - don't check the exact count
        assert mock_db.execute.call_count >= 1

        # Verify service source merge was attempted
        mock_strategy_instance.merge_service.assert_called_once()
        mock_strategy_instance.merge_service.assert_called_with(str(service_id))

        # Reset mocks
        mock_db.reset_mock()
        mock_strategy_instance.reset_mock()

        # Now test the create path - mock no match found
        result.first.return_value = None
        mock_db.execute.return_value = result

        # Mock service creator to return a new service
        with patch.object(service_creator, "create_service") as mock_create_service:
            mock_create_service.return_value = service_id

            # Call process_service (should create a new one)
            created_id, is_new = service_creator.process_service(
                test_service_data["name"],
                test_service_data["description"],
                org_id,
                {"source": "test", "scraper_id": "test_scraper"},
            )

            # Verify service was created
            assert created_id == service_id
            assert is_new is True
            mock_create_service.assert_called_once()


def test_create_schedule(
    mock_db: MagicMock, test_schedule_data: Dict[str, str]
) -> None:
    """Test creating a new schedule."""
    service_creator = ServiceCreator(mock_db)
    service_id = uuid.uuid4()

    # Mock version tracker
    with patch("app.reconciler.service_creator.VersionTracker") as mock_version_tracker:
        mock_tracker_instance = MagicMock()
        mock_version_tracker.return_value = mock_tracker_instance

        schedule_id = service_creator.create_schedule(
            test_schedule_data["freq"],
            test_schedule_data["wkst"],
            test_schedule_data["opens_at"],
            test_schedule_data["closes_at"],
            {"source": "test"},
            service_id=service_id,
            byday=test_schedule_data["byday"],
        )

        # Verify SQL execution
        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        assert isinstance(call_args[0][0], TextClause)
        assert call_args[0][1]["freq"] == test_schedule_data["freq"]
        assert call_args[0][1]["wkst"] == test_schedule_data["wkst"]
        # Verify time objects
        opens_at = call_args[0][1]["opens_at"]
        closes_at = call_args[0][1]["closes_at"]
        assert hasattr(opens_at, "hour") and hasattr(opens_at, "minute")
        assert hasattr(closes_at, "hour") and hasattr(closes_at, "minute")
        assert call_args[0][1]["service_id"] == str(service_id)
        assert call_args[0][1]["byday"] == test_schedule_data["byday"]

        # Verify version was created
        mock_tracker_instance.create_version.assert_called_once()
        version_call = mock_tracker_instance.create_version.call_args
        # Compare str representations to handle UUID vs string
        assert str(version_call[0][0]) == str(schedule_id)
        assert version_call[0][1] == "schedule"
        assert version_call[0][3] == "reconciler"
