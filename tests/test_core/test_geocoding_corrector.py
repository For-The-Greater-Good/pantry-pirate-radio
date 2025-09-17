"""Tests for the geocoding corrector module."""

import pytest
from unittest.mock import MagicMock, patch, Mock
from typing import Optional
from sqlalchemy.orm import Session


class TestGeocodingCorrector:
    """Test cases for GeocodingCorrector."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return MagicMock(spec=Session)

    @pytest.fixture
    def mock_validator(self):
        """Create a mock geocoding validator."""
        validator = MagicMock()
        validator.is_projected_coordinate = MagicMock(return_value=False)
        validator.is_valid_coordinates = MagicMock(return_value=True)
        validator.is_within_us_bounds = MagicMock(return_value=True)
        validator.is_within_state_bounds = MagicMock(return_value=True)
        return validator

    @pytest.fixture
    def mock_geocoding_service(self):
        """Create a mock geocoding service."""
        service = MagicMock()
        service.geocode = MagicMock()
        return service

    @pytest.fixture
    def corrector(self, mock_db, mock_validator, mock_geocoding_service):
        """Create a GeocodingCorrector instance with mocks."""
        # Patch the modules at the point where they're imported
        with patch(
            "app.core.geocoding.validator.GeocodingValidator",
            return_value=mock_validator,
        ):
            with patch(
                "app.core.geocoding.service.get_geocoding_service",
                return_value=mock_geocoding_service,
            ):
                from app.core.geocoding.corrector import GeocodingCorrector

                return GeocodingCorrector(db=mock_db)

    def test_init_without_db(self, mock_validator, mock_geocoding_service):
        """Test initialization without database session."""
        with patch(
            "app.core.geocoding.validator.GeocodingValidator",
            return_value=mock_validator,
        ):
            with patch(
                "app.core.geocoding.service.get_geocoding_service",
                return_value=mock_geocoding_service,
            ):
                from app.core.geocoding.corrector import GeocodingCorrector

                corrector = GeocodingCorrector()
                assert corrector.db is None
                assert corrector.validator is not None
                assert corrector.geocoding_service is not None

    def test_init_with_db(self, mock_db, mock_validator, mock_geocoding_service):
        """Test initialization with database session."""
        with patch(
            "app.core.geocoding.validator.GeocodingValidator",
            return_value=mock_validator,
        ):
            with patch(
                "app.core.geocoding.service.get_geocoding_service",
                return_value=mock_geocoding_service,
            ):
                from app.core.geocoding.corrector import GeocodingCorrector

                corrector = GeocodingCorrector(db=mock_db)
                assert corrector.db == mock_db
                assert corrector.validator is not None
                assert corrector.geocoding_service is not None

    def test_find_invalid_locations_no_db(self, mock_validator, mock_geocoding_service):
        """Test find_invalid_locations without database."""
        with patch(
            "app.core.geocoding.validator.GeocodingValidator",
            return_value=mock_validator,
        ):
            with patch(
                "app.core.geocoding.service.get_geocoding_service",
                return_value=mock_geocoding_service,
            ):
                from app.core.geocoding.corrector import GeocodingCorrector

                corrector = GeocodingCorrector()
                result = corrector.find_invalid_locations()
                assert result == []

    def test_find_invalid_locations_with_zero_coordinates(self, corrector, mock_db):
        """Test finding locations with (0,0) coordinates."""
        # Mock database results with invalid coordinates
        mock_result = [
            MagicMock(
                id=1,
                name="Test Location",
                latitude=0.0,
                longitude=0.0,
                state_province="NY",
                city="New York",
                address_1="123 Main St",
            )
        ]
        mock_db.execute.return_value = mock_result

        invalid_locations = corrector.find_invalid_locations()

        assert len(invalid_locations) == 1
        assert invalid_locations[0]["id"] == 1
        assert "Coordinates are (0, 0)" in invalid_locations[0]["issues"]

    def test_find_invalid_locations_with_projected_coordinates(
        self, corrector, mock_db
    ):
        """Test finding locations with projected coordinates."""
        mock_result = [
            MagicMock(
                id=2,
                name="Test Location 2",
                latitude=4000000.0,
                longitude=-8000000.0,
                state_province="CA",
                city="Los Angeles",
                address_1="456 Oak Ave",
            )
        ]
        mock_db.execute.return_value = mock_result
        corrector.validator.is_projected_coordinate.return_value = True

        invalid_locations = corrector.find_invalid_locations()

        assert len(invalid_locations) == 1
        assert invalid_locations[0]["id"] == 2
        assert "projected coordinate system" in str(invalid_locations[0]["issues"])

    def test_find_invalid_locations_outside_valid_range(self, corrector, mock_db):
        """Test finding locations outside valid coordinate range."""
        mock_result = [
            MagicMock(
                id=3,
                name="Test Location 3",
                latitude=200.0,
                longitude=-400.0,
                state_province="TX",
                city="Houston",
                address_1="789 Elm St",
            )
        ]
        mock_db.execute.return_value = mock_result
        corrector.validator.is_projected_coordinate.return_value = False
        corrector.validator.is_valid_coordinates.return_value = False

        invalid_locations = corrector.find_invalid_locations()

        assert len(invalid_locations) == 1
        assert invalid_locations[0]["id"] == 3
        assert "outside valid range" in str(invalid_locations[0]["issues"])

    def test_find_invalid_locations_outside_us_bounds(self, corrector, mock_db):
        """Test finding locations outside US bounds."""
        mock_result = [
            MagicMock(
                id=4,
                name="Test Location 4",
                latitude=51.5074,
                longitude=-0.1278,
                state_province="FL",
                city="Miami",
                address_1="321 Beach Rd",
            )
        ]
        mock_db.execute.return_value = mock_result
        corrector.validator.is_projected_coordinate.return_value = False
        corrector.validator.is_valid_coordinates.return_value = True
        corrector.validator.is_within_us_bounds.return_value = False

        invalid_locations = corrector.find_invalid_locations()

        assert len(invalid_locations) == 1
        assert invalid_locations[0]["id"] == 4
        assert "outside US bounds" in str(invalid_locations[0]["issues"])

    def test_find_invalid_locations_alaska_hawaii_ok(self, corrector, mock_db):
        """Test that Alaska and Hawaii locations are not flagged as invalid."""
        mock_result = [
            MagicMock(
                id=5,
                name="Alaska Location",
                latitude=64.0685,
                longitude=-141.0234,
                state_province="AK",
                city="Anchorage",
                address_1="100 Alaska Way",
            ),
            MagicMock(
                id=6,
                name="Hawaii Location",
                latitude=21.3099,
                longitude=-157.8581,
                state_province="HI",
                city="Honolulu",
                address_1="200 Aloha St",
            ),
        ]
        mock_db.execute.return_value = mock_result
        corrector.validator.is_projected_coordinate.return_value = False
        corrector.validator.is_valid_coordinates.return_value = True
        corrector.validator.is_within_us_bounds.return_value = False

        invalid_locations = corrector.find_invalid_locations()

        # Alaska and Hawaii should not be flagged as invalid
        assert len(invalid_locations) == 0

    def test_find_invalid_locations_mismatched_state(self, corrector, mock_db):
        """Test finding locations with coordinates that don't match state."""
        mock_result = [
            MagicMock(
                id=7,
                name="Mismatched Location",
                latitude=40.7128,
                longitude=-74.0060,
                state_province="CA",  # NY coordinates with CA state
                city="San Francisco",
                address_1="999 Market St",
            )
        ]
        mock_db.execute.return_value = mock_result
        corrector.validator.is_projected_coordinate.return_value = False
        corrector.validator.is_valid_coordinates.return_value = True
        corrector.validator.is_within_us_bounds.return_value = True
        corrector.validator.is_within_state_bounds.return_value = False
        # Mock suggest_correction to return a proper string
        corrector.validator.suggest_correction = MagicMock(
            return_value="Coordinates do not match state CA - appears to be in NY"
        )

        invalid_locations = corrector.find_invalid_locations()

        assert len(invalid_locations) == 1
        assert invalid_locations[0]["id"] == 7
        assert "not match state" in str(invalid_locations[0]["issues"])
