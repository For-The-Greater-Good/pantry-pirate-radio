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


def create_postgres_materialized_views(pg_conn: PgConnection) -> None:
    """
    Create or refresh materialized views in PostgreSQL for efficient export.

    Args:
        pg_conn: PostgreSQL connection
    """
    logger.info("Creating/refreshing PostgreSQL materialized views")

    with pg_conn.cursor() as cursor:
        # Check if materialized view already exists
        cursor.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM pg_matviews
                WHERE schemaname = 'public' AND matviewname = 'location_master'
            ) as exists
        """
        )
        mat_view_exists = cursor.fetchone()["exists"]

        if mat_view_exists:
            # Refresh existing materialized view
            logger.info("Refreshing existing location_master materialized view")
            cursor.execute("REFRESH MATERIALIZED VIEW location_master")
            pg_conn.commit()
        else:
            # Drop any existing regular view first
            try:
                cursor.execute("DROP VIEW IF EXISTS location_master CASCADE")
                pg_conn.commit()
                logger.info("Dropped existing location_master view")
            except Exception:
                pg_conn.rollback()

            # Create new materialized view
            logger.info("Creating new location_master materialized view")
            cursor.execute(
                """
                CREATE MATERIALIZED VIEW location_master AS
            WITH location_phones AS (
                SELECT
                    COALESCE(p.location_id, p.organization_id) as entity_id,
                    CASE WHEN p.location_id IS NOT NULL THEN 'loc' ELSE 'org' END as entity_type,
                    STRING_AGG(
                        p.number || CASE WHEN p.extension IS NOT NULL THEN ' x' || p.extension ELSE '' END,
                        '; ' ORDER BY p.number
                    ) as phone_number
                FROM phone p
                GROUP BY COALESCE(p.location_id, p.organization_id),
                         CASE WHEN p.location_id IS NOT NULL THEN 'loc' ELSE 'org' END
            ),
            location_services AS (
                SELECT
                    sal.location_id,
                    STRING_AGG(s.name, '; ' ORDER BY s.name) as services
                FROM service s
                JOIN service_at_location sal ON s.id = sal.service_id
                GROUP BY sal.location_id
            ),
            location_languages AS (
                SELECT
                    l.location_id,
                    STRING_AGG(l.name, ', ' ORDER BY l.name) as languages
                FROM language l
                WHERE l.location_id IS NOT NULL
                GROUP BY l.location_id
            ),
            location_schedules AS (
                SELECT DISTINCT ON (sal.location_id)
                    sal.location_id,
                    s.opens_at,
                    s.closes_at,
                    s.byday,
                    s.description as schedule_description
                FROM schedule s
                JOIN service_at_location sal ON s.service_at_location_id = sal.id
                WHERE sal.location_id IS NOT NULL
                  AND (s.opens_at IS NOT NULL OR s.closes_at IS NOT NULL OR s.description IS NOT NULL)
                ORDER BY sal.location_id, s.opens_at, s.closes_at
            ),
            location_sources AS (
                SELECT
                    ls.location_id,
                    STRING_AGG(DISTINCT ls.scraper_id, ', ' ORDER BY ls.scraper_id) as data_sources,
                    COUNT(DISTINCT ls.scraper_id) as source_count,
                    MIN(ls.created_at) as first_seen,
                    MAX(ls.updated_at) as last_updated
                FROM location_source ls
                GROUP BY ls.location_id
            )
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

                -- Validation data
                l.confidence_score,
                l.validation_status,
                l.validation_notes,
                l.geocoding_source,

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

                -- Full address concatenated
                CONCAT_WS(', ',
                    NULLIF(a.address_1, ''),
                    NULLIF(a.address_2, ''),
                    NULLIF(a.city, ''),
                    NULLIF(a.state_province, ''),
                    NULLIF(a.postal_code, '')
                ) AS full_address,

                -- Organization Details
                o.id AS organization_id,
                o.name AS organization_name,
                o.alternate_name AS organization_alternate_name,
                COALESCE(o.description, l.description) AS organization_description,
                o.email AS organization_email,
                o.website AS organization_website,
                o.legal_status,
                o.year_incorporated,
                o.tax_status,
                o.tax_id,

                -- Aggregated Data from CTEs
                COALESCE(lp_loc.phone_number, lp_org.phone_number) AS phone_numbers,
                lsrv.services,
                llang.languages AS languages_spoken,
                lsch.opens_at,
                lsch.closes_at,
                lsch.byday,
                lsch.schedule_description,
                lsrc.data_sources,
                lsrc.source_count,
                lsrc.first_seen,
                lsrc.last_updated

            FROM location l
            LEFT JOIN address a ON a.location_id = l.id
            LEFT JOIN organization o ON o.id = l.organization_id
            LEFT JOIN location_phones lp_loc ON lp_loc.entity_id = l.id AND lp_loc.entity_type = 'loc'
            LEFT JOIN location_phones lp_org ON lp_org.entity_id = o.id AND lp_org.entity_type = 'org'
            LEFT JOIN location_services lsrv ON lsrv.location_id = l.id
            LEFT JOIN location_languages llang ON llang.location_id = l.id
            LEFT JOIN location_schedules lsch ON lsch.location_id = l.id
            LEFT JOIN location_sources lsrc ON lsrc.location_id = l.id
            WHERE l.is_canonical = true
              AND l.latitude IS NOT NULL
              AND l.longitude IS NOT NULL
              AND l.latitude BETWEEN -90 AND 90
              AND l.longitude BETWEEN -180 AND 180
              AND (l.validation_status IS NULL OR l.validation_status != 'rejected')
                ORDER BY l.name
            """
            )
            pg_conn.commit()

            # Create indexes on the new materialized view
            logger.info("Creating indexes on location_master")
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_location_master_city
                ON location_master(city)
            """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_location_master_state
                ON location_master(state_province)
            """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_location_master_location_id
                ON location_master(location_id)
            """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_location_master_coords
                ON location_master(latitude, longitude)
            """
            )

            pg_conn.commit()

        # Get row and column count
        cursor.execute("SELECT COUNT(*) FROM location_master")
        row_count = cursor.fetchone()["count"]

        # Verify columns are accessible
        cursor.execute(
            """
            SELECT COUNT(*) as col_count
            FROM pg_catalog.pg_attribute a
            JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
            WHERE c.relname = 'location_master'
                AND a.attnum > 0
                AND NOT a.attisdropped
        """
        )
        col_count = cursor.fetchone()["col_count"]

        logger.info(
            f"Materialized view location_master ready with {row_count} rows and {col_count} columns"
        )


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

    # Create or refresh materialized view in PostgreSQL for fast exports
    create_postgres_materialized_views(pg_conn)

    # Ensure all changes are committed and visible
    pg_conn.commit()

    # Create or overwrite SQLite database
    if os.path.exists(sqlite_path):
        os.remove(sqlite_path)

    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row

    try:
        # Get list of tables and materialized views from PostgreSQL
        with pg_conn.cursor() as cursor:
            # Get regular tables
            cursor.execute(
                """
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public'
                ORDER BY tablename
            """
            )
            tables = [row["tablename"] for row in cursor.fetchall()]

            # Get materialized views
            cursor.execute(
                """
                SELECT matviewname as tablename
                FROM pg_matviews
                WHERE schemaname = 'public'
                ORDER BY matviewname
            """
            )
            mat_views = [row["tablename"] for row in cursor.fetchall()]

            if mat_views:
                logger.info(f"Found materialized views: {', '.join(mat_views)}")

            # Combine tables and materialized views
            all_tables = tables + mat_views
            logger.info(
                f"Found {len(tables)} tables and {len(mat_views)} materialized views to export"
            )

        # Exclude PostGIS-specific tables and any user-specified tables
        exclude_list = ["geography_columns", "geometry_columns", *exclude_tables]
        tables_to_export = [t for t in all_tables if t not in exclude_list]

        logger.info(f"Found {len(all_tables)} total objects in the public schema")
        logger.info(f"Exporting {len(tables_to_export)} tables/views after exclusions")

        # Export each table
        for table in tables_to_export:
            export_table_data(pg_conn, sqlite_conn, table)

        # Add metadata for Datasette
        add_datasette_metadata(sqlite_conn)

        # Create views for easier data exploration
        create_datasette_views(sqlite_conn)

        # Create indexes for better query performance
        create_performance_indexes(sqlite_conn)

        logger.info(f"Export completed: {sqlite_path}")

    finally:
        pg_conn.close()
        sqlite_conn.close()


def get_table_schema(pg_conn: PgConnection, table_name: str) -> list[dict[str, str]]:
    """
    Get column information for a PostgreSQL table or materialized view.

    Args:
        pg_conn: PostgreSQL connection
        table_name: Name of the table or materialized view

    Returns:
        List of column definitions
    """
    with pg_conn.cursor() as cursor:
        # First check if the table/view exists and what type it is
        cursor.execute(
            """
            SELECT
                CASE
                    WHEN c.relkind = 'r' THEN 'table'
                    WHEN c.relkind = 'v' THEN 'view'
                    WHEN c.relkind = 'm' THEN 'materialized view'
                    ELSE c.relkind::text
                END as object_type
            FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = %s
        """,
            (table_name,),
        )

        result = cursor.fetchone()
        if result:
            logger.debug(f"{table_name} is a {result['object_type']}")
        else:
            logger.warning(f"{table_name} not found in pg_catalog")

        # For materialized views, we need to use pg_catalog directly
        # information_schema doesn't show materialized views
        logger.debug(f"Querying columns for {table_name} from pg_catalog")
        cursor.execute(
            """
            SELECT
                a.attname as column_name,
                pg_catalog.format_type(a.atttypid, a.atttypmod) as data_type,
                CASE
                    WHEN a.atttypmod > 0 AND t.typname IN ('varchar', 'char', 'bpchar')
                    THEN a.atttypmod - 4
                    ELSE NULL
                END as character_maximum_length,
                CASE
                    WHEN t.typname IN ('numeric', 'decimal')
                    THEN ((a.atttypmod - 4) >> 16) & 65535
                    ELSE NULL
                END as numeric_precision,
                CASE
                    WHEN t.typname IN ('numeric', 'decimal')
                    THEN (a.atttypmod - 4) & 65535
                    ELSE NULL
                END as numeric_scale,
                CASE WHEN a.attnotnull THEN 'NO' ELSE 'YES' END as is_nullable
            FROM pg_catalog.pg_attribute a
            JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_catalog.pg_type t ON t.oid = a.atttypid
            WHERE n.nspname = 'public'
                AND c.relname = %s
                AND a.attnum > 0
                AND NOT a.attisdropped
            ORDER BY a.attnum
        """,
            (table_name,),
        )
        columns = cursor.fetchall()
        logger.debug(
            f"pg_catalog query returned {len(columns)} columns for {table_name}"
        )

        if not columns:
            # If still no columns found, try information_schema (for regular tables)
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
            columns = cursor.fetchall()

        if not columns:
            logger.warning(
                f"No columns found for {table_name} in catalog queries, trying direct query"
            )
            # Last resort: use a SELECT query to get column info
            try:
                # Validate table name to prevent SQL injection
                if not table_name.replace("_", "").isalnum():
                    raise ValueError(f"Invalid table name: {table_name}")
                cursor.execute(
                    f'SELECT * FROM "{table_name}" LIMIT 0'
                )  # nosec B608 - table name validated
                # Get column descriptions from the cursor
                columns = []
                if cursor.description:
                    for col in cursor.description:
                        columns.append(
                            {
                                "column_name": col.name,
                                "data_type": "TEXT",  # Default to TEXT for SQLite
                                "character_maximum_length": None,
                                "numeric_precision": None,
                                "numeric_scale": None,
                                "is_nullable": "YES",
                            }
                        )
                    logger.info(
                        f"Retrieved {len(columns)} columns for {table_name} via direct query"
                    )
            except Exception as e:
                logger.error(
                    f"Failed to get columns for {table_name} via direct query: {e}"
                )

        if not columns:
            logger.error(f"No columns found for {table_name} using any method")
        else:
            logger.debug(f"Found {len(columns)} columns for {table_name}")

        return columns


def postgres_to_sqlite_type(pg_type: str) -> str:
    """
    Convert PostgreSQL data type to SQLite data type.

    Args:
        pg_type: PostgreSQL data type

    Returns:
        SQLite data type
    """
    # Clean up type string (remove size specifiers like varchar(255))
    if pg_type:
        pg_type = pg_type.split("(")[0].lower()

    type_mapping = {
        # Numeric types
        "smallint": "INTEGER",
        "integer": "INTEGER",
        "bigint": "INTEGER",
        "int4": "INTEGER",
        "int8": "INTEGER",
        "decimal": "REAL",
        "numeric": "REAL",
        "real": "REAL",
        "float8": "REAL",
        "double precision": "REAL",
        "money": "REAL",
        # Text types
        "character varying": "TEXT",
        "varchar": "TEXT",
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
    # Check if we have columns
    if not columns:
        logger.error(f"No columns found for table {table_name}")
        raise ValueError(f"Cannot create table {table_name} with no columns")

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

    if not columns:
        logger.error(f"No columns found for {table_name}, skipping export")
        return

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
    Create views for data exploration (location_master is now a table, not a view).

    Args:
        sqlite_conn: SQLite connection
    """
    # Check if location_master table was exported
    try:
        result = sqlite_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='location_master'"
        )
        if result.fetchone():
            logger.info("location_master table found, no view needed")

            # Add any other views here if needed in the future

        else:
            logger.warning(
                "location_master table not found - may need to run publisher"
            )
    except sqlite3.Error as e:
        logger.warning(f"Error checking for location_master table: {e}")

    # We could add other views here if needed
    # For now, location_master is a materialized table from PostgreSQL

    sqlite_conn.commit()


