#!/usr/bin/env python3
"""
Export PostgreSQL database to SQLite for use with Datasette.

This script exports data from the PostgreSQL database to a SQLite database
that can be used with Datasette for data exploration and visualization.
"""

import json
import logging
import os
import sqlite3
from datetime import datetime
from decimal import Decimal
from typing import Any

import psycopg2
from psycopg2 import OperationalError
from psycopg2.extensions import connection as PgConnection  # noqa: N812
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


def export_to_sqlite(
    pg_conn_string: str | None = None,
    sqlite_path: str = "pantry_pirate_radio.sqlite",
    exclude_tables: list[str] | None = None,
) -> None:
    """
    Export data from PostgreSQL to SQLite.

    Args:
        pg_conn_string: PostgreSQL connection string (defaults to DATABASE_URL env var)
        sqlite_path: Path to the SQLite database file
        exclude_tables: List of table names to exclude from export
    """
    if pg_conn_string is None:
        pg_conn_string = os.environ.get("DATABASE_URL")
        if not pg_conn_string:
            raise ValueError("DATABASE_URL environment variable not set")

        # Convert SQLAlchemy URL to psycopg2 format
        if pg_conn_string.startswith("postgresql+psycopg2://"):
            pg_conn_string = pg_conn_string.replace(
                "postgresql+psycopg2://", "postgresql://"
            )

    # Default tables to exclude
    if exclude_tables is None:
        exclude_tables = []

    logger.info(f"Starting export to {sqlite_path}")

    # Connect to PostgreSQL
    try:
        pg_conn = psycopg2.connect(pg_conn_string, cursor_factory=RealDictCursor)
    except OperationalError as e:
        logger.error(f"Failed to connect to PostgreSQL: {e}")
        raise

    # Create or overwrite SQLite database
    if os.path.exists(sqlite_path):
        os.remove(sqlite_path)

    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row

    try:
        # Get list of tables from PostgreSQL
        with pg_conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public'
                ORDER BY tablename
            """
            )
            tables = [row["tablename"] for row in cursor.fetchall()]

        # Exclude PostGIS-specific tables and any user-specified tables
        exclude_list = ["geography_columns", "geometry_columns", *exclude_tables]
        tables = [t for t in tables if t not in exclude_list]

        logger.info(f"Found {len(tables)} tables in the public schema")
        logger.info(
            f"Exporting {len([t for t in tables if t not in exclude_list])} tables"
        )

        # Export each table
        for table in tables:
            export_table_data(pg_conn, sqlite_conn, table)

        # Add metadata for Datasette
        add_datasette_metadata(sqlite_conn)

        # Create views for easier data exploration
        create_datasette_views(sqlite_conn)

        logger.info(f"Export completed: {sqlite_path}")

    finally:
        pg_conn.close()
        sqlite_conn.close()


def get_table_schema(pg_conn: PgConnection, table_name: str) -> list[dict[str, str]]:
    """
    Get column information for a PostgreSQL table.

    Args:
        pg_conn: PostgreSQL connection
        table_name: Name of the table

    Returns:
        List of column definitions
    """
    with pg_conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                column_name,
                data_type,
                character_maximum_length,
                numeric_precision,
                numeric_scale,
                is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public'
                AND table_name = %s
            ORDER BY ordinal_position
        """,
            (table_name,),
        )
        return cursor.fetchall()


