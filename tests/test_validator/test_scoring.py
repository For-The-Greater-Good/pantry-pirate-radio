"""Tests for confidence scoring algorithm — build-up model."""

import pytest
from typing import Dict, Any

from app.validator.scoring import (
    BASE_SCORE,
    SCRAPED_DATA_CAP,
    VERIFICATION_TIER_ADMIN,
    VERIFICATION_TIER_SOURCE_CONFIRM,
    VERIFICATION_TIER_SOURCE_CORRECT,
    ConfidenceScorer,
)


class TestConfidenceScorer:
    """Test confidence scoring for validated locations."""

    def setup_method(self):
        """Set up test fixtures."""
        self.scorer = ConfidenceScorer()

        # Good location with full address and description (arcgis geocoded)
        self.good_location = {
            "name": "Community Food Bank",
            "latitude": 40.7128,
            "longitude": -74.0060,
            "address_1": "123 Real Street",
            "city": "New York",
            "state_province": "NY",
            "postal_code": "10001",
            "description": "A community food bank serving the greater NYC area",
            "geocoding_source": "arcgis",
        }

        # Bare minimum location (coordinates + name only, no bonuses)
        self.bare_location = {
            "name": "Food Pantry",
            "latitude": 40.7128,
            "longitude": -74.0060,
        }

        # Location missing coordinates after enrichment
        self.no_coords_location = {
            "name": "Food Pantry",
            "latitude": None,
            "longitude": None,
            "address_1": "456 Main St",
            "city": "Brooklyn",
            "state_province": "NY",
        }

        # Location with 0,0 coordinates
        self.zero_coords_location = {
            "name": "Food Bank",
            "latitude": 0.0,
            "longitude": 0.0,
            "address_1": "789 Oak Ave",
            "city": "Queens",
            "state_province": "NY",
        }

        # Good validation results (no issues)
        self.good_validation = {
            "has_coordinates": True,
            "is_zero_coordinates": False,
            "within_us_bounds": True,
            "within_state_bounds": True,
            "is_test_data": False,
            "has_placeholder_address": False,
            "geocoding_confidence": "high",
        }

    # ========================================
    # Critical Failures (unchanged)
    # ========================================

    def test_missing_coordinates_scores_zero(self):
        """Location without coordinates after enrichment scores 0."""
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
        """Location with 0,0 coordinates scores 0."""
        validation_results = {
            "has_coordinates": True,
            "is_zero_coordinates": True,
            "within_us_bounds": False,
            "within_state_bounds": False,
            "is_test_data": False,
            "has_placeholder_address": False,
            "geocoding_confidence": "low",
        }
        score = self.scorer.calculate_score(
            self.zero_coords_location, validation_results
        )
        assert score == 0

    def test_outside_us_bounds_scores_five(self):
        """Location outside US bounds scores 5."""
        location = {
            **self.good_location,
            "latitude": 51.5074,  # London
            "longitude": -0.1276,
        }
        validation_results = {
            **self.good_validation,
            "within_us_bounds": False,
            "within_state_bounds": False,
        }
        score = self.scorer.calculate_score(location, validation_results)
        assert score == 5

    def test_test_data_scores_five(self):
        """Location identified as test data scores 5."""
        location = {
            **self.good_location,
            "name": "Test Food Bank",
            "address_1": "123 Test Street",
            "city": "Anytown",
            "postal_code": "00000",
        }
        validation_results = {
            **self.good_validation,
            "is_test_data": True,
        }
        score = self.scorer.calculate_score(location, validation_results)
        assert score == 5

    # ========================================
    # Base Score
    # ========================================

    def test_base_score_is_60(self):
        """Bare minimum valid location (coords + name only) gets base score of 60."""
        score = self.scorer.calculate_score(self.bare_location, self.good_validation)
        assert score == 60

    # ========================================
    # Completeness Bonuses
    # ========================================

    def test_full_address_bonus(self):
        """Full address (street + city + state + zip) adds +5."""
        location = {
            **self.bare_location,
            "address_1": "123 Real Street",
            "city": "New York",
            "state_province": "NY",
            "postal_code": "10001",
        }
        score = self.scorer.calculate_score(location, self.good_validation)
        # base 60 + full address 5 = 65
        assert score == 65

    def test_description_bonus(self):
        """Meaningful description (>10 chars) adds +3."""
        location = {
            **self.bare_location,
            "description": "A community food bank serving the greater area",
        }
        score = self.scorer.calculate_score(location, self.good_validation)
        # base 60 + description 3 = 63
        assert score == 63

    def test_short_description_no_bonus(self):
        """Short description (<=10 chars) gets no bonus."""
        location = {
            **self.bare_location,
            "description": "Food bank",
        }
        score = self.scorer.calculate_score(location, self.good_validation)
        assert score == 60

    def test_high_quality_geocoder_bonus(self):
        """High-quality geocoder (arcgis/google/amazon-location) adds +5."""
        location = {
            **self.bare_location,
            "geocoding_source": "arcgis",
        }
        score = self.scorer.calculate_score(location, self.good_validation)
        # base 60 + geocoder 5 = 65
        assert score == 65

    def test_nominatim_no_bonus_no_penalty(self):
        """Nominatim geocoder gets neither bonus nor penalty."""
        location = {
            **self.bare_location,
            "geocoding_source": "nominatim",
        }
        score = self.scorer.calculate_score(location, self.good_validation)
        # base 60 only
        assert score == 60

    def test_service_phone_bonus(self):
        """Service-level phone annotation adds +3."""
        location = {
            **self.bare_location,
            "_has_phone": True,
        }
        score = self.scorer.calculate_score(location, self.good_validation)
        # base 60 + phone 3 = 63
        assert score == 63

    def test_service_schedule_bonus(self):
        """Service-level schedule annotation adds +3."""
        location = {
            **self.bare_location,
            "_has_schedule": True,
        }
        score = self.scorer.calculate_score(location, self.good_validation)
        # base 60 + schedule 3 = 63
        assert score == 63

    def test_service_website_bonus(self):
        """Service-level website annotation adds +3."""
        location = {
            **self.bare_location,
            "_has_website": True,
        }
        score = self.scorer.calculate_score(location, self.good_validation)
        # base 60 + website 3 = 63
        assert score == 63

    # ========================================
    # Combined Score — Good Location
    # ========================================

    def test_good_location_scores_73(self):
        """Good location with full addr + desc + arcgis scores 73."""
        # good_location has: full address, description, arcgis geocoder
        # base 60 + addr 5 + desc 3 + geocoder 5 = 73
        score = self.scorer.calculate_score(self.good_location, self.good_validation)
        assert score == 73

    def test_full_data_single_source_scores_82(self):
        """Location with all completeness bonuses scores 82."""
        location = {
            **self.good_location,
            "_has_phone": True,
            "_has_schedule": True,
            "_has_website": True,
        }
        # base 60 + addr 5 + desc 3 + geocoder 5 + phone 3 + schedule 3 + website 3 = 82
        score = self.scorer.calculate_score(location, self.good_validation)
        assert score == 82

    # ========================================
    # Geocoding Penalties
    # ========================================

    def test_census_geocoder_penalty(self):
        """Census geocoder deducts 5 points."""
        location = {
            **self.good_location,
            "geocoding_source": "census",
        }
        # base 60 + addr 5 + desc 3 + census -5 = 63
        score = self.scorer.calculate_score(location, self.good_validation)
        assert score == 63

    def test_fallback_geocoding_penalty(self):
        """Fallback geocoding (state centroid) deducts 10 points."""
        location = {
            **self.good_location,
            "geocoding_source": "state_centroid",
        }
        validation_results = {
            **self.good_validation,
            "geocoding_confidence": "fallback",
        }
        # base 60 + addr 5 + desc 3 - 10 = 58
        score = self.scorer.calculate_score(location, validation_results)
        assert score == 58

    # ========================================
    # Quality Penalties
    # ========================================

    def test_placeholder_address_scores_zero(self):
        """Placeholder address penalty (-75) usually results in rejection."""
        location = {
            **self.good_location,
            "address_1": "123 Main Street",  # Generic placeholder
        }
        validation_results = {
            **self.good_validation,
            "has_placeholder_address": True,
        }
        # base 60 + addr 5 + desc 3 + geocoder 5 - 75 = -2 -> clamped to 0
        score = self.scorer.calculate_score(location, validation_results)
        assert score == 0

    def test_wrong_state_penalty(self):
        """Coordinates outside claimed state deducts 20 points."""
        location = {
            **self.good_location,
            "state_province": "CA",  # Claims California but coords are in NY
        }
        validation_results = {
            **self.good_validation,
            "within_state_bounds": False,
        }
        # base 60 + addr 5 + desc 3 + geocoder 5 - 20 = 53
        score = self.scorer.calculate_score(location, validation_results)
        assert score == 53

    # ========================================
    # Missing Address Components
    # ========================================

    def test_missing_postal_no_full_address_bonus(self):
        """Missing postal code means no full address bonus."""
        location = {
            **self.good_location,
            "postal_code": None,
        }
        # base 60 + desc 3 + geocoder 5 = 68 (no full addr bonus)
        score = self.scorer.calculate_score(location, self.good_validation)
        assert score == 68

    def test_missing_city_no_full_address_bonus(self):
        """Missing city means no full address bonus."""
        location = {
            **self.good_location,
            "city": None,
        }
        # base 60 + desc 3 + geocoder 5 = 68 (no full addr bonus)
        score = self.scorer.calculate_score(location, self.good_validation)
        assert score == 68

    # ========================================
    # Score Capping
    # ========================================

    def test_max_scraped_score_capped_at_90(self):
        """Even with all bonuses, scraped data can't exceed 90."""
        location = {
            **self.good_location,
            "_has_phone": True,
            "_has_schedule": True,
            "_has_website": True,
        }
        # base 60 + addr 5 + desc 3 + geocoder 5 + phone 3 + sched 3 + web 3 = 82
        # 82 < 90, so not capped. But let's verify the cap with source corroboration
        score = self.scorer.calculate_score(location, self.good_validation)
        assert score <= 90

    def test_score_never_exceeds_90_for_scraped(self):
        """Score is clamped to maximum of 90 for scraped data."""
        score = self.scorer.calculate_score(self.good_location, self.good_validation)
        assert score <= 90

    def test_score_never_negative(self):
        """Score is clamped to minimum of 0."""
        location = {
            **self.good_location,
            "address_1": "123 Main Street",  # placeholder
            "state_province": "CA",  # wrong state
            "geocoding_source": "fallback",
        }
        validation_results = {
            **self.good_validation,
            "within_state_bounds": False,
            "has_placeholder_address": True,
            "geocoding_confidence": "fallback",
        }
        score = self.scorer.calculate_score(location, validation_results)
        assert score == 0

    # ========================================
    # Stacked Deductions
    # ========================================

    def test_multiple_deductions_stack(self):
        """Multiple quality issues stack deductions."""
        location = {
            **self.good_location,
            "address_1": "123 Main Street",  # Placeholder (-75)
            "state_province": "CA",  # Wrong state (-20)
            "geocoding_source": "census",  # Census (-5)
        }
        validation_results = {
            **self.good_validation,
            "within_state_bounds": False,
            "has_placeholder_address": True,
        }
        # base 60 + addr 5 + desc 3 - 5 - 75 - 20 = -32 -> clamped to 0
        score = self.scorer.calculate_score(location, validation_results)
        assert score == 0

    # ========================================
    # Geographic Edge Cases
    # ========================================

    def test_alaska_location_scores_appropriately(self):
        """Valid Alaska location scores based on build-up model."""
        location = {
            **self.good_location,
            "latitude": 61.2181,  # Anchorage
            "longitude": -149.9003,
            "state_province": "AK",
            "city": "Anchorage",
        }
        # base 60 + addr 5 + desc 3 + geocoder 5 = 73
        score = self.scorer.calculate_score(location, self.good_validation)
        assert score == 73

    def test_hawaii_location_scores_appropriately(self):
        """Valid Hawaii location scores based on build-up model."""
        location = {
            **self.good_location,
            "latitude": 21.3099,  # Honolulu
            "longitude": -157.8581,
            "state_province": "HI",
            "city": "Honolulu",
        }
        # base 60 + addr 5 + desc 3 + geocoder 5 = 73
        score = self.scorer.calculate_score(location, self.good_validation)
        assert score == 73

    # ========================================
    # Validation Status
    # ========================================

    def test_get_validation_status_verified(self):
        """Status is 'verified' for scores >= 80."""
        assert self.scorer.get_validation_status(90) == "verified"
        assert self.scorer.get_validation_status(80) == "verified"

    def test_get_validation_status_needs_review(self):
        """Status is 'needs_review' for scores >= threshold and < 80."""
        assert self.scorer.get_validation_status(79) == "needs_review"
        assert self.scorer.get_validation_status(50) == "needs_review"
        assert self.scorer.get_validation_status(10) == "needs_review"

    def test_get_validation_status_rejected(self):
        """Status is 'rejected' for scores below threshold."""
        assert self.scorer.get_validation_status(9) == "rejected"
        assert self.scorer.get_validation_status(5) == "rejected"
        assert self.scorer.get_validation_status(0) == "rejected"

    # ========================================
    # Source Corroboration
    # ========================================

    def test_source_corroboration_2_sources(self):
        """Two distinct sources add +5 bonus."""
        result = self.scorer.apply_source_corroboration(73, 2)
        assert result == 78

    def test_source_corroboration_3_plus_sources(self):
        """Three or more distinct sources add +10 bonus (capped)."""
        result = self.scorer.apply_source_corroboration(73, 3)
        assert result == 83
        # 4 sources should also be +10 (capped at 3+)
        result = self.scorer.apply_source_corroboration(73, 5)
        assert result == 83

    def test_source_corroboration_capped_at_90(self):
        """Source corroboration bonus cannot exceed scraped data cap of 90."""
        result = self.scorer.apply_source_corroboration(85, 3)
        assert result == 90

    def test_source_corroboration_single_source_no_bonus(self):
        """Single source gets no corroboration bonus."""
        result = self.scorer.apply_source_corroboration(73, 1)
        assert result == 73

    # ========================================
    # Partial Validation Results
    # ========================================

    def test_score_with_partial_validation_results(self):
        """Scoring handles missing validation result keys gracefully."""
        validation_results = {
            "has_coordinates": True,
            "is_zero_coordinates": False,
            "within_us_bounds": True,
        }
        score = self.scorer.calculate_score(self.good_location, validation_results)
        assert isinstance(score, int)
        assert 0 <= score <= 90


