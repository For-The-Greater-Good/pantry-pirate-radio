"""PostgreSQL to SQLite exporter for Datasette."""

import decimal
import logging
import sqlite3
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

from app.core.config import settings

logger = logging.getLogger(__name__)


def export_to_sqlite(
    output_path: str = "pantry_pirate_radio.sqlite",
    tables: list[str] | None = None,
    batch_size: int = 1000,
    create_views: bool = True,
) -> str:
    """
    Export PostgreSQL database to SQLite for Datasette.

    Args:
        output_path: Path to save the SQLite database
        tables: List of tables to export (defaults to all tables in the public schema)
        batch_size: Number of rows to process in each batch
        create_views: Whether to create additional SQL views for easier data exploration

    Returns:
        Path to the created SQLite file
    """
    logger.info(f"Starting export to {output_path}")

    # Connect to PostgreSQL
    pg_engine = create_engine(settings.DATABASE_URL)

    # Always get all tables from the public schema, regardless of the tables parameter
    with pg_engine.connect() as pg_conn:
        query = text(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """
        )
        result = pg_conn.execute(query)
        all_tables = [row[0] for row in result.fetchall()]
        logger.info(f"Found {len(all_tables)} tables in the public schema")

    # If specific tables were requested, use them as a filter
    if tables is not None:
        # Make sure all requested tables exist
        missing_tables = [t for t in tables if t not in all_tables]
        if missing_tables:
            logger.warning(
                f"Requested tables not found in database: {', '.join(missing_tables)}"
            )

        # Filter to only include requested tables that exist
        tables = [t for t in tables if t in all_tables]
        logger.info(f"Exporting {len(tables)} requested tables")
    else:
        # Export all tables
        tables = all_tables
        logger.info(f"Exporting all {len(tables)} tables")

    # Create SQLite database
    sqlite_conn = sqlite3.connect(output_path)

    with pg_engine.connect() as pg_conn:
        # Get table schemas and create equivalent tables in SQLite
        for table in tables:
            schema = get_table_schema(pg_conn, table)
            create_sqlite_table(sqlite_conn, table, schema)

        # Export data from each table
        for table in tables:
            # Clear the record_version table before export to avoid UNIQUE constraint errors
            clear_table = table == "record_version"
            export_table_data(pg_conn, sqlite_conn, table, batch_size, clear_table)

    # Add metadata for Datasette
    add_datasette_metadata(sqlite_conn)

    # Create views to make data exploration easier
    if create_views:
        create_datasette_views(sqlite_conn)

    sqlite_conn.close()
    logger.info(f"Export completed: {output_path}")
    return output_path


def get_table_schema(pg_conn: Connection, table_name: str) -> list[dict[str, str]]:
    """
    Get column information for a PostgreSQL table.

    Args:
        pg_conn: PostgreSQL connection
        table_name: Name of the table to get schema for

    Returns:
        List of column definitions
    """
    # Check if the table exists in PostgreSQL
    try:
        check_query = text(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = :table_name
            )
        """
        )
        result = pg_conn.execute(check_query, {"table_name": table_name})
        table_exists = result.scalar()
        if not table_exists:
            logger.warning(
                f"Table {table_name} does not exist in PostgreSQL, skipping schema retrieval"
            )
            return []
    except Exception as e:
        logger.warning(f"Error checking if table {table_name} exists: {e}")
        return []

    # Handle source-specific tables
    if table_name.endswith("_source"):
        # Note: We're not using base_table currently, but keeping for future use
        # base_table = table_name.replace('_source', '')
        query = text(
            """
            SELECT column_name, data_type, is_nullable,
                CASE WHEN column_name = 'id' THEN 'YES' ELSE 'NO' END as is_primary_key
            FROM information_schema.columns
            WHERE table_name = :table_name
            ORDER BY ordinal_position
        """
        )
    else:
        query = text(
            """
            SELECT column_name, data_type, is_nullable,
                CASE WHEN column_name = 'id' THEN 'YES' ELSE 'NO' END as is_primary_key
            FROM information_schema.columns
            WHERE table_name = :table_name
            ORDER BY ordinal_position
        """
        )

    try:
        result = pg_conn.execute(query, {"table_name": table_name})
    except Exception as e:
        logger.warning(f"Error getting schema for table {table_name}: {e}")
        return []

    # Convert rows to dictionaries with proper keys
    schema: list[dict[str, str]] = []
    for row in result:
        # Check if this is a MagicMock object from unittest.mock
        if hasattr(row, "_extract_mock_name") and hasattr(row, "column_name"):
            # This is a MagicMock object (for testing)
            schema.append(
                {
                    "column_name": row.column_name,
                    "data_type": row.data_type,
                    "is_nullable": row.is_nullable,
                    "is_primary_key": row.is_primary_key,
                }
            )
        elif hasattr(row, "__getitem__"):
            # This is a regular database row
            schema.append(
                {
                    "column_name": row[0],
                    "data_type": row[1],
                    "is_nullable": row[2],
                    "is_primary_key": row[3],
                }
            )
        else:
            # Fallback to attribute access
            schema.append(
                {
                    "column_name": row.column_name,
                    "data_type": row.data_type,
                    "is_nullable": row.is_nullable,
                    "is_primary_key": row.is_primary_key,
                }
            )

    return schema


