"""Tests for geocoding validation and correction utilities."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from app.llm.utils.geocoding_validator import GeocodingValidator


class TestGeocodingValidator:
    """Test suite for GeocodingValidator."""

    @pytest.fixture
    def validator(self):
        """Create a GeocodingValidator instance for testing."""
        with patch("app.llm.utils.geocoding_validator.Nominatim"), patch(
            "app.llm.utils.geocoding_validator.ArcGIS"
        ):
            return GeocodingValidator()

    def test_is_valid_lat_long(self, validator):
        """Test validation of latitude/longitude coordinates."""
        # Valid coordinates
        assert validator.is_valid_lat_long(40.7128, -74.0060) is True  # NYC
        assert validator.is_valid_lat_long(35.7596, -79.0193) is True  # NC
        assert validator.is_valid_lat_long(-33.8688, 151.2093) is True  # Sydney
        assert validator.is_valid_lat_long(0, 0) is True  # Null Island
        assert validator.is_valid_lat_long(90, 180) is True  # North Pole, Date Line
        assert validator.is_valid_lat_long(-90, -180) is True  # South Pole, Date Line

        # Invalid coordinates
        assert validator.is_valid_lat_long(91, 0) is False  # Latitude too high
        assert validator.is_valid_lat_long(-91, 0) is False  # Latitude too low
        assert validator.is_valid_lat_long(0, 181) is False  # Longitude too high
        assert validator.is_valid_lat_long(0, -181) is False  # Longitude too low
        assert (
            validator.is_valid_lat_long(4716694.4390345, -8553893.75627903) is False
        )  # Web Mercator

    def test_is_projected_coordinate(self, validator):
        """Test detection of projected coordinate systems."""
        # Projected coordinates (Web Mercator from actual data)
        assert validator.is_projected_coordinate(4716694.4390345) is True
        assert validator.is_projected_coordinate(-8553893.75627903) is True
        assert validator.is_projected_coordinate(1000000) is True
        assert validator.is_projected_coordinate(-1000000) is True

        # Valid lat/long coordinates
        assert validator.is_projected_coordinate(40.7128) is False
        assert validator.is_projected_coordinate(-74.0060) is False
        assert validator.is_projected_coordinate(90) is False
        assert validator.is_projected_coordinate(-180) is False
        assert validator.is_projected_coordinate(180) is False

    def test_convert_web_mercator_to_wgs84(self, validator):
        """Test conversion from Web Mercator to WGS84."""
        # Test with known Web Mercator coordinates for Maryland locations
        # Lanham, MD: 4711637.75015076, -8555931.90483597
        lat, lon = validator.convert_web_mercator_to_wgs84(
            -8555931.90483597, 4711637.75015076
        )
        assert 38.8 < lat < 39.0  # Lanham is around 38.9°N
        assert -77.0 < lon < -76.8  # Lanham is around -76.9°W

        # Test with NYC coordinates (Web Mercator)
        # NYC approximate: 40.7128°N, 74.0060°W
        # In Web Mercator: X=-8238310, Y=4970072
        lat, lon = validator.convert_web_mercator_to_wgs84(-8238310, 4970072)
        assert 40.6 < lat < 40.8
        assert -74.1 < lon < -73.9

    def test_is_within_state_bounds(self, validator):
        """Test checking if coordinates are within state bounds."""
        # Valid NC coordinates
        assert validator.is_within_state_bounds(35.7596, -79.0193, "NC") is True
        assert validator.is_within_state_bounds(35.399864, -80.608841, "NC") is True

        # Invalid NC coordinates (actually in Canada)
        assert validator.is_within_state_bounds(52.5024461, -1.9009857, "NC") is False
        assert validator.is_within_state_bounds(49.8139886, -101.6680452, "NC") is False

        # Edge cases
        assert (
            validator.is_within_state_bounds(36.5, -84.3, "NC") is True
        )  # Near border
        assert (
            validator.is_within_state_bounds(36.6, -84.3, "NC") is False
        )  # Just outside

        # Unknown state code
        assert validator.is_within_state_bounds(40.7128, -74.0060, "XX") is False

        # Case insensitive
        assert validator.is_within_state_bounds(35.7596, -79.0193, "nc") is True
        assert validator.is_within_state_bounds(35.7596, -79.0193, "Nc") is True

    def test_is_within_us_bounds(self, validator):
        """Test checking if coordinates are within US bounds."""
        # Continental US locations
        assert validator.is_within_us_bounds(40.7128, -74.0060) is True  # NYC
        assert validator.is_within_us_bounds(34.0522, -118.2437) is True  # LA
        assert validator.is_within_us_bounds(25.7617, -80.1918) is True  # Miami
        assert validator.is_within_us_bounds(47.6062, -122.3321) is True  # Seattle

        # Outside US
        assert validator.is_within_us_bounds(52.5024461, -1.9009857) is False  # UK
        assert (
            validator.is_within_us_bounds(49.8139886, -101.6680452) is False
        )  # Canada
        assert validator.is_within_us_bounds(-33.8688, 151.2093) is False  # Sydney

        # Edge cases
        assert (
            validator.is_within_us_bounds(49.0, -123.0) is True
        )  # Near Canadian border
        assert validator.is_within_us_bounds(24.5, -81.7) is True  # Key West area

    def test_validate_and_correct_coordinates_projected(self, validator):
        """Test correction of projected coordinates."""
        # Test Web Mercator coordinates from Maryland
        lat, lon, note = validator.validate_and_correct_coordinates(
            4711637.75015076,  # This is actually Y (northing)
            -8555931.90483597,  # This is actually X (easting)
            state_code="MD",
        )

        # Should detect projection and convert
        assert -90 <= lat <= 90
        assert -180 <= lon <= 180
        assert "Converted from Web Mercator" in note
        assert validator.is_within_state_bounds(lat, lon, "MD")

    def test_validate_and_correct_coordinates_wrong_state(self, validator):
        """Test correction of coordinates in wrong state."""
        with patch.object(validator, "nominatim_geocode") as mock_geocode:
            # Mock successful re-geocoding
            mock_location = Mock()
            mock_location.latitude = 35.7596
            mock_location.longitude = -79.0193
            mock_geocode.return_value = mock_location

            # Thomasville, NC geocoded to UK coordinates
            lat, lon, note = validator.validate_and_correct_coordinates(
                52.5024461,  # UK latitude
                -1.9009857,  # UK longitude
                state_code="NC",
                city="Thomasville",
            )

            # Should re-geocode to correct location
            assert validator.is_within_state_bounds(lat, lon, "NC")
            assert "Re-geocoded" in note

    def test_validate_and_correct_coordinates_fallback_to_centroid(self, validator):
        """Test fallback to state centroid when geocoding fails."""
        with patch.object(
            validator, "nominatim_geocode", return_value=None
        ), patch.object(validator, "arcgis_geocode", return_value=None):

            # Invalid coordinates with failed geocoding
            lat, lon, note = validator.validate_and_correct_coordinates(
                52.5024461,  # Invalid for NC
                -1.9009857,
                state_code="NC",
                city="Unknown City",
            )

            # Should use NC centroid
            assert lat == validator.STATE_CENTROIDS["NC"][0]
            assert lon == validator.STATE_CENTROIDS["NC"][1]
            assert "centroid" in note.lower()

    def test_suggest_correction(self, validator):
        """Test correction suggestions for invalid coordinates."""
        # Projected coordinates
        suggestion = validator.suggest_correction(4716694.4390345, -8553893.75627903)
        assert "projected coordinate system" in suggestion.lower()

        # Wrong state (NYC coordinates actually fall in NJ bounding box)
        suggestion = validator.suggest_correction(40.7128, -74.0060, "NC")
        assert suggestion is not None
        assert "not NC" in suggestion  # Should indicate it's not in NC

        # Outside US
        suggestion = validator.suggest_correction(52.5024461, -1.9009857, "NC")
        assert suggestion is not None
        assert "outside" in suggestion.lower()

        # Valid coordinates
        suggestion = validator.suggest_correction(35.7596, -79.0193, "NC")
        assert suggestion is None

    def test_hawaii_alaska_special_handling(self, validator):
        """Test special handling for Hawaii and Alaska coordinates."""
        # Hawaii coordinates (outside continental US bounds but valid)
        lat, lon, note = validator.validate_and_correct_coordinates(
            21.3099, -157.8581, state_code="HI"  # Honolulu
        )
        assert lat == 21.3099  # Should not change
        assert lon == -157.8581  # Should not change

        # Alaska coordinates (may have positive longitude)
        lat, lon, note = validator.validate_and_correct_coordinates(
            61.2181, -149.9003, state_code="AK"  # Anchorage
        )
        assert lat == 61.2181  # Should not change
        assert lon == -149.9003  # Should not change

    def test_geocoding_error_handling(self, validator):
        """Test handling of geocoding errors."""
        with patch.object(
            validator, "nominatim_geocode", side_effect=Exception("API Error")
        ), patch.object(
            validator, "arcgis_geocode", side_effect=Exception("API Error")
        ):

            # Should handle errors gracefully and use centroid
            lat, lon, note = validator.validate_and_correct_coordinates(
                52.5024461, -1.9009857, state_code="NC", city="Test City"  # Invalid
            )

            # Should fall back to centroid
            assert lat == validator.STATE_CENTROIDS["NC"][0]
            assert lon == validator.STATE_CENTROIDS["NC"][1]
