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
                    -- Clean state codes at query level
                    CASE 
                        WHEN LENGTH(a.state_province) <= 2 THEN a.state_province
                        WHEN a.state_province IS NULL THEN NULL
                        ELSE SUBSTRING(a.state_province, 1, 2)
                    END as state,
                    a.postal_code as zip,
                    lp.phone_number as phone,
                    o.website as website,
                    o.email as email,
                    COALESCE(o.description, l.description) as description,
                    a.address_1,
                    a.address_2
                FROM location l
                LEFT JOIN address a ON a.location_id = l.id
                LEFT JOIN organization o ON o.id = l.organization_id
                LEFT JOIN location_phones lp ON (lp.location_id = l.id OR (lp.location_id IS NULL AND lp.organization_id = o.id))
                WHERE l.latitude IS NOT NULL 
                  AND l.longitude IS NOT NULL
                  AND l.latitude BETWEEN -90 AND 90
                  AND l.longitude BETWEEN -180 AND 180
                  AND l.is_canonical = true
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
            metadata = {
                "generated": datetime.now(UTC).isoformat(),
                "total_locations": len(locations),
                "states_covered": len(states),
                "coverage": f"{len(states)} US states/territories",
                "source": "HAARRRvest - Pantry Pirate Radio Database",
                "format_version": "1.0",
                "export_method": "PostgreSQL Direct Export",
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
        # Valid US state codes
        VALID_STATES = {
            "AL",
            "AK",
            "AZ",
            "AR",
            "CA",
            "CO",
            "CT",
            "DE",
            "FL",
            "GA",
            "HI",
            "ID",
            "IL",
            "IN",
            "IA",
            "KS",
            "KY",
            "LA",
            "ME",
            "MD",
            "MA",
            "MI",
            "MN",
            "MS",
            "MO",
            "MT",
            "NE",
            "NV",
            "NH",
            "NJ",
            "NM",
            "NY",
            "NC",
            "ND",
            "OH",
            "OK",
            "OR",
            "PA",
            "RI",
            "SC",
            "SD",
            "TN",
            "TX",
            "UT",
            "VT",
            "VA",
            "WA",
            "WV",
            "WI",
            "WY",
            "DC",
            "PR",
            "VI",
            "GU",
            "AS",
            "MP",  # Include territories
        }

        # Full state name to code mapping
        STATE_NAME_TO_CODE = {
            # States
            "ALABAMA": "AL",
            "ALASKA": "AK",
            "ARIZONA": "AZ",
            "ARKANSAS": "AR",
            "CALIFORNIA": "CA",
            "COLORADO": "CO",
            "CONNECTICUT": "CT",
            "DELAWARE": "DE",
            "FLORIDA": "FL",
            "GEORGIA": "GA",
            "HAWAII": "HI",
            "IDAHO": "ID",
            "ILLINOIS": "IL",
            "INDIANA": "IN",
            "IOWA": "IA",
            "KANSAS": "KS",
            "KENTUCKY": "KY",
            "LOUISIANA": "LA",
            "MAINE": "ME",
            "MARYLAND": "MD",
            "MASSACHUSETTS": "MA",
            "MICHIGAN": "MI",
            "MINNESOTA": "MN",
            "MISSISSIPPI": "MS",
            "MISSOURI": "MO",
            "MONTANA": "MT",
            "NEBRASKA": "NE",
            "NEVADA": "NV",
            "NEW HAMPSHIRE": "NH",
            "NEW JERSEY": "NJ",
            "NEW MEXICO": "NM",
            "NEW YORK": "NY",
            "NORTH CAROLINA": "NC",
            "NORTH DAKOTA": "ND",
            "OHIO": "OH",
            "OKLAHOMA": "OK",
            "OREGON": "OR",
            "PENNSYLVANIA": "PA",
            "RHODE ISLAND": "RI",
            "SOUTH CAROLINA": "SC",
            "SOUTH DAKOTA": "SD",
            "TENNESSEE": "TN",
            "TEXAS": "TX",
            "UTAH": "UT",
            "VERMONT": "VT",
            "VIRGINIA": "VA",
            "WASHINGTON": "WA",
            "WEST VIRGINIA": "WV",
            "WISCONSIN": "WI",
            "WYOMING": "WY",
            # Federal District and Territories
            "DISTRICT OF COLUMBIA": "DC",
            "WASHINGTON DC": "DC",
            "WASHINGTON D.C.": "DC",
            "PUERTO RICO": "PR",
            "VIRGIN ISLANDS": "VI",
            "US VIRGIN ISLANDS": "VI",
            "GUAM": "GU",
            "AMERICAN SAMOA": "AS",
            "NORTHERN MARIANA ISLANDS": "MP",
        }

        def normalize_state(state_str: str) -> str:
            """
            Normalize state string to valid 2-letter code.

            Logic:
            1. If already a valid 2-letter code, use it
            2. If it's a full state name, map it to code
            3. Extract first word(s) and try to match to state name
            4. For multi-word states (New/North/South/West), take first two words
            5. Default to UNKNOWN for unrecognizable values
            """
            if not state_str:
                return "UNKNOWN"

            # Clean the input
            state_upper = state_str.strip().upper()

            # Check if it's already a valid 2-letter code
            if state_upper in VALID_STATES:
                return state_upper

            # Try exact match with full state names
            if state_upper in STATE_NAME_TO_CODE:
                return STATE_NAME_TO_CODE[state_upper]

            # Handle very long garbage values (LLM errors)
            if len(state_str) > 100:
                # Try to extract meaningful words from the beginning
                words = state_upper.split()[:3]  # Take first 3 words max
                state_upper = " ".join(words)

            # Split into words and try to match
            words = state_upper.split()
            if not words:
                return "UNKNOWN"

            # Check if first word indicates a multi-word state
            multi_word_prefixes = {
                "NEW",
                "NORTH",
                "SOUTH",
                "WEST",
                "RHODE",
                "DISTRICT",
                "AMERICAN",
                "NORTHERN",
                "VIRGIN",
                "US",
            }

            if words[0] in multi_word_prefixes and len(words) > 1:
                # Try two-word combination
                two_word = " ".join(words[:2])
                if two_word in STATE_NAME_TO_CODE:
                    return STATE_NAME_TO_CODE[two_word]

                # Special case for "District of Columbia"
                if words[0] == "DISTRICT" and len(words) > 2:
                    three_word = " ".join(words[:3])
                    if three_word in STATE_NAME_TO_CODE:
                        return STATE_NAME_TO_CODE[three_word]

            # Try single word match
            first_word = words[0]
            if first_word in STATE_NAME_TO_CODE:
                return STATE_NAME_TO_CODE[first_word]

            # Check if it's a 2-letter code at the beginning
            if len(first_word) >= 2:
                two_letter = first_word[:2]
                if two_letter in VALID_STATES:
                    return two_letter

            # No match found
            return "UNKNOWN"

        # Group locations by state with validation
        locations_by_state: dict[str, list[dict[str, Any]]] = {}
        invalid_states = set()
        state_mapping_stats: dict[str, int] = {}  # Track how states were mapped

        for location in locations:
            original_state = location["state"] or ""
            normalized_state = normalize_state(original_state)

            # Track mapping for debugging
            if original_state and normalized_state != original_state:
                if normalized_state == "UNKNOWN" and len(original_state) < 100:
                    invalid_states.add(original_state)
                    if len(invalid_states) <= 10:  # Only log first 10
                        logger.warning(f"Could not map state: {original_state[:50]}")
                else:
                    mapping_key = f"{original_state[:30]} -> {normalized_state}"
                    state_mapping_stats[mapping_key] = (
                        state_mapping_stats.get(mapping_key, 0) + 1
                    )

            if normalized_state not in locations_by_state:
                locations_by_state[normalized_state] = []
            locations_by_state[normalized_state].append(location)

        if invalid_states:
            logger.warning(
                f"Found {len(invalid_states)} unique unmappable state values"
            )

        if state_mapping_stats:
            logger.info(
                f"Successfully mapped {len(state_mapping_stats)} non-standard state values"
            )
            # Log a few examples
            examples = list(state_mapping_stats.items())[:5]
            for mapping, count in examples:
                logger.info(f"  Mapped: {mapping} ({count} locations)")

        # Create states directory
        states_dir = data_dir / "states"
        states_dir.mkdir(exist_ok=True)

        # Write state files in parallel
        def write_state_file(state: str, state_locations: List[Dict]):
            if state and state != "UNKNOWN" and state in VALID_STATES:
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
        print(
            f"Locations missing phone: {no_phone} ({no_phone/len(locations)*100:.1f}%)"
        )
        print(
            f"Locations missing website: {no_website} ({no_website/len(locations)*100:.1f}%)"
        )
        print(
            f"Locations missing description: {no_description} ({no_description/len(locations)*100:.1f}%)"
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