def create_sqlite_table(
    sqlite_conn: sqlite3.Connection, table_name: str, schema: list[dict[str, str]]
) -> None:
    """
    Create a table in SQLite based on PostgreSQL schema.

    Args:
        sqlite_conn: SQLite connection
        table_name: Name of the table to create
        schema: Table schema from PostgreSQL
    """
    # If schema is empty, skip table creation
    if not schema:
        logger.warning(f"Empty schema for table {table_name}, skipping creation")
        return

    # Map PostgreSQL types to SQLite types
    type_mapping = {
        "integer": "INTEGER",
        "bigint": "INTEGER",
        "text": "TEXT",
        "character varying": "TEXT",
        "varchar": "TEXT",
        "boolean": "INTEGER",  # SQLite doesn't have boolean
        "timestamp with time zone": "TEXT",
        "timestamp without time zone": "TEXT",
        "date": "TEXT",
        "decimal": "REAL",
        "numeric": "REAL",
        "double precision": "REAL",
        "real": "REAL",
        "bytea": "BLOB",
        "json": "TEXT",
        "jsonb": "TEXT",
    }

    columns: list[str] = []
    for col in schema:
        name = col["column_name"]
        pg_type = col["data_type"]
        nullable = col["is_nullable"] == "YES"
        is_primary_key = col["is_primary_key"] == "YES"

        # Map PostgreSQL type to SQLite type
        sqlite_type = type_mapping.get(pg_type, "TEXT")

        # Add NOT NULL constraint if needed
        constraint = "" if nullable else " NOT NULL"

        # Special handling for primary key
        if is_primary_key:
            constraint += " PRIMARY KEY"

        columns.append(f"{name} {sqlite_type}{constraint}")

    # Filter out any empty column definitions
    columns = [col for col in columns if col.strip()]

    if not columns:
        logger.warning(
            f"No valid columns found for table {table_name}, skipping creation"
        )
        return

    # Create the table
    create_sql = (
        f"CREATE TABLE IF NOT EXISTS {table_name} (\n  " + ",\n  ".join(columns) + "\n)"
    )

    try:
        logger.debug(f"Creating table {table_name} with SQL: {create_sql}")
        sqlite_conn.execute(create_sql)
        sqlite_conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Error creating table {table_name}: {e}")
        logger.error(f"SQL was: {create_sql}")
        raise


