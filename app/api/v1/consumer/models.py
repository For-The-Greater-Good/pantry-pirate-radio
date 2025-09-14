"""Pydantic models for Consumer API endpoints."""

from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class LocationPin(BaseModel):
    """Single location pin for map display."""

    type: Literal["single"]
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    location_ids: List[str]  # Single item for individual pins
    name: str
    confidence: int = Field(default=50, ge=0, le=100)
    source_count: int = Field(default=1, ge=1)
    has_schedule: bool = False
    open_now: Optional[bool] = None


class GroupedPin(BaseModel):
    """Grouped location pin for clustered display."""

    type: Literal["group"]
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    location_ids: List[str]  # Multiple IDs in group
    name: str  # e.g., "3 locations"
    primary_name: Optional[str] = None  # Most common name in group
    confidence_avg: int = Field(default=50, ge=0, le=100)
    source_count: int  # Total sources across all locations
    bounds: Dict[str, float]  # north, south, east, west


class MapPinsMetadata(BaseModel):
    """Metadata for map pins response."""

    total_pins: int
    total_locations: int
    viewport_bounds: Dict[str, float]
    grouping_radius: int
    timestamp: datetime


class MapPinsResponse(BaseModel):
    """Response for map pins endpoint."""

    pins: List[Dict[str, Any]]  # Mix of LocationPin and GroupedPin
    metadata: MapPinsMetadata


class SourceData(BaseModel):
    """Data from a specific scraper source."""

    scraper_id: str
    last_updated: datetime
    first_seen: Optional[datetime] = None
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    email: Optional[str] = None
    schedule: Optional[Dict[str, Any]] = None
    services: Optional[List[str]] = None
    confidence: int = Field(default=50, ge=0, le=100)


class CanonicalData(BaseModel):
    """Canonical (best) data for a location."""

    name: str
    alternate_name: Optional[str] = None
    description: Optional[str] = None
    address: Optional[Dict[str, Any]] = None  # street, city, state, zip
    coordinates: Dict[str, Any]  # lat, lng, geocoding_source, confidence
    contact: Optional[Dict[str, Any]] = None  # phone, email, website
    confidence: int = Field(default=50, ge=0, le=100)
    validation_status: Optional[str] = None


class LocationDetail(BaseModel):
    """Detailed location information."""

    id: str
    canonical: CanonicalData
    sources: List[SourceData]
    distance_meters: Optional[float] = None
    is_open: Optional[bool] = None
    schedule_merged: Optional[Dict[str, Any]] = None
    data_quality: Optional[Dict[str, Any]] = None


class MultiLocationResponse(BaseModel):
    """Response for multi-location fetch endpoint."""

    locations: List[LocationDetail]
    similarities: Optional[List[Dict[str, Any]]] = None  # Future: similarity analysis


class NearbyLocation(BaseModel):
    """Nearby location summary."""

    id: str
    name: str
    distance_meters: float
    bearing: Optional[str] = None  # N, NE, E, SE, S, SW, W, NW
    address: Optional[str] = None
    is_open: Optional[bool] = None


class SingleLocationResponse(BaseModel):
    """Response for single location detail endpoint."""

    location: LocationDetail
    nearby_locations: Optional[List[NearbyLocation]] = None
    version_history: Optional[List[Dict[str, Any]]] = None