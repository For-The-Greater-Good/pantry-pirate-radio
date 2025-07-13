"""Tests for the version tracking utilities."""

import json
import uuid
from typing import Dict
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import TextClause

from app.reconciler.version_tracker import VersionTracker


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
def test_record_data() -> Dict[str, str]:
    """Create test record data."""
    return {
        "name": "Test Record",
        "description": "Test Description",
        "status": "active",
    }


def test_create_version_new_record(
    mock_db: MagicMock, test_record_data: Dict[str, str]
) -> None:
    """Test creating first version of a record."""
    version_tracker = VersionTracker(mock_db)
    record_id = str(uuid.uuid4())
    record_type = "test_record"

    # Mock the database query result for version number
    mock_result = MagicMock()
    mock_result.first.return_value = None  # No existing versions
    mock_db.execute.return_value = mock_result

    version_tracker.create_version(
        record_id, record_type, test_record_data, "test", source_id=None, commit=True
    )

    # Verify SQL execution
    mock_db.execute.assert_called_once()
    call_args = mock_db.execute.call_args
    # First arg should be SQL text
    assert isinstance(call_args[0][0], TextClause)
    assert call_args[0][1] == {
        "record_id": record_id,
        "record_type": record_type,
        "data": json.dumps(test_record_data),
        "created_by": "test",
        "source_id": None,
    }

    # Verify commit was called
    mock_db.commit.assert_called_once()


def test_create_version_existing_record(
    mock_db: MagicMock, test_record_data: Dict[str, str]
) -> None:
    """Test creating new version of existing record."""
    version_tracker = VersionTracker(mock_db)
    record_id = str(uuid.uuid4())
    record_type = "test_record"

    # Mock the database query result for version number
    mock_result = MagicMock()
    mock_result.first.return_value = (2,)  # Existing version 2
    mock_db.execute.return_value = mock_result

    version_tracker.create_version(
        record_id, record_type, test_record_data, "test", source_id=None, commit=True
    )

    # Verify SQL execution
    mock_db.execute.assert_called_once()
    call_args = mock_db.execute.call_args
    # First arg should be SQL text
    assert isinstance(call_args[0][0], TextClause)
    assert call_args[0][1] == {
        "record_id": record_id,
        "record_type": record_type,
        "data": json.dumps(test_record_data),
        "created_by": "test",
        "source_id": None,
    }

    # Verify commit was called
    mock_db.commit.assert_called_once()


def test_create_version_no_commit(
    mock_db: MagicMock, test_record_data: Dict[str, str]
) -> None:
    """Test creating version without committing."""
    version_tracker = VersionTracker(mock_db)
    record_id = str(uuid.uuid4())
    record_type = "test_record"

    # Mock the database query result
    mock_result = MagicMock()
    mock_result.first.return_value = None
    mock_db.execute.return_value = mock_result

    version_tracker.create_version(
        record_id, record_type, test_record_data, "test", source_id=None, commit=False
    )

    # Verify SQL execution
    mock_db.execute.assert_called_once()

    # Verify commit was not called
    mock_db.commit.assert_not_called()


def test_create_version_with_metrics(
    mock_db: MagicMock, test_record_data: Dict[str, str], mocker: MockerFixture
) -> None:
    """Test version creation updates metrics."""
    # Mock the metrics
    mock_record_versions = mocker.patch(
        "app.reconciler.version_tracker.RECORD_VERSIONS.labels"
    )
    mock_counter = MagicMock()
    mock_record_versions.return_value = mock_counter

    version_tracker = VersionTracker(mock_db)
    record_id = str(uuid.uuid4())
    record_type = "test_record"

    # Mock the database query result
    mock_result = MagicMock()
    mock_result.first.return_value = None
    mock_db.execute.return_value = mock_result

    version_tracker.create_version(
        record_id, record_type, test_record_data, "test", source_id=None, commit=True
    )

    # Verify metrics were updated
    mock_record_versions.assert_called_once_with(record_type=record_type)
    mock_counter.inc.assert_called_once()