def export_table_data(
    pg_conn: Connection,
    sqlite_conn: sqlite3.Connection,
    table_name: str,
    batch_size: int,
    clear_table: bool = False,
) -> None:
    """
    Export data from PostgreSQL table to SQLite.

    Args:
        pg_conn: PostgreSQL connection
        sqlite_conn: SQLite connection
        table_name: Name of the table to export
        batch_size: Number of rows to process in each batch
        clear_table: Whether to clear the table before inserting new data
    """
    # Validate table name to prevent SQL injection
    import re

    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", table_name):
        raise ValueError(f"Invalid table name: {table_name}")

    # Clear the table if requested
    if clear_table:
        try:
            sqlite_conn.execute(f"DELETE FROM {table_name}")  # nosec B608
            sqlite_conn.commit()
            logger.info(f"Cleared table {table_name} before export")
        except sqlite3.Error as e:
            logger.warning(f"Error clearing table {table_name}: {e}")
    # Check if the table exists in PostgreSQL
    try:
        check_query = text(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = :table_name
            )
        """
        )
        result = pg_conn.execute(check_query, {"table_name": table_name})
        table_exists = result.scalar()
        if not table_exists:
            logger.warning(
                f"Table {table_name} does not exist in PostgreSQL, skipping export"
            )
            return
    except Exception as e:
        logger.warning(f"Error checking if table {table_name} exists: {e}")
        return

    # Get total count for progress reporting
    try:
        count_query = text(f"SELECT COUNT(*) FROM {table_name}")  # nosec B608
        result = pg_conn.execute(count_query)
        row = result.fetchone()
        total_rows = 0
        if row is not None and len(row) > 0:
            total_rows = row[0] if row[0] is not None else 0
    except Exception as e:
        logger.warning(f"Error getting row count for {table_name}: {e}")
        total_rows = 0

    logger.info(f"Exporting {total_rows} rows from {table_name}")

    # If there are no rows, we can skip the export
    if total_rows == 0:
        return

    # Get column names
    schema_query = text(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = :table_name
        ORDER BY ordinal_position
    """
    )
    result = pg_conn.execute(schema_query, {"table_name": table_name})
    columns = [row[0] for row in result.fetchall()]

    # If there are no columns, we can skip the export
    if not columns:
        logger.warning(f"No columns found for table {table_name}, skipping export")
        return

    # Prepare SQLite insert statement
    placeholders = ", ".join(["?" for _ in columns])
    # Use INSERT OR IGNORE to skip rows that would violate constraints
    insert_sql = f"INSERT OR IGNORE INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"  # nosec B608

    # Process in batches
    offset = 0
    while offset < total_rows:
        # Fetch batch of rows
        query = text(
            f"SELECT * FROM {table_name} LIMIT :batch_size OFFSET :offset"  # nosec B608
        )
        result = pg_conn.execute(query, {"batch_size": batch_size, "offset": offset})
        rows = result.fetchall()

        if not rows:
            break

        # Convert rows to tuples for SQLite
        sqlite_rows: list[tuple[Any, ...]] = []
        for row in rows:
            # Convert row to tuple, handling special types
            sqlite_row: list[Any] = []
            for value in row:
                # Convert boolean to integer (0/1) for SQLite
                if isinstance(value, bool):
                    sqlite_row.append(1 if value else 0)
                # Convert Decimal to float for SQLite
                elif isinstance(value, decimal.Decimal):
                    sqlite_row.append(float(value))
                # Convert UUID to string for SQLite
                elif (
                    hasattr(value, "hex")
                    and hasattr(value, "bytes")
                    and hasattr(value, "version")
                ):
                    sqlite_row.append(str(value))
                # Convert dict to JSON string for SQLite
                elif isinstance(value, dict):
                    import json

                    sqlite_row.append(json.dumps(value))
                # Convert datetime.time to string for SQLite
                elif (
                    hasattr(value, "hour")
                    and hasattr(value, "minute")
                    and hasattr(value, "second")
                    and not hasattr(value, "year")
                ):
                    sqlite_row.append(value.strftime("%H:%M:%S"))
                # Convert datetime.datetime to ISO format string for SQLite
                elif (
                    hasattr(value, "year")
                    and hasattr(value, "month")
                    and hasattr(value, "day")
                    and hasattr(value, "hour")
                ):
                    sqlite_row.append(value.isoformat())
                # Convert date to ISO format string for SQLite
                elif (
                    hasattr(value, "year")
                    and hasattr(value, "month")
                    and hasattr(value, "day")
                    and not hasattr(value, "hour")
                ):
                    sqlite_row.append(value.isoformat())
                else:
                    sqlite_row.append(value)
            sqlite_rows.append(tuple(sqlite_row))

        # Insert into SQLite
        sqlite_conn.executemany(insert_sql, sqlite_rows)
        sqlite_conn.commit()

        offset += batch_size
        logger.info(
            f"Exported {min(offset, total_rows)}/{total_rows} rows from {table_name}"
        )


