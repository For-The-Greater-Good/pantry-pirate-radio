"""Backward compatibility shim for geocoding corrector.

This file maintains backward compatibility with the old import path.
All functionality has been moved to app.core.geocoding.corrector.
"""

# Re-export everything from the new location for backward compatibility
from app.core.geocoding.corrector import GeocodingCorrector
from app.core.geocoding.validator import GeocodingValidator
from app.core.geocoding import get_geocoding_service

__all__ = ["GeocodingCorrector", "GeocodingValidator", "get_geocoding_service"]