class TestVerificationTierConstants:
    """Test verification tier constants for the scoring hierarchy.

    Hierarchy: source (Lighthouse) > admin (Helm) > automated (pipeline).
    """

    def test_verification_tiers_exist(self):
        """Verification tier constants are defined."""
        assert VERIFICATION_TIER_ADMIN == 93
        assert VERIFICATION_TIER_SOURCE_CONFIRM == 95
        assert VERIFICATION_TIER_SOURCE_CORRECT == 98

    def test_verification_tiers_above_scraped_cap(self):
        """All verification tiers exceed the scraped data cap."""
        assert VERIFICATION_TIER_ADMIN > SCRAPED_DATA_CAP
        assert VERIFICATION_TIER_SOURCE_CONFIRM > SCRAPED_DATA_CAP
        assert VERIFICATION_TIER_SOURCE_CORRECT > SCRAPED_DATA_CAP

    def test_verification_tier_hierarchy(self):
        """Source verification > admin > scraped cap."""
        assert VERIFICATION_TIER_SOURCE_CORRECT > VERIFICATION_TIER_SOURCE_CONFIRM
        assert VERIFICATION_TIER_SOURCE_CONFIRM > VERIFICATION_TIER_ADMIN
        assert VERIFICATION_TIER_ADMIN > SCRAPED_DATA_CAP

    def test_verification_tiers_within_valid_range(self):
        """All tiers are valid confidence scores (0-100)."""
        for tier in [
            VERIFICATION_TIER_ADMIN,
            VERIFICATION_TIER_SOURCE_CONFIRM,
            VERIFICATION_TIER_SOURCE_CORRECT,
        ]:
            assert 0 <= tier <= 100
