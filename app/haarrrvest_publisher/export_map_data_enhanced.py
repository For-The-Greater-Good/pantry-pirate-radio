#!/usr/bin/env python3
"""
Enhanced export for location data that preserves scraper-specific information.
Instead of just showing canonical/merged data, this shows ALL data from each scraper.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone, UTC
from pathlib import Path
from typing import Dict, List, Any, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
import time

from app.core.state_mapping import normalize_state_to_code, VALID_STATE_CODES

logger = logging.getLogger(__name__)


class EnhancedMapDataExporter:
    def __init__(self, data_repo_path: Path, pg_conn_string: Optional[str] = None):
        self.data_repo_path = data_repo_path
        self.pg_conn_string = pg_conn_string or self._get_connection_string()

    def _get_connection_string(self) -> str:
        """Build PostgreSQL connection string from environment variables."""
        db_host = os.getenv("POSTGRES_HOST", "db")
        db_port = os.getenv("POSTGRES_PORT", "5432")
        db_user = os.getenv("POSTGRES_USER", "pantry_pirate_radio")
        db_name = os.getenv("POSTGRES_DB", "pantry_pirate_radio")
        db_password = os.getenv("POSTGRES_PASSWORD", "")

        db_url = os.getenv("DATABASE_URL")
        if db_url:
            if db_url.startswith("postgresql+psycopg2://"):
                return db_url.replace("postgresql+psycopg2://", "postgresql://")
            return db_url

        return f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

    def export(self) -> bool:
        """Main export function that generates enhanced map data files."""
        start_time = time.time()
        logger.info("Starting enhanced map data export with scraper-specific data")

        try:
            conn = psycopg2.connect(self.pg_conn_string)

            # Get canonical locations first
            locations = self._fetch_canonical_locations(conn)

            # Enrich each location with scraper-specific data
            for location in locations:
                location["scraper_data"] = self._fetch_scraper_data(
                    conn, location["id"]
                )

            # Generate output files
            success = self._generate_output_files(locations)

            conn.close()

            elapsed = time.time() - start_time
            logger.info(f"Enhanced map data export completed in {elapsed:.2f} seconds")

            return success

        except Exception as e:
            logger.error(f"Enhanced map data export failed: {e}")
            return False

    def _fetch_canonical_locations(self, conn) -> List[Dict[str, Any]]:
        """Fetch canonical location data with basic info."""
        locations = []

        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT
                    l.id,
                    l.latitude as lat,
                    l.longitude as lng,
                    l.name as canonical_name,
                    o.name as canonical_org,
                    a.address_1,
                    a.city,
                    a.state_province as state,
                    a.postal_code as zip,
                    l.confidence_score,
                    l.validation_status,
                    l.is_canonical,
                    COUNT(DISTINCT ls.scraper_id) as scraper_count
                FROM location l
                LEFT JOIN address a ON a.location_id = l.id
                LEFT JOIN organization o ON o.id = l.organization_id
                LEFT JOIN location_source ls ON ls.location_id = l.id
                WHERE l.latitude IS NOT NULL
                  AND l.longitude IS NOT NULL
                  AND l.latitude BETWEEN -90 AND 90
                  AND l.longitude BETWEEN -180 AND 180
                  AND l.is_canonical = true
                  AND (l.validation_status IS NULL OR l.validation_status != 'rejected')
                GROUP BY l.id, l.latitude, l.longitude, l.name, o.name,
                         a.address_1, a.city, a.state_province, a.postal_code,
                         l.confidence_score, l.validation_status, l.is_canonical
                ORDER BY a.state_province, a.city, l.name
            """
            )

            for row in cursor:
                # Validate state
                state_value = row["state"] or ""
                if len(state_value) > 2:
                    if len(state_value) >= 2 and state_value[:2].isalpha():
                        state_value = state_value[:2].upper()
                    else:
                        state_value = ""

                location = {
                    "id": row["id"],
                    "lat": float(row["lat"]),
                    "lng": float(row["lng"]),
                    "canonical_name": row["canonical_name"]
                    or "Food Assistance Location",
                    "canonical_org": row["canonical_org"] or "Community Organization",
                    "address": f"{row['address_1'] or ''}, {row['city'] or ''}, {state_value} {row['zip'] or ''}".strip(
                        ", "
                    ),
                    "city": row["city"] or "",
                    "state": state_value,
                    "zip": row["zip"] or "",
                    "confidence_score": (
                        row["confidence_score"]
                        if row["confidence_score"] is not None
                        else 50
                    ),
                    "validation_status": row["validation_status"] or "needs_review",
                    "scraper_count": row["scraper_count"] or 0,
                    "scraper_data": [],  # Will be populated next
                }
                locations.append(location)

        logger.info(f"Fetched {len(locations)} canonical locations")
        return locations

    def _fetch_scraper_data(self, conn, location_id: str) -> List[Dict[str, Any]]:
        """Fetch all scraper-specific data for a location."""
        scraper_data = []

        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT DISTINCT ON (ls.scraper_id)
                    ls.scraper_id,
                    ls.name as location_name,
                    ls.description as location_description,
                    ls.created_at,
                    ls.updated_at,
                    os.name as org_name,
                    os.description as org_description,
                    os.website,
                    os.email,
                    -- Get services for this scraper
                    (
                        SELECT STRING_AGG(DISTINCT s.name, ', ' ORDER BY s.name)
                        FROM service s
                        JOIN service_at_location sal ON sal.service_id = s.id
                        JOIN service_source ss ON ss.service_id = s.id
                        WHERE sal.location_id = l.id
                          AND ss.scraper_id = ls.scraper_id
                    ) as services,
                    -- Get schedule for this scraper
                    (
                        SELECT json_build_object(
                            'opens_at', sch.opens_at::text,
                            'closes_at', sch.closes_at::text,
                            'byday', sch.byday,
                            'description', sch.description
                        )
                        FROM schedule sch
                        JOIN service_at_location sal ON sch.service_id = sal.service_id
                        JOIN service_source ss ON ss.service_id = sch.service_id
                        WHERE sal.location_id = l.id
                          AND ss.scraper_id = ls.scraper_id
                        LIMIT 1
                    ) as schedule,
                    -- Get phone for this location/org from this scraper
                    (
                        SELECT p.number || COALESCE(' x' || p.extension, '')
                        FROM phone p
                        WHERE (p.location_id = l.id OR p.organization_id = o.id)
                        ORDER BY p.location_id DESC NULLS LAST
                        LIMIT 1
                    ) as phone
                FROM location l
                JOIN location_source ls ON ls.location_id = l.id
                LEFT JOIN organization o ON o.id = l.organization_id
                LEFT JOIN organization_source os ON os.organization_id = o.id
                    AND os.scraper_id = ls.scraper_id
                WHERE l.id = %s
                ORDER BY ls.scraper_id, ls.updated_at DESC
            """,
                (location_id,),
            )

            for row in cursor:
                data = {
                    "scraper_id": row["scraper_id"],
                    "location_name": row["location_name"],
                    "location_description": row["location_description"],
                    "org_name": row["org_name"],
                    "org_description": row["org_description"],
                    "website": row["website"],
                    "email": row["email"],
                    "phone": row["phone"] or "",
                    "services": row["services"],
                    "schedule": row["schedule"] if row["schedule"] else None,
                    "first_seen": (
                        row["created_at"].isoformat() if row["created_at"] else None
                    ),
                    "last_updated": (
                        row["updated_at"].isoformat() if row["updated_at"] else None
                    ),
                }
                scraper_data.append(data)

        return scraper_data

    def _generate_output_files(self, locations: List[Dict[str, Any]]) -> bool:
        """Generate JSON output files for enhanced map interface."""
        try:
            data_dir = self.data_repo_path / "data"
            data_dir.mkdir(exist_ok=True)

            # Create metadata
            metadata = {
                "generated": datetime.now(UTC).isoformat(),
                "total_locations": len(locations),
                "format_version": "4.0",  # New version for enhanced data
                "includes_scraper_data": True,
                "source": "HAARRRvest - Pantry Pirate Radio Enhanced Export",
            }

            # Calculate statistics
            locations_with_multiple_scrapers = sum(
                1 for loc in locations if loc["scraper_count"] > 1
            )
            total_scraper_records = sum(len(loc["scraper_data"]) for loc in locations)

            metadata["statistics"] = {
                "locations_with_multiple_scrapers": locations_with_multiple_scrapers,
                "total_scraper_records": total_scraper_records,
                "average_scrapers_per_location": (
                    total_scraper_records / len(locations) if locations else 0
                ),
            }

            # Write enhanced locations file
            output_data = {"metadata": metadata, "locations": locations}

            output_file = data_dir / "locations_enhanced.json"
            logger.info(f"Writing {len(locations)} enhanced locations to {output_file}")

            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(output_data, f, separators=(",", ":"), ensure_ascii=False)

            # Print summary
            print("\n=== Enhanced Export Summary ===")
            print(f"Total locations: {len(locations)}")
            print(
                f"Locations with multiple scrapers: {locations_with_multiple_scrapers}"
            )
            print(f"Total scraper records: {total_scraper_records}")
            print(f"Output file: {output_file}")

            return True

        except Exception as e:
            logger.error(f"Failed to generate enhanced output files: {e}")
            return False


def main():
    """Standalone entry point for testing."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    data_repo_path = Path(os.getenv("DATA_REPO_PATH", "/data-repo"))

    if not data_repo_path.exists():
        logger.error(f"Data repository path does not exist: {data_repo_path}")
        sys.exit(1)

    exporter = EnhancedMapDataExporter(data_repo_path)
    success = exporter.export()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
