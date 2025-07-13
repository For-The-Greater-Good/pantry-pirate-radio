"""Tests for the organization creation utilities."""

import uuid
from typing import Dict
from unittest.mock import MagicMock, patch

import pytest
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import TextClause

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
