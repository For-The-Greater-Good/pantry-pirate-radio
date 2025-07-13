"""Tests for the PostgreSQL to SQLite exporter."""

import sqlite3
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from app.datasette.exporter import (
    add_datasette_metadata,
    create_sqlite_table,
    export_table_data,
    export_to_sqlite,
    get_table_schema,
)


@pytest.fixture
def sqlite_conn():
    """Create a temporary SQLite database connection."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite") as temp_file:
        conn = sqlite3.connect(temp_file.name)
        yield conn
        conn.close()


def test_get_table_schema():
    """Test getting table schema from PostgreSQL."""
    # Mock the PostgreSQL connection and result
    mock_conn = MagicMock()
    mock_result = MagicMock()
    mock_conn.execute.return_value = mock_result

    # Mock the result rows
    mock_rows = [
        {
            "column_name": "id",
            "data_type": "integer",
            "is_nullable": "NO",
            "is_primary_key": "YES",
        },
        {
            "column_name": "name",
            "data_type": "character varying",
            "is_nullable": "NO",
            "is_primary_key": "NO",
        },
        {
            "column_name": "description",
            "data_type": "text",
            "is_nullable": "YES",
            "is_primary_key": "NO",
        },
    ]
    mock_result.__iter__.return_value = [MagicMock(**row) for row in mock_rows]

    # Call the function
    result = get_table_schema(mock_conn, "test_table")

    # Verify the result
    assert len(result) == 3
    assert result[0]["column_name"] == "id"
    assert result[1]["data_type"] == "character varying"
    assert result[2]["is_nullable"] == "YES"

    # Verify the SQL queries - one to check if table exists, one to get schema
    assert mock_conn.execute.call_count == 2
    call_args = mock_conn.execute.call_args[0]
    # Check that the query is a SQL text object by checking its string representation
    query_str = str(call_args[0])
    assert "SELECT column_name" in query_str
    assert "data_type" in query_str
    assert "is_nullable" in query_str
    assert "is_primary_key" in query_str
    assert call_args[1] == {"table_name": "test_table"}


def test_create_sqlite_table(sqlite_conn):
    """Test creating a SQLite table from schema."""
    # Define a test schema
    schema = [
        {
            "column_name": "id",
            "data_type": "integer",
            "is_nullable": "NO",
            "is_primary_key": "YES",
        },
        {
            "column_name": "name",
            "data_type": "character varying",
            "is_nullable": "NO",
            "is_primary_key": "NO",
        },
        {
            "column_name": "description",
            "data_type": "text",
            "is_nullable": "YES",
            "is_primary_key": "NO",
        },
        {
            "column_name": "created_at",
            "data_type": "timestamp with time zone",
            "is_nullable": "YES",
            "is_primary_key": "NO",
        },
        {
            "column_name": "is_active",
            "data_type": "boolean",
            "is_nullable": "NO",
            "is_primary_key": "NO",
        },
    ]

    # Create the table
    create_sqlite_table(sqlite_conn, "test_table", schema)

    # Verify the table was created with the correct schema
    cursor = sqlite_conn.cursor()
    cursor.execute("PRAGMA table_info(test_table)")
    columns = cursor.fetchall()

    # Check column count
    assert len(columns) == 5

    # Check column definitions
    column_dict = {
        col[1]: {"type": col[2], "notnull": col[3], "pk": col[5]} for col in columns
    }

    assert column_dict["id"]["type"] == "INTEGER"
    assert column_dict["id"]["pk"] == 1

    assert column_dict["name"]["type"] == "TEXT"
    assert column_dict["name"]["notnull"] == 1

    assert column_dict["description"]["type"] == "TEXT"
    assert column_dict["description"]["notnull"] == 0

    assert column_dict["created_at"]["type"] == "TEXT"

    assert column_dict["is_active"]["type"] == "INTEGER"
    assert column_dict["is_active"]["notnull"] == 1


def test_export_table_data(sqlite_conn):
    """Test exporting data from PostgreSQL to SQLite."""
    # Create a test table in SQLite
    sqlite_conn.execute(
        """
        CREATE TABLE test_table (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            is_active INTEGER NOT NULL
        )
    """
    )

    # Mock the PostgreSQL connection and results
    mock_pg_conn = MagicMock()

    # Mock the table exists check
    mock_exists_result = MagicMock()
    mock_exists_result.scalar.return_value = True

    # Mock the count query
    mock_count_result = MagicMock()
    mock_count_result.fetchone.return_value = [3]  # 3 rows

    # Mock the schema query
    mock_schema_result = MagicMock()
    mock_schema_result.fetchall.return_value = [
        ("id",),
        ("name",),
        ("description",),
        ("is_active",),
    ]

    # Mock the data query
    mock_data_result = MagicMock()
    mock_data_result.fetchall.return_value = [
        (1, "Item 1", "Description 1", True),
        (2, "Item 2", "Description 2", False),
        (3, "Item 3", "Description 3", True),
    ]

    # Set up the execute method to return different results for different queries
    def mock_execute(query, *args, **kwargs):
        query_str = str(query)
        if "EXISTS" in query_str:
            return mock_exists_result
        elif "COUNT(*)" in query_str:
            return mock_count_result
        elif "column_name" in query_str:
            return mock_schema_result
        elif "SELECT *" in query_str:
            return mock_data_result
        return MagicMock()

    mock_pg_conn.execute = MagicMock(side_effect=mock_execute)

    # Call the function
    export_table_data(mock_pg_conn, sqlite_conn, "test_table", 10)

    # Verify the data was inserted correctly
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT * FROM test_table ORDER BY id")
    rows = cursor.fetchall()

    assert len(rows) == 3
    # Boolean True converted to 1
    assert rows[0] == (1, "Item 1", "Description 1", 1)
    # Boolean False converted to 0
    assert rows[1] == (2, "Item 2", "Description 2", 0)
    assert rows[2] == (3, "Item 3", "Description 3", 1)


def test_add_datasette_metadata(sqlite_conn):
    """Test adding metadata for Datasette."""
    # Add metadata
    add_datasette_metadata(sqlite_conn)

    # Verify the metadata table was created
    cursor = sqlite_conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='_datasette_metadata'"
    )
    assert cursor.fetchone() is not None

    # Verify metadata entries
    cursor.execute("SELECT key, value FROM _datasette_metadata")
    metadata = dict(cursor.fetchall())

    assert "title" in metadata
    assert "description" in metadata
    assert "license" in metadata
    assert "source" in metadata
    assert "source_url" in metadata

    # Verify datasette.json table was created
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='datasette_json'"
    )
    assert cursor.fetchone() is not None


def test_create_datasette_views(sqlite_conn):
    """Test creating SQL views for Datasette."""
    # Create required tables for the views
    sqlite_conn.execute(
        """
        CREATE TABLE location (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            latitude REAL,
            longitude REAL,
            is_canonical INTEGER NOT NULL
        )
    """
    )

    sqlite_conn.execute(
        """
        CREATE TABLE location_source (
            id INTEGER PRIMARY KEY,
            location_id INTEGER NOT NULL,
            scraper_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            latitude REAL,
            longitude REAL
        )
    """
    )

    sqlite_conn.execute(
        """
        CREATE TABLE scraper (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        )
    """
    )

    # Insert some test data
    sqlite_conn.execute(
        "INSERT INTO scraper (id, name) VALUES (1, 'Test Scraper 1'), (2, 'Test Scraper 2')"
    )

    sqlite_conn.execute(
        "INSERT INTO location (id, name, description, latitude, longitude, is_canonical) VALUES (1, 'Test Location', 'A test location', 40.7128, -74.0060, 1)"
    )

    sqlite_conn.execute(
        "INSERT INTO location_source (id, location_id, scraper_id, name, description, latitude, longitude) VALUES "
        "(1, 1, 1, 'Test Location', 'A test location', 40.7128, -74.0060), "
        "(2, 1, 2, 'Test Location Alt', 'An alternate description', 40.7129, -74.0061)"
    )

    # Call the function to create views
    from app.datasette.exporter import create_datasette_views

    create_datasette_views(sqlite_conn)

    # Verify the views were created
    cursor = sqlite_conn.cursor()

    # Check that the location_with_sources view was created
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='view' AND name='location_with_sources'"
    )
    assert cursor.fetchone() is not None

    # Check that the multi_source_locations view was created
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='view' AND name='multi_source_locations'"
    )
    assert cursor.fetchone() is not None

    # Check that the locations_by_scraper view was created
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='view' AND name='locations_by_scraper'"
    )
    assert cursor.fetchone() is not None

    # Verify the view data
    cursor.execute("SELECT * FROM multi_source_locations")
    rows = cursor.fetchall()
    assert len(rows) == 1  # We should have one location with multiple sources

    # Verify the locations_by_scraper view
    cursor.execute(
        "SELECT scraper_name, location_name FROM locations_by_scraper ORDER BY scraper_name"
    )
    rows = cursor.fetchall()
    assert len(rows) == 2  # We should have two entries (one for each scraper)
    assert rows[0][0] == "Test Scraper 1"
    assert rows[1][0] == "Test Scraper 2"


@patch("app.datasette.exporter.create_engine")
@patch("app.datasette.exporter.sqlite3.connect")
def test_export_to_sqlite(mock_sqlite_connect, mock_create_engine):
    """Test the full export process."""
    # Mock SQLite connection
    mock_sqlite_conn = MagicMock()
    mock_sqlite_connect.return_value = mock_sqlite_conn

    # Mock PostgreSQL engine and connection
    mock_engine = MagicMock()
    mock_pg_conn = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_pg_conn
    mock_create_engine.return_value = mock_engine

    # Mock the database query that gets table list
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [("organization",), ("location",)]
    mock_pg_conn.execute.return_value = mock_result

    # Mock the get_table_schema function
    with patch("app.datasette.exporter.get_table_schema") as mock_get_schema:
        mock_get_schema.return_value = [
            {
                "column_name": "id",
                "data_type": "integer",
                "is_nullable": "NO",
                "is_primary_key": "YES",
            },
            {
                "column_name": "name",
                "data_type": "text",
                "is_nullable": "NO",
                "is_primary_key": "NO",
            },
        ]

        # Mock the create_sqlite_table function
        with patch("app.datasette.exporter.create_sqlite_table") as mock_create_table:
            # Mock the export_table_data function
            with patch("app.datasette.exporter.export_table_data") as mock_export_data:
                # Mock the add_datasette_metadata function
                with patch(
                    "app.datasette.exporter.add_datasette_metadata"
                ) as mock_add_metadata:
                    # Mock the create_datasette_views function
                    with patch(
                        "app.datasette.exporter.create_datasette_views"
                    ) as mock_create_views:
                        # Call the function
                        result = export_to_sqlite(
                            "test.sqlite", ["organization", "location"]
                        )

                        # Verify the result
                        assert result == "test.sqlite"

                        # Verify the functions were called correctly
                        mock_create_engine.assert_called_once()
                        mock_sqlite_connect.assert_called_once_with("test.sqlite")

                        # Verify get_table_schema was called for each table
                        assert mock_get_schema.call_count == 2

                        # Verify create_sqlite_table was called for each table
                        assert mock_create_table.call_count == 2

                        # Verify export_table_data was called for each table
                        assert mock_export_data.call_count == 2

                        # Verify add_datasette_metadata was called
                        mock_add_metadata.assert_called_once_with(mock_sqlite_conn)

                        # Verify create_datasette_views was called
                        mock_create_views.assert_called_once_with(mock_sqlite_conn)

                        # Verify the SQLite connection was closed
                        mock_sqlite_conn.close.assert_called_once()
