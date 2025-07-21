"""Grid generation utilities for geographic coverage."""

import json
import math
from typing import Literal

from app.models.geographic import BoundingBox, GridPoint, USBounds


class GridGenerator:
    """Generates a grid of coordinates covering a geographic area."""

    # Core settings
    SEARCH_RADIUS_MILES = 80.0
    OVERLAP_FACTOR = 0.45  # 45% overlap between circles

    def __init__(
        self,
        bounds: BoundingBox | None = None,
        search_radius_miles: float | None = None,
        overlap_factor: float | None = None,
    ):
        """Initialize with boundary constants.

        Args:
            bounds: Optional bounding box, defaults to continental US
            search_radius_miles: Optional custom search radius in miles
            overlap_factor: Optional custom overlap factor (0.0 to 1.0)
        """
        self.bounds = bounds or USBounds()
        self.search_radius_miles = search_radius_miles or self.SEARCH_RADIUS_MILES
        self.overlap_factor = overlap_factor or self.OVERLAP_FACTOR

    @staticmethod
    def miles_to_lat_degrees(miles: float) -> float:
        """Convert miles to degrees of latitude.

        Args:
            miles: Distance in miles

        Returns:
            float: Equivalent degrees of latitude (1 degree ≈ 69 miles)
        """
        return miles / 69.0

    @staticmethod
    def miles_to_lon_degrees(miles: float, latitude: float) -> float:
        """Convert miles to degrees of longitude at a given latitude.

        Args:
            miles: Distance in miles
            latitude: Current latitude in degrees

        Returns:
            float: Equivalent degrees of longitude (varies with latitude)
        """
        miles_per_degree = math.cos(math.radians(latitude)) * 69.0
        return miles / miles_per_degree

    @staticmethod
    def round_coordinate(coord: float, precision: int = 4) -> float:
        """Round coordinate to specified precision.

        Args:
            coord: Coordinate value to round
            precision: Number of decimal places

        Returns:
            float: Rounded coordinate value
        """
        return round(coord * (10**precision)) / (10**precision)

    def generate_grid(self) -> list[GridPoint]:
        """Generate grid of coordinates covering the bounded area.

        Returns:
            List[GridPoint]: List of grid points with overlapping coverage
        """
        coordinates: list[GridPoint] = []
        spacing = self.search_radius_miles * (1 - self.overlap_factor)
        point_count = 0

        # Start at southernmost point
        lat = self.bounds.south
        while lat <= self.bounds.north:
            # Convert miles to longitude degrees at current latitude
            lon_spacing = self.miles_to_lon_degrees(spacing, lat)

            # Generate points along this latitude
            lon = self.bounds.west
            while lon <= self.bounds.east:
                point_count += 1
                coordinates.append(
                    GridPoint(
                        latitude=self.round_coordinate(lat),
                        longitude=self.round_coordinate(lon),
                        name=f"{self.bounds.name} Point {point_count} ({self.round_coordinate(lat)}, {self.round_coordinate(lon)})",
                    )
                )
                lon += lon_spacing

            # Move north by our spacing
            lat += self.miles_to_lat_degrees(spacing)

        return coordinates

    def export_grid(self, format: Literal["json", "csv"]) -> None:
        """Export grid points to file.

        Args:
            format: Output format ("json" or "csv")
        """
        coordinates = self.generate_grid()

        if format == "json":
            # Export as JSON
            json_data = [coord.model_dump() for coord in coordinates]
            with open("coordinates.json", "w") as f:
                json.dump(json_data, f, indent=2)

        elif format == "csv":
            # Export as CSV
            csv_lines = ["latitude,longitude,name"]
            for coord in coordinates:
                # Format name without coordinates to avoid CSV parsing issues
                point_num = coord.name.split("(")[0].strip()
                csv_lines.append(f'{coord.latitude},{coord.longitude},"{point_num}"')
            with open("coordinates.csv", "w") as f:
                f.write("\n".join(csv_lines))

        print(f"Generated {len(coordinates)} coordinate points")
        print(f"Saved to coordinates.{format}")
