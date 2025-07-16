"""Tests for the organization creation utilities."""

import uuid
import time
from typing import Dict
from unittest.mock import MagicMock, patch, call

import pytest
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import TextClause
from sqlalchemy.exc import IntegrityError

from app.reconciler.organization_creator import OrganizationCreator


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
def test_org_data() -> Dict[str, str]:
    """Create test organization data with required and optional fields."""
    return {
        # Required fields
        "name": "Test Organization",
        "description": "Test Description",
        # Optional fields
        "website": "https://test.org",
        "email": "contact@test.org",
        "legal_status": "nonprofit",
        "tax_status": "501c3",
        "tax_id": "12-3456789",
        "uri": "https://test.org/id/123",
    }


@pytest.fixture
def test_identifier_data() -> Dict[str, str]:
    """Create test organization identifier data."""
    return {"identifier_type": "EIN", "identifier": "12-3456789"}


def test_create_organization(mock_db: MagicMock, test_org_data: Dict[str, str]) -> None:
    """Test creating a new organization."""
    org_creator = OrganizationCreator(mock_db)

    # Mock version tracker
    with patch(
        "app.reconciler.organization_creator.VersionTracker"
    ) as mock_version_tracker:
        mock_tracker_instance = MagicMock()
        mock_version_tracker.return_value = mock_tracker_instance

        org_id = org_creator.create_organization(
            test_org_data["name"],
            test_org_data["description"],
            {"source": "test"},
            website=test_org_data["website"],
            email=test_org_data["email"],
            legal_status=test_org_data["legal_status"],
            tax_status=test_org_data["tax_status"],
            tax_id=test_org_data["tax_id"],
            uri=test_org_data["uri"],
        )

        # Verify SQL execution
        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        assert isinstance(call_args[0][0], TextClause)
        assert call_args[0][1]["name"] == test_org_data["name"]
        assert call_args[0][1]["description"] == test_org_data["description"]
        assert call_args[0][1]["website"] == test_org_data["website"]
        assert call_args[0][1]["email"] == test_org_data["email"]
        assert call_args[0][1]["legal_status"] == test_org_data["legal_status"]
        assert call_args[0][1]["tax_status"] == test_org_data["tax_status"]
        assert call_args[0][1]["tax_id"] == test_org_data["tax_id"]
        assert call_args[0][1]["uri"] == test_org_data["uri"]

        # Verify version was created
        mock_tracker_instance.create_version.assert_called_once()
        version_call = mock_tracker_instance.create_version.call_args
        # Compare str representations to handle UUID vs string
        assert str(version_call[0][0]) == str(org_id)
        assert version_call[0][1] == "organization"
        assert version_call[0][3] == "reconciler"


def test_create_organization_minimal(
    mock_db: MagicMock, test_org_data: Dict[str, str]
) -> None:
    """Test creating a new organization with minimal data."""
    org_creator = OrganizationCreator(mock_db)

    # Mock version tracker
    with patch(
        "app.reconciler.organization_creator.VersionTracker"
    ) as mock_version_tracker:
        mock_tracker_instance = MagicMock()
        mock_version_tracker.return_value = mock_tracker_instance

        org_id = org_creator.create_organization(
            test_org_data["name"], test_org_data["description"], {"source": "test"}
        )

        # Verify SQL execution
        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        assert isinstance(call_args[0][0], TextClause)
        assert call_args[0][1]["name"] == test_org_data["name"]
        assert call_args[0][1]["description"] == test_org_data["description"]
        assert call_args[0][1]["website"] is None
        assert call_args[0][1]["email"] is None
        assert call_args[0][1]["legal_status"] is None
        assert call_args[0][1]["tax_status"] is None
        assert call_args[0][1]["tax_id"] is None
        assert call_args[0][1]["uri"] is None

        # Verify version was created
        mock_tracker_instance.create_version.assert_called_once()
        version_call = mock_tracker_instance.create_version.call_args
        # Compare str representations to handle UUID vs string
        assert str(version_call[0][0]) == str(org_id)
        assert version_call[0][1] == "organization"
        assert version_call[0][3] == "reconciler"