def postgres_to_sqlite_type(pg_type: str) -> str:
    """
    Convert PostgreSQL data type to SQLite data type.

    Args:
        pg_type: PostgreSQL data type

    Returns:
        SQLite data type
    """
    type_mapping = {
        # Numeric types
        "smallint": "INTEGER",
        "integer": "INTEGER",
        "bigint": "INTEGER",
        "decimal": "REAL",
        "numeric": "REAL",
        "real": "REAL",
        "double precision": "REAL",
        "money": "REAL",
        # Text types
        "character varying": "TEXT",
        "character": "TEXT",
        "text": "TEXT",
        "bytea": "BLOB",
        # Date/Time types
        "timestamp": "TEXT",
        "timestamp without time zone": "TEXT",
        "timestamp with time zone": "TEXT",
        "date": "TEXT",
        "time": "TEXT",
        "time without time zone": "TEXT",
        "time with time zone": "TEXT",
        "interval": "TEXT",
        # Boolean
        "boolean": "INTEGER",  # SQLite uses 0/1 for booleans
        # UUID
        "uuid": "TEXT",
        # JSON
        "json": "TEXT",
        "jsonb": "TEXT",
        # Arrays
        "ARRAY": "TEXT",  # Store as JSON
        # Geometric types (PostGIS)
        "geometry": "TEXT",
        "geography": "TEXT",
        # Other
        "inet": "TEXT",
        "cidr": "TEXT",
        "macaddr": "TEXT",
        "USER-DEFINED": "TEXT",  # For custom types like enums
    }

    # Handle array types
    if pg_type.endswith("[]"):
        return "TEXT"

    return type_mapping.get(pg_type, "TEXT")


def create_sqlite_table(
    sqlite_conn: sqlite3.Connection, table_name: str, columns: list[dict[str, Any]]
) -> None:
    """
    Create a table in SQLite based on PostgreSQL schema.

    Args:
        sqlite_conn: SQLite connection
        table_name: Name of the table to create
        columns: List of column definitions from PostgreSQL
    """
    # Build column definitions
    col_defs = []
    for col in columns:
        col_name = col["column_name"]
        pg_type = col["data_type"]
        sqlite_type = postgres_to_sqlite_type(pg_type)

        # Add NOT NULL constraint if applicable
        nullable = "NULL" if col["is_nullable"] == "YES" else "NOT NULL"

        col_def = f'"{col_name}" {sqlite_type} {nullable}'
        col_defs.append(col_def)

    # Create table
    col_defs_str = ",\n    ".join(col_defs)
    create_sql = f'CREATE TABLE "{table_name}" (\n    {col_defs_str}\n)'

    try:
        sqlite_conn.execute(create_sql)
        logger.debug(f"Created table: {table_name}")
    except sqlite3.Error as e:
        logger.error(f"Error creating table {table_name}: {e}")
        logger.error(f"SQL: {create_sql}")
        raise


def convert_value(value: Any, pg_type: str) -> Any:
    """
    Convert PostgreSQL value to SQLite-compatible value.

    Args:
        value: Value to convert
        pg_type: PostgreSQL data type

    Returns:
        Converted value
    """
    if value is None:
        return None

    # Handle arrays - convert to JSON
    if pg_type.endswith("[]") or isinstance(value, list):
        return json.dumps(value)

    # Handle JSON/JSONB
    if pg_type in ["json", "jsonb"]:
        if isinstance(value, dict) or isinstance(value, list):
            return json.dumps(value)
        return value

    # Handle booleans
    if pg_type == "boolean":
        return 1 if value else 0

    # Handle datetime objects
    if isinstance(value, datetime):
        return value.isoformat()

    # Handle time objects
    from datetime import time

    if isinstance(value, time):
        return value.isoformat()

    # Handle geometric types (store as WKT or GeoJSON)
    if pg_type in ["geometry", "geography"]:
        # If it's already a string (WKT), keep it
        if isinstance(value, str):
            return value
        # Otherwise, try to convert to string representation
        return str(value)

    # Handle Decimal values
    if isinstance(value, Decimal):
        return float(value)

    return value


