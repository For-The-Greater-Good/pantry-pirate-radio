"""Backward compatibility shim for geocoding validator.

This file maintains backward compatibility with the old import path.
All functionality has been moved to app.core.geocoding.validator.
"""

# Re-export everything from the new location for backward compatibility
from app.core.geocoding.validator import GeocodingValidator
from app.core.geocoding.constants import US_BOUNDS, STATE_BOUNDS

# Make bounds available as class attributes for backward compatibility
GeocodingValidator.US_BOUNDS = US_BOUNDS
GeocodingValidator.STATE_BOUNDS = STATE_BOUNDS

__all__ = ["GeocodingValidator"]
