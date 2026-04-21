"""Unified geocoding module for the application.

This package provides centralized geocoding functionality including:
- Geocoding service with multiple providers
- Coordinate validation and correction
- Geographic bounds checking
- Database coordinate correction utilities
"""

# Import main components for easy access
from app.core.geocoding.cache_backend import (
    GeocodingCacheBackend,
    get_geocoding_cache_backend,
    make_geocoding_cache_key,
    make_reverse_geocoding_cache_key,
)
from app.core.geocoding.service import (
    GeocodingService,
    get_geocoding_service,
    _geocoding_service,
)
from app.core.geocoding.validator import GeocodingValidator
from app.core.geocoding.corrector import GeocodingCorrector
from app.core.geocoding.constants import US_BOUNDS, STATE_BOUNDS

__all__ = [
    "STATE_BOUNDS",
    "US_BOUNDS",
    "GeocodingCacheBackend",
    "GeocodingCorrector",
    "GeocodingService",
    "GeocodingValidator",
    "_geocoding_service",
    "get_geocoding_cache_backend",
    "get_geocoding_service",
    "make_geocoding_cache_key",
    "make_reverse_geocoding_cache_key",
]