def export_table_data(
    pg_conn: PgConnection, sqlite_conn: sqlite3.Connection, table_name: str
) -> None:
    """
    Export data from a PostgreSQL table to SQLite.

    Args:
        pg_conn: PostgreSQL connection
        sqlite_conn: SQLite connection
        table_name: Name of the table to export
    """
    # Get table schema
    columns = get_table_schema(pg_conn, table_name)

    # Create table in SQLite
    create_sqlite_table(sqlite_conn, table_name, columns)

    # Clear the record_version table if it exists
    if table_name == "record_version":
        logger.info(f"Clearing table {table_name} before export")
        # Table name comes from PostgreSQL catalog, but we'll still validate it
        if not table_name.replace("_", "").isalnum():
            raise ValueError(f"Invalid table name: {table_name}")
        sqlite_conn.execute(f'DELETE FROM "{table_name}"')  # nosec B608
        sqlite_conn.commit()

    logger.info(f"Exporting {count_rows(pg_conn, table_name)} rows from {table_name}")

    # Copy data
    with pg_conn.cursor() as pg_cursor:
        # Use server-side cursor for large tables
        pg_cursor = pg_conn.cursor("export_cursor", cursor_factory=RealDictCursor)
        pg_cursor.itersize = 1000  # Fetch 1000 rows at a time

        # Table name comes from PostgreSQL catalog - already validated
        pg_cursor.execute(f'SELECT * FROM "{table_name}"')  # nosec B608

        # Prepare column names and types for conversion
        col_names = [col["column_name"] for col in columns]
        col_types = {col["column_name"]: col["data_type"] for col in columns}

        # Insert data in batches
        batch = []
        batch_size = 1000
        row_count = 0

        for row in pg_cursor:
            # Convert values
            converted_row = []
            for col_name in col_names:
                value = row.get(col_name)
                pg_type = col_types[col_name]
                converted_value = convert_value(value, pg_type)
                converted_row.append(converted_value)

            batch.append(converted_row)

            if len(batch) >= batch_size:
                insert_batch(sqlite_conn, table_name, col_names, batch)
                row_count += len(batch)
                if row_count % 1000 == 0:
                    logger.info(
                        f"Exported {row_count}/{count_rows(pg_conn, table_name)} rows from {table_name}"
                    )
                batch = []

        # Insert remaining rows
        if batch:
            insert_batch(sqlite_conn, table_name, col_names, batch)
            row_count += len(batch)
            logger.info(
                f"Exported {row_count}/{count_rows(pg_conn, table_name)} rows from {table_name}"
            )

        pg_cursor.close()


def count_rows(pg_conn: PgConnection, table_name: str) -> int:
    """Count rows in a PostgreSQL table."""
    with pg_conn.cursor() as cursor:
        # Table name comes from PostgreSQL catalog
        cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')  # nosec B608
        return cursor.fetchone()["count"]


def insert_batch(
    sqlite_conn: sqlite3.Connection,
    table_name: str,
    column_names: list[str],
    batch: list[list[Any]],
) -> None:
    """
    Insert a batch of rows into SQLite table.

    Args:
        sqlite_conn: SQLite connection
        table_name: Name of the table
        column_names: List of column names
        batch: List of rows to insert
    """
    if not batch:
        return

    placeholders = ",".join(["?" for _ in column_names])
    col_names_quoted = ",".join([f'"{col}"' for col in column_names])
    # Table and column names come from PostgreSQL catalog
    insert_sql = f'INSERT INTO "{table_name}" ({col_names_quoted}) VALUES ({placeholders})'  # nosec B608

    try:
        sqlite_conn.executemany(insert_sql, batch)
        sqlite_conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Error inserting batch into {table_name}: {e}")
        logger.error(f"First row of batch: {batch[0] if batch else 'empty'}")
        raise