def create_datasette_views_old(sqlite_conn: sqlite3.Connection) -> None:
    """
    DEPRECATED: Old view creation - kept for reference.
    location_master is now a materialized table exported from PostgreSQL.
    """
    # This is the old view creation code - no longer used
    try:
        sqlite_conn.execute(
            """
            CREATE VIEW IF NOT EXISTS location_master AS
            WITH location_phones AS (
                SELECT
                    COALESCE(p.location_id, p.organization_id) as entity_id,
                    'loc_' || p.location_id as entity_type,
                    GROUP_CONCAT(p.number || CASE WHEN p.extension IS NOT NULL THEN ' x' || p.extension ELSE '' END, '; ') as phone_number
                FROM phone p
                WHERE p.location_id IS NOT NULL
                GROUP BY p.location_id
                UNION
                SELECT
                    p.organization_id as entity_id,
                    'org_' || p.organization_id as entity_type,
                    GROUP_CONCAT(p.number || CASE WHEN p.extension IS NOT NULL THEN ' x' || p.extension ELSE '' END, '; ') as phone_number
                FROM phone p
                WHERE p.location_id IS NULL AND p.organization_id IS NOT NULL
                GROUP BY p.organization_id
            ),
            location_services AS (
                SELECT
                    sal.location_id,
                    GROUP_CONCAT(s.name, '; ') as services
                FROM service s
                JOIN service_at_location sal ON s.id = sal.service_id
                GROUP BY sal.location_id
            ),
            location_languages AS (
                SELECT
                    l.location_id,
                    GROUP_CONCAT(l.name, ', ') as languages
                FROM language l
                WHERE l.location_id IS NOT NULL
                GROUP BY l.location_id
            ),
            location_schedules AS (
                SELECT
                    sal.location_id,
                    s.opens_at,
                    s.closes_at,
                    s.description as schedule_description
                FROM schedule s
                JOIN service_at_location sal ON s.service_at_location_id = sal.id
                WHERE sal.location_id IS NOT NULL
                  AND (s.opens_at IS NOT NULL OR s.closes_at IS NOT NULL OR s.description IS NOT NULL)
            ),
            location_sources AS (
                SELECT
                    ls.location_id,
                    GROUP_CONCAT(ls.scraper_id, ', ') as data_sources,
                    COUNT(DISTINCT ls.scraper_id) as source_count,
                    MIN(ls.created_at) as first_seen,
                    MAX(ls.updated_at) as last_updated
                FROM location_source ls
                GROUP BY ls.location_id
            )
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

                -- Validation data
                l.confidence_score,
                l.validation_status,
                l.validation_notes,
                l.geocoding_source,

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

                -- Full address concatenated
                COALESCE(a.address_1, '') ||
                CASE WHEN a.address_2 IS NOT NULL THEN ', ' || a.address_2 ELSE '' END ||
                CASE WHEN a.city IS NOT NULL THEN ', ' || a.city ELSE '' END ||
                CASE WHEN a.state_province IS NOT NULL THEN ', ' || a.state_province ELSE '' END ||
                CASE WHEN a.postal_code IS NOT NULL THEN ' ' || a.postal_code ELSE '' END AS full_address,

                -- Organization Details
                o.id AS organization_id,
                o.name AS organization_name,
                o.alternate_name AS organization_alternate_name,
                COALESCE(o.description, l.description) AS organization_description,
                o.email AS organization_email,
                o.website AS organization_website,
                o.legal_status,
                o.year_incorporated,
                o.tax_status,
                o.tax_id,

                -- Aggregated Data from CTEs
                COALESCE(lp_loc.phone_number, lp_org.phone_number) AS phone_numbers,
                lsrv.services,
                llang.languages AS languages_spoken,
                lsch.opens_at,
                lsch.closes_at,
                lsch.schedule_description,
                lsrc.data_sources,
                lsrc.source_count,
                lsrc.first_seen,
                lsrc.last_updated

            FROM location l
            LEFT JOIN address a ON a.location_id = l.id
            LEFT JOIN organization o ON o.id = l.organization_id
            LEFT JOIN location_phones lp_loc ON lp_loc.entity_id = l.id AND lp_loc.entity_type = 'loc_' || l.id
            LEFT JOIN location_phones lp_org ON lp_org.entity_id = o.id AND lp_org.entity_type = 'org_' || o.id
            LEFT JOIN location_services lsrv ON lsrv.location_id = l.id
            LEFT JOIN location_languages llang ON llang.location_id = l.id
            LEFT JOIN location_schedules lsch ON lsch.location_id = l.id
            LEFT JOIN location_sources lsrc ON lsrc.location_id = l.id
            WHERE l.is_canonical = 1
              AND l.latitude IS NOT NULL
              AND l.longitude IS NOT NULL
              AND l.latitude BETWEEN -90 AND 90
              AND l.longitude BETWEEN -180 AND 180
              AND (l.validation_status IS NULL OR l.validation_status != 'rejected')
            ORDER BY l.name
        """
        )

        logger.info("Created view: location_master")

    except sqlite3.Error as e:
        logger.warning(f"Error creating view location_master: {e}")

    sqlite_conn.commit()