def add_datasette_metadata(sqlite_conn: sqlite3.Connection) -> None:
    """
    Add metadata to help Datasette display the data effectively.

    Args:
        sqlite_conn: SQLite connection
    """
    # Create _datasette_metadata table if it doesn't exist
    sqlite_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS _datasette_metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """
    )

    # Add basic metadata
    metadata = {
        "title": "Pantry Pirate Radio",
        "description": "Food security data aggregation system using HSDS (Human Services Data Specification)",
        "license": "Open Data",
        "source": "Pantry Pirate Radio PostgreSQL Database",
        "source_url": "https://github.com/your-org/pantry-pirate-radio",
    }

    # Insert metadata
    for key, value in metadata.items():
        sqlite_conn.execute(
            "INSERT OR REPLACE INTO _datasette_metadata (key, value) VALUES (?, ?)",
            (key, value),
        )

    # Create datasette.json for table/view descriptions and foreign keys
    sqlite_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS datasette_json (
            id INTEGER PRIMARY KEY,
            json TEXT
        )
    """
    )

    # Define table descriptions and foreign keys as a JSON string
    datasette_json_str = """
    {
        "databases": {
            "": {
                "tables": {
                    "location": {
                        "description": "Canonical locations of food services (merged from multiple sources)",
                        "sort_desc": "id"
                    },
                    "location_source": {
                        "description": "Source-specific location data from individual scrapers",
                        "foreign_keys": {
                            "location_id": "location.id"
                        }
                    },
                    "organization": {
                        "description": "Canonical organizations providing food services (merged from multiple sources)",
                        "sort_desc": "id"
                    },
                    "organization_source": {
                        "description": "Source-specific organization data from individual scrapers",
                        "foreign_keys": {
                            "organization_id": "organization.id"
                        }
                    },
                    "service": {
                        "description": "Canonical services provided (merged from multiple sources)",
                        "sort_desc": "id"
                    },
                    "service_source": {
                        "description": "Source-specific service data from individual scrapers",
                        "foreign_keys": {
                            "service_id": "service.id"
                        }
                    },
                    "service_at_location": {
                        "description": "Links between services and their locations",
                        "foreign_keys": {
                            "service_id": "service.id",
                            "location_id": "location.id"
                        }
                    },
                    "record_version": {
                        "description": "Version history for all records",
                        "sort_desc": "created_at"
                    },
                    "locations_by_scraper": {
                        "description": "Locations grouped by scraper source"
                    },
                    "multi_source_locations": {
                        "description": "Locations that have data from multiple scrapers"
                    },
                    "location_with_services": {
                        "description": "Simplified view of locations with their services and organizations"
                    },
                    "organization_with_services": {
                        "description": "Simplified view of organizations with their services"
                    },
                    "service_with_locations": {
                        "description": "Simplified view of services with their locations and organizations"
                    }
                }
            }
        }
    }
    """

    # Insert the JSON configuration
    sqlite_conn.execute(
        "INSERT OR REPLACE INTO datasette_json (id, json) VALUES (1, ?)",
        (datasette_json_str,),
    )

    sqlite_conn.commit()


