"""Geographic coordinate validation and correction utilities.

This module provides consolidated validation functionality for
geographic coordinates, including bounds checking and correction.
"""

import logging
import math
from typing import Optional, Tuple

from app.core.geocoding.constants import US_BOUNDS, STATE_BOUNDS

logger = logging.getLogger(__name__)


class GeocodingValidator:
    """Validates and corrects geographic coordinates.

    This class provides methods for validating coordinates against
    US and state bounds, detecting test data, and correcting invalid
    coordinates using geocoding services.
    """

    # Reference the constants from the constants module
    US_BOUNDS = US_BOUNDS
    STATE_BOUNDS = STATE_BOUNDS

    # State centroids for fallback
    STATE_CENTROIDS = {
        "AL": (32.318231, -86.902298),
        "AK": (63.588753, -154.493062),
        "AZ": (34.048928, -111.093731),
        "AR": (35.20105, -91.831833),
        "CA": (36.778261, -119.417932),
        "CO": (39.550051, -105.782067),
        "CT": (41.603221, -73.087749),
        "DE": (38.910832, -75.527670),
        "DC": (38.905985, -77.033418),
        "FL": (27.664827, -81.515754),
        "GA": (32.157435, -82.907123),
        "HI": (19.898682, -155.665857),
        "ID": (44.068202, -114.742041),
        "IL": (40.633125, -89.398528),
        "IN": (40.551217, -85.602364),
        "IA": (41.878003, -93.097702),
        "KS": (39.011902, -98.484246),
        "KY": (37.839333, -84.270018),
        "LA": (31.244823, -92.145024),
        "ME": (45.253783, -69.445469),
        "MD": (39.045755, -76.641271),
        "MA": (42.407211, -71.382437),
        "MI": (44.314844, -85.602364),
        "MN": (46.729553, -94.685900),
        "MS": (32.354668, -89.398528),
        "MO": (37.964253, -91.831833),
        "MT": (46.879682, -110.362566),
        "NE": (41.492537, -99.901813),
        "NV": (38.802610, -116.419389),
        "NH": (43.193852, -71.572395),
        "NJ": (40.058324, -74.405661),
        "NM": (34.519940, -105.870090),
        "NY": (43.299428, -74.217933),
        "NC": (35.759573, -79.019300),
        "ND": (47.551493, -101.002012),
        "OH": (40.417287, -82.907123),
        "OK": (35.467560, -97.516428),
        "OR": (43.804133, -120.554201),
        "PA": (41.203322, -77.194525),
        "RI": (41.580095, -71.477429),
        "SC": (33.836081, -81.163725),
        "SD": (43.969515, -99.901813),
        "TN": (35.517491, -86.580447),
        "TX": (31.968599, -99.901813),
        "UT": (39.320980, -111.093731),
        "VT": (44.558803, -72.577841),
        "VA": (37.431573, -78.656894),
        "WA": (47.751074, -120.740139),
        "WV": (38.597626, -80.454903),
        "WI": (43.784440, -88.787868),
        "WY": (43.075968, -107.290284),
    }

    def __init__(self):
        """Initialize the geocoding validator.

        Uses the shared geocoding service instead of creating its own geocoders.
        """
        # Import here to avoid circular dependency
        from app.core.geocoding.service import get_geocoding_service

        # Use the shared geocoding service
        self.geocoding_service = get_geocoding_service()

        # Backward compatibility attributes
        self.nominatim_geocode = self._geocode_with_nominatim
        self.arcgis_geocode = self._geocode_with_arcgis

    def _geocode_with_nominatim(self, query, **kwargs):
        """Backward compatibility method for nominatim geocoding."""
        result = self.geocoding_service.geocode(query, provider="nominatim")
        if result:
            # Return a mock location object for compatibility
            from unittest.mock import Mock

            location = Mock()
            location.latitude = result[0]
            location.longitude = result[1]
            return location
        return None

    def _geocode_with_arcgis(self, query):
        """Backward compatibility method for arcgis geocoding."""
        result = self.geocoding_service.geocode(query, provider="arcgis")
        if result:
            # Return a mock location object for compatibility
            from unittest.mock import Mock

            location = Mock()
            location.latitude = result[0]
            location.longitude = result[1]
            return location
        return None

    def is_valid_coordinates(self, latitude: float, longitude: float) -> bool:
        """Check if coordinates are valid lat/long values."""
        return -90 <= latitude <= 90 and -180 <= longitude <= 180

    # Alias for backward compatibility
    def is_valid_lat_long(self, latitude: float, longitude: float) -> bool:
        """Check if coordinates are valid lat/long values (backward compat)."""
        return self.is_valid_coordinates(latitude, longitude)

    def is_projected_coordinate(self, value: float) -> bool:
        """Check if a coordinate value appears to be from a projected system."""
        return abs(value) > 180

    def convert_web_mercator_to_wgs84(self, x: float, y: float) -> Tuple[float, float]:
        """Convert Web Mercator (EPSG:3857) to WGS84 lat/long."""
        R = 6378137.0  # Earth radius in meters

        longitude = (x / R) * (180 / math.pi)
        latitude = (math.atan(math.exp(y / R)) * 360 / math.pi) - 90

        return latitude, longitude

    def is_within_state_bounds(
        self, latitude: float, longitude: float, state_code: str
    ) -> bool:
        """Check if coordinates are within a state's bounds."""
        state_code = state_code.upper()
        if state_code not in self.STATE_BOUNDS:
            logger.warning(f"Unknown state code: {state_code}")
            return False

        bounds = self.STATE_BOUNDS[state_code]
        return (
            bounds["min_lat"] <= latitude <= bounds["max_lat"]
            and bounds["min_lon"] <= longitude <= bounds["max_lon"]
        )

    def is_within_us_bounds(self, latitude: float, longitude: float) -> bool:
        """Check if coordinates are within continental US bounds."""
        # Handle Alaska's longitude wrap-around
        if longitude > 0:  # Eastern hemisphere longitude for Alaska
            longitude = longitude - 360

        return (
            self.US_BOUNDS["min_lat"] <= latitude <= self.US_BOUNDS["max_lat"]
            and self.US_BOUNDS["min_lon"] <= longitude <= self.US_BOUNDS["max_lon"]
        )

    def detect_test_data(
        self, latitude: float, longitude: float, name: Optional[str] = None
    ) -> bool:
        """Detect if coordinates or name indicate test data.

        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate
            name: Optional location name to check

        Returns:
            True if this appears to be test data
        """
        # Check for common test coordinates
        if latitude == 0 and longitude == 0:
            return True
        if latitude == 1 and longitude == 1:
            return True
        if abs(latitude) == 90 or abs(longitude) == 180:
            return True

        # Check for test names
        if name:
            test_indicators = ["test", "demo", "example", "sample", "dummy", "fake"]
            name_lower = name.lower()
            for indicator in test_indicators:
                if indicator in name_lower:
                    return True

        return False

    def validate_and_correct(
        self,
        latitude: float,
        longitude: float,
        state_code: Optional[str] = None,
        city: Optional[str] = None,
        address: Optional[str] = None,
    ) -> Tuple[float, float, str]:
        """Validate coordinates and attempt correction if invalid.

        This is the main validation method that combines all validation logic.
        """
        return self.validate_and_correct_coordinates(
            latitude, longitude, state_code, city, address
        )

    def validate_and_correct_coordinates(
        self,
        latitude: float,
        longitude: float,
        state_code: Optional[str] = None,
        city: Optional[str] = None,
        address: Optional[str] = None,
    ) -> Tuple[float, float, str]:
        """Validate coordinates and attempt correction if invalid."""
        correction_note = ""

        # Check if coordinates might be projected
        if self.is_projected_coordinate(latitude) or self.is_projected_coordinate(
            longitude
        ):
            # Attempt Web Mercator conversion
            try:
                lat, lon = self.convert_web_mercator_to_wgs84(longitude, latitude)
                if self.is_valid_coordinates(lat, lon):
                    correction_note = "Converted from Web Mercator projection"
                    latitude, longitude = lat, lon

                    # Also check if coordinates are within state bounds
                    if state_code and self.is_within_state_bounds(lat, lon, state_code):
                        return latitude, longitude, correction_note
                else:
                    # Try swapped coordinates
                    lat, lon = self.convert_web_mercator_to_wgs84(latitude, longitude)
                    if self.is_valid_coordinates(lat, lon):
                        correction_note = (
                            "Converted from Web Mercator projection (swapped)"
                        )
                        latitude, longitude = lat, lon
            except Exception as e:
                logger.error(f"Error converting projected coordinates: {e}")

        # Validate against state bounds if state is known
        if state_code and self.is_valid_coordinates(latitude, longitude):
            if not self.is_within_state_bounds(latitude, longitude, state_code):
                # Coordinates are outside state bounds, try re-geocoding
                if city and state_code:
                    try:
                        # Try geocoding with state hint
                        query = f"{city}, {state_code}, USA"
                        if address:
                            query = f"{address}, {city}, {state_code}, USA"

                        # Use the shared geocoding service
                        result = self.geocoding_service.geocode(query)
                        if result and self.is_within_state_bounds(
                            result[0], result[1], state_code
                        ):
                            latitude = result[0]
                            longitude = result[1]
                            correction_note = "Re-geocoded to correct state bounds"
                    except Exception as e:
                        logger.error(f"Error re-geocoding location: {e}")

                # If still outside bounds, use state centroid
                if not self.is_within_state_bounds(latitude, longitude, state_code):
                    if state_code in self.STATE_CENTROIDS:
                        latitude, longitude = self.STATE_CENTROIDS[state_code]
                        correction_note = (
                            f"Using {state_code} centroid (geocoding failed)"
                        )

        # Final validation - ensure within US bounds
        if not self.is_within_us_bounds(latitude, longitude):
            # For Hawaii and Alaska, check their specific bounds
            if state_code == "HI" and self.is_within_state_bounds(
                latitude, longitude, "HI"
            ):
                pass  # Hawaii coordinates are valid
            elif state_code == "AK" and self.is_within_state_bounds(
                latitude, longitude, "AK"
            ):
                pass  # Alaska coordinates are valid
            elif state_code and state_code in self.STATE_CENTROIDS:
                # Use state centroid as last resort
                latitude, longitude = self.STATE_CENTROIDS[state_code]
                correction_note = f"Using {state_code} centroid (outside US bounds)"

        return latitude, longitude, correction_note

    def suggest_correction(
        self,
        latitude: float,
        longitude: float,
        state_code: Optional[str] = None,
    ) -> Optional[str]:
        """Suggest a correction for invalid coordinates."""
        if not self.is_valid_coordinates(latitude, longitude):
            if self.is_projected_coordinate(latitude) or self.is_projected_coordinate(
                longitude
            ):
                return "Coordinates appear to be in a projected coordinate system (e.g., Web Mercator)"

        if state_code and not self.is_within_state_bounds(
            latitude, longitude, state_code
        ):
            # Find which state the coordinates actually fall in
            for state, bounds in self.STATE_BOUNDS.items():
                if (
                    bounds["min_lat"] <= latitude <= bounds["max_lat"]
                    and bounds["min_lon"] <= longitude <= bounds["max_lon"]
                ):
                    return f"Coordinates are in {state}, not {state_code}"

            return f"Coordinates are outside {state_code} bounds"

        if not self.is_within_us_bounds(latitude, longitude):
            return "Coordinates are outside US bounds"

        return None