def test_create_organization_identifier(
    mock_db: MagicMock, test_identifier_data: Dict[str, str]
) -> None:
    """Test creating a new organization identifier."""
    org_creator = OrganizationCreator(mock_db)
    org_id = uuid.uuid4()

    identifier_id = org_creator.create_organization_identifier(
        org_id,
        test_identifier_data["identifier_type"],
        test_identifier_data["identifier"],
    )

    # Verify SQL execution
    mock_db.execute.assert_called_once()
    call_args = mock_db.execute.call_args
    assert isinstance(call_args[0][0], TextClause)
    assert call_args[0][1]["organization_id"] == str(org_id)
    assert call_args[0][1]["identifier_type"] == test_identifier_data["identifier_type"]
    assert call_args[0][1]["identifier"] == test_identifier_data["identifier"]

    # Verify commit was called and identifier was created
    mock_db.commit.assert_called_once()
    assert isinstance(identifier_id, uuid.UUID)


def test_create_organization_source(
    mock_db: MagicMock, test_org_data: Dict[str, str]
) -> None:
    """Test creating a new organization source record."""
    org_creator = OrganizationCreator(mock_db)
    org_id = str(uuid.uuid4())
    scraper_id = "test_scraper"

    # Mock database result for INSERT...ON CONFLICT
    result = MagicMock()
    result.first.return_value = ["test-source-id"]
    mock_db.execute.return_value = result

    # Mock version tracker
    with patch(
        "app.reconciler.organization_creator.VersionTracker"
    ) as mock_version_tracker:
        mock_tracker_instance = MagicMock()
        mock_version_tracker.return_value = mock_tracker_instance

        source_id = org_creator.create_organization_source(
            org_id,
            scraper_id,
            test_org_data["name"],
            test_org_data["description"],
            {"source": "test"},
            website=test_org_data["website"],
            email=test_org_data["email"],
            legal_status=test_org_data["legal_status"],
            tax_status=test_org_data["tax_status"],
            tax_id=test_org_data["tax_id"],
            uri=test_org_data["uri"],
        )

        # Verify SQL execution
        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        assert isinstance(call_args[0][0], TextClause)
        assert call_args[0][1]["organization_id"] == org_id
        assert call_args[0][1]["scraper_id"] == scraper_id
        assert call_args[0][1]["name"] == test_org_data["name"]
        assert call_args[0][1]["description"] == test_org_data["description"]
        assert call_args[0][1]["website"] == test_org_data["website"]
        assert call_args[0][1]["email"] == test_org_data["email"]

        # Verify version was created
        mock_tracker_instance.create_version.assert_called_once()
        version_call = mock_tracker_instance.create_version.call_args
        assert version_call[0][0] == "test-source-id"
        assert version_call[0][1] == "organization_source"
        assert version_call[0][3] == "reconciler"

        # Verify commit was called
        mock_db.commit.assert_called_once()
        assert source_id == "test-source-id"


def test_create_organization_source_no_result(
    mock_db: MagicMock, test_org_data: Dict[str, str]
) -> None:
    """Test creating organization source when query returns no result."""
    org_creator = OrganizationCreator(mock_db)
    org_id = str(uuid.uuid4())
    scraper_id = "test_scraper"

    # Mock database result for INSERT...ON CONFLICT returning None
    result = MagicMock()
    result.first.return_value = None
    mock_db.execute.return_value = result

    # Mock version tracker
    with patch(
        "app.reconciler.organization_creator.VersionTracker"
    ) as mock_version_tracker:
        mock_tracker_instance = MagicMock()
        mock_version_tracker.return_value = mock_tracker_instance

        source_id = org_creator.create_organization_source(
            org_id,
            scraper_id,
            test_org_data["name"],
            test_org_data["description"],
            {"source": "test"},
        )

        # Should still create version with original UUID
        mock_tracker_instance.create_version.assert_called_once()
        version_call = mock_tracker_instance.create_version.call_args
        assert len(version_call[0][0]) == 36  # UUID string length
        assert version_call[0][1] == "organization_source"


