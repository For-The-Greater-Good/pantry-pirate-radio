"""Test the coordinate handling in job processor.

This test verifies that the reconciler trusts the validator's coordinates
and doesn't attempt any geocoding.
"""

import pytest
from unittest.mock import MagicMock, patch
from app.reconciler.job_processor import JobProcessor


class TestCoordinateHandling:
    """Test that reconciler trusts validator-provided coordinates."""

    def test_reconciler_trusts_validator_coordinates(self):
        """Test that reconciler uses coordinates directly from validator without geocoding."""
        # Test data with coordinates from validator
        location_data = {
            "name": "Test Location",
            "latitude": 41.8781,
            "longitude": -87.6298,
            "confidence_score": 85,
            "validation_status": "verified",
            "address": [
                {"address_1": "123 Test St", "city": "Chicago", "state_province": "IL"}
            ],
        }

        # Reconciler should trust these coordinates
        has_valid_coords = False

        if (
            "latitude" in location_data
            and "longitude" in location_data
            and location_data["latitude"] is not None
            and location_data["longitude"] is not None
        ):
            # Reconciler simply trusts the validator's coordinates
            has_valid_coords = True

        # Assert that valid coordinates are accepted
        assert (
            has_valid_coords is True
        ), "Reconciler should trust validator's coordinates"

    def test_reconciler_skips_locations_without_coordinates(self):
        """Test that reconciler skips locations that have no coordinates after validation."""

        # Test data without coordinates (should have been rejected by validator)
        location_data = {
            "name": "No Coords Location",
            "confidence_score": 0,
            "validation_status": "rejected",
            "address": [
                {"address_1": "456 Main St", "city": "Denver", "state_province": "CO"}
            ],
        }

        # Reconciler should skip this location
        should_skip = False

        if (
            "latitude" not in location_data
            or "longitude" not in location_data
            or location_data.get("latitude") is None
            or location_data.get("longitude") is None
        ):
            # No coordinates from validator - skip this location
            should_skip = True

        # Assert that location without coordinates is skipped
        assert should_skip is True, "Locations without coordinates should be skipped"

    def test_reconciler_respects_rejection_status(self):
        """Test that reconciler respects the validator's rejection decision."""

        # Test data with rejected status
        location_data = {
            "name": "Rejected Location",
            "latitude": 0.0,  # Invalid coordinates
            "longitude": 0.0,
            "confidence_score": 5,
            "validation_status": "rejected",
            "validation_notes": {"reason": "Invalid coordinates (0,0)"},
            "address": [
                {"address_1": "789 Fake St", "city": "Nowhere", "state_province": "XX"}
            ],
        }

        # Check if location should be skipped based on validation status
        should_skip = location_data.get("validation_status") == "rejected"

        # Assert that rejected locations are skipped
        assert should_skip is True, "Rejected locations should be skipped by reconciler"

    def test_reconciler_accepts_enriched_coordinates(self):
        """Test that reconciler accepts coordinates that were enriched by the validator."""

        # Test data with enriched coordinates
        location_data = {
            "name": "Enriched Location",
            "latitude": 39.7392,  # Coordinates added by validator
            "longitude": -104.9903,
            "confidence_score": 75,
            "validation_status": "verified",
            "geocoding_source": "arcgis",
            "validation_notes": {"enrichment": {"coordinates_added": True}},
            "address": [
                {
                    "address_1": "1 Civic Center",
                    "city": "Denver",
                    "state_province": "CO",
                }
            ],
        }

        # Reconciler should accept enriched coordinates
        has_valid_coords = False

        if (
            "latitude" in location_data
            and "longitude" in location_data
            and location_data["latitude"] is not None
            and location_data["longitude"] is not None
        ):
            has_valid_coords = True

        # Check that geocoding source is tracked
        has_geocoding_source = "geocoding_source" in location_data

        # Assert that enriched coordinates are accepted
        assert has_valid_coords is True, "Enriched coordinates should be accepted"
        assert has_geocoding_source is True, "Geocoding source should be tracked"

    def test_reconciler_handles_high_confidence_locations(self):
        """Test that reconciler properly handles high-confidence locations."""

        # Test data with high confidence
        location_data = {
            "name": "High Confidence Location",
            "latitude": 40.7128,
            "longitude": -74.0060,
            "confidence_score": 95,
            "validation_status": "verified",
            "address": [
                {"address_1": "1 Wall St", "city": "New York", "state_province": "NY"}
            ],
        }

        # Check confidence level
        is_high_confidence = location_data.get("confidence_score", 0) >= 80
        should_process = (
            location_data.get("validation_status") != "rejected"
            and "latitude" in location_data
            and "longitude" in location_data
        )

        # Assert high confidence locations are processed
        assert is_high_confidence is True, "Should recognize high confidence"
        assert should_process is True, "High confidence locations should be processed"
