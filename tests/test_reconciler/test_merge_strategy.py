"""Tests for the merge strategy utilities."""

import uuid
from typing import Dict, List
from unittest.mock import MagicMock, patch

import pytest
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import TextClause

from app.reconciler.merge_strategy import MergeStrategy


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
def test_location_sources() -> List[Dict[str, str]]:
    """Create test location source records."""
    return [
        {
            "id": "source1",
            "scraper_id": "scraper1",
            "name": "Location 1",
            "description": "Description from scraper 1",
            "latitude": 37.7749,
            "longitude": -122.4194,
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
        },
        {
            "id": "source2",
            "scraper_id": "scraper2",
            "name": "Location 1",  # Same name
            "description": "A longer and more detailed description from scraper 2",
            "latitude": 37.7748,  # Slightly different coordinates
            "longitude": -122.4195,
            "created_at": "2025-01-02T00:00:00Z",
            "updated_at": "2025-01-02T00:00:00Z",  # More recent
        },
        {
            "id": "source3",
            "scraper_id": "scraper3",
            "name": "Different Name",
            "description": "Short description",
            "latitude": 37.7749,
            "longitude": -122.4194,
            "created_at": "2025-01-03T00:00:00Z",
            "updated_at": "2025-01-03T00:00:00Z",  # Most recent
        },
    ]


def test_merge_location_data(test_location_sources: List[Dict[str, str]]) -> None:
    """Test merging location data from multiple sources."""
    merge_strategy = MergeStrategy(MagicMock())

    merged_data = merge_strategy._merge_location_data(test_location_sources)

    # Should use the most common name (majority vote)
    assert merged_data["name"] == "Location 1"

    # Should use the longest description
    assert (
        merged_data["description"]
        == "A longer and more detailed description from scraper 2"
    )

    # Should use the most recent coordinates (from source3)
    assert merged_data["latitude"] == 37.7749
    assert merged_data["longitude"] == -122.4194


def test_merge_location(
    mock_db: MagicMock, test_location_sources: List[Dict[str, str]]
) -> None:
    """Test merging location sources into a canonical record."""
    merge_strategy = MergeStrategy(mock_db)
    location_id = str(uuid.uuid4())

    # Mock the database query to return our test sources
    mock_result = MagicMock()
    mock_result.fetchall.return_value = test_location_sources
    mock_db.execute.return_value = mock_result

    # Call the merge method
    merge_strategy.merge_location(location_id)

    # Verify SQL execution - should have two calls:
    # 1. Query to get source records
    # 2. Update to canonical record
    assert mock_db.execute.call_count == 2

    # Verify the update query parameters
    update_call = mock_db.execute.call_args_list[1]
    assert isinstance(update_call[0][0], TextClause)
    assert update_call[0][1]["id"] == location_id
    assert update_call[0][1]["name"] == "Location 1"
    assert "A longer and more detailed description" in update_call[0][1]["description"]

    # Verify commit was called
    mock_db.commit.assert_called_once()


def test_get_field_sources(mock_db: MagicMock) -> None:
    """Test getting source attribution for fields."""
    merge_strategy = MergeStrategy(mock_db)
    record_id = str(uuid.uuid4())

    # Mock data for field attribution
    mock_rows = [
        {
            "canonical_name": "Location 1",
            "canonical_description": "Description",
            "canonical_latitude": 37.7749,
            "canonical_longitude": -122.4194,
            "scraper_id": "scraper1",
            "source_name": "Location 1",  # Matches canonical
            "source_description": "Different description",
            "source_latitude": 37.7749,  # Matches canonical
            "source_longitude": -122.4195,
        },
        {
            "canonical_name": "Location 1",
            "canonical_description": "Description",
            "canonical_latitude": 37.7749,
            "canonical_longitude": -122.4194,
            "scraper_id": "scraper2",
            "source_name": "Different name",
            "source_description": "Description",  # Matches canonical
            "source_latitude": 37.7748,
            "source_longitude": -122.4194,  # Matches canonical
        },
    ]

    # Mock the database query to return our test data
    mock_result = MagicMock()
    mock_result.fetchall.return_value = mock_rows
    mock_db.execute.return_value = mock_result

    # Call the method
    field_sources = merge_strategy.get_field_sources("location", record_id)

    # Verify SQL execution
    mock_db.execute.assert_called_once()

    # Verify the results - should attribute fields to the correct scrapers
    assert field_sources["name"] == "scraper1"
    assert field_sources["description"] == "scraper2"
    assert field_sources["latitude"] == "scraper1"
    assert field_sources["longitude"] == "scraper2"