def test_retry_with_backoff_success(mock_db: MagicMock) -> None:
    """Test retry with backoff succeeds on first attempt."""
    org_creator = OrganizationCreator(mock_db)

    # Mock operation that succeeds
    mock_operation = MagicMock(return_value="success")

    result = org_creator._retry_with_backoff(mock_operation)

    assert result == "success"
    mock_operation.assert_called_once()


def test_retry_with_backoff_retry_and_succeed(mock_db: MagicMock) -> None:
    """Test retry with backoff retries on IntegrityError then succeeds."""
    org_creator = OrganizationCreator(mock_db)

    # Mock operation that fails once then succeeds
    mock_operation = MagicMock(side_effect=[IntegrityError("", "", ""), "success"])

    with patch("time.sleep") as mock_sleep, patch(
        "app.reconciler.organization_creator.secrets.SystemRandom"
    ) as mock_random:
        mock_random.return_value.uniform.return_value = 0.1

        result = org_creator._retry_with_backoff(mock_operation)

        assert result == "success"
        assert mock_operation.call_count == 2
        mock_sleep.assert_called_once()


def test_retry_with_backoff_max_retries(mock_db: MagicMock) -> None:
    """Test retry with backoff fails after max retries."""
    org_creator = OrganizationCreator(mock_db)

    # Mock operation that always fails
    error = IntegrityError("", "", "")
    mock_operation = MagicMock(side_effect=error)

    # Mock _log_constraint_violation to avoid database calls
    with patch.object(org_creator, "_log_constraint_violation") as mock_log, patch(
        "time.sleep"
    ) as mock_sleep:

        with pytest.raises(IntegrityError):
            org_creator._retry_with_backoff(mock_operation, max_attempts=3)

        assert mock_operation.call_count == 3
        mock_log.assert_called_once()
        assert mock_sleep.call_count == 2  # Should sleep 2 times (attempts 1 and 2)


def test_log_constraint_violation_success(mock_db: MagicMock) -> None:
    """Test logging constraint violation succeeds."""
    org_creator = OrganizationCreator(mock_db)

    org_creator._log_constraint_violation(
        "organization", "INSERT", {"error": "duplicate key", "attempt": 1}
    )

    # Verify SQL execution for logging
    mock_db.execute.assert_called_once()
    call_args = mock_db.execute.call_args
    assert isinstance(call_args[0][0], TextClause)
    assert call_args[0][1]["table_name"] == "organization"
    assert call_args[0][1]["operation"] == "INSERT"
    assert "duplicate key" in call_args[0][1]["conflicting_data"]

    mock_db.commit.assert_called_once()


def test_log_constraint_violation_exception(mock_db: MagicMock) -> None:
    """Test logging constraint violation handles exceptions."""
    org_creator = OrganizationCreator(mock_db)

    # Mock database execute to raise exception
    mock_db.execute.side_effect = Exception("Database error")

    # Mock logger to verify error is logged
    with patch.object(org_creator, "logger") as mock_logger:
        org_creator._log_constraint_violation(
            "organization", "INSERT", {"error": "duplicate key", "attempt": 1}
        )

        # Should log the error but not raise
        mock_logger.error.assert_called_once()
        assert "Failed to log constraint violation" in mock_logger.error.call_args[0][0]


