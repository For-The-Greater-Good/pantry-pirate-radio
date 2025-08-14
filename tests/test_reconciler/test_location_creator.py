"""Tests for the location creation utilities."""

import uuid
import time
from typing import Dict, Union
from unittest.mock import MagicMock, patch

import pytest
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import TextClause
from sqlalchemy.exc import IntegrityError

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

    # Mock database responses for advisory lock and search
    # First call: acquire_location_lock - returns lock_id
    lock_result = MagicMock()
    lock_result.scalar.return_value = "mock_lock_id"

    # Second call: location search - returns location
    search_result = MagicMock()
    search_result.first.return_value = (existing_id,)

    # Third call: release_location_lock
    release_result = MagicMock()

    # Set up mock_db.execute to return different results for each call
    mock_db.execute.side_effect = [lock_result, search_result, release_result]

    result = location_creator.find_matching_location(37.7749, -122.4194)

    # Verify result
    assert result == existing_id

    # Verify SQL execution - should be called 3 times due to advisory locks
    # 1: acquire_location_lock, 2: location search, 3: release_location_lock
    assert mock_db.execute.call_count == 3

    # Verify the second call (location search) has correct parameters
    location_search_call = mock_db.execute.call_args_list[1]
    assert isinstance(location_search_call[0][0], TextClause)
    assert location_search_call[0][1] == {
        "lat1": 37.7749,
        "lon1": -122.4194,
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


def test_retry_with_backoff_success(mock_db: MagicMock) -> None:
    """Test retry with backoff succeeds on first attempt."""
    location_creator = LocationCreator(mock_db)

    # Mock operation that succeeds
    mock_operation = MagicMock(return_value="success")

    result = location_creator._retry_with_backoff(mock_operation)

    assert result == "success"
    mock_operation.assert_called_once()


def test_retry_with_backoff_retry_and_succeed(mock_db: MagicMock) -> None:
    """Test retry with backoff retries on IntegrityError then succeeds."""
    location_creator = LocationCreator(mock_db)

    # Mock operation that fails once then succeeds
    mock_operation = MagicMock(side_effect=[IntegrityError("", "", ""), "success"])

    with patch("time.sleep") as mock_sleep, patch(
        "app.reconciler.location_creator.secrets.SystemRandom"
    ) as mock_random:
        mock_random.return_value.uniform.return_value = 0.1

        result = location_creator._retry_with_backoff(mock_operation)

        assert result == "success"
        assert mock_operation.call_count == 2
        mock_sleep.assert_called_once()


def test_retry_with_backoff_max_retries(mock_db: MagicMock) -> None:
    """Test retry with backoff fails after max retries."""
    location_creator = LocationCreator(mock_db)

    # Mock operation that always fails
    error = IntegrityError("", "", "")
    mock_operation = MagicMock(side_effect=error)

    # Mock _log_constraint_violation to avoid database calls
    with patch.object(location_creator, "_log_constraint_violation") as mock_log, patch(
        "time.sleep"
    ) as mock_sleep:

        with pytest.raises(IntegrityError):
            location_creator._retry_with_backoff(mock_operation, max_attempts=3)

        assert mock_operation.call_count == 3
        mock_log.assert_called_once()
        assert mock_sleep.call_count == 2  # Should sleep 2 times (attempts 1 and 2)


def test_log_constraint_violation_success(mock_db: MagicMock) -> None:
    """Test logging constraint violation succeeds."""
    location_creator = LocationCreator(mock_db)

    location_creator._log_constraint_violation(
        "location", "INSERT", {"error": "duplicate key", "attempt": 1}
    )

    # Verify SQL execution for logging
    mock_db.execute.assert_called_once()
    call_args = mock_db.execute.call_args
    assert isinstance(call_args[0][0], TextClause)
    assert call_args[0][1]["table_name"] == "location"
    assert call_args[0][1]["operation"] == "INSERT"
    assert "duplicate key" in call_args[0][1]["conflicting_data"]

    mock_db.commit.assert_called_once()


def test_log_constraint_violation_exception(mock_db: MagicMock) -> None:
    """Test logging constraint violation handles exceptions."""
    location_creator = LocationCreator(mock_db)

    # Mock database execute to raise exception
    mock_db.execute.side_effect = Exception("Database error")

    # Mock logger to verify error is logged
    with patch.object(location_creator, "logger") as mock_logger:
        location_creator._log_constraint_violation(
            "location", "INSERT", {"error": "duplicate key", "attempt": 1}
        )

        # Should log the error but not raise
        mock_logger.error.assert_called_once()
        assert "Failed to log constraint violation" in mock_logger.error.call_args[0][0]


def test_process_location_new(
    mock_db: MagicMock, test_location_data: Dict[str, Union[str, float]]
) -> None:
    """Test processing a new location."""
    location_creator = LocationCreator(mock_db)

    # Create a valid UUID for testing
    test_uuid = str(uuid.uuid4())

    # Mock retry with backoff to return new location
    with patch.object(
        location_creator, "_retry_with_backoff"
    ) as mock_retry, patch.object(
        location_creator, "create_location_source"
    ) as mock_create_source, patch(
        "app.reconciler.location_creator.VersionTracker"
    ) as mock_version_tracker:

        mock_retry.return_value = (test_uuid, True)
        mock_create_source.return_value = "source-id"
        mock_tracker_instance = MagicMock()
        mock_version_tracker.return_value = mock_tracker_instance

        location_id, is_new = location_creator.process_location(
            str(test_location_data["name"]),
            str(test_location_data["description"]),
            float(test_location_data["latitude"]),
            float(test_location_data["longitude"]),
            {"scraper_id": "test_scraper"},
        )

        # Verify retry was called
        mock_retry.assert_called_once()

        # Verify source was created
        mock_create_source.assert_called_once()

        # Verify version was created for new location
        mock_tracker_instance.create_version.assert_called_once()

        # Verify result
        assert location_id == test_uuid
        assert is_new is True


def test_process_location_existing(
    mock_db: MagicMock, test_location_data: Dict[str, Union[str, float]]
) -> None:
    """Test processing an existing location."""
    location_creator = LocationCreator(mock_db)

    # Create a valid UUID for testing
    test_uuid = str(uuid.uuid4())

    # Mock retry with backoff to return existing location
    with patch.object(
        location_creator, "_retry_with_backoff"
    ) as mock_retry, patch.object(
        location_creator, "create_location_source"
    ) as mock_create_source, patch(
        "app.reconciler.location_creator.VersionTracker"
    ) as mock_version_tracker, patch(
        "app.reconciler.location_creator.MergeStrategy"
    ) as mock_merge_strategy:

        mock_retry.return_value = (test_uuid, False)
        mock_create_source.return_value = "source-id"
        mock_tracker_instance = MagicMock()
        mock_version_tracker.return_value = mock_tracker_instance
        mock_merge_instance = MagicMock()
        mock_merge_strategy.return_value = mock_merge_instance

        location_id, is_new = location_creator.process_location(
            str(test_location_data["name"]),
            str(test_location_data["description"]),
            float(test_location_data["latitude"]),
            float(test_location_data["longitude"]),
            {"scraper_id": "test_scraper"},
        )

        # Verify retry was called
        mock_retry.assert_called_once()

        # Verify source was created
        mock_create_source.assert_called_once()

        # Verify version was NOT created for existing location
        mock_tracker_instance.create_version.assert_not_called()

        # Verify merge was called
        mock_merge_instance.merge_location.assert_called_once_with(test_uuid)

        # Verify result
        assert location_id == test_uuid
        assert is_new is False


def test_process_location_with_organization_id(
    mock_db: MagicMock, test_location_data: Dict[str, Union[str, float]]
) -> None:
    """Test processing location with organization ID update."""
    location_creator = LocationCreator(mock_db)

    # Create a valid UUID for testing
    test_uuid = str(uuid.uuid4())
    org_id = str(uuid.uuid4())

    # Mock retry with backoff to return existing location
    with patch.object(
        location_creator, "_retry_with_backoff"
    ) as mock_retry, patch.object(
        location_creator, "create_location_source"
    ) as mock_create_source, patch(
        "app.reconciler.location_creator.MergeStrategy"
    ) as mock_merge_strategy:

        mock_retry.return_value = (test_uuid, False)
        mock_create_source.return_value = "source-id"
        mock_merge_instance = MagicMock()
        mock_merge_strategy.return_value = mock_merge_instance

        location_id, is_new = location_creator.process_location(
            str(test_location_data["name"]),
            str(test_location_data["description"]),
            float(test_location_data["latitude"]),
            float(test_location_data["longitude"]),
            {"scraper_id": "test_scraper"},
            organization_id=org_id,
        )

        # Verify retry was called
        mock_retry.assert_called_once()

        # Verify source was created
        mock_create_source.assert_called_once()

        # Verify organization ID update was called
        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        assert isinstance(call_args[0][0], TextClause)
        assert call_args[0][1]["id"] == test_uuid
        assert call_args[0][1]["organization_id"] == org_id

        # Verify merge was called
        mock_merge_instance.merge_location.assert_called_once_with(test_uuid)

        # Verify result
        assert location_id == test_uuid
        assert is_new is False


def test_create_location_source_with_result(
    mock_db: MagicMock, test_location_data: Dict[str, Union[str, float]]
) -> None:
    """Test creating location source when query returns result."""
    location_creator = LocationCreator(mock_db)
    location_id = str(uuid.uuid4())

    # Mock database result for INSERT...ON CONFLICT
    result = MagicMock()
    result.first.return_value = ["returned-source-id"]
    mock_db.execute.return_value = result

    # Mock version tracker
    with patch(
        "app.reconciler.location_creator.VersionTracker"
    ) as mock_version_tracker:
        mock_tracker_instance = MagicMock()
        mock_version_tracker.return_value = mock_tracker_instance

        source_id = location_creator.create_location_source(
            location_id,
            "test_scraper",
            str(test_location_data["name"]),
            str(test_location_data["description"]),
            float(test_location_data["latitude"]),
            float(test_location_data["longitude"]),
            {"source": "test"},
        )

        # Verify SQL execution
        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        assert isinstance(call_args[0][0], TextClause)
        assert call_args[0][1]["location_id"] == location_id
        assert call_args[0][1]["scraper_id"] == "test_scraper"
        assert call_args[0][1]["name"] == test_location_data["name"]
        assert call_args[0][1]["description"] == test_location_data["description"]
        assert call_args[0][1]["latitude"] == test_location_data["latitude"]
        assert call_args[0][1]["longitude"] == test_location_data["longitude"]

        # Verify version was created
        mock_tracker_instance.create_version.assert_called_once()
        version_call = mock_tracker_instance.create_version.call_args
        assert version_call[0][0] == "returned-source-id"
        assert version_call[0][1] == "location_source"
        assert version_call[0][3] == "reconciler"

        # Verify commit was called
        mock_db.commit.assert_called_once()
        assert source_id == "returned-source-id"


def test_create_address_missing_postal_code(mock_db: MagicMock) -> None:
    """Test creating address with missing postal code."""
    location_creator = LocationCreator(mock_db)
    location_id = str(uuid.uuid4())

    # Mock version tracker
    with patch(
        "app.reconciler.location_creator.VersionTracker"
    ) as mock_version_tracker:
        mock_tracker_instance = MagicMock()
        mock_version_tracker.return_value = mock_tracker_instance

        # Mock logger to verify warning is logged
        with patch.object(location_creator, "logger") as mock_logger:
            address_id = location_creator.create_address(
                "123 Test St",
                "Test City",
                "CA",
                "",  # Empty postal code
                "US",
                "physical",
                {"source": "test"},
                location_id,
            )

            # Verify logger warning was called
            mock_logger.warning.assert_called_once()
            assert "Using default postal code" in mock_logger.warning.call_args[0][0]

            # Verify SQL execution with default CA postal code
            address_call = mock_db.execute.call_args_list[0]
            assert isinstance(address_call[0][0], TextClause)
            assert address_call[0][1]["postal_code"] == "90001"  # Default for CA
            assert address_call[0][1]["address_1"] == "123 Test St"
            assert address_call[0][1]["location_id"] == location_id
