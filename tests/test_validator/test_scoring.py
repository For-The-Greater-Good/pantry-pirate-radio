"""Tests for confidence scoring algorithm."""

import pytest
from typing import Dict, Any

from app.validator.scoring import ConfidenceScorer


class TestConfidenceScorer:
    """Test confidence scoring for validated locations."""

    def setup_method(self):
        """Set up test fixtures."""
        self.scorer = ConfidenceScorer()
        
        # Base location with good data (should score high)
        self.good_location = {
            "name": "Community Food Bank",
            "latitude": 40.7128,
            "longitude": -74.0060,
            "address": "123 Real Street",
            "city": "New York",
            "state": "NY",
            "postal_code": "10001",
            "geocoding_source": "arcgis",
        }
        
        # Location missing coordinates after enrichment (should score 0)
        self.no_coords_location = {
            "name": "Food Pantry",
            "latitude": None,
            "longitude": None,
            "address": "456 Main St",
            "city": "Brooklyn",
            "state": "NY",
        }
        
        # Location with 0,0 coordinates (should score 0)
        self.zero_coords_location = {
            "name": "Food Bank",
            "latitude": 0.0,
            "longitude": 0.0,
            "address": "789 Oak Ave",
            "city": "Queens",
            "state": "NY",
        }

    def test_perfect_score_location(self):
        """Test location with all valid data scores 100."""
        validation_results = {
            "has_coordinates": True,
            "is_zero_coordinates": False,
            "within_us_bounds": True,
            "within_state_bounds": True,
            "is_test_data": False,
            "has_placeholder_address": False,
            "geocoding_confidence": "high",
        }
        
        score = self.scorer.calculate_score(self.good_location, validation_results)
        assert score == 100

    def test_missing_coordinates_scores_zero(self):
        """Test location without coordinates after enrichment scores 0."""
        validation_results = {
            "has_coordinates": False,
            "is_zero_coordinates": False,
            "within_us_bounds": False,
            "within_state_bounds": False,
            "is_test_data": False,
            "has_placeholder_address": False,
            "geocoding_confidence": "failed",
        }
        
        score = self.scorer.calculate_score(self.no_coords_location, validation_results)
        assert score == 0

    def test_zero_coordinates_scores_zero(self):
        """Test location with 0,0 coordinates scores 0."""
        validation_results = {
            "has_coordinates": True,
            "is_zero_coordinates": True,
            "within_us_bounds": False,
            "within_state_bounds": False,
            "is_test_data": False,
            "has_placeholder_address": False,
            "geocoding_confidence": "low",
        }
        
        score = self.scorer.calculate_score(self.zero_coords_location, validation_results)
        assert score == 0

    def test_outside_us_bounds_scores_five(self):
        """Test location outside US bounds scores 5."""
        location = {
            **self.good_location,
            "latitude": 51.5074,  # London
            "longitude": -0.1276,
        }
        validation_results = {
            "has_coordinates": True,
            "is_zero_coordinates": False,
            "within_us_bounds": False,
            "within_state_bounds": False,
            "is_test_data": False,
            "has_placeholder_address": False,
            "geocoding_confidence": "high",
        }
        
        score = self.scorer.calculate_score(location, validation_results)
        assert score == 5

    def test_test_data_scores_five(self):
        """Test location identified as test data scores 5."""
        location = {
            **self.good_location,
            "name": "Test Food Bank",
            "address": "123 Test Street",
            "city": "Anytown",
            "postal_code": "00000",
        }
        validation_results = {
            "has_coordinates": True,
            "is_zero_coordinates": False,
            "within_us_bounds": True,
            "within_state_bounds": True,
            "is_test_data": True,
            "has_placeholder_address": False,
            "geocoding_confidence": "high",
        }
        
        score = self.scorer.calculate_score(location, validation_results)
        assert score == 5

    def test_placeholder_address_deducts_75_points(self):
        """Test placeholder address reduces score by 75 points."""
        location = {
            **self.good_location,
            "address": "123 Main Street",  # Generic placeholder
        }
        validation_results = {
            "has_coordinates": True,
            "is_zero_coordinates": False,
            "within_us_bounds": True,
            "within_state_bounds": True,
            "is_test_data": False,
            "has_placeholder_address": True,
            "geocoding_confidence": "high",
        }
        
        score = self.scorer.calculate_score(location, validation_results)
        assert score == 25  # 100 - 75

    def test_wrong_state_deducts_20_points(self):
        """Test coordinates outside claimed state reduces score by 20."""
        location = {
            **self.good_location,
            "state": "CA",  # Claims California but coords are in NY
        }
        validation_results = {
            "has_coordinates": True,
            "is_zero_coordinates": False,
            "within_us_bounds": True,
            "within_state_bounds": False,  # Not in claimed state
            "is_test_data": False,
            "has_placeholder_address": False,
            "geocoding_confidence": "high",
        }
        
        score = self.scorer.calculate_score(location, validation_results)
        assert score == 80  # 100 - 20

    def test_census_geocoder_deducts_10_points(self):
        """Test Census geocoder source reduces score by 10."""
        location = {
            **self.good_location,
            "geocoding_source": "census",
        }
        validation_results = {
            "has_coordinates": True,
            "is_zero_coordinates": False,
            "within_us_bounds": True,
            "within_state_bounds": True,
            "is_test_data": False,
            "has_placeholder_address": False,
            "geocoding_confidence": "medium",
        }
        
        score = self.scorer.calculate_score(location, validation_results)
        assert score == 90  # 100 - 10

    def test_fallback_geocoding_deducts_15_points(self):
        """Test fallback geocoding (state centroid) reduces score by 15."""
        location = {
            **self.good_location,
            "geocoding_source": "state_centroid",
        }
        validation_results = {
            "has_coordinates": True,
            "is_zero_coordinates": False,
            "within_us_bounds": True,
            "within_state_bounds": True,
            "is_test_data": False,
            "has_placeholder_address": False,
            "geocoding_confidence": "fallback",
        }
        
        score = self.scorer.calculate_score(location, validation_results)
        assert score == 85  # 100 - 15

    def test_missing_postal_deducts_5_points(self):
        """Test missing postal code reduces score by 5."""
        location = {
            **self.good_location,
            "postal_code": None,
        }
        validation_results = {
            "has_coordinates": True,
            "is_zero_coordinates": False,
            "within_us_bounds": True,
            "within_state_bounds": True,
            "is_test_data": False,
            "has_placeholder_address": False,
            "geocoding_confidence": "high",
            "missing_postal": True,
        }
        
        score = self.scorer.calculate_score(location, validation_results)
        assert score == 95  # 100 - 5

    def test_missing_city_deducts_10_points(self):
        """Test missing city reduces score by 10."""
        location = {
            **self.good_location,
            "city": None,
        }
        validation_results = {
            "has_coordinates": True,
            "is_zero_coordinates": False,
            "within_us_bounds": True,
            "within_state_bounds": True,
            "is_test_data": False,
            "has_placeholder_address": False,
            "geocoding_confidence": "high",
            "missing_city": True,
        }
        
        score = self.scorer.calculate_score(location, validation_results)
        assert score == 90  # 100 - 10

    def test_multiple_deductions_stack(self):
        """Test multiple quality issues stack deductions."""
        location = {
            **self.good_location,
            "address": "123 Main Street",  # Placeholder (-75)
            "state": "CA",  # Wrong state (-20)
            "geocoding_source": "census",  # Less reliable (-10)
            "postal_code": None,  # Missing postal (-5)
        }
        validation_results = {
            "has_coordinates": True,
            "is_zero_coordinates": False,
            "within_us_bounds": True,
            "within_state_bounds": False,
            "is_test_data": False,
            "has_placeholder_address": True,
            "geocoding_confidence": "medium",
            "missing_postal": True,
        }
        
        score = self.scorer.calculate_score(location, validation_results)
        # 100 - 75 - 20 - 10 - 5 = -10, but should be clamped to 0
        assert score == 0

    def test_score_never_negative(self):
        """Test score is clamped to minimum of 0."""
        location = {
            **self.good_location,
            "address": "123 Main Street",  # -75
            "state": "CA",  # -20
            "city": None,  # -10
            "postal_code": None,  # -5
            "geocoding_source": "fallback",  # -15
        }
        validation_results = {
            "has_coordinates": True,
            "is_zero_coordinates": False,
            "within_us_bounds": True,
            "within_state_bounds": False,
            "is_test_data": False,
            "has_placeholder_address": True,
            "geocoding_confidence": "fallback",
            "missing_postal": True,
            "missing_city": True,
        }
        
        score = self.scorer.calculate_score(location, validation_results)
        assert score == 0  # Should be 0, not negative

    def test_score_never_exceeds_100(self):
        """Test score is clamped to maximum of 100."""
        # Even with perfect data, score should not exceed 100
        validation_results = {
            "has_coordinates": True,
            "is_zero_coordinates": False,
            "within_us_bounds": True,
            "within_state_bounds": True,
            "is_test_data": False,
            "has_placeholder_address": False,
            "geocoding_confidence": "high",
        }
        
        score = self.scorer.calculate_score(self.good_location, validation_results)
        assert score == 100

    def test_alaska_location_scores_high(self):
        """Test valid Alaska location scores appropriately."""
        location = {
            **self.good_location,
            "latitude": 61.2181,  # Anchorage
            "longitude": -149.9003,
            "state": "AK",
            "city": "Anchorage",
        }
        validation_results = {
            "has_coordinates": True,
            "is_zero_coordinates": False,
            "within_us_bounds": True,  # Should handle Alaska
            "within_state_bounds": True,
            "is_test_data": False,
            "has_placeholder_address": False,
            "geocoding_confidence": "high",
        }
        
        score = self.scorer.calculate_score(location, validation_results)
        assert score == 100

    def test_hawaii_location_scores_high(self):
        """Test valid Hawaii location scores appropriately."""
        location = {
            **self.good_location,
            "latitude": 21.3099,  # Honolulu
            "longitude": -157.8581,
            "state": "HI",
            "city": "Honolulu",
        }
        validation_results = {
            "has_coordinates": True,
            "is_zero_coordinates": False,
            "within_us_bounds": True,  # Should handle Hawaii
            "within_state_bounds": True,
            "is_test_data": False,
            "has_placeholder_address": False,
            "geocoding_confidence": "high",
        }
        
        score = self.scorer.calculate_score(location, validation_results)
        assert score == 100

    def test_get_validation_status_verified(self):
        """Test status is 'verified' for high confidence scores."""
        assert self.scorer.get_validation_status(100) == "verified"
        assert self.scorer.get_validation_status(90) == "verified"
        assert self.scorer.get_validation_status(80) == "verified"

    def test_get_validation_status_needs_review(self):
        """Test status is 'needs_review' for medium confidence scores."""
        assert self.scorer.get_validation_status(79) == "needs_review"
        assert self.scorer.get_validation_status(50) == "needs_review"
        assert self.scorer.get_validation_status(10) == "needs_review"

    def test_get_validation_status_rejected(self):
        """Test status is 'rejected' for low confidence scores."""
        assert self.scorer.get_validation_status(9) == "rejected"
        assert self.scorer.get_validation_status(5) == "rejected"
        assert self.scorer.get_validation_status(0) == "rejected"

    def test_score_with_partial_validation_results(self):
        """Test scoring handles missing validation result keys gracefully."""
        # Minimal validation results
        validation_results = {
            "has_coordinates": True,
            "is_zero_coordinates": False,
            "within_us_bounds": True,
        }
        
        score = self.scorer.calculate_score(self.good_location, validation_results)
        # Should handle missing keys without error
        assert isinstance(score, int)
        assert 0 <= score <= 100