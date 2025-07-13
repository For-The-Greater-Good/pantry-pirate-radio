"""Geographic models for grid generation and coordinate handling."""

from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from geopandas import GeoDataFrame

# Defer geopandas import to runtime
import geopandas as gpd  # type: ignore
from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    """Geographic bounding box."""

    north: float = Field(..., description="Northern latitude boundary")
    south: float = Field(..., description="Southern latitude boundary")
    east: float = Field(..., description="Eastern longitude boundary")
    west: float = Field(..., description="Western longitude boundary")

    class Config:
        frozen = True

    @classmethod
    def from_geojson(cls, file_path: Path) -> "BoundingBox":
        """Create bounding box from GeoJSON file.

        Args:
            file_path: Path to GeoJSON file

        Returns:
            BoundingBox: Bounding box covering the GeoJSON area

        Raises:
            ValueError: If file cannot be read or is invalid
        """
        try:
            # Read GeoJSON and get bounds
            # Type hints for mypy but defer actual import
            gdf = cast("GeoDataFrame", gpd.read_file(file_path))
            # Returns [minx, miny, maxx, maxy]
            bounds = cast(list[float], gdf.total_bounds)

            return cls(
                north=float(bounds[3]),  # maxy
                south=float(bounds[1]),  # miny
                east=float(bounds[2]),  # maxx
                west=float(bounds[0]),  # minx
            )
        except Exception as e:
            raise ValueError(f"Failed to extract bounds from GeoJSON: {e}") from e

    @property
    def name(self) -> str:
        """Get a descriptive name for this bounding box.

        Returns:
            str: Description of the box's location
        """
        return f"Area ({self.south:.2f}, {self.west:.2f}) to ({self.north:.2f}, {self.east:.2f})"


class GridPoint(BaseModel):
    """A point in the grid with coordinates and identifier."""

    latitude: float = Field(..., description="Latitude in decimal degrees")
    longitude: float = Field(..., description="Longitude in decimal degrees")
    name: str = Field(..., description="Unique identifier for this grid point")

    class Config:
        frozen = True


class USBounds(BoundingBox):
    """Continental United States boundary constants."""

    north: float = Field(49.0, description="Northern border with Canada")
    south: float = Field(25.0, description="Southern tip of Florida")
    east: float = Field(-67.0, description="Eastern Maine")
    west: float = Field(-125.0, description="Western Washington state")

    @property
    def name(self) -> str:
        """Get name for US bounds.

        Returns:
            str: Description
        """
        return "Continental United States"
