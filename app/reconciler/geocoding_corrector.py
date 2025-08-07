"""Geocoding correction utilities for the reconciler.

This module provides functionality for detecting and correcting
invalid geographic coordinates in the database.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.geocoding import get_geocoding_service
from app.llm.utils.geocoding_validator import GeocodingValidator

logger = logging.getLogger(__name__)


class GeocodingCorrector:
    """Corrects invalid geographic coordinates in location data."""

    def __init__(self, db: Optional[Session] = None):
        """Initialize the geocoding corrector.

        Args:
            db: Database session (optional)
        """
        self.db = db
        self.validator = GeocodingValidator()
        self.geocoding_service = get_geocoding_service()

    def find_invalid_locations(self) -> List[Dict[str, Any]]:
        """Find all locations with invalid coordinates.

        Returns:
            List of locations with invalid coordinates and their issues
        """
        query = text(
            """
            SELECT
                l.id,
                l.name,
                l.latitude,
                l.longitude,
                a.state_province,
                a.city,
                a.address_1
            FROM location l
            LEFT JOIN address a ON l.id = a.location_id
            WHERE l.latitude IS NOT NULL
            AND l.longitude IS NOT NULL
        """
        )

        result = self.db.execute(query)
        invalid_locations = []

        for row in result:
            lat = row.latitude
            lon = row.longitude

            # Check for various types of invalid coordinates
            issue = None

            # Check if coordinates are projected
            if self.validator.is_projected_coordinate(
                lat
            ) or self.validator.is_projected_coordinate(lon):
                issue = "Projected coordinates detected"
            # Check if not valid lat/long
            elif not self.validator.is_valid_lat_long(lat, lon):
                issue = f"Invalid lat/long values: {lat}, {lon}"
            # Check state bounds if state is known
            elif row.state_province:
                if not self.validator.is_within_state_bounds(
                    lat, lon, row.state_province
                ):
                    issue = f"Coordinates outside {row.state_province} bounds"
            # Check US bounds
            elif not self.validator.is_within_us_bounds(lat, lon):
                # Special case for HI and AK
                if row.state_province not in ["HI", "AK"]:
                    issue = "Coordinates outside US bounds"

            if issue:
                invalid_locations.append(
                    {
                        "id": row.id,
                        "name": row.name,
                        "latitude": lat,
                        "longitude": lon,
                        "state_province": row.state_province,
                        "city": row.city,
                        "address": row.address_1,
                        "issue": issue,
                    }
                )

        return invalid_locations

    def correct_location(
        self,
        location_id: str,
        latitude: float,
        longitude: float,
        state: Optional[str] = None,
        city: Optional[str] = None,
        address: Optional[str] = None,
    ) -> bool:
        """Correct a single location's coordinates.

        Args:
            location_id: Location ID to correct
            latitude: Current latitude
            longitude: Current longitude
            state: State code if known
            city: City name if known
            address: Street address if known

        Returns:
            True if correction was successful
        """
        try:
            # Attempt to correct coordinates
            corrected_lat, corrected_lon, note = (
                self.validator.validate_and_correct_coordinates(
                    latitude, longitude, state, city, address
                )
            )

            # Update location in database
            update_query = text(
                """
                UPDATE location
                SET latitude = :lat,
                    longitude = :lon
                WHERE id = :id
            """
            )

            self.db.execute(
                update_query,
                {"lat": corrected_lat, "lon": corrected_lon, "id": location_id},
            )

            # Add correction note if there was a change
            if note:
                self.add_correction_note(location_id, note)

            self.db.commit()
            logger.info(f"Corrected location {location_id}: {note}")
            return True

        except Exception as e:
            logger.error(f"Failed to correct location {location_id}: {e}")
            self.db.rollback()
            return False

    def batch_correct_locations(self, limit: Optional[int] = None) -> Dict[str, Any]:
        """Batch correct invalid locations.

        Args:
            limit: Maximum number of locations to correct

        Returns:
            Dictionary with correction statistics
        """
        invalid_locations = self.find_invalid_locations()

        if limit:
            invalid_locations = invalid_locations[:limit]

        results = {
            "total_invalid": len(invalid_locations),
            "corrected": 0,
            "failed": 0,
            "details": [],
        }

        for location in invalid_locations:
            success = self.correct_location(
                location["id"],
                location["latitude"],
                location["longitude"],
                location.get("state_province"),
                location.get("city"),
                location.get("address"),
            )

            if success:
                results["corrected"] += 1
            else:
                results["failed"] += 1

            results["details"].append(
                {
                    "id": location["id"],
                    "name": location["name"],
                    "issue": location["issue"],
                    "corrected": success,
                }
            )

        return results

    def validate_all_locations(self) -> Dict[str, Any]:
        """Validate all locations in the database.

        Returns:
            Validation report with statistics
        """
        query = text(
            """
            SELECT
                l.id,
                l.name,
                l.latitude,
                l.longitude,
                a.state_province,
                a.city
            FROM location l
            LEFT JOIN address a ON l.id = a.location_id
            WHERE l.latitude IS NOT NULL
            AND l.longitude IS NOT NULL
        """
        )

        result = self.db.execute(query)

        report = {
            "total_locations": 0,
            "valid_locations": 0,
            "invalid_locations": 0,
            "issues": [],
        }

        for row in result:
            report["total_locations"] += 1

            # Validate coordinates
            suggestion = self.validator.suggest_correction(
                row.latitude, row.longitude, row.state_province
            )

            if suggestion:
                report["invalid_locations"] += 1
                report["issues"].append(
                    {"id": row.id, "name": row.name, "suggestion": suggestion}
                )
            else:
                report["valid_locations"] += 1

        return report

    def add_correction_note(self, location_id: str, note: str) -> None:
        """Add a correction note to location metadata.

        Args:
            location_id: Location ID
            note: Correction note to add
        """
        try:
            # Add note to metadata or a separate corrections table
            # This is a simplified version - you might want to use a proper metadata table
            query = text(
                """
                INSERT INTO metadata (
                    id,
                    resource_id,
                    resource_type,
                    metadata
                ) VALUES (
                    gen_random_uuid(),
                    :location_id,
                    'location',
                    jsonb_build_object('coordinate_correction', :note)
                )
                ON CONFLICT (resource_id, resource_type)
                DO UPDATE SET
                    metadata = metadata.metadata || jsonb_build_object('coordinate_correction', :note)
            """
            )

            self.db.execute(query, {"location_id": location_id, "note": note})
            self.db.commit()
        except Exception as e:
            # If metadata table doesn't exist, log the note
            logger.info(f"Correction note for {location_id}: {note}")

    def get_correction_statistics(self) -> Dict[str, Any]:
        """Get statistics about coordinate corrections.

        Returns:
            Dictionary with correction statistics
        """
        try:
            # This is a simplified query - adjust based on your actual schema
            query = text(
                """
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN metadata @> '{"coordinate_correction": ""}' THEN 1 END) as corrected,
                    COUNT(CASE WHEN metadata @> '{"correction_failed": true}' THEN 1 END) as failed
                FROM location l
                LEFT JOIN metadata m ON l.id = m.resource_id AND m.resource_type = 'location'
            """
            )

            result = self.db.execute(query).fetchone()

            total = result[0] or 0
            corrected = result[1] or 0
            failed = result[2] or 0

            return {
                "total_locations": total,
                "corrected_locations": corrected,
                "failed_corrections": failed,
                "correction_rate": corrected / total if total > 0 else 0,
            }
        except Exception:
            # Fallback if metadata table doesn't exist
            return {
                "total_locations": 0,
                "corrected_locations": 0,
                "failed_corrections": 0,
                "correction_rate": 0,
            }

    def validate_coordinates(
        self, latitude: float, longitude: float, address: str
    ) -> Tuple[bool, float, Optional[Tuple[float, float]]]:
        """Validate coordinates against an address.

        Args:
            latitude: Latitude to validate
            longitude: Longitude to validate
            address: Address to validate against

        Returns:
            Tuple of (is_valid, confidence, suggested_coords)
            - is_valid: Whether the coordinates are valid for the address
            - confidence: Confidence score (0-1)
            - suggested_coords: Suggested corrected coordinates if invalid
        """
        # First check if coordinates are valid lat/long
        if not self.validator.is_valid_lat_long(latitude, longitude):
            # Try to geocode the address to get correct coordinates
            suggested = self._geocode_address(address)
            if suggested:
                return False, 0.0, suggested
            return False, 0.0, None

        # Geocode the address to get expected coordinates
        expected_coords = self._geocode_address(address)
        if not expected_coords:
            # Can't validate without geocoding result
            return True, 0.5, None  # Medium confidence

        # Calculate distance between provided and expected coordinates
        distance = self._calculate_distance(
            latitude, longitude, expected_coords[0], expected_coords[1]
        )

        # Determine validity and confidence based on distance
        if distance < 0.1:  # Within ~11km
            return True, 0.95, None
        elif distance < 0.5:  # Within ~55km
            return True, 0.7, None
        elif distance < 1.0:  # Within ~111km
            return False, 0.4, expected_coords
        else:
            return False, 0.1, expected_coords

    def _geocode_address(self, address: str) -> Optional[Tuple[float, float]]:
        """Geocode an address to get coordinates.

        Args:
            address: Address to geocode

        Returns:
            Tuple of (latitude, longitude) or None if geocoding fails
        """
        # Use the unified geocoding service which handles:
        # - Caching to avoid duplicate API calls
        # - Rate limiting to respect API quotas
        # - Fallback between providers
        # - Proper error handling
        result = self.geocoding_service.geocode(address)
        if result:
            logger.info(f"Successfully geocoded address: {address[:50]}...")
            return result
        else:
            logger.warning(f"Failed to geocode address: {address[:50]}...")
            return None

    def _calculate_distance(
        self, lat1: float, lon1: float, lat2: float, lon2: float
    ) -> float:
        """Calculate approximate distance between two coordinates.

        Args:
            lat1, lon1: First coordinate
            lat2, lon2: Second coordinate

        Returns:
            Distance in degrees (approximate)
        """
        import math

        return math.sqrt((lat2 - lat1) ** 2 + (lon2 - lon1) ** 2)

    def convert_projected_to_wgs84(self, x: float, y: float) -> Tuple[float, float]:
        """Convert projected coordinates to WGS84.

        Args:
            x: X coordinate (easting)
            y: Y coordinate (northing)

        Returns:
            Tuple of (latitude, longitude)
        """
        return self.validator.convert_web_mercator_to_wgs84(x, y)

    def pre_create_correction(self, location_data: Dict[str, Any]) -> Dict[str, Any]:
        """Correct location data before creating in database.

        Args:
            location_data: Location data dictionary

        Returns:
            Corrected location data
        """
        if "latitude" not in location_data or "longitude" not in location_data:
            return location_data

        lat = location_data["latitude"]
        lon = location_data["longitude"]

        # Check if correction is needed
        if self.validator.is_projected_coordinate(
            lat
        ) or self.validator.is_projected_coordinate(lon):
            # Correct the coordinates
            corrected_lat, corrected_lon, note = (
                self.validator.validate_and_correct_coordinates(
                    lat,
                    lon,
                    location_data.get("state_province"),
                    location_data.get("city"),
                    location_data.get("address"),
                )
            )

            # Update the data
            corrected_data = dict(location_data)
            corrected_data["latitude"] = corrected_lat
            corrected_data["longitude"] = corrected_lon
            corrected_data["coordinate_correction_note"] = note

            return corrected_data

        return location_data