def create_datasette_views(sqlite_conn: sqlite3.Connection) -> None:
    """
    Create SQL views to make data exploration easier in Datasette.

    Args:
        sqlite_conn: SQLite connection
    """
    # Check if required tables exist
    try:
        result = sqlite_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('location', 'location_source', 'organization', 'organization_source', 'service', 'service_source', 'service_at_location', 'phone', 'schedule')"
        )
        existing_tables = {row[0] for row in result.fetchall()}

        required_tables = {
            "location",
            "location_source",
            "organization",
            "organization_source",
            "service",
            "service_source",
        }
        missing_tables = required_tables - existing_tables

        if missing_tables:
            logger.warning(
                f"Missing tables for views: {', '.join(missing_tables)}. Some views may not be created."
            )
    except sqlite3.Error as e:
        logger.warning(f"Error checking for required tables: {e}")
        return

    # View 1: Location with sources (detailed view of locations with their source data)
    if "location" in existing_tables and "location_source" in existing_tables:
        try:
            sqlite_conn.execute(
                """
            CREATE VIEW IF NOT EXISTS location_with_sources AS
            SELECT
                l.id AS location_id,
                l.name AS location_name,
                l.description AS location_description,
                l.latitude AS canonical_latitude,
                l.longitude AS canonical_longitude,
                ls.id AS source_id,
                ls.scraper_id,
                ls.name AS source_name,
                ls.description AS source_description,
                ls.latitude AS source_latitude,
                ls.longitude AS source_longitude
            FROM
                location l
            JOIN
                location_source ls ON l.id = ls.location_id
            WHERE
                l.is_canonical = 1
            ORDER BY
                l.name, ls.scraper_id
            """
            )
            logger.info("Created view: location_with_sources")
        except sqlite3.Error as e:
            logger.warning(f"Error creating view location_with_sources: {e}")
    else:
        logger.warning("Skipping view location_with_sources due to missing tables")

    # View 2: Locations by scraper
    if "location" in existing_tables and "location_source" in existing_tables:
        # Check if scraper table exists
        try:
            result = sqlite_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='scraper'"
            )
            scraper_exists = bool(result.fetchone())

            if scraper_exists:
                try:
                    sqlite_conn.execute(
                        """
                    CREATE VIEW IF NOT EXISTS locations_by_scraper AS
                    SELECT
                        ls.scraper_id,
                        s.name AS scraper_name,
                        l.id AS location_id,
                        l.name AS location_name,
                        l.latitude,
                        l.longitude,
                        l.description
                    FROM
                        location l
                    JOIN
                        location_source ls ON l.id = ls.location_id
                    JOIN
                        scraper s ON ls.scraper_id = s.id
                    WHERE
                        l.is_canonical = 1
                    ORDER BY
                        ls.scraper_id, l.name
                    """
                    )
                    logger.info("Created view: locations_by_scraper")
                except sqlite3.Error as e:
                    logger.warning(f"Error creating view locations_by_scraper: {e}")
            else:
                # Create a simplified view without joining to scraper table
                try:
                    sqlite_conn.execute(
                        """
                    CREATE VIEW IF NOT EXISTS locations_by_scraper AS
                    SELECT
                        ls.scraper_id,
                        ls.scraper_id AS scraper_name, -- Use ID as name since we don't have the scraper table
                        l.id AS location_id,
                        l.name AS location_name,
                        l.latitude,
                        l.longitude,
                        l.description
                    FROM
                        location l
                    JOIN
                        location_source ls ON l.id = ls.location_id
                    WHERE
                        l.is_canonical = 1
                    ORDER BY
                        ls.scraper_id, l.name
                    """
                    )
                    logger.info(
                        "Created simplified view: locations_by_scraper (without scraper table)"
                    )
                except sqlite3.Error as e:
                    logger.warning(
                        f"Error creating simplified view locations_by_scraper: {e}"
                    )
        except sqlite3.Error as e:
            logger.warning(f"Error checking for scraper table: {e}")
    else:
        logger.warning("Skipping view locations_by_scraper due to missing tables")

    # View 2: Locations with multiple sources
    if "location" in existing_tables and "location_source" in existing_tables:
        try:
            sqlite_conn.execute(
                """
            CREATE VIEW IF NOT EXISTS multi_source_locations AS
            SELECT
                l.*,
                COUNT(DISTINCT ls.scraper_id) AS source_count,
                GROUP_CONCAT(DISTINCT ls.scraper_id) AS scrapers
            FROM
                location l
            JOIN
                location_source ls ON l.id = ls.location_id
            WHERE
                l.is_canonical = 1
            GROUP BY
                l.id
            HAVING
                COUNT(DISTINCT ls.scraper_id) > 1
            ORDER BY
                source_count DESC, l.name
            """
            )
            logger.info("Created view: multi_source_locations")
        except sqlite3.Error as e:
            logger.warning(f"Error creating view multi_source_locations: {e}")
    else:
        logger.warning("Skipping view multi_source_locations due to missing tables")

    # View 3: Simplified Location with Services
    if all(
        table in existing_tables
        for table in ["location", "service_at_location", "service"]
    ):
        try:
            sqlite_conn.execute(
                """
            CREATE VIEW IF NOT EXISTS location_with_services AS
            SELECT
                l.id AS location_id,
                l.name AS location_name,
                l.description AS location_description,
                l.latitude,
                l.longitude,
                s.id AS service_id,
                s.name AS service_name,
                s.description AS service_description,
                o.id AS organization_id,
                o.name AS organization_name
            FROM
                location l
            JOIN
                service_at_location sal ON l.id = sal.location_id
            JOIN
                service s ON sal.service_id = s.id
            LEFT JOIN
                organization o ON s.organization_id = o.id
            WHERE
                l.is_canonical = 1
            ORDER BY
                l.name, s.name
            """
            )
            logger.info("Created view: location_with_services")
        except sqlite3.Error as e:
            logger.warning(f"Error creating view location_with_services: {e}")
    else:
        logger.warning("Skipping view location_with_services due to missing tables")

    # View 4: Simplified Organization with Services
    if all(table in existing_tables for table in ["organization", "service"]):
        try:
            sqlite_conn.execute(
                """
            CREATE VIEW IF NOT EXISTS organization_with_services AS
            SELECT
                o.id AS organization_id,
                o.name AS organization_name,
                o.description AS organization_description,
                o.email,
                o.website,
                s.id AS service_id,
                s.name AS service_name,
                s.description AS service_description
            FROM
                organization o
            LEFT JOIN
                service s ON o.id = s.organization_id
            ORDER BY
                o.name, s.name
            """
            )
            logger.info("Created view: organization_with_services")
        except sqlite3.Error as e:
            logger.warning(f"Error creating view organization_with_services: {e}")
    else:
        logger.warning("Skipping view organization_with_services due to missing tables")

    # View 5: Simplified Service with Locations
    if all(
        table in existing_tables
        for table in ["service", "service_at_location", "location"]
    ):
        try:
            sqlite_conn.execute(
                """
            CREATE VIEW IF NOT EXISTS service_with_locations AS
            SELECT
                s.id AS service_id,
                s.name AS service_name,
                s.description AS service_description,
                o.id AS organization_id,
                o.name AS organization_name,
                l.id AS location_id,
                l.name AS location_name,
                l.description AS location_description,
                l.latitude,
                l.longitude
            FROM
                service s
            LEFT JOIN
                organization o ON s.organization_id = o.id
            JOIN
                service_at_location sal ON s.id = sal.service_id
            JOIN
                location l ON sal.location_id = l.id
            WHERE
                l.is_canonical = 1
            ORDER BY
                s.name, l.name
            """
            )
            logger.info("Created view: service_with_locations")
        except sqlite3.Error as e:
            logger.warning(f"Error creating view service_with_locations: {e}")
    else:
        logger.warning("Skipping view service_with_locations due to missing tables")

    # View 6: Comprehensive Outreach View
    try:
        sqlite_conn.execute(
            """
        CREATE VIEW IF NOT EXISTS comprehensive_outreach_view AS
        SELECT
            -- Organization Information
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
            o.logo AS organization_logo,
            o.uri AS organization_uri,
            o.parent_organization_id,

            -- Organization Scraper Information
            GROUP_CONCAT(DISTINCT os.scraper_id, ', ') AS organization_scrapers,
            COUNT(DISTINCT os.scraper_id) AS organization_scraper_count,
            GROUP_CONCAT(DISTINCT os.id, ', ') AS organization_source_ids,
            MAX(os.updated_at) AS organization_last_updated,
            MIN(os.created_at) AS organization_first_created,
            COUNT(DISTINCT rv.id) AS organization_version_count,

            -- Location Information
            l.id AS location_id,
            l.name AS location_name,
            l.alternate_name AS location_alternate_name,
            l.description AS location_description,
            l.latitude,
            l.longitude,
            l.location_type,
            l.transportation,
            l.external_identifier AS location_external_id,
            l.external_identifier_type AS location_external_id_type,
            l.url AS location_url,

            -- Location Scraper Information
            GROUP_CONCAT(DISTINCT ls.scraper_id, ', ') AS location_scrapers,
            COUNT(DISTINCT ls.scraper_id) AS location_scraper_count,
            GROUP_CONCAT(DISTINCT ls.id, ', ') AS location_source_ids,
            MAX(ls.updated_at) AS location_last_updated,
            MIN(ls.created_at) AS location_first_created,
            COUNT(DISTINCT rv.id) AS location_version_count,

            -- Address Information
            a.id AS address_id,
            a.attention,
            a.address_1,
            a.address_2,
            a.city,
            a.region,
            a.state_province,
            a.postal_code,
            a.country,
            a.address_type,

            -- Phone Information
            GROUP_CONCAT(DISTINCT p.number ||
                CASE WHEN p.extension IS NOT NULL THEN ' x' || p.extension ELSE '' END ||
                CASE WHEN p.type IS NOT NULL THEN ' (' || p.type || ')' ELSE '' END,
                ', ') AS phone_numbers,

            -- Contact Information
            GROUP_CONCAT(
                DISTINCT
                COALESCE(c.name, '') ||
                CASE WHEN c.title IS NOT NULL THEN ' (' || c.title || ')' ELSE '' END ||
                CASE WHEN c.department IS NOT NULL THEN ', ' || c.department ELSE '' END ||
                CASE WHEN c.email IS NOT NULL THEN ': ' || c.email ELSE '' END,
                '; '
            ) AS contacts,

            -- Service Information
            COUNT(DISTINCT s.id) AS service_count,
            GROUP_CONCAT(DISTINCT s.name, '; ') AS services,
            GROUP_CONCAT(DISTINCT s.description, '; ') AS service_descriptions,

            -- Service Scraper Information
            GROUP_CONCAT(DISTINCT ss.scraper_id, ', ') AS service_scrapers,
            COUNT(DISTINCT ss.scraper_id) AS service_scraper_count,
            GROUP_CONCAT(DISTINCT ss.id, ', ') AS service_source_ids,
            MAX(ss.updated_at) AS service_last_updated,
            MIN(ss.created_at) AS service_first_created,
            COUNT(DISTINCT rv.id) AS service_version_count,

            -- Schedule Information
            GROUP_CONCAT(
                DISTINCT
                CASE
                    WHEN sch.byday IS NOT NULL THEN
                        sch.byday ||
                        CASE
                            WHEN sch.opens_at IS NOT NULL AND sch.closes_at IS NOT NULL
                            THEN ': ' || sch.opens_at || ' - ' || sch.closes_at
                            ELSE ''
                        END
                    ELSE
                        COALESCE(sch.description, '')
                END,
                '; '
            ) AS operating_hours,

            -- Language Information
            GROUP_CONCAT(DISTINCT lang.name, ', ') AS languages,

            -- Accessibility Information
            GROUP_CONCAT(DISTINCT acc.description, '; ') AS accessibility_features,

            -- Service Area Information
            GROUP_CONCAT(DISTINCT sa.name, '; ') AS service_areas,

            -- Required Document Information
            GROUP_CONCAT(DISTINCT rd.document, '; ') AS required_documents,

            -- Organization Identifier Information
            GROUP_CONCAT(DISTINCT oi.identifier_type || ': ' || oi.identifier, '; ') AS organization_identifiers,

            -- Funding Information
            GROUP_CONCAT(DISTINCT f.source, '; ') AS funding_sources,

            -- Cost Option Information
            GROUP_CONCAT(
                DISTINCT
                co.option ||
                CASE WHEN co.amount IS NOT NULL THEN ' (' || co.amount ||
                    CASE WHEN co.currency IS NOT NULL THEN ' ' || co.currency ELSE '' END || ')'
                ELSE '' END,
                '; '
            ) AS cost_options,

            -- Overall Source Information
            GROUP_CONCAT(DISTINCT
                CASE
                    WHEN os.scraper_id IS NOT NULL THEN 'Organization: ' || os.scraper_id
                    WHEN ls.scraper_id IS NOT NULL THEN 'Location: ' || ls.scraper_id
                    WHEN ss.scraper_id IS NOT NULL THEN 'Service: ' || ss.scraper_id
                END,
                '; '
            ) AS all_data_sources

        FROM
            organization o
        -- Use LEFT JOIN to ensure we get all organizations even without locations
        LEFT JOIN
            location l ON l.organization_id = o.id
        -- Use LEFT JOIN to get addresses, one row per address
        LEFT JOIN
            address a ON a.location_id = l.id
        LEFT JOIN
            phone p ON (p.organization_id = o.id OR p.location_id = l.id)
        LEFT JOIN
            contact c ON (c.organization_id = o.id OR c.location_id = l.id)
        LEFT JOIN
            service s ON s.organization_id = o.id
        LEFT JOIN
            service_at_location sal ON sal.service_id = s.id AND (sal.location_id = l.id OR l.id IS NULL)
        LEFT JOIN
            schedule sch ON (sch.service_id = s.id OR sch.location_id = l.id OR sch.service_at_location_id = sal.id)
        LEFT JOIN
            language lang ON (lang.service_id = s.id OR lang.location_id = l.id OR lang.phone_id = p.id)
        LEFT JOIN
            accessibility acc ON acc.location_id = l.id
        LEFT JOIN
            service_area sa ON (sa.service_id = s.id OR sa.service_at_location_id = sal.id)
        LEFT JOIN
            required_document rd ON rd.service_id = s.id
        LEFT JOIN
            organization_identifier oi ON oi.organization_id = o.id
        LEFT JOIN
            funding f ON (f.organization_id = o.id OR f.service_id = s.id)
        LEFT JOIN
            cost_option co ON co.service_id = s.id
        -- Add source tables to get scraper information
        LEFT JOIN
            organization_source os ON os.organization_id = o.id
        LEFT JOIN
            location_source ls ON ls.location_id = l.id
        LEFT JOIN
            service_source ss ON ss.service_id = s.id
        LEFT JOIN
            record_version rv ON (rv.source_id = os.id OR rv.source_id = ls.id OR rv.source_id = ss.id)

        WHERE
            (l.is_canonical IS NULL OR l.is_canonical = 1) -- Only include canonical locations

        GROUP BY
            o.id, o.name, o.alternate_name, o.description, o.email, o.website, o.legal_status, o.year_incorporated,
            o.tax_status, o.tax_id, o.logo, o.uri, o.parent_organization_id,
            l.id, l.name, l.alternate_name, l.description, l.latitude, l.longitude, l.location_type, l.transportation,
            l.external_identifier, l.external_identifier_type, l.url,
            a.id, a.attention, a.address_1, a.address_2, a.city, a.region, a.state_province, a.postal_code, a.country, a.address_type

        ORDER BY
            o.name, l.name
        """
        )
        logger.info("Created view: comprehensive_outreach_view")
    except sqlite3.Error as e:
        logger.warning(f"Error creating view comprehensive_outreach_view: {e}")

    sqlite_conn.commit()


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Run the export
    export_to_sqlite()
