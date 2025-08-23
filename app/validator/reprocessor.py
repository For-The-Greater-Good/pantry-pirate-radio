"""Service for reprocessing locations marked as 'needs_review'."""

import asyncio
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, UTC

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.zip_state_mapping import (
    get_state_from_zip,
    get_state_from_city,
    resolve_state_conflict,
)
from app.llm.utils.geocoding_validator import GeocodingValidator

logger = logging.getLogger(__name__)


class NeedsReviewReprocessor:
    """Reprocess locations marked as needs_review to fix data quality issues."""

    def __init__(self, session: Optional[AsyncSession] = None):
        """Initialize reprocessor with database session."""
        self.session = session
        self.geocoding_validator = GeocodingValidator()
        self.stats = {
            "total_processed": 0,
            "state_corrected": 0,
            "coordinates_corrected": 0,
            "status_updated": 0,
            "errors": 0,
        }

    async def get_needs_review_locations(
        self, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Fetch locations that need review.

        Args:
            limit: Maximum number of locations to fetch (None for all)

        Returns:
            List of location records with address and validation data
        """
        query = """
            SELECT
                l.id,
                l.name,
                l.latitude,
                l.longitude,
                l.confidence_score,
                l.validation_status,
                l.validation_notes,
                l.geocoding_source,
                a.id as address_id,
                a.address_1,
                a.city,
                a.state_province,
                a.postal_code,
                ls.scraper_id
            FROM location l
            LEFT JOIN address a ON a.location_id = l.id
            LEFT JOIN location_source ls ON ls.location_id = l.id
            WHERE l.validation_status = 'needs_review'
              AND l.validation_notes::jsonb->'validation_results'->>'within_state_bounds' = 'false'
            ORDER BY l.confidence_score ASC
        """

        if limit:
            query += " LIMIT :limit"
            result = await self.session.execute(text(query), {"limit": limit})
        else:
            result = await self.session.execute(text(query))
        locations = []
        for row in result:
            locations.append(
                {
                    "id": row.id,
                    "name": row.name,
                    "latitude": row.latitude,
                    "longitude": row.longitude,
                    "confidence_score": row.confidence_score,
                    "validation_status": row.validation_status,
                    "validation_notes": row.validation_notes,
                    "geocoding_source": row.geocoding_source,
                    "address_id": row.address_id,
                    "address_1": row.address_1,
                    "city": row.city,
                    "state_province": row.state_province,
                    "postal_code": row.postal_code,
                    "scraper_id": row.scraper_id,
                }
            )

        return locations

    async def analyze_state_conflict(self, location: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze state/coordinate/zip conflicts to determine truth.

        Args:
            location: Location data with address and coordinates

        Returns:
            Analysis result with corrections needed
        """
        claimed_state = location.get("state_province")
        postal_code = location.get("postal_code")
        city = location.get("city")
        lat = location.get("latitude")
        lng = location.get("longitude")

        # Get state from ZIP
        zip_state = get_state_from_zip(postal_code) if postal_code else None

        # Get state from city
        city_state = get_state_from_city(city) if city else None

        # Get state from coordinates
        coord_state = None
        if lat and lng:
            # Use geocoding validator to check which state the coordinates are in
            for state in ["AL", "WI", "CO", "NY", "CA", "TX", "FL", "PA", "OH", "IL"]:
                if self.geocoding_validator.is_within_state_bounds(lat, lng, state):
                    coord_state = state
                    break

        logger.info(
            f"Analyzing {location['name']}: "
            f"claimed={claimed_state}, zip={zip_state}, "
            f"city={city_state}, coord={coord_state}"
        )

        # Resolve conflicts
        resolved_state, reason = resolve_state_conflict(
            claimed_state, postal_code, city, coord_state
        )

        # Determine if coordinates might be wrong
        coordinates_suspect = False
        if zip_state and city_state and zip_state == city_state:
            # ZIP and city agree
            if coord_state and coord_state != zip_state:
                # But coordinates point elsewhere - coords might be wrong
                coordinates_suspect = True

        return {
            "location_id": location["id"],
            "claimed_state": claimed_state,
            "zip_state": zip_state,
            "city_state": city_state,
            "coord_state": coord_state,
            "resolved_state": resolved_state,
            "resolution_reason": reason,
            "state_needs_correction": resolved_state != claimed_state,
            "coordinates_suspect": coordinates_suspect,
            "confidence_adjustment": 0,
        }

    async def correct_state(
        self, address_id: str, old_state: str, new_state: str, reason: str
    ) -> bool:
        """Update state in address table.

        Args:
            address_id: Address record ID
            old_state: Current incorrect state
            new_state: Corrected state
            reason: Reason for correction

        Returns:
            True if successful
        """
        try:
            # Skip if we can't determine a new state
            if not new_state:
                logger.warning(
                    f"Cannot correct state for address {address_id}: "
                    f"no valid state could be determined"
                )
                return False

            # Handle empty old_state differently
            if not old_state or old_state == "":
                update_query = """
                    UPDATE address
                    SET state_province = :new_state,
                        updated_at = :updated_at
                    WHERE id = :address_id
                      AND (state_province IS NULL OR state_province = '')
                """
            else:
                update_query = """
                    UPDATE address
                    SET state_province = :new_state,
                        updated_at = :updated_at
                    WHERE id = :address_id
                      AND state_province = :old_state
                """

            result = await self.session.execute(
                text(update_query),
                {
                    "address_id": address_id,
                    "old_state": old_state if old_state else "",
                    "new_state": new_state,
                    "updated_at": datetime.now(UTC),
                },
            )

            if result.rowcount > 0:
                logger.info(
                    f"Corrected state for address {address_id}: "
                    f"'{old_state}' -> '{new_state}' (reason: {reason})"
                )
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to correct state for {address_id}: {e}")
            return False

    async def update_validation_notes(
        self, location_id: str, correction_info: Dict[str, Any]
    ) -> bool:
        """Update validation notes with correction information.

        Args:
            location_id: Location ID
            correction_info: Information about corrections made

        Returns:
            True if successful
        """
        try:
            # Get current validation notes
            query = "SELECT validation_notes FROM location WHERE id = :location_id"
            result = await self.session.execute(
                text(query), {"location_id": location_id}
            )
            row = result.fetchone()

            if row and row.validation_notes:
                notes = (
                    row.validation_notes
                    if isinstance(row.validation_notes, dict)
                    else {}
                )
            else:
                notes = {}

            # Add correction info
            if "corrections" not in notes:
                notes["corrections"] = []

            notes["corrections"].append(
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "type": "state_reprocessing",
                    **correction_info,
                }
            )

            # Update validation results if state was corrected
            if correction_info.get("state_corrected"):
                if "validation_results" in notes:
                    notes["validation_results"]["within_state_bounds"] = True

            # Update database
            update_query = """
                UPDATE location
                SET validation_notes = :notes,
                    updated_at = :updated_at
                WHERE id = :location_id
            """

            await self.session.execute(
                text(update_query),
                {
                    "location_id": location_id,
                    "notes": json.dumps(notes),
                    "updated_at": datetime.now(UTC),
                },
            )

            return True

        except Exception as e:
            logger.error(f"Failed to update validation notes for {location_id}: {e}")
            return False

    async def recalculate_confidence(
        self, location_id: str, state_corrected: bool, coordinates_suspect: bool
    ) -> int:
        """Recalculate confidence score after corrections.

        Args:
            location_id: Location ID
            state_corrected: Whether state was corrected
            coordinates_suspect: Whether coordinates are suspect

        Returns:
            New confidence score
        """
        # Get current score
        query = "SELECT confidence_score FROM location WHERE id = :location_id"
        result = await self.session.execute(text(query), {"location_id": location_id})
        row = result.fetchone()

        current_score = row.confidence_score if row else 50
        new_score = current_score

        # Add points for state correction (fixed a known issue)
        if state_corrected:
            new_score += 20  # Restore the 20 points that were deducted

        # Deduct points if coordinates are suspect
        if coordinates_suspect:
            new_score -= 15

        # Cap at 0-100
        new_score = max(0, min(100, new_score))

        # Update score and potentially status
        new_status = "needs_review"
        if new_score >= 80:
            new_status = "verified"
        elif new_score < 10:
            new_status = "rejected"

        update_query = """
            UPDATE location
            SET confidence_score = :score,
                validation_status = :status,
                updated_at = :updated_at
            WHERE id = :location_id
        """

        await self.session.execute(
            text(update_query),
            {
                "location_id": location_id,
                "score": new_score,
                "status": new_status,
                "updated_at": datetime.now(UTC),
            },
        )

        return new_score

    async def process_location(self, location: Dict[str, Any]) -> Dict[str, Any]:
        """Process a single location to fix issues.

        Args:
            location: Location data

        Returns:
            Processing result
        """
        try:
            # Analyze conflicts
            analysis = await self.analyze_state_conflict(location)

            result = {
                "location_id": location["id"],
                "name": location["name"],
                "state_corrected": False,
                "coordinates_flagged": False,
                "new_confidence": location["confidence_score"],
                "new_status": location["validation_status"],
            }

            # Correct state if needed
            if analysis["state_needs_correction"] and location.get("address_id"):
                success = await self.correct_state(
                    location["address_id"],
                    analysis["claimed_state"],
                    analysis["resolved_state"],
                    analysis["resolution_reason"],
                )

                if success:
                    result["state_corrected"] = True
                    self.stats["state_corrected"] += 1

                    # Update validation notes
                    await self.update_validation_notes(
                        location["id"],
                        {
                            "state_corrected": True,
                            "old_state": analysis["claimed_state"],
                            "new_state": analysis["resolved_state"],
                            "reason": analysis["resolution_reason"],
                        },
                    )

            # Flag coordinates if suspect
            if analysis["coordinates_suspect"]:
                result["coordinates_flagged"] = True
                self.stats["coordinates_corrected"] += 1

                await self.update_validation_notes(
                    location["id"],
                    {
                        "coordinates_suspect": True,
                        "reason": "State/ZIP agree but coordinates point elsewhere",
                    },
                )

            # Recalculate confidence
            new_score = await self.recalculate_confidence(
                location["id"], result["state_corrected"], result["coordinates_flagged"]
            )

            result["new_confidence"] = new_score

            self.stats["total_processed"] += 1

            # Commit after each successful location
            await self.session.commit()

            return result

        except Exception as e:
            logger.error(f"Error processing location {location['id']}: {e}")
            # Rollback the failed transaction
            await self.session.rollback()
            self.stats["errors"] += 1
            return {"location_id": location["id"], "error": str(e)}

    async def reprocess_batch(self, limit: Optional[int] = None) -> Dict[str, Any]:
        """Reprocess a batch of needs_review locations.

        Args:
            limit: Maximum number to process (None for all)

        Returns:
            Processing statistics
        """
        if limit:
            logger.info(
                f"Starting reprocessing of up to {limit} needs_review locations"
            )
        else:
            logger.info("Starting reprocessing of ALL needs_review locations")

        # Get locations to process
        locations = await self.get_needs_review_locations(limit)

        if not locations:
            logger.info("No locations found needing reprocessing")
            return self.stats

        logger.info(f"Found {len(locations)} locations to reprocess")

        # Process each location
        results = []
        for location in locations:
            result = await self.process_location(location)
            results.append(result)

            # Log progress every 10 locations
            if len(results) % 10 == 0:
                logger.info(f"Processed {len(results)}/{len(locations)} locations")

        logger.info(
            f"Reprocessing complete: "
            f"processed={self.stats['total_processed']}, "
            f"state_corrected={self.stats['state_corrected']}, "
            f"coords_flagged={self.stats['coordinates_corrected']}, "
            f"errors={self.stats['errors']}"
        )

        return self.stats


async def main():
    """Run reprocessing as standalone script."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Create async engine
    engine = create_async_engine(
        settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"),
        echo=False,
    )

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        reprocessor = NeedsReviewReprocessor(session)
        # Process ALL needs_review locations
        stats = await reprocessor.reprocess_batch(limit=None)

        print("\n=== Reprocessing Complete ===")
        print(f"Total Processed: {stats['total_processed']}")
        print(f"States Corrected: {stats['state_corrected']}")
        print(f"Coordinates Flagged: {stats['coordinates_corrected']}")
        print(f"Errors: {stats['errors']}")


if __name__ == "__main__":
    asyncio.run(main())
