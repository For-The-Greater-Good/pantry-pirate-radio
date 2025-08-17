"""
Test confidence score export functionality in HAARRRvest publisher.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import psycopg2
from psycopg2.extras import RealDictCursor

from app.haarrrvest_publisher.export_map_data import MapDataExporter


class TestConfidenceExport:
    """Test confidence score export functionality."""

    @pytest.fixture
    def mock_db_connection(self):
        """Create a mock database connection."""
        with patch(
            "app.haarrrvest_publisher.export_map_data.psycopg2.connect"
        ) as mock_connect:
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn

            # Create mock cursor for context manager
            mock_cursor = MagicMock()

            # Mock cursor for server-side cursor
            mock_server_cursor = MagicMock()

            # Set up the cursor method to return different cursors based on arguments
            def cursor_factory(*args, **kwargs):
                if args and args[0] == "map_export_cursor":  # Server-side cursor
                    return mock_server_cursor
                else:  # Regular cursor (for count query)
                    context_manager = MagicMock()
                    context_manager.__enter__.return_value = mock_cursor
                    context_manager.__exit__.return_value = None
                    return context_manager

            mock_conn.cursor.side_effect = cursor_factory
            mock_server_cursor.__enter__.return_value = mock_server_cursor
            mock_server_cursor.__exit__.return_value = None

            yield mock_conn, mock_cursor, mock_server_cursor

    def test_sql_query_includes_confidence_fields(self, mock_db_connection):
        """Test that SQL query includes confidence fields."""
        mock_conn, mock_cursor, mock_server_cursor = mock_db_connection

        # Mock a location to ensure the query gets executed
        mock_location = {
            "id": "123",
            "lat": 38.9072,
            "lng": -77.0369,
            "name": "Test Food Bank",
            "org": "Test Organization",
            "address": "123 Test St, Washington, DC",
            "city": "Washington",
            "state": "DC",
            "zip": "20001",
            "phone": "555-1234",
            "website": "https://test.org",
            "email": "test@test.org",
            "description": "Test description",
            "address_1": "123 Test St",
            "address_2": None,
            "confidence_score": 85,
            "validation_status": "verified",
            "validation_notes": {"source": "automated"},
            "geocoding_source": "ArcGIS",
        }

        # Setup mock responses - need at least 1 location for query to execute
        mock_cursor.fetchone.return_value = [1]
        mock_server_cursor.fetchmany.side_effect = [[mock_location], []]

        with tempfile.TemporaryDirectory() as tmpdir:
            data_repo_path = Path(tmpdir)
            exporter = MapDataExporter(data_repo_path)

            # Run export
            exporter.export()

            # Check that the query includes confidence fields
            executed_query = mock_server_cursor.execute.call_args[0][0]
            assert "l.confidence_score" in executed_query
            assert "l.validation_status" in executed_query
            assert "l.validation_notes" in executed_query
            assert "l.geocoding_source" in executed_query

            # Check that rejected locations are filtered
            assert "validation_status != 'rejected'" in executed_query

    def test_location_dict_includes_confidence_data(self, mock_db_connection):
        """Test that location dictionaries include confidence data."""
        mock_conn, mock_cursor, mock_server_cursor = mock_db_connection

        # Mock data with confidence fields
        mock_location = {
            "id": "123",
            "lat": 38.9072,
            "lng": -77.0369,
            "name": "Test Food Bank",
            "org": "Test Organization",
            "address": "123 Test St, Washington, DC",
            "city": "Washington",
            "state": "DC",
            "zip": "20001",
            "phone": "555-1234",
            "website": "https://test.org",
            "email": "test@test.org",
            "description": "Test description",
            "address_1": "123 Test St",
            "address_2": None,
            "confidence_score": 85,
            "validation_status": "verified",
            "validation_notes": {"source": "automated"},
            "geocoding_source": "ArcGIS",
        }

        # Setup mock responses
        mock_cursor.fetchone.return_value = [1]  # 1 location
        mock_server_cursor.fetchmany.side_effect = [[mock_location], []]

        with tempfile.TemporaryDirectory() as tmpdir:
            data_repo_path = Path(tmpdir)
            exporter = MapDataExporter(data_repo_path)

            # Run export
            result = exporter.export()
            assert result is True

            # Check output file
            output_file = data_repo_path / "data" / "locations.json"
            assert output_file.exists()

            with open(output_file) as f:
                data = json.load(f)

            assert len(data["locations"]) == 1
            location = data["locations"][0]

            # Verify confidence fields are included
            assert location["confidence_score"] == 85
            assert location["validation_status"] == "verified"
            assert location["geocoding_source"] == "ArcGIS"
            assert location["validation_notes"] == {"source": "automated"}

    def test_metadata_includes_confidence_metrics(self, mock_db_connection):
        """Test that metadata includes confidence metrics."""
        mock_conn, mock_cursor, mock_server_cursor = mock_db_connection

        # Mock multiple locations with varying confidence
        mock_locations = [
            {
                "id": f"loc_{i}",
                "lat": 38.9 + i * 0.01,
                "lng": -77.0 + i * 0.01,
                "name": f"Location {i}",
                "org": "Test Org",
                "address": f"{i} Main St",
                "city": "Washington",
                "state": "DC",
                "zip": "20001",
                "phone": "",
                "website": "",
                "email": "",
                "description": "",
                "address_1": f"{i} Main St",
                "address_2": None,
                "confidence_score": [90, 75, 45, 85, 60][i % 5],
                "validation_status": ["verified", "needs_review"][i % 2],
                "validation_notes": {},
                "geocoding_source": "Census",
            }
            for i in range(5)
        ]

        # Setup mock responses
        mock_cursor.fetchone.return_value = [5]  # 5 locations
        mock_server_cursor.fetchmany.side_effect = [mock_locations, []]

        with tempfile.TemporaryDirectory() as tmpdir:
            data_repo_path = Path(tmpdir)
            exporter = MapDataExporter(data_repo_path)

            # Run export
            result = exporter.export()
            assert result is True

            # Check output file
            output_file = data_repo_path / "data" / "locations.json"
            with open(output_file) as f:
                data = json.load(f)

            # Check metadata
            metadata = data["metadata"]
            assert "confidence_metrics" in metadata
            assert "average_confidence" in metadata["confidence_metrics"]
            assert "high_confidence_locations" in metadata["confidence_metrics"]
            assert metadata["confidence_metrics"]["includes_validation_data"] is True

            # Check average calculation
            expected_avg = (90 + 75 + 45 + 85 + 60) / 5
            assert metadata["confidence_metrics"]["average_confidence"] == round(
                expected_avg, 1
            )

            # Check high confidence count (>= 80)
            assert (
                metadata["confidence_metrics"]["high_confidence_locations"] == 2
            )  # 90 and 85

    def test_default_values_for_missing_confidence_data(self, mock_db_connection):
        """Test that missing confidence data gets appropriate defaults."""
        mock_conn, mock_cursor, mock_server_cursor = mock_db_connection

        # Mock location with NULL confidence fields
        mock_location = {
            "id": "456",
            "lat": 38.9072,
            "lng": -77.0369,
            "name": "Test Location",
            "org": "Test Org",
            "address": "456 Test Ave",
            "city": "Washington",
            "state": "DC",
            "zip": "20002",
            "phone": None,
            "website": None,
            "email": None,
            "description": None,
            "address_1": "456 Test Ave",
            "address_2": None,
            "confidence_score": None,  # NULL in database
            "validation_status": None,  # NULL in database
            "validation_notes": None,  # NULL in database
            "geocoding_source": None,  # NULL in database
        }

        # Setup mock responses
        mock_cursor.fetchone.return_value = [1]
        mock_server_cursor.fetchmany.side_effect = [[mock_location], []]

        with tempfile.TemporaryDirectory() as tmpdir:
            data_repo_path = Path(tmpdir)
            exporter = MapDataExporter(data_repo_path)

            # Run export
            result = exporter.export()
            assert result is True

            # Check output file
            output_file = data_repo_path / "data" / "locations.json"
            with open(output_file) as f:
                data = json.load(f)

            location = data["locations"][0]

            # Verify defaults are applied
            assert location["confidence_score"] == 50  # Default score
            assert location["validation_status"] == "needs_review"  # Default status
            assert location["geocoding_source"] == ""  # Empty string for None
            assert location["validation_notes"] == {}  # Empty dict for None
