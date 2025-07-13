"""Tests for the location creation utilities."""

import uuid
from typing import Dict, Union
from unittest.mock import MagicMock, patch

import pytest
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import TextClause

from app.reconciler.location_creator import LocationCreator


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
def test_location_data() -> Dict[str, Union[str, float]]:
    """Create test location data."""
    return {
        "name": "Test Location",
        "description": "Test Description",
        "latitude": 37.7749,
        "longitude": -122.4194,
    }


@pytest.fixture
def test_address_data() -> Dict[str, str]:
    """Create test address data."""
    return {
        "address_1": "123 Test St",
        "city": "Test City",
        "state_province": "CA",
        "postal_code": "94105",
        "country": "US",
        "address_type": "physical",
    }


def test_find_matching_location_found(mock_db: MagicMock) -> None:
    """Test finding matching location when one exists."""
    location_creator = LocationCreator(mock_db)
    existing_id = str(uuid.uuid4())

    # Mock database response
    result = MagicMock()
    result.first.return_value = (existing_id,)
    mock_db.execute.return_value = result

    result = location_creator.find_matching_location(37.7749, -122.4194)

    # Verify result
    assert result == existing_id

    # Verify SQL execution
    mock_db.execute.assert_called_once()
    call_args = mock_db.execute.call_args
    assert isinstance(call_args[0][0], TextClause)
    assert call_args[0][1] == {
        "latitude": 37.7749,
        "longitude": -122.4194,
        "tolerance": 0.0001,
    }


def test_find_matching_location_not_found(mock_db: MagicMock) -> None:
    """Test finding matching location when none exists."""
    location_creator = LocationCreator(mock_db)

    # Mock database response
    result = MagicMock()
    result.first.return_value = None
    mock_db.execute.return_value = result

    result = location_creator.find_matching_location(37.7749, -122.4194)

    # Verify result
    assert result is None


def test_create_location(
    mock_db: MagicMock, test_location_data: Dict[str, Union[str, float]]
) -> None:
    """Test creating a new location."""
    location_creator = LocationCreator(mock_db)

    # Mock version tracker
    with patch(
        "app.reconciler.location_creator.VersionTracker"
    ) as mock_version_tracker, patch(
        "app.reconciler.location_creator.MergeStrategy"
    ) as mock_merge_strategy:
        mock_tracker_instance = MagicMock()
        mock_version_tracker.return_value = mock_tracker_instance

        # Mock database response for location creation
        location_result = MagicMock()
        # Mock database response for source record creation
        source_result = MagicMock()
        source_result.first.return_value = ("source_id",)

        # Set up the mock to return different results for each call
        mock_db.execute.side_effect = [location_result, source_result]

        location_id = location_creator.create_location(
            str(test_location_data["name"]),
            str(test_location_data["description"]),
            float(test_location_data["latitude"]),
            float(test_location_data["longitude"]),
            {"scraper_id": "test_scraper"},
        )

        # Verify SQL execution - should be called twice
        assert mock_db.execute.call_count == 2

        # First call should be for location creation
        location_call = mock_db.execute.call_args_list[0]
        assert isinstance(location_call[0][0], TextClause)
        assert location_call[0][1]["name"] == test_location_data["name"]
        assert location_call[0][1]["description"] == test_location_data["description"]
        assert location_call[0][1]["latitude"] == test_location_data["latitude"]
        assert location_call[0][1]["longitude"] == test_location_data["longitude"]

        # Second call should be for source record creation
        source_call = mock_db.execute.call_args_list[1]
        assert isinstance(source_call[0][0], TextClause)
        assert source_call[0][1]["location_id"] == location_id
        assert source_call[0][1]["scraper_id"] == "test_scraper"

        # Verify version was created
        assert mock_tracker_instance.create_version.call_count >= 1
        version_call = mock_tracker_instance.create_version.call_args_list[0]
        assert version_call[0][0] == location_id
        assert version_call[0][1] == "location"
        assert version_call[0][3] == "reconciler"


def test_create_address(mock_db: MagicMock, test_address_data: Dict[str, str]) -> None:
    """Test creating a new address."""
    location_creator = LocationCreator(mock_db)
    location_id = str(uuid.uuid4())

    # Mock version tracker
    with patch(
        "app.reconciler.location_creator.VersionTracker"
    ) as mock_version_tracker:
        mock_tracker_instance = MagicMock()
        mock_version_tracker.return_value = mock_tracker_instance

        # Mock database response
        result = MagicMock()
        mock_db.execute.return_value = result

        address_id = location_creator.create_address(
            test_address_data["address_1"],
            test_address_data["city"],
            test_address_data["state_province"],
            test_address_data["postal_code"],
            test_address_data["country"],
            test_address_data["address_type"],
            {"source": "test"},
            location_id,
        )

        # Verify address SQL execution
        assert mock_db.execute.call_count == 2  # Address insert + location update
        address_call = mock_db.execute.call_args_list[0]
        assert isinstance(address_call[0][0], TextClause)
        assert address_call[0][1]["address_1"] == test_address_data["address_1"]
        assert address_call[0][1]["city"] == test_address_data["city"]
        assert address_call[0][1]["location_id"] == location_id

        # Verify location name update
        location_call = mock_db.execute.call_args_list[1]
        assert isinstance(location_call[0][0], TextClause)
        assert location_call[0][1]["name"] == test_address_data["city"]
        assert location_call[0][1]["id"] == location_id

        # Verify version was created
        mock_tracker_instance.create_version.assert_called_once()
        version_call = mock_tracker_instance.create_version.call_args
        assert version_call[0][0] == address_id
        assert version_call[0][1] == "address"
        assert version_call[0][3] == "reconciler"


def test_create_accessibility(mock_db: MagicMock) -> None:
    """Test creating a new accessibility record."""
    location_creator = LocationCreator(mock_db)
    location_id = str(uuid.uuid4())

    # Mock version tracker
    with patch(
        "app.reconciler.location_creator.VersionTracker"
    ) as mock_version_tracker:
        mock_tracker_instance = MagicMock()
        mock_version_tracker.return_value = mock_tracker_instance

        # Mock database response
        result = MagicMock()
        mock_db.execute.return_value = result

        accessibility_id = location_creator.create_accessibility(
            location_id,
            {"source": "test"},
            description="Test accessibility",
            details="Test details",
            url="http://test.com",
        )

        # Verify SQL execution
        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        assert isinstance(call_args[0][0], TextClause)
        assert call_args[0][1]["location_id"] == location_id
        assert call_args[0][1]["description"] == "Test accessibility"
        assert call_args[0][1]["details"] == "Test details"
        assert call_args[0][1]["url"] == "http://test.com"

        # Verify version was created
        mock_tracker_instance.create_version.assert_called_once()
        version_call = mock_tracker_instance.create_version.call_args
        assert version_call[0][0] == accessibility_id
        assert version_call[0][1] == "accessibility"
        assert version_call[0][3] == "reconciler"
