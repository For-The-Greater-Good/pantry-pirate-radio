"""Response models for map API endpoints."""

from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field


class MapSchedule(BaseModel):
    """Schedule information for a location."""

    opens_at: Optional[str] = None
    closes_at: Optional[str] = None
    byday: Optional[str] = None
    description: Optional[str] = None


class MapSource(BaseModel):
    """Source information from a specific scraper."""

    scraper: str = Field(..., description="Scraper ID")
    name: str = Field(default="", description="Location name from this source")
    org: str = Field(default="", description="Organization name")
    description: str = Field(default="", description="Description")
    services: str = Field(default="", description="Comma-separated services")
    languages: str = Field(default="", description="Comma-separated languages")
    schedule: Optional[MapSchedule] = None
    phone: str = Field(default="", description="Phone number")
    website: str = Field(default="", description="Website URL")
    email: str = Field(default="", description="Email address")
    address: str = Field(default="", description="Full address")
    first_seen: Optional[str] = None
    last_updated: Optional[str] = None
    confidence_score: int = Field(default=50, ge=0, le=100)


class MapLocation(BaseModel):
    """Location data for map display."""

    id: UUID
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    name: str
    org: str = Field(default="", description="Organization name")
    address: str = Field(default="", description="Full address")
    city: str = Field(default="")
    state: str = Field(default="", max_length=2)
    zip: str = Field(default="", description="Postal code")
    phone: str = Field(default="")
    website: str = Field(default="")
    email: str = Field(default="")
    description: str = Field(default="")

    # Aggregation data
    source_count: int = Field(
        default=1, description="Number of sources for this location"
    )
    sources: List[MapSource] = Field(default_factory=list)

    # Validation data
    confidence_score: int = Field(default=50, ge=0, le=100)
    validation_status: str = Field(default="needs_review")
    geocoding_source: str = Field(default="")
    location_type: str = Field(default="")


class MapCluster(BaseModel):
    """Cluster of locations for efficient rendering."""

    id: str = Field(..., description="Cluster ID")
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    count: int = Field(..., description="Number of locations in cluster")
    bounds: Dict[str, float] = Field(..., description="Bounding box of cluster")
    zoom_expand: int = Field(..., description="Zoom level to expand cluster")


class MapMetadata(BaseModel):
    """Metadata about the map data."""

    generated: str = Field(..., description="ISO timestamp of data generation")
    total_locations: int
    total_source_records: int
    multi_source_locations: int
    states_covered: int
    coverage: str = Field(..., description="Human-readable coverage description")
    source: str = Field(default="Pantry Pirate Radio HSDS API")
    format_version: str = Field(default="4.0")
    export_method: str = Field(default="API Query")
    aggregation_radius_meters: int = Field(default=150)


class MapLocationsResponse(BaseModel):
    """Response for map locations endpoint."""

    metadata: MapMetadata
    locations: List[MapLocation]

    # Pagination info when applicable
    page: Optional[int] = None
    per_page: Optional[int] = None
    total_pages: Optional[int] = None
    has_more: bool = False


class MapClustersResponse(BaseModel):
    """Response for map clusters endpoint."""

    clusters: List[MapCluster]
    locations: List[MapLocation] = Field(
        default_factory=list, description="Individual locations not in clusters"
    )
    zoom: int
    bounds: Dict[str, float]


class StateInfo(BaseModel):
    """Information about a state's coverage."""

    state_code: str = Field(..., max_length=2)
    state_name: str
    location_count: int
    bounds: Optional[Dict[str, float]] = None
    last_updated: Optional[datetime] = None


class MapStatesResponse(BaseModel):
    """Response for states coverage endpoint."""

    total_states: int
    states: List[StateInfo]


class CompactLocation(BaseModel):
    """Compact location format for map markers."""

    id: str
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    name: str
    confidence: int = Field(default=50, ge=0, le=100)


class GeoJSONFeature(BaseModel):
    """GeoJSON Feature for a location."""

    type: str = Field(default="Feature")
    geometry: Dict[str, Any] = Field(..., description="GeoJSON geometry")
    properties: Dict[str, Any] = Field(..., description="Feature properties")


class GeoJSONFeatureCollection(BaseModel):
    """GeoJSON FeatureCollection response."""

    type: str = Field(default="FeatureCollection")
    features: List[Dict[str, Any]]
    properties: Dict[str, Any] = Field(default_factory=dict)


class MapSearchResponse(BaseModel):
    """Response for map search endpoint."""

    metadata: MapMetadata
    locations: List[Any] = Field(
        ..., description="List of locations in requested format"
    )
    total: int = Field(..., description="Total number of matching locations")
    page: int = Field(default=1, description="Current page number")
    per_page: int = Field(default=100, description="Items per page")
    has_more: bool = Field(default=False, description="Whether more results exist")
