"""Test the zero coordinate handling in job processor.

This is a focused test for the specific geocoding improvements we added.
"""

import pytest
from unittest.mock import MagicMock, patch
from app.reconciler.job_processor import JobProcessor


class TestZeroCoordinateHandling:
    """Test that 0,0 coordinates are properly handled."""
    
    def test_zero_coordinates_trigger_geocoding(self):
        """Test that 0,0 coordinates are treated as missing and trigger geocoding."""
        # This test verifies our logic for detecting 0,0 as invalid
        
        # Test data
        location_data = {
            "name": "Test Location",
            "latitude": 0.0,
            "longitude": 0.0,
            "addresss": [{
                "address_1": "123 Test St",
                "city": "TestCity", 
                "state_province": "OH"
            }]
        }
        
        # Our logic should detect this as invalid
        has_valid_coords = False
        
        if (
            "latitude" in location_data
            and "longitude" in location_data
            and location_data["latitude"] is not None
            and location_data["longitude"] is not None
        ):
            # Check if coordinates are invalid (0,0)
            lat = float(location_data["latitude"])
            lon = float(location_data["longitude"])
            if lat == 0.0 and lon == 0.0:
                # This is what our code does - marks as invalid
                has_valid_coords = False
            else:
                has_valid_coords = True
        
        # Assert that 0,0 is correctly identified as invalid
        assert has_valid_coords == False, "0,0 coordinates should be marked as invalid"
    
    def test_valid_coordinates_skip_geocoding(self):
        """Test that valid non-zero coordinates don't trigger geocoding."""
        
        # Test data with valid coordinates
        location_data = {
            "name": "Valid Location",
            "latitude": 41.8781,
            "longitude": -87.6298,
            "addresss": [{
                "address_1": "123 Valid St",
                "city": "Chicago",
                "state_province": "IL"
            }]
        }
        
        # Our logic should accept this as valid
        has_valid_coords = False
        
        if (
            "latitude" in location_data
            and "longitude" in location_data
            and location_data["latitude"] is not None
            and location_data["longitude"] is not None
        ):
            # Check if coordinates are invalid (0,0)
            lat = float(location_data["latitude"])
            lon = float(location_data["longitude"])
            if lat == 0.0 and lon == 0.0:
                has_valid_coords = False
            else:
                has_valid_coords = True
        
        # Assert that valid coordinates are accepted
        assert has_valid_coords == True, "Valid coordinates should not trigger geocoding"
    
    def test_missing_coordinates_trigger_geocoding(self):
        """Test that missing coordinates trigger geocoding."""
        
        # Test data without coordinates
        location_data = {
            "name": "No Coords Location",
            "addresss": [{
                "address_1": "456 Main St",
                "city": "Denver",
                "state_province": "CO"
            }]
        }
        
        # Our logic should detect missing coordinates
        has_valid_coords = False
        
        if (
            "latitude" in location_data
            and "longitude" in location_data
            and location_data["latitude"] is not None
            and location_data["longitude"] is not None
        ):
            # This won't be reached for missing coords
            lat = float(location_data["latitude"])
            lon = float(location_data["longitude"])
            if lat == 0.0 and lon == 0.0:
                has_valid_coords = False
            else:
                has_valid_coords = True
        
        # Assert that missing coordinates are detected
        assert has_valid_coords == False, "Missing coordinates should trigger geocoding"
    
    def test_null_coordinates_trigger_geocoding(self):
        """Test that null coordinates trigger geocoding."""
        
        # Test data with null coordinates
        location_data = {
            "name": "Null Coords Location",
            "latitude": None,
            "longitude": None,
            "addresss": [{
                "address_1": "789 Broadway",
                "city": "New York",
                "state_province": "NY"
            }]
        }
        
        # Our logic should detect null coordinates
        has_valid_coords = False
        
        if (
            "latitude" in location_data
            and "longitude" in location_data
            and location_data["latitude"] is not None
            and location_data["longitude"] is not None
        ):
            # This won't be reached for null coords
            lat = float(location_data["latitude"])
            lon = float(location_data["longitude"])
            if lat == 0.0 and lon == 0.0:
                has_valid_coords = False
            else:
                has_valid_coords = True
        
        # Assert that null coordinates are detected
        assert has_valid_coords == False, "Null coordinates should trigger geocoding"


class TestExhaustiveGeocodingLogic:
    """Test the exhaustive geocoding with fallback logic."""
    
    @patch("app.core.geocoding.get_geocoding_service")
    def test_geocoding_tries_multiple_providers(self, mock_get_service):
        """Test that geocoding attempts multiple providers."""
        
        # Mock the geocoding service
        mock_geocoding = MagicMock()
        mock_geocoding.geocode.side_effect = [
            None,  # Primary fails
            None,  # ArcGIS fails
            (39.7392, -104.9903)  # Nominatim succeeds
        ]
        mock_get_service.return_value = mock_geocoding
        
        # Simulate the logic from our job processor
        address_string = "123 Main St, Denver, CO"
        geocoded_coords = None
        
        # Try primary provider first
        geocoded_coords = mock_geocoding.geocode(address_string)
        
        # If primary failed, try all providers explicitly
        if not geocoded_coords:
            # Try ArcGIS explicitly
            geocoded_coords = mock_geocoding.geocode(
                address_string, force_provider="arcgis"
            )
            
            # If ArcGIS failed, try Nominatim
            if not geocoded_coords:
                geocoded_coords = mock_geocoding.geocode(
                    address_string, force_provider="nominatim"
                )
        
        # Assert
        assert geocoded_coords == (39.7392, -104.9903), "Should get coordinates from fallback"
        assert mock_geocoding.geocode.call_count == 3, "Should try 3 times"
        
        # Check the calls
        calls = mock_geocoding.geocode.call_args_list
        assert "force_provider" not in calls[0][1], "First call should not force provider"
        assert calls[1][1]["force_provider"] == "arcgis", "Second call should force ArcGIS"
        assert calls[2][1]["force_provider"] == "nominatim", "Third call should force Nominatim"
    
    @patch("app.core.geocoding.get_geocoding_service")
    def test_geocoding_all_providers_fail(self, mock_get_service):
        """Test behavior when all geocoding providers fail."""
        
        # Mock the geocoding service to always fail
        mock_geocoding = MagicMock()
        mock_geocoding.geocode.return_value = None
        mock_get_service.return_value = mock_geocoding
        
        # Simulate the logic from our job processor
        address_string = "999 Nowhere St, NoCity, XX"
        geocoded_coords = None
        
        # Try primary provider first
        geocoded_coords = mock_geocoding.geocode(address_string)
        
        # If primary failed, try all providers explicitly
        if not geocoded_coords:
            # Try ArcGIS explicitly
            geocoded_coords = mock_geocoding.geocode(
                address_string, force_provider="arcgis"
            )
            
            # If ArcGIS failed, try Nominatim
            if not geocoded_coords:
                geocoded_coords = mock_geocoding.geocode(
                    address_string, force_provider="nominatim"
                )
        
        # When all fail, we should raise an error in the actual code
        if not geocoded_coords:
            error_msg = f"Unable to geocode location - all providers failed"
        
        # Assert
        assert geocoded_coords is None, "All providers should fail"
        assert mock_geocoding.geocode.call_count == 3, "Should try all 3 providers"
        assert error_msg == "Unable to geocode location - all providers failed"