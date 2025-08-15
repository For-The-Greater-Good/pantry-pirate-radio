"""Unified geocoding module for the application.

This package provides centralized geocoding functionality including:
- Geocoding service with multiple providers
- Coordinate validation and correction
- Geographic bounds checking
- Database coordinate correction utilities
"""

# Import main components for easy access
from app.core.geocoding.service import (
    GeocodingService,
    get_geocoding_service,
    _geocoding_service,
)
from app.core.geocoding.validator import GeocodingValidator
from app.core.geocoding.corrector import GeocodingCorrector
from app.core.geocoding.constants import US_BOUNDS, STATE_BOUNDS

__all__ = [
    "GeocodingService",
    "get_geocoding_service",
    "GeocodingValidator",
    "GeocodingCorrector",
    "US_BOUNDS",
    "STATE_BOUNDS",
    "_geocoding_service",
]