def test_process_organization_new(
    mock_db: MagicMock, test_org_data: Dict[str, str]
) -> None:
    """Test processing a new organization."""
    org_creator = OrganizationCreator(mock_db)

    # Create a valid UUID string for testing
    test_uuid_str = str(uuid.uuid4())

    # Mock database result for INSERT...ON CONFLICT (new organization)
    result = MagicMock()
    result.first.return_value = [test_uuid_str, True]  # (id, is_new)
    mock_db.execute.return_value = result

    # Mock all dependencies
    with patch(
        "app.reconciler.organization_creator.VersionTracker"
    ) as mock_version_tracker, patch.object(
        org_creator, "create_organization_source"
    ) as mock_create_source:

        mock_tracker_instance = MagicMock()
        mock_version_tracker.return_value = mock_tracker_instance
        mock_create_source.return_value = "source-id"

        org_id, is_new = org_creator.process_organization(
            test_org_data["name"],
            test_org_data["description"],
            {"scraper_id": "test_scraper"},
            website=test_org_data["website"],
            email=test_org_data["email"],
        )

        # Verify organization was created
        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        assert isinstance(call_args[0][0], TextClause)
        assert call_args[0][1]["name"] == test_org_data["name"]
        assert call_args[0][1]["description"] == test_org_data["description"]
        assert call_args[0][1]["website"] == test_org_data["website"]
        assert call_args[0][1]["email"] == test_org_data["email"]

        # Verify source was created
        mock_create_source.assert_called_once()

        # Verify version was created for new organization
        mock_tracker_instance.create_version.assert_called_once()

        # Verify result
        assert str(org_id) == test_uuid_str
        assert is_new is True


def test_process_organization_existing(
    mock_db: MagicMock, test_org_data: Dict[str, str]
) -> None:
    """Test processing an existing organization."""
    org_creator = OrganizationCreator(mock_db)

    # Create a valid UUID string for testing
    test_uuid_str = str(uuid.uuid4())

    # Mock database result for INSERT...ON CONFLICT (existing organization)
    result = MagicMock()
    result.first.return_value = [test_uuid_str, False]  # (id, is_new)
    mock_db.execute.return_value = result

    # Mock all dependencies
    with patch(
        "app.reconciler.organization_creator.VersionTracker"
    ) as mock_version_tracker, patch.object(
        org_creator, "create_organization_source"
    ) as mock_create_source, patch(
        "app.reconciler.organization_creator.MergeStrategy"
    ) as mock_merge_strategy:

        mock_tracker_instance = MagicMock()
        mock_version_tracker.return_value = mock_tracker_instance
        mock_create_source.return_value = "source-id"
        mock_merge_instance = MagicMock()
        mock_merge_strategy.return_value = mock_merge_instance

        org_id, is_new = org_creator.process_organization(
            test_org_data["name"],
            test_org_data["description"],
            {"scraper_id": "test_scraper"},
            website=test_org_data["website"],
        )

        # Verify source was created
        mock_create_source.assert_called_once()

        # Verify version was NOT created for existing organization
        mock_tracker_instance.create_version.assert_not_called()

        # Verify merge was called for existing organization
        mock_merge_instance.merge_organization.assert_called_once_with(test_uuid_str)

        # Verify result
        assert str(org_id) == test_uuid_str
        assert is_new is False


def test_process_organization_no_result(
    mock_db: MagicMock, test_org_data: Dict[str, str]
) -> None:
    """Test processing organization when query returns no result."""
    org_creator = OrganizationCreator(mock_db)

    # Mock database result for INSERT...ON CONFLICT returning None
    result = MagicMock()
    result.first.return_value = None
    mock_db.execute.return_value = result

    with patch.object(org_creator, "create_organization_source"):
        with pytest.raises(
            RuntimeError, match="INSERT...ON CONFLICT failed to return a row"
        ):
            org_creator.process_organization(
                test_org_data["name"],
                test_org_data["description"],
                {"scraper_id": "test_scraper"},
            )


def test_process_organization_with_retry(
    mock_db: MagicMock, test_org_data: Dict[str, str]
) -> None:
    """Test processing organization with retry logic."""
    org_creator = OrganizationCreator(mock_db)

    # Create a valid UUID for testing
    test_uuid = uuid.uuid4()

    # Mock retry logic
    with patch.object(org_creator, "_retry_with_backoff") as mock_retry, patch.object(
        org_creator, "create_organization_source"
    ) as mock_create_source:

        mock_retry.return_value = (test_uuid, True)
        mock_create_source.return_value = "source-id"

        org_id, is_new = org_creator.process_organization(
            test_org_data["name"],
            test_org_data["description"],
            {"scraper_id": "test_scraper"},
        )

        # Verify retry was called
        mock_retry.assert_called_once()

        # Verify source was created
        mock_create_source.assert_called_once()

        # Verify result
        assert org_id == test_uuid
        assert is_new is True