def add_datasette_metadata(sqlite_conn: sqlite3.Connection) -> None:
    """
    Add metadata table for Datasette configuration.

    Args:
        sqlite_conn: SQLite connection
    """
    # Create metadata table
    sqlite_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS "_datasette_metadata" (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """
    )

    # Add basic metadata
    metadata = {
        "title": "Pantry Pirate Radio Data",
        "description": "Food pantry and service provider data collected by Pantry Pirate Radio",
        "license": "CC-BY-SA",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
        "source": "Pantry Pirate Radio",
        "source_url": "https://github.com/For-The-Greater-Good/pantry-pirate-radio",
    }

    for key, value in metadata.items():
        sqlite_conn.execute(
            """
            INSERT OR REPLACE INTO "_datasette_metadata" (key, value)
            VALUES (?, ?)
        """,
            (key, value),
        )

    # Add table descriptions
    table_descriptions = {
        "location": "Physical locations where services are provided",
        "organization": "Organizations that provide services",
        "service": "Services offered by organizations",
        "service_at_location": "Links services to specific locations",
        "address": "Physical addresses for locations",
        "phone": "Phone numbers for organizations, services, and locations",
        "schedule": "Operating hours and schedules",
        "language": "Languages supported at locations or by services",
        "accessibility": "Accessibility features of locations",
        "location_source": "Source data for locations from different scrapers",
        "organization_source": "Source data for organizations from different scrapers",
        "service_source": "Source data for services from different scrapers",
    }

    for table, description in table_descriptions.items():
        sqlite_conn.execute(
            """
            INSERT OR REPLACE INTO "_datasette_metadata" (key, value)
            VALUES (?, ?)
        """,
            (f"table_description_{table}", description),
        )

    sqlite_conn.commit()


def create_datasette_views(sqlite_conn: sqlite3.Connection) -> None:
    """
    Create a single comprehensive view for all location data.

    Args:
        sqlite_conn: SQLite connection
    """
    # Check if required tables exist
    try:
        result = sqlite_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        existing_tables = {row[0] for row in result.fetchall()}

        # Check if we have the minimum required table
        if "location" not in existing_tables:
            logger.warning("Missing required table: location. View cannot be created.")
            return
    except sqlite3.Error as e:
        logger.warning(f"Error checking for required tables: {e}")
        return

    # Create comprehensive location_master view
    try:
        sqlite_conn.execute(
            """
            CREATE VIEW IF NOT EXISTS location_master AS
            SELECT
                -- Location Core Data
                l.id AS location_id,
                l.name AS location_name,
                l.alternate_name AS location_alternate_name,
                l.description AS location_description,
                l.latitude,
                l.longitude,
                l.location_type,
                l.transportation,
                l.external_identifier,
                l.external_identifier_type,
                l.url AS location_url,
                l.is_canonical,

                -- Address Information
                a.id AS address_id,
                a.attention AS address_attention,
                a.address_1,
                a.address_2,
                a.city,
                a.region,
                a.state_province,
                a.postal_code,
                a.country,

                -- Organization Details
                o.id AS organization_id,
                o.name AS organization_name,
                o.alternate_name AS organization_alternate_name,
                o.description AS organization_description,
                o.email AS organization_email,
                o.website AS organization_website,
                o.legal_status,
                o.year_incorporated,
                o.tax_status,
                o.tax_id,

                -- Aggregated Data
                (SELECT GROUP_CONCAT(p.number || CASE WHEN p.extension IS NOT NULL THEN ' x' || p.extension ELSE '' END, '; ')
                 FROM phone p
                 WHERE p.location_id = l.id OR p.organization_id = o.id) AS phone_numbers,

                (SELECT GROUP_CONCAT(s.name, '; ')
                 FROM service s
                 LEFT JOIN service_at_location sal ON s.id = sal.service_id
                 WHERE sal.location_id = l.id OR s.organization_id = o.id) AS services,

                (SELECT GROUP_CONCAT(lang.name, ', ')
                 FROM language lang
                 WHERE lang.location_id = l.id) AS languages_spoken,

                (SELECT GROUP_CONCAT(ls.scraper_id, ', ')
                 FROM location_source ls
                 WHERE ls.location_id = l.id) AS data_sources,

                (SELECT COUNT(DISTINCT ls.scraper_id)
                 FROM location_source ls
                 WHERE ls.location_id = l.id) AS source_count,

                (SELECT MIN(ls.created_at)
                 FROM location_source ls
                 WHERE ls.location_id = l.id) AS first_seen,

                (SELECT MAX(ls.updated_at)
                 FROM location_source ls
                 WHERE ls.location_id = l.id) AS last_updated

            FROM location l
            LEFT JOIN address a ON a.location_id = l.id
            LEFT JOIN organization o ON o.id = l.organization_id
            WHERE l.is_canonical = 1
            ORDER BY l.name
        """
        )

        logger.info("Created view: location_master")

    except sqlite3.Error as e:
        logger.warning(f"Error creating view location_master: {e}")

    sqlite_conn.commit()


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Run the export
    export_to_sqlite()