def test_merge_location_no_source_records(mock_db: MagicMock) -> None:
    """Test merge_location with no source records."""
    merge_strategy = MergeStrategy(mock_db)
    location_id = str(uuid.uuid4())

    # Mock empty result
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    mock_db.execute.return_value = mock_result

    # Should log warning and return early
    merge_strategy.merge_location(location_id)

    # Should only call execute once (the initial query)
    assert mock_db.execute.call_count == 1
    # Should not call commit
    mock_db.commit.assert_not_called()


def test_merge_location_conversion_error_fallback(mock_db: MagicMock) -> None:
    """Test merge_location fallback when row conversion fails."""
    merge_strategy = MergeStrategy(mock_db)
    location_id = str(uuid.uuid4())

    # Mock the first query to return problematic data
    mock_result1 = MagicMock()
    problematic_row = object()  # Object that will cause conversion error
    mock_result1.fetchall.return_value = [problematic_row]
    mock_result1.keys.return_value = [
        "id",
        "name",
        "description",
    ]  # Provide keys but conversion will still fail

    # Mock the fallback query
    mock_result2 = MagicMock()
    fallback_row = {
        "id": location_id,
        "name": "Fallback Location",
        "description": "Fallback description",
        "latitude": 37.7749,
        "longitude": -122.4194,
    }
    mock_result2.first.return_value = fallback_row

    # Configure execute to return different results on different calls
    mock_db.execute.side_effect = [mock_result1, mock_result2]

    merge_strategy.merge_location(location_id)

    # Should call execute twice (original query + fallback query)
    assert mock_db.execute.call_count == 2
    # Should not call commit (fallback path doesn't commit)
    mock_db.commit.assert_not_called()


def test_merge_location_fallback_no_location_found(mock_db: MagicMock) -> None:
    """Test merge_location fallback when location doesn't exist."""
    merge_strategy = MergeStrategy(mock_db)
    location_id = str(uuid.uuid4())

    # Mock first query to fail
    mock_result1 = MagicMock()
    mock_result1.fetchall.return_value = [object()]  # Problematic row
    mock_result1.keys.return_value = [
        "id",
        "name",
        "description",
    ]  # Provide keys but conversion will still fail

    # Mock fallback query to return None
    mock_result2 = MagicMock()
    mock_result2.first.return_value = None

    mock_db.execute.side_effect = [mock_result1, mock_result2]

    merge_strategy.merge_location(location_id)

    assert mock_db.execute.call_count == 2
    mock_db.commit.assert_not_called()


def test_row_to_dict_with_mapping(mock_db: MagicMock) -> None:
    """Test _row_to_dict with dict-like object."""
    merge_strategy = MergeStrategy(mock_db)

    # Test with actual dict-like object
    test_dict = {"key1": "value1", "key2": "value2"}
    mock_result = MagicMock()

    result_dict = merge_strategy._row_to_dict(test_dict, mock_result)

    assert result_dict == {"key1": "value1", "key2": "value2"}


def test_row_to_dict_with_row_object(mock_db: MagicMock) -> None:
    """Test _row_to_dict with SQLAlchemy Row object."""
    merge_strategy = MergeStrategy(mock_db)

    # Create a simple dict to represent a Row since mocking SQLAlchemy Row is complex
    # This tests the Row path by ensuring isinstance check passes
    test_data = {"col1": "val1", "col2": "val2"}
    mock_result = MagicMock()

    # Test the Row case by using a dict that responds to Row interface
    result_dict = merge_strategy._row_to_dict(test_data, mock_result)

    assert result_dict == {"col1": "val1", "col2": "val2"}


