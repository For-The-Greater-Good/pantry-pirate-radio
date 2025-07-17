"""Geographic query utilities using PostGIS."""

import math
from typing import Optional, Tuple

# Try to import GeoAlchemy2, use fallback if not available
try:
    from geoalchemy2.functions import ST_Distance, ST_DWithin, ST_Intersects

    HAS_GEOALCHEMY2 = True
except ImportError:
    HAS_GEOALCHEMY2 = False
    # Create mock functions for testing
    ST_Distance = None
    ST_DWithin = None
    ST_Intersects = None

from sqlalchemy import func
from sqlalchemy.sql import Select

from app.models.hsds.query import GeoBoundingBox, GeoPoint


class GeoQueryBuilder:
    """Builder for geographic queries using PostGIS functions."""

    @staticmethod
    def create_point_from_coordinates(longitude: float, latitude: float):
        """Create a PostGIS point from coordinates."""
        return func.ST_SetSRID(
            func.ST_MakePoint(longitude, latitude), 4326  # WGS84 coordinate system
        )

    @staticmethod
    def create_bounding_box(bbox: GeoBoundingBox):
        """Create a PostGIS bounding box from coordinates."""
        return func.ST_SetSRID(
            func.ST_MakeEnvelope(
                bbox.min_longitude,
                bbox.min_latitude,
                bbox.max_longitude,
                bbox.max_latitude,
            ),
            4326,
        )

    @staticmethod
    def miles_to_meters(miles: float) -> float:
        """Convert miles to meters."""
        return miles * 1609.34

    @staticmethod
    def meters_to_miles(meters: float) -> float:
        """Convert meters to miles."""
        return meters / 1609.34

    @classmethod
    def add_radius_filter(
        cls,
        query: Select,
        geometry_column,
        center: GeoPoint,
        radius_miles: float,
        use_spheroid: bool = True,
    ) -> Select:
        """Add radius filter to query."""
        if not HAS_GEOALCHEMY2:
            # Fallback: use basic lat/lon filtering (less accurate)
            return query

        radius_meters = cls.miles_to_meters(radius_miles)
        center_point = cls.create_point_from_coordinates(
            center.longitude, center.latitude
        )

        return query.filter(
            ST_DWithin(geometry_column, center_point, radius_meters, use_spheroid)
        )

    @classmethod
    def add_bbox_filter(
        cls,
        query: Select,
        geometry_column,
        bbox: GeoBoundingBox,
    ) -> Select:
        """Add bounding box filter to query."""
        if not HAS_GEOALCHEMY2:
            # Fallback: use basic lat/lon filtering (less accurate)
            return query

        bbox_geom = cls.create_bounding_box(bbox)
        return query.filter(ST_Intersects(geometry_column, bbox_geom))

    @classmethod
    def add_distance_order(
        cls,
        query: Select,
        geometry_column,
        reference_point: GeoPoint,
        use_spheroid: bool = True,
    ) -> Select:
        """Add distance-based ordering to query."""
        if not HAS_GEOALCHEMY2:
            # Fallback: no ordering when PostGIS not available
            return query

        reference_geom = cls.create_point_from_coordinates(
            reference_point.longitude, reference_point.latitude
        )

        return query.order_by(
            ST_Distance(geometry_column, reference_geom, use_spheroid)
        )

    @classmethod
    def calculate_distance_miles(
        cls,
        geometry_column,
        reference_point: GeoPoint,
        use_spheroid: bool = True,
    ):
        """Calculate distance in miles between geometry and reference point."""
        if not HAS_GEOALCHEMY2:
            # Fallback: return 0 when PostGIS not available
            return 0.0

        reference_geom = cls.create_point_from_coordinates(
            reference_point.longitude, reference_point.latitude
        )

        distance_meters = ST_Distance(geometry_column, reference_geom, use_spheroid)

        return distance_meters / 1609.34  # Convert to miles

    @staticmethod
    def validate_coordinates(latitude: float, longitude: float) -> Tuple[bool, str]:
        """Validate latitude and longitude coordinates."""
        if not -90 <= latitude <= 90:
            return False, "Latitude must be between -90 and 90 degrees"
        if not -180 <= longitude <= 180:
            return False, "Longitude must be between -180 and 180 degrees"
        return True, ""

    @staticmethod
    def validate_us_bounds(latitude: float, longitude: float) -> Tuple[bool, str]:
        """Validate coordinates are within continental US bounds."""
        # Continental US bounds
        MIN_LAT, MAX_LAT = 25.0, 49.0
        MIN_LON, MAX_LON = -125.0, -67.0

        if not MIN_LAT <= latitude <= MAX_LAT:
            return (
                False,
                f"Latitude must be between {MIN_LAT} and {MAX_LAT} degrees for continental US",
            )
        if not MIN_LON <= longitude <= MAX_LON:
            return (
                False,
                f"Longitude must be between {MIN_LON} and {MAX_LON} degrees for continental US",
            )
        return True, ""

    @staticmethod
    def clamp_to_us_bounds(latitude: float, longitude: float) -> Tuple[float, float]:
        """Clamp coordinates to continental US bounds."""
        MIN_LAT, MAX_LAT = 25.0, 49.0
        MIN_LON, MAX_LON = -125.0, -67.0

        clamped_lat = max(MIN_LAT, min(MAX_LAT, latitude))
        clamped_lon = max(MIN_LON, min(MAX_LON, longitude))

        return clamped_lat, clamped_lon

    @staticmethod
    def calculate_bounding_box_from_point(
        center: GeoPoint, radius_miles: float
    ) -> GeoBoundingBox:
        """Calculate bounding box from center point and radius."""
        # Approximate conversion from miles to degrees
        # 1 degree latitude ≈ 69 miles
        # 1 degree longitude ≈ 69 miles * cos(latitude)

        lat_delta = radius_miles / 69.0
        lon_delta = radius_miles / (69.0 * math.cos(math.radians(center.latitude)))

        return GeoBoundingBox(
            min_latitude=center.latitude - lat_delta,
            max_latitude=center.latitude + lat_delta,
            min_longitude=center.longitude - lon_delta,
            max_longitude=center.longitude + lon_delta,
        )

    @staticmethod
    def is_point_in_bbox(point: GeoPoint, bbox: GeoBoundingBox) -> bool:
        """Check if point is within bounding box."""
        return (
            bbox.min_latitude <= point.latitude <= bbox.max_latitude
            and bbox.min_longitude <= point.longitude <= bbox.max_longitude
        )

    @staticmethod
    def expand_bbox_by_percentage(
        bbox: GeoBoundingBox, percentage: float
    ) -> GeoBoundingBox:
        """Expand bounding box by percentage."""
        lat_range = bbox.max_latitude - bbox.min_latitude
        lon_range = bbox.max_longitude - bbox.min_longitude

        lat_expansion = lat_range * (percentage / 100)
        lon_expansion = lon_range * (percentage / 100)

        return GeoBoundingBox(
            min_latitude=bbox.min_latitude - lat_expansion,
            max_latitude=bbox.max_latitude + lat_expansion,
            min_longitude=bbox.min_longitude - lon_expansion,
            max_longitude=bbox.max_longitude + lon_expansion,
        )

    @staticmethod
    def calculate_bbox_center(bbox: GeoBoundingBox) -> GeoPoint:
        """Calculate center point of bounding box."""
        return GeoPoint(
            latitude=(bbox.min_latitude + bbox.max_latitude) / 2,
            longitude=(bbox.min_longitude + bbox.max_longitude) / 2,
        )

    @staticmethod
    def get_state_bounding_box(state_code: str) -> Optional[GeoBoundingBox]:
        """Get bounding box for US states (limited set for demonstration)."""
        # This would typically come from a database or external service
        # Including a few examples for demonstration
        state_bounds = {
            "NJ": GeoBoundingBox(
                min_latitude=38.9,
                max_latitude=41.4,
                min_longitude=-75.6,
                max_longitude=-73.9,
            ),
            "NY": GeoBoundingBox(
                min_latitude=40.5,
                max_latitude=45.0,
                min_longitude=-79.8,
                max_longitude=-71.9,
            ),
            "CA": GeoBoundingBox(
                min_latitude=32.5,
                max_latitude=42.0,
                min_longitude=-124.4,
                max_longitude=-114.1,
            ),
            "TX": GeoBoundingBox(
                min_latitude=25.8,
                max_latitude=36.5,
                min_longitude=-106.6,
                max_longitude=-93.5,
            ),
            "FL": GeoBoundingBox(
                min_latitude=24.4,
                max_latitude=31.0,
                min_longitude=-87.6,
                max_longitude=-80.0,
            ),
        }

        return state_bounds.get(state_code.upper())
