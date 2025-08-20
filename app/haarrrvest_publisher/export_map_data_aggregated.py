#!/usr/bin/env python3
"""
Export location data with aggregation of nearby locations from multiple scrapers.
This version groups locations within a radius and shows all scraper data.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone, UTC
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import psycopg2
from psycopg2.extras import RealDictCursor
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from math import radians, cos, sin, asin, sqrt

from app.core.state_mapping import normalize_state_to_code, VALID_STATE_CODES

logger = logging.getLogger(__name__)


class AggregatedMapDataExporter:
    def __init__(self, data_repo_path: Path, pg_conn_string: Optional[str] = None, grouping_radius_meters: Optional[int] = None):
        self.data_repo_path = data_repo_path
        self.pg_conn_string = pg_conn_string or self._get_connection_string()
        # Radius in meters for grouping nearby locations
        # Can be configured via environment variable or parameter
        if grouping_radius_meters is not None:
            self.grouping_radius_meters = grouping_radius_meters
        else:
            # Get from environment variable, default to 150 meters
            self.grouping_radius_meters = int(os.getenv("MAP_GROUPING_RADIUS_METERS", "150"))

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

    def haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate the great circle distance between two points in meters."""
        # Radius of earth in meters
        R = 6371000
        
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a))
        
        return R * c

    def export(self) -> bool:
        """Main export function that generates aggregated map data files."""
        start_time = time.time()
        logger.info("Starting aggregated map data export from PostgreSQL")

        try:
            # Connect to PostgreSQL
            conn = psycopg2.connect(self.pg_conn_string)

            # Get all location data with source information
            locations_data = self._fetch_all_locations_with_sources(conn)
            
            if not locations_data:
                logger.warning("No locations found to export")
                return False

            # Group nearby locations
            location_groups = self._group_nearby_locations(locations_data)
            
            # Create aggregated location entries
            aggregated_locations = self._create_aggregated_locations(location_groups)

            # Generate output files
            success = self._generate_output_files(aggregated_locations)

            conn.close()

            elapsed = time.time() - start_time
            logger.info(f"Aggregated map data export completed in {elapsed:.2f} seconds")

            return success

        except Exception as e:
            logger.error(f"Map data export failed: {e}")
            return False

    def _fetch_all_locations_with_sources(self, conn) -> List[Dict[str, Any]]:
        """Fetch all locations with their source scraper information."""
        locations = []
        
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Get ALL locations, not just canonical ones, with their source info
            cursor.execute("""
                WITH location_phones AS (
                    SELECT
                        COALESCE(p.location_id, p.organization_id) as ref_id,
                        p.location_id,
                        p.organization_id,
                        MIN(p.number || COALESCE(' x' || p.extension, '')) as phone_number
                    FROM phone p
                    GROUP BY p.location_id, p.organization_id
                ),
                location_services AS (
                    SELECT
                        sal.location_id,
                        STRING_AGG(DISTINCT s.name, ', ' ORDER BY s.name) as services
                    FROM service_at_location sal
                    JOIN service s ON s.id = sal.service_id
                    GROUP BY sal.location_id
                ),
                location_languages AS (
                    SELECT
                        l.location_id,
                        STRING_AGG(DISTINCT l.name, ', ' ORDER BY l.name) as languages
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
                    JOIN service_at_location sal ON s.service_id = sal.service_id
                    WHERE sal.location_id IS NOT NULL
                      AND (s.opens_at IS NOT NULL OR s.closes_at IS NOT NULL OR s.description IS NOT NULL)
                    ORDER BY sal.location_id, s.opens_at, s.closes_at
                )
                SELECT
                    l.id,
                    l.latitude as lat,
                    l.longitude as lng,
                    l.name as location_name,
                    o.name as org_name,
                    o.website,
                    o.email,
                    COALESCE(o.description, l.description) as description,
                    CONCAT_WS(', ',
                        NULLIF(a.address_1, ''),
                        NULLIF(a.address_2, ''),
                        NULLIF(a.city, ''),
                        NULLIF(a.state_province, ''),
                        NULLIF(a.postal_code, '')
                    ) as address,
                    a.address_1,
                    a.address_2,
                    a.city,
                    a.state_province as state,
                    a.postal_code as zip,
                    lp.phone_number as phone,
                    -- Source information
                    ls.scraper_id,
                    ls.created_at as first_seen,
                    ls.updated_at as last_updated,
                    -- Additional data
                    lsrv.services,
                    llang.languages,
                    lsch.opens_at,
                    lsch.closes_at,
                    lsch.byday,
                    lsch.schedule_description,
                    -- Validation data
                    l.confidence_score,
                    l.validation_status,
                    l.validation_notes,
                    l.geocoding_source,
                    l.location_type,
                    l.is_canonical
                FROM location l
                JOIN location_source ls ON ls.location_id = l.id
                LEFT JOIN address a ON a.location_id = l.id
                LEFT JOIN organization o ON o.id = l.organization_id
                LEFT JOIN location_phones lp ON (lp.location_id = l.id OR (lp.location_id IS NULL AND lp.organization_id = o.id))
                LEFT JOIN location_services lsrv ON lsrv.location_id = l.id
                LEFT JOIN location_languages llang ON llang.location_id = l.id
                LEFT JOIN location_schedules lsch ON lsch.location_id = l.id
                WHERE l.latitude IS NOT NULL
                  AND l.longitude IS NOT NULL
                  AND l.latitude BETWEEN -90 AND 90
                  AND l.longitude BETWEEN -180 AND 180
                  -- Include all locations, not just rejected ones
                  AND (l.validation_status IS NULL OR l.validation_status != 'rejected')
                ORDER BY l.latitude, l.longitude, ls.scraper_id
            """)
            
            for row in cursor:
                locations.append(dict(row))
                
        logger.info(f"Fetched {len(locations)} location records from database")
        return locations

    def _group_nearby_locations(self, locations: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """Group locations that are within the grouping radius of each other."""
        groups = []
        used_indices = set()
        
        for i, loc1 in enumerate(locations):
            if i in used_indices:
                continue
                
            # Start a new group with this location
            group = [loc1]
            used_indices.add(i)
            
            # Find all nearby locations
            for j, loc2 in enumerate(locations):
                if j <= i or j in used_indices:
                    continue
                    
                # Check distance
                distance = self.haversine_distance(
                    loc1['lat'], loc1['lng'],
                    loc2['lat'], loc2['lng']
                )
                
                if distance <= self.grouping_radius_meters:
                    group.append(loc2)
                    used_indices.add(j)
            
            groups.append(group)
        
        logger.info(f"Grouped {len(locations)} locations into {len(groups)} groups")
        return groups

    def _create_aggregated_locations(self, location_groups: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """Create aggregated location entries from groups."""
        aggregated = []
        
        for group in location_groups:
            # Use the first canonical location as the primary, or just the first one
            primary = next((loc for loc in group if loc.get('is_canonical')), group[0])
            
            # Collect all sources
            sources = []
            scrapers_seen = set()
            
            for loc in group:
                scraper_id = loc.get('scraper_id')
                if scraper_id and scraper_id not in scrapers_seen:
                    scrapers_seen.add(scraper_id)
                    
                    # Format schedule if available
                    schedule = None
                    if loc.get('opens_at') or loc.get('closes_at') or loc.get('schedule_description'):
                        schedule = {
                            'opens_at': str(loc['opens_at']) if loc.get('opens_at') else None,
                            'closes_at': str(loc['closes_at']) if loc.get('closes_at') else None,
                            'byday': loc.get('byday') or '',
                            'description': loc.get('schedule_description') or ''
                        }
                    
                    source_data = {
                        'scraper': scraper_id,
                        'name': loc.get('location_name') or loc.get('org_name') or '',
                        'org': loc.get('org_name') or '',
                        'description': loc.get('description') or '',
                        'services': loc.get('services') or '',
                        'languages': loc.get('languages') or '',
                        'schedule': schedule,
                        'phone': loc.get('phone') or '',
                        'website': loc.get('website') or '',
                        'email': loc.get('email') or '',
                        'address': loc.get('address') or '',
                        'first_seen': loc['first_seen'].isoformat() if loc.get('first_seen') else None,
                        'last_updated': loc['last_updated'].isoformat() if loc.get('last_updated') else None,
                        'confidence_score': loc.get('confidence_score', 50)
                    }
                    sources.append(source_data)
            
            # Defensive validation of state field
            state_value = primary.get('state') or ''
            if len(state_value) > 2:
                # Try to extract a valid 2-letter code
                if len(state_value) >= 2 and state_value[:2].isalpha():
                    state_value = state_value[:2].upper()
                else:
                    state_value = ''
            
            # Create the aggregated location
            aggregated_location = {
                'id': primary['id'],
                'lat': float(primary['lat']),
                'lng': float(primary['lng']),
                # Use the most common or highest confidence name
                'name': primary.get('location_name') or primary.get('org_name') or 'Food Assistance Location',
                'org': primary.get('org_name') or 'Community Organization',
                'address': primary.get('address') or 'Address not available',
                'city': primary.get('city') or '',
                'state': state_value,
                'zip': primary.get('zip') or '',
                # Primary contact info
                'phone': primary.get('phone') or '',
                'website': primary.get('website') or '',
                'email': primary.get('email') or '',
                'description': primary.get('description') or '',
                # Aggregated data
                'source_count': len(sources),
                'sources': sources,
                # Validation info from primary
                'confidence_score': primary.get('confidence_score', 50),
                'validation_status': primary.get('validation_status') or 'needs_review',
                'geocoding_source': primary.get('geocoding_source') or '',
                'location_type': primary.get('location_type') or ''
            }
            
            aggregated.append(aggregated_location)
        
        return aggregated

    def _generate_output_files(self, locations: List[Dict[str, Any]]) -> bool:
        """Generate JSON output files for map interface."""
        try:
            # Ensure data directory exists
            data_dir = self.data_repo_path / "data"
            data_dir.mkdir(exist_ok=True)

            # Create metadata
            states = set(loc["state"] for loc in locations if loc["state"])
            
            # Calculate statistics
            total_sources = sum(loc['source_count'] for loc in locations)
            multi_source_locations = sum(1 for loc in locations if loc['source_count'] > 1)
            
            metadata = {
                "generated": datetime.now(UTC).isoformat(),
                "total_locations": len(locations),
                "total_source_records": total_sources,
                "multi_source_locations": multi_source_locations,
                "states_covered": len(states),
                "coverage": f"{len(states)} US states/territories",
                "source": "HAARRRvest - Pantry Pirate Radio Database (Aggregated)",
                "format_version": "4.0",  # New version for aggregated data
                "export_method": "PostgreSQL Aggregated Export",
                "aggregation_radius_meters": self.grouping_radius_meters
            }

            # Write main locations file
            output_data = {
                "metadata": metadata,
                "locations": locations
            }

            output_file = data_dir / "locations.json"
            logger.info(f"Writing {len(locations)} aggregated locations to {output_file}")

            # Write with minimal formatting for smaller file size
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(output_data, f, separators=(",", ":"), ensure_ascii=False)

            # Generate state files
            self._generate_state_files(locations, metadata, data_dir)

            # Print summary
            self._print_summary(locations, metadata, output_file)

            return True

        except Exception as e:
            logger.error(f"Failed to generate output files: {e}")
            return False

    def _generate_state_files(self, locations: List[Dict[str, Any]], base_metadata: Dict, data_dir: Path):
        """Generate state-specific files."""
        # Group locations by state
        locations_by_state = {}
        
        for location in locations:
            state = location.get("state") or "UNKNOWN"
            if state not in locations_by_state:
                locations_by_state[state] = []
            locations_by_state[state].append(location)
        
        # Create states directory
        states_dir = data_dir / "states"
        states_dir.mkdir(exist_ok=True)
        
        # Write state files
        for state, state_locations in locations_by_state.items():
            if state and state != "UNKNOWN" and state in VALID_STATE_CODES:
                try:
                    state_metadata = base_metadata.copy()
                    state_metadata["total_locations"] = len(state_locations)
                    state_metadata["filtered_by"] = f"state = {state}"
                    
                    state_data = {
                        "metadata": state_metadata,
                        "locations": state_locations
                    }
                    
                    state_file = states_dir / f"{state.lower()}.json"
                    with open(state_file, "w", encoding="utf-8") as f:
                        json.dump(state_data, f, separators=(",", ":"), ensure_ascii=False)
                except Exception as e:
                    logger.error(f"Failed to write state file for {state}: {e}")
        
        logger.info(f"Created {len(locations_by_state)} state-specific files")

    def _print_summary(self, locations: List[Dict], metadata: Dict, output_file: Path):
        """Print export summary statistics."""
        print("\n=== Aggregated Export Summary ===")
        print(f"Total locations: {len(locations)}")
        print(f"Total source records: {metadata['total_source_records']}")
        print(f"Locations with multiple sources: {metadata['multi_source_locations']}")
        print(f"Aggregation radius: {self.grouping_radius_meters} meters")
        print(f"Generated: {metadata['generated']}")
        print(f"Output file: {output_file}")
        
        # Source distribution
        source_counts = {}
        for loc in locations:
            for source in loc.get('sources', []):
                scraper = source.get('scraper', 'unknown')
                source_counts[scraper] = source_counts.get(scraper, 0) + 1
        
        print("\n=== Source Distribution ===")
        for scraper, count in sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  {scraper}: {count} locations")


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

    exporter = AggregatedMapDataExporter(data_repo_path)
    success = exporter.export()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()