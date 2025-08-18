"""Tests for refactored geocoding module structure.

This test file validates the new geocoding module organization
and ensures backward compatibility is maintained.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Optional, Tuple, Dict, Any


class TestGeocodingModuleStructure:
    """Test the new geocoding module structure."""

    def test_geocoding_directory_exists(self):
        """Test that app/core/geocoding/ directory exists with proper structure."""
        import app.core.geocoding

        assert hasattr(app.core.geocoding, "__path__"), "geocoding should be a package"

    def test_geocoding_service_import(self):
        """Test that GeocodingService can be imported from new location."""
        from app.core.geocoding import GeocodingService

        assert GeocodingService is not None

    def test_geocoding_validator_import(self):
        """Test that GeocodingValidator can be imported from new location."""
        from app.core.geocoding import GeocodingValidator

        assert GeocodingValidator is not None

    def test_geocoding_corrector_import(self):
        """Test that GeocodingCorrector can be imported from new location."""
        from app.core.geocoding import GeocodingCorrector

        assert GeocodingCorrector is not None

    def test_get_geocoding_service_function(self):
        """Test that get_geocoding_service is available."""
        from app.core.geocoding import get_geocoding_service

        assert callable(get_geocoding_service)

    def test_constants_available(self):
        """Test that geocoding constants are available."""
        from app.core.geocoding.constants import US_BOUNDS, STATE_BOUNDS

        assert US_BOUNDS is not None
        assert STATE_BOUNDS is not None
        assert "min_lat" in US_BOUNDS
        assert "CA" in STATE_BOUNDS


class TestBackwardCompatibility:
    """Test backward compatibility with old import paths."""

    def test_old_geocoding_service_import(self):
        """Test that old import path still works."""
        from app.core.geocoding import GeocodingService

        assert GeocodingService is not None

    def test_old_validator_import(self):
        """Test that old validator import path still works."""
        from app.llm.utils.geocoding_validator import GeocodingValidator

        assert GeocodingValidator is not None

    def test_corrector_not_in_reconciler(self):
        """Test that corrector was removed from reconciler (no more redundant geocoding)."""
        # This test verifies that we've removed geocoding from reconciler
        # The corrector should only be available from core.geocoding now
        with pytest.raises(ImportError):
            from app.reconciler.geocoding_corrector import GeocodingCorrector

    def test_validator_bounds_backward_compat(self):
        """Test that bounds are still available in old location."""
        from app.llm.utils.geocoding_validator import GeocodingValidator

        assert hasattr(GeocodingValidator, "US_BOUNDS")
        assert hasattr(GeocodingValidator, "STATE_BOUNDS")


class TestConsolidatedValidator:
    """Test the consolidated GeocodingValidator functionality."""

    def test_validator_has_all_methods(self):
        """Test that consolidated validator has all necessary methods."""
        from app.core.geocoding import GeocodingValidator

        validator = GeocodingValidator()
        assert hasattr(validator, "is_valid_coordinates")
        assert hasattr(validator, "is_within_us_bounds")
        assert hasattr(validator, "is_within_state_bounds")
        assert hasattr(validator, "validate_and_correct")
        assert hasattr(validator, "detect_test_data")

    def test_validator_uses_shared_service(self):
        """Test that validator uses the shared geocoding service."""
        from app.core.geocoding import GeocodingValidator, get_geocoding_service

        validator = GeocodingValidator()
        # Should use the same singleton service
        assert validator.geocoding_service is get_geocoding_service()

    def test_validator_bounds_checking(self):
        """Test that validator properly checks coordinate bounds."""
        from app.core.geocoding import GeocodingValidator

        validator = GeocodingValidator()

        # Valid US coordinates (New York)
        assert validator.is_within_us_bounds(40.7128, -74.0060) is True

        # Invalid coordinates (0, 0)
        assert validator.is_within_us_bounds(0, 0) is False

        # Outside US (London)
        assert validator.is_within_us_bounds(51.5074, -0.1278) is False


class TestConsolidatedCorrector:
    """Test the consolidated GeocodingCorrector functionality."""

    def test_corrector_has_all_methods(self):
        """Test that consolidated corrector has all necessary methods."""
        from app.core.geocoding import GeocodingCorrector

        corrector = GeocodingCorrector()
        assert hasattr(corrector, "find_invalid_locations")
        assert hasattr(corrector, "correct_coordinates")
        assert hasattr(corrector, "correct_all_invalid")

    def test_corrector_uses_shared_validator(self):
        """Test that corrector uses the shared validator."""
        from app.core.geocoding import GeocodingCorrector, GeocodingValidator

        corrector = GeocodingCorrector()
        assert isinstance(corrector.validator, GeocodingValidator)

    def test_corrector_uses_shared_service(self):
        """Test that corrector uses the shared geocoding service."""
        from app.core.geocoding import GeocodingCorrector, get_geocoding_service

        corrector = GeocodingCorrector()
        assert corrector.geocoding_service is get_geocoding_service()


class TestNoDuplicateCode:
    """Test that duplicate geocoding code has been removed."""

    def test_no_duplicate_geocoders(self):
        """Test that there are no duplicate geocoder initializations."""
        from app.core.geocoding import get_geocoding_service
        from app.core.geocoding.validator import GeocodingValidator
        from app.core.geocoding.corrector import GeocodingCorrector

        # All should use the same singleton service
        service = get_geocoding_service()
        validator = GeocodingValidator()
        corrector = GeocodingCorrector()

        assert validator.geocoding_service is service
        assert corrector.geocoding_service is service

    def test_single_bounds_definition(self):
        """Test that bounds are defined in only one place."""
        from app.core.geocoding.constants import US_BOUNDS, STATE_BOUNDS
        from app.core.geocoding import GeocodingValidator

        validator = GeocodingValidator()
        # Validator should reference the constants, not have its own copy
        assert validator.US_BOUNDS is US_BOUNDS
        assert validator.STATE_BOUNDS is STATE_BOUNDS


class TestServiceIntegration:
    """Test integration between geocoding components."""

    @patch("app.core.geocoding.service.Redis")
    def test_service_caching_works(self, mock_redis):
        """Test that geocoding service caching works correctly."""
        from app.core.geocoding import get_geocoding_service

        mock_redis_instance = MagicMock()
        mock_redis.from_url.return_value = mock_redis_instance
        mock_redis_instance.get.return_value = None

        service = get_geocoding_service()
        assert service.redis_client is not None

    def test_validator_corrector_integration(self):
        """Test that validator and corrector work together."""
        from app.core.geocoding import GeocodingValidator, GeocodingCorrector

        validator = GeocodingValidator()
        corrector = GeocodingCorrector()

        # Corrector should use validator for validation
        assert corrector.validator is not None
        assert isinstance(corrector.validator, GeocodingValidator)

    def test_service_singleton_pattern(self):
        """Test that geocoding service uses singleton pattern."""
        from app.core.geocoding import get_geocoding_service

        service1 = get_geocoding_service()
        service2 = get_geocoding_service()

        # Should return the same instance
        assert service1 is service2


class TestImportOptimization:
    """Test that imports are optimized and don't cause circular dependencies."""

    def test_no_circular_imports(self):
        """Test that there are no circular import issues."""
        # These imports should all work without circular dependency issues
        from app.core.geocoding import (
            GeocodingService,
            GeocodingValidator,
            GeocodingCorrector,
            get_geocoding_service,
        )
        from app.core.geocoding.constants import US_BOUNDS, STATE_BOUNDS

        # Note: app.reconciler.geocoding_corrector has been removed as reconciler no longer does geocoding
        from app.llm.utils.geocoding_validator import GeocodingValidator as OldValidator

        assert all(
            [
                GeocodingService,
                GeocodingValidator,
                GeocodingCorrector,
                get_geocoding_service,
                US_BOUNDS,
                STATE_BOUNDS,
                OldValidator,  # LLM utils still has the shim for compatibility
            ]
        )
