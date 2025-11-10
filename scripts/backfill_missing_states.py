#!/usr/bin/env python3
"""Backfill missing state data for locations with valid lat/long coordinates.

This script uses point-in-polygon checks against GeoJSON state boundaries
to determine which state a coordinate falls into. This is much more reliable
than reverse geocoding APIs which frequently fail.

Usage:
    python3 scripts/backfill_missing_states.py                  # Dry run (preview changes)
    python3 scripts/backfill_missing_states.py --execute        # Actually update database
    python3 scripts/backfill_missing_states.py --limit 50       # Process only 50 records
    python3 scripts/backfill_missing_states.py --batch-size 10  # Process in batches of 10
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple, List

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from shapely.geometry import Point, shape
from shapely.prepared import prep

from app.core.config import settings
from app.core.zip_state_mapping import get_state_from_city
from app.core.state_mapping import normalize_state_to_code
from app.database.models import LocationModel, AddressModel


# US bounds for coordinate validation
US_BOUNDS = {
    "lat_min": 24.0,  # Southern tip of Florida
    "lat_max": 50.0,  # Northern border
    "lon_min": -125.0,  # West coast
    "lon_max": -66.0,  # East coast
}

# State FIPS codes to abbreviations
STATE_FIPS_TO_ABBR = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA",
    "08": "CO", "09": "CT", "10": "DE", "11": "DC", "12": "FL",
    "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN",
    "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME",
    "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS",
    "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND",
    "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI",
    "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT",
    "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI",
    "56": "WY", "72": "PR", "78": "VI",
}


class StateGeometryLoader:
    """Loads and caches state boundary geometries from GeoJSON files."""

    def __init__(self, geojson_dir: Path):
        """Initialize the geometry loader.

        Args:
            geojson_dir: Directory containing state GeoJSON files
        """
        self.geojson_dir = geojson_dir
        self.state_geometries: Dict[str, List] = {}
        self.logger = logging.getLogger(__name__)

    def load_all_states(self):
        """Load all state geometries into memory."""
        self.logger.info("Loading state boundary geometries from GeoJSON files...")

        geojson_files = list(self.geojson_dir.glob("*.json"))
        self.logger.info(f"Found {len(geojson_files)} GeoJSON files")

        for geojson_file in geojson_files:
            # Extract state code from filename (e.g., "co_colorado_zip_codes_geo.min.json" -> "CO")
            state_code = geojson_file.stem.split("_")[0].upper()

            if state_code == "README":
                continue

            try:
                with open(geojson_file, "r") as f:
                    data = json.load(f)

                # Convert all features to Shapely geometries for this state
                geometries = []
                for feature in data.get("features", []):
                    try:
                        geom = shape(feature["geometry"])
                        # Prepare geometry for faster point-in-polygon checks
                        geometries.append(prep(geom))
                    except Exception as e:
                        self.logger.debug(f"Error loading feature from {geojson_file}: {e}")
                        continue

                if geometries:
                    self.state_geometries[state_code] = geometries
                    self.logger.debug(f"Loaded {len(geometries)} geometries for {state_code}")

            except Exception as e:
                self.logger.error(f"Error loading {geojson_file}: {e}")
                continue

        self.logger.info(f"Loaded geometries for {len(self.state_geometries)} states")

    def find_state_for_point(self, lat: float, lon: float) -> Optional[str]:
        """Find which state a point falls into using point-in-polygon checks.

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            Two-letter state code or None if not found
        """
        point = Point(lon, lat)  # Note: Shapely uses (lon, lat) order

        # Check each state's geometries
        for state_code, geometries in self.state_geometries.items():
            for geom in geometries:
                try:
                    if geom.contains(point):
                        return state_code
                except Exception as e:
                    self.logger.debug(f"Error checking point in {state_code}: {e}")
                    continue

        return None


class StateBackfiller:
    """Backfills missing state data using point-in-polygon checks."""

    def __init__(
        self,
        session: AsyncSession,
        geometry_loader: StateGeometryLoader,
        dry_run: bool = True,
    ):
        """Initialize the backfiller.

        Args:
            session: Database session
            geometry_loader: State geometry loader
            dry_run: If True, don't actually update the database
        """
        self.session = session
        self.geometry_loader = geometry_loader
        self.dry_run = dry_run

        # Statistics tracking
        self.stats = {
            "total_processed": 0,
            "skipped_invalid_coords": 0,
            "skipped_out_of_bounds": 0,
            "updated_point_in_polygon": 0,
            "updated_city_lookup": 0,
            "failed": 0,
            "errors": 0,
        }

        # Setup logging
        self.logger = logging.getLogger(__name__)

    def is_valid_coordinates(
        self, lat: float, lon: float
    ) -> Tuple[bool, Optional[str]]:
        """Check if coordinates are valid and within US bounds.

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            Tuple of (is_valid, reason_if_invalid)
        """
        # Check for null/None
        if lat is None or lon is None:
            return False, "null coordinates"

        # Check for (0,0) placeholder
        if abs(float(lat)) < 0.001 and abs(float(lon)) < 0.001:
            return False, "zero coordinates (placeholder)"

        # Check US bounds
        if not (
            US_BOUNDS["lat_min"] <= float(lat) <= US_BOUNDS["lat_max"]
            and US_BOUNDS["lon_min"] <= float(lon) <= US_BOUNDS["lon_max"]
        ):
            return False, f"out of US bounds ({lat}, {lon})"

        return True, None

    async def get_locations_needing_backfill(self, limit: Optional[int] = None):
        """Query locations with valid lat/long but missing state.

        Args:
            limit: Optional limit on number of records to fetch

        Returns:
            List of location records with addresses
        """
        self.logger.info("Querying locations with missing state data...")

        # Query for locations with:
        # 1. Valid lat/long (not null)
        # 2. At least one address
        # 3. Address has empty/missing state_province
        query = (
            select(LocationModel, AddressModel)
            .join(AddressModel, LocationModel.id == AddressModel.location_id)
            .where(
                and_(
                    LocationModel.latitude.isnot(None),
                    LocationModel.longitude.isnot(None),
                    or_(
                        AddressModel.state_province == "",
                        AddressModel.state_province.is_(None),
                    ),
                )
            )
        )

        if limit:
            query = query.limit(limit)

        result = await self.session.execute(query)
        records = result.all()

        self.logger.info(f"Found {len(records)} locations needing state backfill")
        return records

    async def process_location(
        self, location: LocationModel, address: AddressModel
    ) -> bool:
        """Process a single location to backfill state data.

        Args:
            location: Location model
            address: Address model

        Returns:
            True if state was updated, False otherwise
        """
        location_name = location.name or f"Location {location.id[:8]}"
        self.stats["total_processed"] += 1

        self.logger.info(f"\n{'='*60}")
        self.logger.info(f"Processing: {location_name}")
        self.logger.info(
            f"Coordinates: ({location.latitude}, {location.longitude})"
        )
        self.logger.info(f"Current address: {address.city}, {address.postal_code}")

        # Validate coordinates
        is_valid, reason = self.is_valid_coordinates(
            location.latitude, location.longitude
        )
        if not is_valid:
            self.logger.warning(f"⚠️  Skipping - {reason}")
            if "zero" in reason:
                self.stats["skipped_invalid_coords"] += 1
            else:
                self.stats["skipped_out_of_bounds"] += 1
            return False

        # Try point-in-polygon check first
        self.logger.info("🔍 Checking point-in-polygon against state boundaries...")
        state = self.geometry_loader.find_state_for_point(
            float(location.latitude), float(location.longitude)
        )
        source = None

        if state:
            source = "point_in_polygon"
            self.logger.info(f"✅ Point-in-polygon found state: {state}")
        else:
            # Try city lookup as fallback
            self.logger.info("🔄 Point-in-polygon failed, trying city lookup...")
            if address.city:
                city_state = get_state_from_city(address.city)
                if city_state:
                    state = city_state
                    source = "city_lookup"
                    self.logger.info(f"✅ City lookup found state: {state}")

        if not state:
            self.logger.warning("❌ All strategies failed - no state found")
            self.stats["failed"] += 1
            return False

        # Update the database
        if self.dry_run:
            self.logger.info(
                f"🔍 DRY RUN - Would update state to: {state} (source: {source})"
            )
        else:
            try:
                address.state_province = state
                await self.session.commit()
                self.logger.info(f"✅ Updated state to: {state} (source: {source})")
            except Exception as e:
                self.logger.error(f"❌ Database update failed: {e}")
                await self.session.rollback()
                self.stats["errors"] += 1
                return False

        # Update stats
        if source == "point_in_polygon":
            self.stats["updated_point_in_polygon"] += 1
        elif source == "city_lookup":
            self.stats["updated_city_lookup"] += 1

        return True

    async def backfill_batch(
        self, batch_size: int = 50, limit: Optional[int] = None
    ) -> Dict[str, int]:
        """Backfill states in batches.

        Args:
            batch_size: Number of records to process in each batch
            limit: Optional total limit on records to process

        Returns:
            Statistics dictionary
        """
        # Get locations needing backfill
        records = await self.get_locations_needing_backfill(limit)

        if not records:
            self.logger.info("No locations found needing state backfill")
            return self.stats

        # Process in batches
        total_records = len(records)
        for i in range(0, total_records, batch_size):
            batch = records[i : i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (total_records + batch_size - 1) // batch_size

            self.logger.info(
                f"\n{'='*60}\n"
                f"Processing batch {batch_num}/{total_batches} "
                f"(records {i+1}-{min(i+batch_size, total_records)} of {total_records})\n"
                f"{'='*60}"
            )

            for location, address in batch:
                try:
                    await self.process_location(location, address)
                except Exception as e:
                    self.logger.error(
                        f"Error processing location {location.id}: {e}",
                        exc_info=True,
                    )
                    self.stats["errors"] += 1

        return self.stats

    def print_summary(self):
        """Print a summary of the backfill operation."""
        self.logger.info("\n" + "=" * 60)
        self.logger.info("BACKFILL SUMMARY")
        self.logger.info("=" * 60)
        self.logger.info(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE UPDATE'}")
        self.logger.info(f"Total processed: {self.stats['total_processed']}")
        self.logger.info(f"Skipped (invalid coords): {self.stats['skipped_invalid_coords']}")
        self.logger.info(f"Skipped (out of bounds): {self.stats['skipped_out_of_bounds']}")
        self.logger.info(
            f"Updated via point-in-polygon: {self.stats['updated_point_in_polygon']}"
        )
        self.logger.info(f"Updated via city lookup: {self.stats['updated_city_lookup']}")
        self.logger.info(f"Failed (no state found): {self.stats['failed']}")
        self.logger.info(f"Errors: {self.stats['errors']}")

        total_updated = (
            self.stats["updated_point_in_polygon"]
            + self.stats["updated_city_lookup"]
        )
        self.logger.info(f"\nTotal {'would be ' if self.dry_run else ''}updated: {total_updated}")
        self.logger.info("=" * 60)


async def main():
    """Main function to run the backfill process."""
    parser = argparse.ArgumentParser(
        description="Backfill missing state data using GeoJSON boundaries"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually update the database (default is dry-run)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of records to process",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Number of records to process in each batch (default: 50)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose debug logging",
    )
    parser.add_argument(
        "--geojson-dir",
        type=str,
        default="docs/GeoJson/States",
        help="Directory containing state GeoJSON files (default: docs/GeoJson/States)",
    )

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(
                f"backfill_missing_states_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            ),
        ],
    )

    logger = logging.getLogger(__name__)

    # Print header
    logger.info("=" * 60)
    logger.info("STATE BACKFILL PROCESS (GeoJSON Point-in-Polygon)")
    logger.info("=" * 60)
    logger.info(f"Mode: {'LIVE UPDATE' if args.execute else 'DRY RUN (preview only)'}")
    logger.info(f"Batch size: {args.batch_size}")
    if args.limit:
        logger.info(f"Limit: {args.limit} records")
    logger.info("=" * 60)

    if not args.execute:
        logger.warning(
            "\n⚠️  DRY RUN MODE - No changes will be made to the database\n"
            "⚠️  Use --execute flag to actually update the database\n"
        )

    # Load state geometries
    geojson_dir = Path(__file__).parent.parent / args.geojson_dir
    if not geojson_dir.exists():
        logger.error(f"GeoJSON directory not found: {geojson_dir}")
        sys.exit(1)

    geometry_loader = StateGeometryLoader(geojson_dir)
    geometry_loader.load_all_states()

    if not geometry_loader.state_geometries:
        logger.error("No state geometries loaded!")
        sys.exit(1)

    # Create database connection
    db_url = settings.DATABASE_URL
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")
    elif db_url.startswith("postgresql+psycopg2://"):
        db_url = db_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")

    engine = create_async_engine(db_url, echo=False, pool_pre_ping=True)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with async_session() as session:
            # Create backfiller
            backfiller = StateBackfiller(
                session, geometry_loader, dry_run=not args.execute
            )

            # Run backfill
            await backfiller.backfill_batch(
                batch_size=args.batch_size, limit=args.limit
            )

            # Print summary
            backfiller.print_summary()

            if not args.execute:
                logger.warning(
                    "\n⚠️  This was a DRY RUN - No changes were made\n"
                    "⚠️  Use --execute flag to actually update the database\n"
                )

    except Exception as e:
        logger.error(f"Fatal error during backfill: {e}", exc_info=True)
        sys.exit(1)

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