def create_performance_indexes(sqlite_conn: sqlite3.Connection) -> None:
    """
    Create indexes to improve query performance, especially for the location_master view.

    Args:
        sqlite_conn: SQLite connection
    """
    logger.info("Creating performance indexes")

    # Define indexes to create
    # Format: (index_name, table_name, columns)
    indexes = [
        # Primary key indexes (if not already created)
        ("idx_location_id", "location", "id"),
        ("idx_organization_id", "organization", "id"),
        ("idx_service_id", "service", "id"),
        ("idx_address_id", "address", "id"),
        # Foreign key indexes for joins
        ("idx_location_org_id", "location", "organization_id"),
        ("idx_location_canonical", "location", "is_canonical"),
        ("idx_address_location_id", "address", "location_id"),
        ("idx_service_org_id", "service", "organization_id"),
        ("idx_service_at_location_loc", "service_at_location", "location_id"),
        ("idx_service_at_location_svc", "service_at_location", "service_id"),
        ("idx_phone_location_id", "phone", "location_id"),
        ("idx_phone_org_id", "phone", "organization_id"),
        ("idx_phone_service_id", "phone", "service_id"),
        ("idx_schedule_sal_id", "schedule", "service_at_location_id"),
        ("idx_language_location_id", "language", "location_id"),
        ("idx_language_service_id", "language", "service_id"),
        # Source tracking indexes
        ("idx_location_source_loc", "location_source", "location_id"),
        ("idx_location_source_scraper", "location_source", "scraper_id"),
        ("idx_org_source_org", "organization_source", "organization_id"),
        ("idx_org_source_scraper", "organization_source", "scraper_id"),
        ("idx_service_source_svc", "service_source", "service_id"),
        ("idx_service_source_scraper", "service_source", "scraper_id"),
        # Geographic indexes
        ("idx_location_coords", "location", "latitude, longitude"),
        # Text search optimization
        ("idx_location_name", "location", "name"),
        ("idx_location_city", "address", "city"),
        ("idx_location_state", "address", "state_province"),
        ("idx_location_postal", "address", "postal_code"),
        ("idx_org_name", "organization", "name"),
        ("idx_service_name", "service", "name"),
        # Composite indexes for common queries
        ("idx_location_canonical_name", "location", "is_canonical, name"),
        ("idx_address_city_state", "address", "city, state_province"),
        ("idx_location_source_composite", "location_source", "location_id, scraper_id"),
        # Indexes for location_master materialized table
        ("idx_location_master_location_id", "location_master", "location_id"),
        ("idx_location_master_city", "location_master", "city"),
        ("idx_location_master_state", "location_master", "state_province"),
        ("idx_location_master_coords", "location_master", "latitude, longitude"),
        ("idx_location_master_name", "location_master", "location_name"),
        ("idx_location_master_org", "location_master", "organization_name"),
        ("idx_location_master_canonical", "location_master", "is_canonical"),
        ("idx_location_master_confidence", "location_master", "confidence_score"),
        ("idx_location_master_validation", "location_master", "validation_status"),
    ]

    # Check which tables exist
    result = sqlite_conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    existing_tables = {row[0] for row in result.fetchall()}

    # Create indexes
    created = 0
    skipped = 0

    for index_name, table_name, columns in indexes:
        # Skip if table doesn't exist
        if table_name not in existing_tables:
            logger.debug(
                f"Skipping index {index_name}: table {table_name} doesn't exist"
            )
            skipped += 1
            continue

        try:
            # Check if index already exists
            result = sqlite_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
                (index_name,),
            )
            if result.fetchone():
                logger.debug(f"Index {index_name} already exists")
                skipped += 1
                continue

            # Create the index
            create_sql = f'CREATE INDEX IF NOT EXISTS "{index_name}" ON "{table_name}" ({columns})'
            sqlite_conn.execute(create_sql)
            created += 1
            logger.debug(f"Created index: {index_name} on {table_name}({columns})")

        except sqlite3.Error as e:
            logger.warning(f"Failed to create index {index_name}: {e}")
            skipped += 1

    sqlite_conn.commit()
    logger.info(f"Created {created} indexes, skipped {skipped}")


if __name__ == "__main__":
    import argparse

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Export PostgreSQL database to SQLite for Datasette"
    )
    parser.add_argument(
        "--output",
        "-o",
        default="pantry_pirate_radio.sqlite",
        help="Output SQLite database path (default: pantry_pirate_radio.sqlite)",
    )
    parser.add_argument(
        "--database-url",
        help="PostgreSQL connection string (default: uses DATABASE_URL env var)",
    )
    parser.add_argument(
        "--exclude",
        nargs="+",
        help="Tables to exclude from export",
    )

    args = parser.parse_args()

    # Run the export
    export_to_sqlite(
        pg_conn_string=args.database_url,
        sqlite_path=args.output,
        exclude_tables=args.exclude,
    )
