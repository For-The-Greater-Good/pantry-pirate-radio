"""Unit tests for Datasette exporter."""

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from app.datasette.exporter import export_to_sqlite


@pytest.fixture
def temp_sqlite_path():
    """Create a temporary SQLite file path."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        yield f.name
    # Cleanup
    Path(f.name).unlink(missing_ok=True)


@patch("app.datasette.exporter.create_engine")
@patch("app.datasette.exporter.sqlite3.connect")
@patch("app.datasette.exporter.get_table_schema")
@patch("app.datasette.exporter.create_sqlite_table")
@patch("app.datasette.exporter.export_table_data")
@patch("app.datasette.exporter.add_datasette_metadata")
@patch("app.datasette.exporter.create_datasette_views")
def test_export_to_sqlite_basic(
    mock_create_views,
    mock_add_metadata,
    mock_export_data,
    mock_create_table,
    mock_get_schema,
    mock_sqlite_connect,
    mock_create_engine,
    temp_sqlite_path,
):
    """Test basic export functionality."""
    # Mock PostgreSQL engine and connection
    mock_pg_engine = MagicMock()
    mock_create_engine.return_value = mock_pg_engine
    mock_pg_conn = MagicMock()
    mock_pg_engine.connect.return_value.__enter__.return_value = mock_pg_conn

    # Mock table discovery query
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [("test_table",), ("another_table",)]
    mock_pg_conn.execute.return_value = mock_result

    # Mock SQLite connection
    mock_sqlite_conn = MagicMock()
    mock_sqlite_connect.return_value = mock_sqlite_conn

    # Mock schema
    mock_get_schema.return_value = [{"name": "id", "type": "integer"}]

    # Execute export
    result_path = export_to_sqlite(temp_sqlite_path, batch_size=100)

    # Verify the export completed
    assert result_path == temp_sqlite_path
    mock_create_engine.assert_called_once()
    mock_sqlite_connect.assert_called_once_with(temp_sqlite_path)

    # Verify all tables were processed
    assert mock_get_schema.call_count == 2  # Called for each table
    assert mock_create_table.call_count == 2  # Called for each table
    assert mock_export_data.call_count == 2  # Called for each table

    # Verify metadata and views were created
    mock_add_metadata.assert_called_once_with(mock_sqlite_conn)
    mock_create_views.assert_called_once_with(mock_sqlite_conn)


@patch("app.datasette.exporter.create_engine")
def test_export_to_sqlite_connection_error(mock_create_engine):
    """Test export handles connection errors gracefully."""
    # Mock engine creation to raise an exception
    mock_create_engine.side_effect = Exception("Connection failed")

    with pytest.raises(Exception, match="Connection failed"):
        export_to_sqlite("test.sqlite")


@patch("app.datasette.exporter.create_engine")
@patch("app.datasette.exporter.sqlite3.connect")
@patch("app.datasette.exporter.add_datasette_metadata")
@patch("app.datasette.exporter.create_datasette_views")
def test_export_to_sqlite_no_tables(
    mock_create_views,
    mock_add_metadata,
    mock_sqlite_connect,
    mock_create_engine,
    temp_sqlite_path,
):
    """Test export when no tables are found."""
    # Mock PostgreSQL engine and connection
    mock_pg_engine = MagicMock()
    mock_create_engine.return_value = mock_pg_engine
    mock_pg_conn = MagicMock()
    mock_pg_engine.connect.return_value.__enter__.return_value = mock_pg_conn

    # Mock empty table discovery
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []  # No tables found
    mock_pg_conn.execute.return_value = mock_result

    # Mock SQLite connection
    mock_sqlite_conn = MagicMock()
    mock_sqlite_connect.return_value = mock_sqlite_conn

    # Execute export
    result_path = export_to_sqlite(temp_sqlite_path)

    # Should still complete successfully
    assert result_path == temp_sqlite_path
    mock_add_metadata.assert_called_once_with(mock_sqlite_conn)
    mock_create_views.assert_called_once_with(mock_sqlite_conn)


@patch("app.datasette.exporter.create_engine")
@patch("app.datasette.exporter.sqlite3.connect")
@patch("app.datasette.exporter.add_datasette_metadata")
@patch("app.datasette.exporter.create_datasette_views")
def test_export_to_sqlite_default_parameters(
    mock_create_views, mock_add_metadata, mock_sqlite_connect, mock_create_engine
):
    """Test export with default parameters."""
    # Mock basic setup
    mock_pg_engine = MagicMock()
    mock_create_engine.return_value = mock_pg_engine
    mock_pg_conn = MagicMock()
    mock_pg_engine.connect.return_value.__enter__.return_value = mock_pg_conn

    # Mock empty results to avoid complex setup
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    mock_pg_conn.execute.return_value = mock_result

    mock_sqlite_conn = MagicMock()
    mock_sqlite_connect.return_value = mock_sqlite_conn

    # Test default parameters
    result = export_to_sqlite()

    # Should use default output path
    assert result == "pantry_pirate_radio.sqlite"
    mock_sqlite_connect.assert_called_once_with("pantry_pirate_radio.sqlite")


@patch("app.datasette.exporter.create_engine")
@patch("app.datasette.exporter.sqlite3.connect")
@patch("app.datasette.exporter.get_table_schema")
@patch("app.datasette.exporter.create_sqlite_table")
@patch("app.datasette.exporter.export_table_data")
@patch("app.datasette.exporter.add_datasette_metadata")
def test_export_to_sqlite_skip_views(
    mock_add_metadata,
    mock_export_data,
    mock_create_table,
    mock_get_schema,
    mock_sqlite_connect,
    mock_create_engine,
    temp_sqlite_path,
):
    """Test export with create_views=False."""
    # Mock PostgreSQL engine and connection
    mock_pg_engine = MagicMock()
    mock_create_engine.return_value = mock_pg_engine
    mock_pg_conn = MagicMock()
    mock_pg_engine.connect.return_value.__enter__.return_value = mock_pg_conn

    # Mock table discovery
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [("test_table",)]
    mock_pg_conn.execute.return_value = mock_result

    # Mock SQLite connection
    mock_sqlite_conn = MagicMock()
    mock_sqlite_connect.return_value = mock_sqlite_conn

    # Mock schema
    mock_get_schema.return_value = [{"name": "id", "type": "integer"}]

    # Execute export with create_views=False
    with patch("app.datasette.exporter.create_datasette_views") as mock_create_views:
        result_path = export_to_sqlite(temp_sqlite_path, create_views=False)

        # Verify views were not created
        mock_create_views.assert_not_called()

        # But metadata was still added
        mock_add_metadata.assert_called_once_with(mock_sqlite_conn)


def test_export_to_sqlite_specific_tables():
    """Test export with specific table list."""
    with patch("app.datasette.exporter.create_engine") as mock_create_engine, patch(
        "app.datasette.exporter.sqlite3.connect"
    ) as mock_sqlite_connect, patch(
        "app.datasette.exporter.get_table_schema"
    ) as mock_get_schema, patch(
        "app.datasette.exporter.create_sqlite_table"
    ) as mock_create_table, patch(
        "app.datasette.exporter.export_table_data"
    ) as mock_export_data, patch(
        "app.datasette.exporter.add_datasette_metadata"
    ) as mock_add_metadata, patch(
        "app.datasette.exporter.create_datasette_views"
    ) as mock_create_views:

        # Mock PostgreSQL engine and connection
        mock_pg_engine = MagicMock()
        mock_create_engine.return_value = mock_pg_engine
        mock_pg_conn = MagicMock()
        mock_pg_engine.connect.return_value.__enter__.return_value = mock_pg_conn

        # Mock table discovery - all available tables
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [("table1",), ("table2",), ("table3",)]
        mock_pg_conn.execute.return_value = mock_result

        # Mock SQLite connection
        mock_sqlite_conn = MagicMock()
        mock_sqlite_connect.return_value = mock_sqlite_conn

        # Mock schema
        mock_get_schema.return_value = [{"name": "id", "type": "integer"}]

        # Execute export with specific tables
        result_path = export_to_sqlite("test.sqlite", tables=["table1", "table3"])

        # Verify only requested tables were processed
        assert mock_get_schema.call_count == 2  # Only table1 and table3
        assert mock_create_table.call_count == 2
        assert mock_export_data.call_count == 2


@patch("app.datasette.exporter.logger")
def test_export_to_sqlite_missing_tables_warning(mock_logger):
    """Test warning when requested tables don't exist."""
    with patch("app.datasette.exporter.create_engine") as mock_create_engine, patch(
        "app.datasette.exporter.sqlite3.connect"
    ) as mock_sqlite_connect, patch(
        "app.datasette.exporter.add_datasette_metadata"
    ), patch(
        "app.datasette.exporter.create_datasette_views"
    ), patch(
        "app.datasette.exporter.get_table_schema"
    ), patch(
        "app.datasette.exporter.create_sqlite_table"
    ), patch(
        "app.datasette.exporter.export_table_data"
    ):

        # Mock PostgreSQL engine and connection
        mock_pg_engine = MagicMock()
        mock_create_engine.return_value = mock_pg_engine
        mock_pg_conn = MagicMock()
        mock_pg_engine.connect.return_value.__enter__.return_value = mock_pg_conn

        # Mock table discovery - only table1 exists
        mock_execute_result = MagicMock()
        mock_execute_result.fetchall.return_value = [("table1",)]
        mock_pg_conn.execute.return_value = mock_execute_result

        # Mock SQLite connection
        mock_sqlite_conn = MagicMock()
        mock_sqlite_connect.return_value = mock_sqlite_conn

        # Execute export requesting non-existent table
        export_to_sqlite("test.sqlite", tables=["table1", "nonexistent"])

        # Verify warning was logged
        mock_logger.warning.assert_called_with(
            "Requested tables not found in database: nonexistent"
        )
