"""Geographic coordinate validation and correction utilities."""

import logging
import math
from typing import Optional, Tuple

from geopy.geocoders import Nominatim, ArcGIS
from geopy.extra.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class GeocodingValidator:
    """Validates and corrects geographic coordinates."""

    # Continental US bounds (excluding Alaska and Hawaii)
    US_BOUNDS = {
        "min_lat": 24.396308,  # Southern tip of Florida
        "max_lat": 49.384358,  # Northern border with Canada
        "min_lon": -125.0,  # West coast
        "max_lon": -66.93457,  # East coast
    }

    # State-specific bounds
    STATE_BOUNDS = {
        "AL": {
            "min_lat": 30.223334,
            "max_lat": 35.008028,
            "min_lon": -88.473227,
            "max_lon": -84.888180,
        },
        "AK": {
            "min_lat": 51.214183,
            "max_lat": 71.538800,
            "min_lon": -179.148909,
            "max_lon": -129.979511,
        },
        "AZ": {
            "min_lat": 31.332177,
            "max_lat": 37.004260,
            "min_lon": -114.818269,
            "max_lon": -109.045223,
        },
        "AR": {
            "min_lat": 33.004106,
            "max_lat": 36.499600,
            "min_lon": -94.617919,
            "max_lon": -89.644395,
        },
        "CA": {
            "min_lat": 32.534156,
            "max_lat": 42.009518,
            "min_lon": -124.409591,
            "max_lon": -114.131211,
        },
        "CO": {
            "min_lat": 36.992426,
            "max_lat": 41.003444,
            "min_lon": -109.060253,
            "max_lon": -102.041524,
        },
        "CT": {
            "min_lat": 40.950943,
            "max_lat": 42.050587,
            "min_lon": -73.727775,
            "max_lon": -71.786994,
        },
        "DE": {
            "min_lat": 38.451013,
            "max_lat": 39.839007,
            "min_lon": -75.788658,
            "max_lon": -75.048939,
        },
        "DC": {
            "min_lat": 38.791645,
            "max_lat": 38.995548,
            "min_lon": -77.119759,
            "max_lon": -76.909395,
        },
        "FL": {
            "min_lat": 24.396308,
            "max_lat": 31.000968,
            "min_lon": -87.634938,
            "max_lon": -79.974307,
        },
        "GA": {
            "min_lat": 30.355757,
            "max_lat": 35.000659,
            "min_lon": -85.605165,
            "max_lon": -80.839729,
        },
        "HI": {
            "min_lat": 18.910361,
            "max_lat": 28.402123,
            "min_lon": -178.334698,
            "max_lon": -154.806773,
        },
        "ID": {
            "min_lat": 41.988057,
            "max_lat": 49.001146,
            "min_lon": -117.243027,
            "max_lon": -111.043564,
        },
        "IL": {
            "min_lat": 36.970298,
            "max_lat": 42.508481,
            "min_lon": -91.513079,
            "max_lon": -87.494756,
        },
        "IN": {
            "min_lat": 37.771742,
            "max_lat": 41.761368,
            "min_lon": -88.097892,
            "max_lon": -84.784579,
        },
        "IA": {
            "min_lat": 40.375501,
            "max_lat": 43.501196,
            "min_lon": -96.639704,
            "max_lon": -90.140061,
        },
        "KS": {
            "min_lat": 36.993016,
            "max_lat": 40.003162,
            "min_lon": -102.051744,
            "max_lon": -94.588413,
        },
        "KY": {
            "min_lat": 36.497129,
            "max_lat": 39.147458,
            "min_lon": -89.571509,
            "max_lon": -81.964971,
        },
        "LA": {
            "min_lat": 28.928609,
            "max_lat": 33.019457,
            "min_lon": -94.043147,
            "max_lon": -88.817017,
        },
        "ME": {
            "min_lat": 42.977764,
            "max_lat": 47.459686,
            "min_lon": -71.083924,
            "max_lon": -66.949895,
        },
        "MD": {
            "min_lat": 37.911717,
            "max_lat": 39.723043,
            "min_lon": -79.487651,
            "max_lon": -75.048939,
        },
        "MA": {
            "min_lat": 41.237964,
            "max_lat": 42.886589,
            "min_lon": -73.508142,
            "max_lon": -69.928393,
        },
        "MI": {
            "min_lat": 41.696118,
            "max_lat": 48.306063,
            "min_lon": -90.418136,
            "max_lon": -82.413474,
        },
        "MN": {
            "min_lat": 43.499356,
            "max_lat": 49.384358,
            "min_lon": -97.239209,
            "max_lon": -89.491739,
        },
        "MS": {
            "min_lat": 30.173943,
            "max_lat": 34.996052,
            "min_lon": -91.655009,
            "max_lon": -88.097888,
        },
        "MO": {
            "min_lat": 35.995683,
            "max_lat": 40.613640,
            "min_lon": -95.774704,
            "max_lon": -89.098843,
        },
        "MT": {
            "min_lat": 44.358221,
            "max_lat": 49.001390,
            "min_lon": -116.050003,
            "max_lon": -104.039138,
        },
        "NE": {
            "min_lat": 39.999998,
            "max_lat": 43.001708,
            "min_lon": -104.053514,
            "max_lon": -95.308290,
        },
        "NV": {
            "min_lat": 35.001857,
            "max_lat": 42.002207,
            "min_lon": -120.005746,
            "max_lon": -114.039648,
        },
        "NH": {
            "min_lat": 42.696990,
            "max_lat": 45.305476,
            "min_lon": -72.557247,
            "max_lon": -70.610621,
        },
        "NJ": {
            "min_lat": 38.928519,
            "max_lat": 41.357423,
            "min_lon": -75.559614,
            "max_lon": -73.893979,
        },
        "NM": {
            "min_lat": 31.332301,
            "max_lat": 37.000232,
            "min_lon": -109.050173,
            "max_lon": -103.001964,
        },
        "NY": {
            "min_lat": 40.496103,
            "max_lat": 45.012810,
            "min_lon": -79.762152,
            "max_lon": -71.856214,
        },
        "NC": {
            "min_lat": 33.841469,
            "max_lat": 36.588117,
            "min_lon": -84.321869,
            "max_lon": -75.460621,
        },
        "ND": {
            "min_lat": 45.935054,
            "max_lat": 49.000574,
            "min_lon": -104.048915,
            "max_lon": -96.554507,
        },
        "OH": {
            "min_lat": 38.403202,
            "max_lat": 41.977523,
            "min_lon": -84.820159,
            "max_lon": -80.518693,
        },
        "OK": {
            "min_lat": 33.615833,
            "max_lat": 37.002206,
            "min_lon": -103.002565,
            "max_lon": -94.430662,
        },
        "OR": {
            "min_lat": 41.991794,
            "max_lat": 46.292035,
            "min_lon": -124.566244,
            "max_lon": -116.463504,
        },
        "PA": {
            "min_lat": 39.719872,
            "max_lat": 42.516072,
            "min_lon": -80.519891,
            "max_lon": -74.689516,
        },
        "RI": {
            "min_lat": 41.146339,
            "max_lat": 42.018798,
            "min_lon": -71.862772,
            "max_lon": -71.120570,
        },
        "SC": {
            "min_lat": 32.034600,
            "max_lat": 35.215402,
            "min_lon": -83.339000,
            "max_lon": -78.540800,
        },
        "SD": {
            "min_lat": 42.479635,
            "max_lat": 45.945455,
            "min_lon": -104.057698,
            "max_lon": -96.436589,
        },
        "TN": {
            "min_lat": 34.982972,
            "max_lat": 36.678118,
            "min_lon": -90.310298,
            "max_lon": -81.646900,
        },
        "TX": {
            "min_lat": 25.837377,
            "max_lat": 36.500704,
            "min_lon": -106.645646,
            "max_lon": -93.508292,
        },
        "UT": {
            "min_lat": 36.997968,
            "max_lat": 42.001567,
            "min_lon": -114.052962,
            "max_lon": -109.041058,
        },
        "VT": {
            "min_lat": 42.726853,
            "max_lat": 45.016659,
            "min_lon": -73.437740,
            "max_lon": -71.464555,
        },
        "VA": {
            "min_lat": 36.540738,
            "max_lat": 39.466012,
            "min_lon": -83.675395,
            "max_lon": -75.242266,
        },
        "WA": {
            "min_lat": 45.543541,
            "max_lat": 49.002494,
            "min_lon": -124.763068,
            "max_lon": -116.915989,
        },
        "WV": {
            "min_lat": 37.201483,
            "max_lat": 40.638801,
            "min_lon": -82.644739,
            "max_lon": -77.719519,
        },
        "WI": {
            "min_lat": 42.491983,
            "max_lat": 47.080621,
            "min_lon": -92.888114,
            "max_lon": -86.805415,
        },
        "WY": {
            "min_lat": 40.994746,
            "max_lat": 45.005904,
            "min_lon": -111.056888,
            "max_lon": -104.052330,
        },
    }

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
        """Initialize the geocoding validator."""
        # Initialize geocoders for re-geocoding if needed
        self.nominatim = Nominatim(
            user_agent="pantry-pirate-radio-validator", timeout=10
        )
        self.nominatim_geocode = RateLimiter(
            self.nominatim.geocode,
            min_delay_seconds=2,
            max_retries=3,
        )

        self.arcgis = ArcGIS(timeout=10)
        self.arcgis_geocode = RateLimiter(
            self.arcgis.geocode,
            min_delay_seconds=2,
            max_retries=3,
        )

    def is_valid_lat_long(self, latitude: float, longitude: float) -> bool:
        """Check if coordinates are valid lat/long values."""
        return -90 <= latitude <= 90 and -180 <= longitude <= 180

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
                if self.is_valid_lat_long(lat, lon):
                    correction_note = "Converted from Web Mercator projection"
                    latitude, longitude = lat, lon

                    # Also check if coordinates are within state bounds
                    if state_code and self.is_within_state_bounds(lat, lon, state_code):
                        return latitude, longitude, correction_note
                else:
                    # Try swapped coordinates
                    lat, lon = self.convert_web_mercator_to_wgs84(latitude, longitude)
                    if self.is_valid_lat_long(lat, lon):
                        correction_note = (
                            "Converted from Web Mercator projection (swapped)"
                        )
                        latitude, longitude = lat, lon
            except Exception as e:
                logger.error(f"Error converting projected coordinates: {e}")

        # Validate against state bounds if state is known
        if state_code and self.is_valid_lat_long(latitude, longitude):
            if not self.is_within_state_bounds(latitude, longitude, state_code):
                # Coordinates are outside state bounds, try re-geocoding
                if city and state_code:
                    try:
                        # Try geocoding with state hint
                        query = f"{city}, {state_code}, USA"
                        if address:
                            query = f"{address}, {city}, {state_code}, USA"

                        # Try Nominatim first
                        location = self.nominatim_geocode(query, country_codes=["us"])
                        if location and self.is_within_state_bounds(
                            location.latitude, location.longitude, state_code
                        ):
                            latitude = location.latitude
                            longitude = location.longitude
                            correction_note = "Re-geocoded to correct state bounds"
                        else:
                            # Try ArcGIS as fallback
                            location = self.arcgis_geocode(query)
                            if location and self.is_within_state_bounds(
                                location.latitude, location.longitude, state_code
                            ):
                                latitude = location.latitude
                                longitude = location.longitude
                                correction_note = "Re-geocoded with ArcGIS"
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
        if not self.is_valid_lat_long(latitude, longitude):
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