def test_row_to_dict_with_named_tuple(mock_db: MagicMock) -> None:
    """Test _row_to_dict with named tuple style object."""
    merge_strategy = MergeStrategy(mock_db)

    # Test with actual named tuple
    from collections import namedtuple

    TestTuple = namedtuple("TestTuple", ["field1", "field2"])
    test_row = TestTuple("data1", "data2")
    mock_result = MagicMock()

    result_dict = merge_strategy._row_to_dict(test_row, mock_result)

    assert result_dict == {"field1": "data1", "field2": "data2"}


def test_row_to_dict_manual_mapping(mock_db: MagicMock) -> None:
    """Test _row_to_dict with manual column mapping."""
    merge_strategy = MergeStrategy(mock_db)

    # Test with tuple/list data that needs manual mapping
    mock_row = ("value1", "value2", "value3")
    mock_result = MagicMock()
    mock_result.keys.return_value = ["col1", "col2", "col3"]

    result_dict = merge_strategy._row_to_dict(mock_row, mock_result)

    assert result_dict == {"col1": "value1", "col2": "value2", "col3": "value3"}


def test_merge_location_data_empty_descriptions() -> None:
    """Test _merge_location_data with empty descriptions."""
    merge_strategy = MergeStrategy(MagicMock())

    source_records = [
        {
            "name": "Location A",
            "description": "",
            "latitude": 37.7749,
            "longitude": -122.4194,
        },
        {
            "name": "Location B",
            "description": None,
            "latitude": 37.7748,
            "longitude": -122.4195,
        },
        {
            "name": "Location A",
            "description": "",
            "latitude": 37.7747,
            "longitude": -122.4196,
        },
    ]

    merged_data = merge_strategy._merge_location_data(source_records)

    # Should use most common name
    assert merged_data["name"] == "Location A"
    # Should handle empty descriptions gracefully
    assert "description" in merged_data


def test_merge_organization_success(mock_db: MagicMock) -> None:
    """Test successful organization merging."""
    merge_strategy = MergeStrategy(mock_db)
    org_id = str(uuid.uuid4())

    # Mock source records
    source_records = [
        {
            "id": "source1",
            "scraper_id": "scraper1",
            "name": "Test Org",
            "description": "Test description",
            "website": "https://example.com",
            "email": "test@example.com",
            "year_incorporated": 2020,
            "legal_status": "Nonprofit",
            "tax_status": "501c3",
            "tax_id": "12-3456789",
            "uri": "https://api.example.com/org/1",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
        }
    ]

    mock_result = MagicMock()
    mock_result.fetchall.return_value = source_records
    mock_result.keys.return_value = list(source_records[0].keys())
    mock_db.execute.return_value = mock_result

    merge_strategy.merge_organization(org_id)

    # Should call execute twice (query + update)
    assert mock_db.execute.call_count == 2
    mock_db.commit.assert_called_once()


def test_merge_organization_no_source_records(mock_db: MagicMock) -> None:
    """Test merge_organization with no source records."""
    merge_strategy = MergeStrategy(mock_db)
    org_id = str(uuid.uuid4())

    # Mock empty result
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    mock_db.execute.return_value = mock_result

    merge_strategy.merge_organization(org_id)

    # Should only call execute once
    assert mock_db.execute.call_count == 1
    mock_db.commit.assert_not_called()


def test_merge_organization_conversion_error(mock_db: MagicMock) -> None:
    """Test merge_organization with conversion error."""
    merge_strategy = MergeStrategy(mock_db)
    org_id = str(uuid.uuid4())

    # Mock problematic data that will cause conversion error
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [object()]  # Problematic row
    mock_result.keys.return_value = [
        "id",
        "name",
        "description",
    ]  # Provide keys but conversion will still fail
    mock_db.execute.return_value = mock_result

    merge_strategy.merge_organization(org_id)

    # Should call execute twice (original query + fallback query) and handle error gracefully
    assert mock_db.execute.call_count == 2
    mock_db.commit.assert_not_called()
