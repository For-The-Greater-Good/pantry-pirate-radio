#!/usr/bin/env python3
"""
Export location data directly from PostgreSQL for web mapping interface.
Optimized version that bypasses SQLite for better performance with large datasets.
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
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from app.core.state_mapping import normalize_state_to_code, VALID_STATE_CODES

logger = logging.getLogger(__name__)


class MapDataExporter:
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

        # Handle DATABASE_URL format
        db_url = os.getenv("DATABASE_URL")
        if db_url:
            # Convert SQLAlchemy URL to psycopg2 format
            if db_url.startswith("postgresql+psycopg2://"):
                return db_url.replace("postgresql+psycopg2://", "postgresql://")
            return db_url

        return f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

    def export(self) -> bool:
        """Main export function that generates map data files."""
        start_time = time.time()
        logger.info("Starting optimized map data export from PostgreSQL")

        try:
            # Connect to PostgreSQL
            conn = psycopg2.connect(self.pg_conn_string)

            # Get total count first for progress tracking
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM location
                    WHERE latitude IS NOT NULL
                      AND longitude IS NOT NULL
                      AND latitude BETWEEN -90 AND 90
                      AND longitude BETWEEN -180 AND 180
                      AND is_canonical = true
                      AND (validation_status IS NULL OR validation_status != 'rejected')
                """
                )
                total_count = cursor.fetchone()[0]
                logger.info(
                    f"Found {total_count} canonical locations with valid coordinates"
                )

            if total_count == 0:
                logger.warning("No locations found to export")
                return False

            # Fetch location data using optimized query with chunking
            locations = self._fetch_locations_chunked(conn, total_count)

            # Generate output files
            success = self._generate_output_files(locations)

            conn.close()

            elapsed = time.time() - start_time
            logger.info(f"Map data export completed in {elapsed:.2f} seconds")

            return success

        except Exception as e:
            logger.error(f"Map data export failed: {e}")
            return False

    def _fetch_locations_chunked(self, conn, total_count: int) -> List[Dict[str, Any]]:
        """Fetch location data in chunks using server-side cursor for memory efficiency."""
        locations = []
        chunk_size = 10000  # Increased chunk size for better performance

        with conn.cursor("map_export_cursor", cursor_factory=RealDictCursor) as cursor:
            # Set cursor to use less memory
            cursor.itersize = chunk_size

            # Use optimized query with PostgreSQL-specific features
            # Removed the subquery for phone and simplified the query
            cursor.execute(
                """
                WITH location_phones AS (
                    -- Pre-aggregate phones to avoid subquery in main SELECT
                    SELECT
                        COALESCE(p.location_id, p.organization_id) as ref_id,
                        p.location_id,
                        p.organization_id,
                        MIN(p.number || COALESCE(' x' || p.extension, '')) as phone_number
                    FROM phone p
                    GROUP BY p.location_id, p.organization_id
                ),
                location_scrapers AS (
                    -- Aggregate scrapers that found this location
                    SELECT
                        location_id,
                        STRING_AGG(DISTINCT scraper_id, ', ' ORDER BY scraper_id) as scrapers,
                        COUNT(DISTINCT scraper_id) as scraper_count,
                        MIN(created_at) as first_seen,
                        MAX(updated_at) as last_updated
                    FROM location_source
                    GROUP BY location_id
                ),
                location_services AS (
                    -- Aggregate services at this location
                    SELECT
                        sal.location_id,
                        STRING_AGG(DISTINCT s.name, ', ' ORDER BY s.name) as services
                    FROM service_at_location sal
                    JOIN service s ON s.id = sal.service_id
                    GROUP BY sal.location_id
                ),
                location_languages AS (
                    -- Aggregate languages spoken at location
                    SELECT
                        l.location_id,
                        STRING_AGG(DISTINCT l.name, ', ' ORDER BY l.name) as languages
                    FROM language l
                    WHERE l.location_id IS NOT NULL
                    GROUP BY l.location_id
                ),
                location_schedules AS (
                    -- Get regular schedule for locations through service_at_location
                    SELECT DISTINCT ON (sal.location_id)
                        sal.location_id,
                        s.opens_at,
                        s.closes_at,
                        s.byday,
                        s.description as schedule_description
                    FROM schedule s
                    JOIN service_at_location sal ON s.service_id = sal.service_id
                    WHERE sal.location_id IS NOT NULL
                      AND (s.opens_at IS NOT NULL OR s.closes_at IS NOT NULL OR s.description IS NOT NULL)
                    ORDER BY sal.location_id, s.opens_at, s.closes_at
                )
                SELECT
                    l.id,
                    l.latitude as lat,
                    l.longitude as lng,
                    l.name,
                    o.name as org,
                    -- Build full address efficiently
                    CONCAT_WS(', ',
                        NULLIF(a.address_1, ''),
                        NULLIF(a.address_2, ''),
                        NULLIF(a.city, ''),
                        NULLIF(a.state_province, ''),
                        NULLIF(a.postal_code, '')
                    ) as address,
                    a.city,
                    -- State codes should already be normalized to 2-letter codes
                    a.state_province as state,
                    a.postal_code as zip,
                    lp.phone_number as phone,
                    o.website as website,
                    o.email as email,
                    COALESCE(o.description, l.description) as description,
                    a.address_1,
                    a.address_2,
                    -- Add confidence and validation fields
                    l.confidence_score,
                    l.validation_status,
                    l.validation_notes,
                    l.geocoding_source,
                    l.location_type,
                    -- Add new fields
                    lscr.scrapers,
                    lscr.scraper_count,
                    lscr.first_seen,
                    lscr.last_updated,
                    lsrv.services,
                    llang.languages,
                    lsch.opens_at,
                    lsch.closes_at,
                    lsch.byday,
                    lsch.schedule_description
                FROM location l
                LEFT JOIN address a ON a.location_id = l.id
                LEFT JOIN organization o ON o.id = l.organization_id
                LEFT JOIN location_phones lp ON (lp.location_id = l.id OR (lp.location_id IS NULL AND lp.organization_id = o.id))
                LEFT JOIN location_scrapers lscr ON lscr.location_id = l.id
                LEFT JOIN location_services lsrv ON lsrv.location_id = l.id
                LEFT JOIN location_languages llang ON llang.location_id = l.id
                LEFT JOIN location_schedules lsch ON lsch.location_id = l.id
                WHERE l.latitude IS NOT NULL
                  AND l.longitude IS NOT NULL
                  AND l.latitude BETWEEN -90 AND 90
                  AND l.longitude BETWEEN -180 AND 180
                  AND l.is_canonical = true
                  -- Exclude rejected locations from export
                  AND (l.validation_status IS NULL OR l.validation_status != 'rejected')
                ORDER BY a.state_province, a.city, l.name
            """
            )

            # Process in chunks
            processed = 0
            while True:
                rows = cursor.fetchmany(chunk_size)
                if not rows:
                    break

                for row in rows:
                    # Format schedule if available
                    schedule = None
                    if (
                        row["opens_at"]
                        or row["closes_at"]
                        or row["schedule_description"]
                    ):
                        schedule = {
                            "opens_at": (
                                str(row["opens_at"]) if row["opens_at"] else None
                            ),
                            "closes_at": (
                                str(row["closes_at"]) if row["closes_at"] else None
                            ),
                            "byday": row["byday"] or "",
                            "description": row["schedule_description"] or "",
                        }

                    location = {
                        "id": row["id"],
                        "lat": float(row["lat"]),
                        "lng": float(row["lng"]),
                        "name": row["name"] or "Food Assistance Location",
                        "org": row["org"] or "Community Organization",
                        "address": row["address"] or "Address not available",
                        "city": row["city"] or "",
                        "state": row["state"] or "",
                        "zip": row["zip"] or "",
                        "phone": row["phone"] or "",
                        "website": row["website"] or "",
                        "email": row["email"] or "",
                        "description": row["description"] or "",
                        # Add confidence and validation fields
                        "confidence_score": (
                            row["confidence_score"]
                            if row["confidence_score"] is not None
                            else 50
                        ),
                        "validation_status": row["validation_status"] or "needs_review",
                        "geocoding_source": row["geocoding_source"] or "",
                        # Parse validation_notes if it's a JSON object
                        "validation_notes": (
                            row["validation_notes"] if row["validation_notes"] else {}
                        ),
                        # Add new fields
                        "location_type": row["location_type"] or "",
                        "scrapers": row["scrapers"] or "",
                        "scraper_count": row["scraper_count"] or 0,
                        "first_seen": (
                            row["first_seen"].isoformat() if row["first_seen"] else None
                        ),
                        "last_updated": (
                            row["last_updated"].isoformat()
                            if row["last_updated"]
                            else None
                        ),
                        "services": row["services"] or "",
                        "languages": row["languages"] or "",
                        "schedule": schedule,
                    }
                    locations.append(location)

                processed += len(rows)
                if processed % 10000 == 0:
                    logger.info(f"Processed {processed}/{total_count} locations")

        return locations

    def _generate_output_files(self, locations: List[Dict[str, Any]]) -> bool:
        """Generate JSON output files for map interface."""
        try:
            # Ensure data directory exists
            data_dir = self.data_repo_path / "data"
            data_dir.mkdir(exist_ok=True)

            # Create metadata
            states = set(loc["state"] for loc in locations if loc["state"])

            # Calculate confidence statistics for metadata
            confidence_scores = [loc.get("confidence_score", 50) for loc in locations]
            avg_confidence = (
                sum(confidence_scores) / len(confidence_scores)
                if confidence_scores
                else 0
            )
            high_confidence_count = sum(1 for score in confidence_scores if score >= 80)

            metadata = {
                "generated": datetime.now(UTC).isoformat(),
                "total_locations": len(locations),
                "states_covered": len(states),
                "coverage": f"{len(states)} US states/territories",
                "source": "HAARRRvest - Pantry Pirate Radio Database",
                "format_version": "3.0",  # Updated version to include scrapers, services, languages, schedules
                "export_method": "PostgreSQL Direct Export",
                "confidence_metrics": {
                    "average_confidence": round(avg_confidence, 1),
                    "high_confidence_locations": high_confidence_count,
                    "includes_validation_data": True,
                },
            }

            # Write main locations file
            output_data = {"metadata": metadata, "locations": locations}

            output_file = data_dir / "locations.json"
            logger.info(f"Writing {len(locations)} locations to {output_file}")

            # Write with minimal formatting for smaller file size
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(output_data, f, separators=(",", ":"), ensure_ascii=False)

            # Generate state files in parallel for better performance
            self._generate_state_files_parallel(locations, metadata, data_dir)

            # Print summary
            self._print_summary(locations, metadata, output_file)

            return True

        except Exception as e:
            logger.error(f"Failed to generate output files: {e}")
            return False

    def _generate_state_files_parallel(
        self, locations: List[Dict[str, Any]], base_metadata: Dict, data_dir: Path
    ):
        """Generate state-specific files using parallel processing."""

        # Group locations by state with validation
        locations_by_state: dict[str, list[dict[str, Any]]] = {}
        invalid_states = []

        for location in locations:
            state = location["state"] or ""

            # States should already be normalized to 2-letter codes
            # Just validate and warn about any non-standard ones
            if state and state not in VALID_STATE_CODES:
                # Try to normalize if it's not already a valid code
                normalized = normalize_state_to_code(state)
                if normalized:
                    state = normalized
                else:
                    invalid_states.append(state)
                    if len(invalid_states) <= 10:
                        logger.warning(f"Invalid state code found: {state}")
                    state = "UNKNOWN"

            if not state:
                state = "UNKNOWN"

            if state not in locations_by_state:
                locations_by_state[state] = []
            locations_by_state[state].append(location)

        if invalid_states:
            logger.warning(
                f"Found {len(invalid_states)} locations with invalid state codes"
            )

        # Create states directory
        states_dir = data_dir / "states"
        states_dir.mkdir(exist_ok=True)

        # Write state files in parallel
        def write_state_file(state: str, state_locations: List[Dict]):
            if state and state != "UNKNOWN" and state in VALID_STATE_CODES:
                try:
                    state_metadata = base_metadata.copy()
                    state_metadata["total_locations"] = len(state_locations)
                    state_metadata["filtered_by"] = f"state = {state}"

                    state_data = {
                        "metadata": state_metadata,
                        "locations": state_locations,
                    }

                    # Use sanitized filename
                    state_file = states_dir / f"{state.lower()}.json"
                    with open(state_file, "w", encoding="utf-8") as f:
                        json.dump(
                            state_data, f, separators=(",", ":"), ensure_ascii=False
                        )
                except Exception as e:
                    logger.error(f"Failed to write state file for {state}: {e}")

        # Use ThreadPoolExecutor for parallel writes
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            for state, state_locations in locations_by_state.items():
                future = executor.submit(write_state_file, state, state_locations)
                futures.append(future)

            # Wait for all to complete
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"Failed to write state file: {e}")

        logger.info(f"Created {len(locations_by_state)} state-specific files")

    def _print_summary(self, locations: List[Dict], metadata: Dict, output_file: Path):
        """Print export summary statistics."""
        states = set(loc["state"] for loc in locations if loc["state"])

        print("\n=== Export Summary ===")
        print(f"Total locations: {len(locations)}")
        print(f"States covered: {sorted(states)}")
        print(f"Generated: {metadata['generated']}")
        print(f"Output file: {output_file}")

        # Data quality metrics
        no_phone = sum(1 for loc in locations if not loc["phone"])
        no_website = sum(1 for loc in locations if not loc["website"])
        no_description = sum(1 for loc in locations if not loc["description"])

        print("\n=== Data Quality ===")
        if locations:
            print(
                f"Locations missing phone: {no_phone} ({no_phone/len(locations)*100:.1f}%)"
            )
            print(
                f"Locations missing website: {no_website} ({no_website/len(locations)*100:.1f}%)"
            )
            print(
                f"Locations missing description: {no_description} ({no_description/len(locations)*100:.1f}%)"
            )
        else:
            print("No locations to analyze")

        # Confidence score metrics
        if locations and len(locations) > 0:
            confidence_scores = [loc.get("confidence_score", 50) for loc in locations]
            avg_confidence = sum(confidence_scores) / len(confidence_scores)
            high_confidence = sum(1 for score in confidence_scores if score >= 80)
            medium_confidence = sum(
                1 for score in confidence_scores if 50 <= score < 80
            )
            low_confidence = sum(1 for score in confidence_scores if score < 50)

            # Validation status breakdown
            verified = sum(
                1 for loc in locations if loc.get("validation_status") == "verified"
            )
            needs_review = sum(
                1 for loc in locations if loc.get("validation_status") == "needs_review"
            )

            print("\n=== Confidence Metrics ===")
            print(f"Average confidence score: {avg_confidence:.1f}")
            print(
                f"High confidence (80-100): {high_confidence} ({high_confidence/len(locations)*100:.1f}%)"
            )
            print(
                f"Medium confidence (50-79): {medium_confidence} ({medium_confidence/len(locations)*100:.1f}%)"
            )
            print(
                f"Low confidence (<50): {low_confidence} ({low_confidence/len(locations)*100:.1f}%)"
            )
            print("\n=== Validation Status ===")
            print(f"Verified: {verified} ({verified/len(locations)*100:.1f}%)")
            print(
                f"Needs review: {needs_review} ({needs_review/len(locations)*100:.1f}%)"
            )


def main():
    """Standalone entry point for testing."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Get data repo path from environment or use default
    data_repo_path = Path(os.getenv("DATA_REPO_PATH", "/data-repo"))

    if not data_repo_path.exists():
        logger.error(f"Data repository path does not exist: {data_repo_path}")
        sys.exit(1)

    exporter = MapDataExporter(data_repo_path)
    success = exporter.export()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
