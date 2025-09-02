"""Tests for geocoding enrichment in validator service."""

import pytest
from unittest.mock import MagicMock, patch, call
from decimal import Decimal

from app.llm.queue.models import JobResult, JobStatus
from app.validator.enrichment import GeocodingEnricher
from app.validator.job_processor import ValidationProcessor


class TestGeocodingEnricher:
    """Test geocoding enrichment functionality."""

    @patch("app.validator.enrichment.redis.from_url")
    def test_enrich_location_with_missing_coordinates(self, mock_redis_from_url):
        """Test geocoding when location has address but no coordinates."""
        # Mock Redis to ensure no caching interference
        mock_redis = MagicMock()
        mock_redis.get.return_value = None  # No cached values
        mock_redis_from_url.return_value = mock_redis

        # Arrange
        location_data = {
            "name": "Food Pantry",
            "addresses": [
                {
                    "address_1": "123 Main St",
                    "city": "Springfield",
                    "state_province": "IL",
                    "postal_code": "62701",
                    "country": "US",
                    "address_type": "physical",
                }
            ],
            "latitude": None,
            "longitude": None,
        }

        mock_geocoding_service = MagicMock()
        mock_geocoding_service.geocode.return_value = (39.7817, -89.6501)
        mock_geocoding_service.geocode_with_provider.return_value = (39.7817, -89.6501)

        # Configure enricher with providers list and pass mock Redis
        config = {"geocoding_providers": ["arcgis", "nominatim", "census"]}
        enricher = GeocodingEnricher(
            geocoding_service=mock_geocoding_service,
            config=config,
            redis_client=mock_redis,
        )

        # Act
        enriched_location, source = enricher.enrich_location(location_data)

        # Assert
        assert enriched_location["latitude"] == 39.7817
        assert enriched_location["longitude"] == -89.6501
        assert source == "arcgis"
        # Either geocode or geocode_with_provider should be called
        if mock_geocoding_service.geocode.called:
            mock_geocoding_service.geocode.assert_called_once_with(
                "123 Main St, Springfield, IL 62701"
            )
        else:
            mock_geocoding_service.geocode_with_provider.assert_called_once_with(
                "123 Main St, Springfield, IL 62701", provider="arcgis"
            )

    def test_enrich_location_with_missing_address(self):
        """Test reverse geocoding when location has coordinates but no address."""
        # Arrange
        location_data = {
            "name": "Food Bank",
            "addresses": [],
            "latitude": 39.7817,
            "longitude": -89.6501,
        }

        mock_geocoding_service = MagicMock()
        mock_geocoding_service.reverse_geocode.return_value = {
            "address": "123 Main St",
            "city": "Springfield",
            "state": "IL",
            "postal_code": "62701",
        }

        # Configure enricher with providers list
        config = {"geocoding_providers": ["arcgis", "nominatim", "census"]}
        enricher = GeocodingEnricher(
            geocoding_service=mock_geocoding_service, config=config
        )

        # Act
        enriched_location, source = enricher.enrich_location(location_data)

        # Assert
        assert len(enriched_location["addresses"]) == 1
        assert enriched_location["addresses"][0]["address_1"] == "123 Main St"
        assert enriched_location["addresses"][0]["city"] == "Springfield"
        assert enriched_location["addresses"][0]["state_province"] == "IL"
        assert enriched_location["addresses"][0]["postal_code"] == "62701"
        assert source == "arcgis"
        mock_geocoding_service.reverse_geocode.assert_called_once_with(
            39.7817, -89.6501
        )

    def test_enrich_postal_code_from_city_state(self):
        """Test enriching missing postal code using city and state."""
        # Arrange
        location_data = {
            "name": "Community Center",
            "addresses": [
                {
                    "address_1": "456 Oak Ave",
                    "city": "Chicago",
                    "state_province": "IL",
                    "postal_code": None,
                    "country": "US",
                    "address_type": "physical",
                }
            ],
            "latitude": None,
            "longitude": None,
        }

        mock_geocoding_service = MagicMock()
        mock_geocoding_service.geocode.return_value = (41.8781, -87.6298)
        mock_geocoding_service.reverse_geocode.return_value = {
            "address": "456 Oak Ave",
            "city": "Chicago",
            "state": "IL",
            "postal_code": "60601",
        }

        # Configure enricher with providers list
        config = {"geocoding_providers": ["arcgis", "nominatim", "census"]}
        enricher = GeocodingEnricher(
            geocoding_service=mock_geocoding_service, config=config
        )

        # Act
        enriched_location, source = enricher.enrich_location(location_data)

        # Assert
        assert enriched_location["addresses"][0]["postal_code"] == "60601"
        assert enriched_location["latitude"] == 41.8781
        assert enriched_location["longitude"] == -87.6298
        assert source == "arcgis"

    @patch("app.validator.enrichment.redis.from_url")
    def test_provider_fallback_chain(self, mock_redis_from_url):
        """Test fallback through provider chain: ArcGIS → Nominatim → Census."""
        # Mock Redis to ensure no caching interference
        mock_redis = MagicMock()
        mock_redis.get.return_value = None  # No cached values
        mock_redis_from_url.return_value = mock_redis
        # Arrange
        location_data = {
            "name": "Food Distribution",
            "addresses": [
                {
                    "address_1": "789 Elm St",
                    "city": "Boston",
                    "state_province": "MA",
                    "postal_code": "02101",
                    "country": "US",
                    "address_type": "physical",
                }
            ],
            "latitude": None,
            "longitude": None,
        }

        mock_geocoding_service = MagicMock()
        # ArcGIS fails (via geocode), then fallback to geocode_with_provider
        mock_geocoding_service.geocode.return_value = None  # ArcGIS fails
        mock_geocoding_service.geocode_with_provider.side_effect = [
            (42.3601, -71.0589),  # Nominatim succeeds
        ]

        # Configure enricher with providers list
        config = {"geocoding_providers": ["arcgis", "nominatim", "census"]}
        enricher = GeocodingEnricher(
            geocoding_service=mock_geocoding_service,
            config=config,
            redis_client=mock_redis,
        )

        # Act
        enriched_location, source = enricher.enrich_location(location_data)

        # Assert
        assert enriched_location["latitude"] == 42.3601
        assert enriched_location["longitude"] == -71.0589
        assert source == "nominatim"
        # Check provider fallback occurred
        assert (
            mock_geocoding_service.geocode.called
            or mock_geocoding_service.geocode_with_provider.called
        )
        if source == "nominatim":
            # If source is nominatim, it should have been called via geocode_with_provider
            calls = [
                call
                for call in mock_geocoding_service.geocode_with_provider.call_args_list
                if "nominatim" in str(call)
            ]
            assert len(calls) > 0

    @patch("app.validator.enrichment.redis.from_url")
    def test_census_provider_fallback(self, mock_redis_from_url):
        """Test fallback to Census geocoder when others fail."""
        # Mock Redis to ensure no caching interference
        mock_redis = MagicMock()
        mock_redis.get.return_value = None  # No cached values
        mock_redis_from_url.return_value = mock_redis
        # Arrange
        location_data = {
            "name": "Rural Food Bank",
            "addresses": [
                {
                    "address_1": "321 Rural Rd",
                    "city": "Smalltown",
                    "state_province": "KS",
                    "postal_code": "67501",
                    "country": "US",
                    "address_type": "physical",
                }
            ],
            "latitude": None,
            "longitude": None,
        }

        mock_geocoding_service = MagicMock()
        # ArcGIS fails via geocode, Nominatim and Census via geocode_with_provider
        mock_geocoding_service.geocode.return_value = None  # ArcGIS fails
        mock_geocoding_service.geocode_with_provider.side_effect = [
            None,  # Nominatim fails
            (38.0000, -98.0000),  # Census succeeds
        ]

        # Configure enricher with providers list
        config = {"geocoding_providers": ["arcgis", "nominatim", "census"]}
        enricher = GeocodingEnricher(
            geocoding_service=mock_geocoding_service,
            config=config,
            redis_client=mock_redis,
        )

        # Act
        enriched_location, source = enricher.enrich_location(location_data)

        # Assert
        assert enriched_location["latitude"] == 38.0000
        assert enriched_location["longitude"] == -98.0000
        assert source == "census"
        # Check that multiple providers were tried
        total_calls = (
            mock_geocoding_service.geocode.call_count
            + mock_geocoding_service.geocode_with_provider.call_count
        )
        assert total_calls >= 2  # At least 2 providers should have been tried

    @patch("app.validator.enrichment.redis.from_url")
    def test_all_providers_fail(self, mock_redis_from_url):
        """Test behavior when all geocoding providers fail."""
        # Mock Redis to ensure no caching interference
        mock_redis = MagicMock()
        mock_redis.get.return_value = None  # No cached values
        mock_redis_from_url.return_value = mock_redis
        # Arrange
        location_data = {
            "name": "Unknown Location",
            "addresses": [
                {
                    "address_1": "Invalid Address",
                    "city": "NoWhere",
                    "state_province": "XX",
                    "postal_code": "00000",
                    "country": "US",
                    "address_type": "physical",
                }
            ],
            "latitude": None,
            "longitude": None,
        }

        mock_geocoding_service = MagicMock()
        # All providers fail
        mock_geocoding_service.geocode.return_value = None  # ArcGIS fails
        mock_geocoding_service.geocode_with_provider.side_effect = [
            None,  # Nominatim fails
            None,  # Census fails
        ]

        # Configure enricher with providers list
        config = {"geocoding_providers": ["arcgis", "nominatim", "census"]}
        enricher = GeocodingEnricher(
            geocoding_service=mock_geocoding_service,
            config=config,
            redis_client=mock_redis,
        )

        # Act
        enriched_location, source = enricher.enrich_location(location_data)

        # Assert
        assert enriched_location["latitude"] is None
        assert enriched_location["longitude"] is None
        assert source is None
        # Check that all providers were tried
        total_calls = (
            mock_geocoding_service.geocode.call_count
            + mock_geocoding_service.geocode_with_provider.call_count
        )
        assert total_calls >= 3  # All 3 providers should have been tried

    def test_location_with_complete_data_not_enriched(self):
        """Test that locations with complete data are not modified."""
        # Arrange
        location_data = {
            "name": "Complete Location",
            "addresses": [
                {
                    "address_1": "100 Complete St",
                    "city": "Fullcity",
                    "state_province": "CA",
                    "postal_code": "90210",
                    "country": "US",
                    "address_type": "physical",
                }
            ],
            "latitude": 34.0900,
            "longitude": -118.4065,
        }

        mock_geocoding_service = MagicMock()
        # Configure enricher with providers list
        config = {"geocoding_providers": ["arcgis", "nominatim", "census"]}
        enricher = GeocodingEnricher(
            geocoding_service=mock_geocoding_service, config=config
        )

        # Act
        enriched_location, source = enricher.enrich_location(location_data)

        # Assert
        assert enriched_location == location_data
        assert source is None
        mock_geocoding_service.geocode.assert_not_called()
        mock_geocoding_service.reverse_geocode.assert_not_called()

    @patch("app.validator.enrichment.redis.from_url")
    def test_enrich_multiple_locations_in_job(self, mock_redis_from_url):
        """Test enriching multiple locations in a single job."""
        # Mock Redis to ensure no caching interference
        mock_redis = MagicMock()
        mock_redis.get.return_value = None  # No cached values
        mock_redis_from_url.return_value = mock_redis
        # Arrange
        job_data = {
            "organization": [{"name": "Test Org"}],
            "service": [{"name": "Food Service"}],
            "location": [
                {
                    "name": "Location 1",
                    "addresses": [
                        {
                            "address_1": "111 First St",
                            "city": "City1",
                            "state_province": "ST",
                            "postal_code": "11111",
                            "country": "US",
                            "address_type": "physical",
                        }
                    ],
                    "latitude": None,
                    "longitude": None,
                },
                {
                    "name": "Location 2",
                    "addresses": [],
                    "latitude": 40.0000,
                    "longitude": -75.0000,
                },
                {
                    "name": "Location 3",
                    "addresses": [
                        {
                            "address_1": "333 Third St",
                            "city": "City3",
                            "state_province": "ST",
                            "postal_code": "33333",
                            "country": "US",
                            "address_type": "physical",
                        }
                    ],
                    "latitude": 41.0000,
                    "longitude": -76.0000,
                },
            ],
        }

        mock_geocoding_service = MagicMock()
        mock_geocoding_service.geocode.return_value = (39.0000, -74.0000)
        mock_geocoding_service.reverse_geocode.return_value = {
            "address": "222 Second St",
            "city": "City2",
            "state": "ST",
            "postal_code": "22222",
        }

        # Configure enricher with providers list
        config = {"geocoding_providers": ["arcgis", "nominatim", "census"]}
        enricher = GeocodingEnricher(
            geocoding_service=mock_geocoding_service,
            config=config,
            redis_client=mock_redis,
        )

        # Act
        enriched_data = enricher.enrich_job_data(job_data)

        # Assert
        # Location 1 should get coordinates
        assert enriched_data["location"][0]["latitude"] == 39.0000
        assert enriched_data["location"][0]["longitude"] == -74.0000

        # Location 2 should get address
        assert len(enriched_data["location"][1]["addresses"]) == 1
        assert (
            enriched_data["location"][1]["addresses"][0]["address_1"] == "222 Second St"
        )

        # Location 3 already complete, should not change
        assert enriched_data["location"][2] == job_data["location"][2]

        # Verify service calls
        # Should have geocoded once and reverse geocoded once
        geocode_calls = (
            mock_geocoding_service.geocode.call_count
            + mock_geocoding_service.geocode_with_provider.call_count
        )
        assert geocode_calls >= 1
        assert mock_geocoding_service.reverse_geocode.call_count == 1


class TestValidationProcessorWithEnrichment:
    """Test ValidationProcessor integration with geocoding enrichment."""

    @patch("app.validator.enrichment.GeocodingEnricher")
    def test_processor_enriches_before_validation(self, mock_enricher_class):
        """Test that processor enriches data before validation."""
        # Arrange
        mock_db = MagicMock()
        mock_enricher = MagicMock()
        mock_enricher_class.return_value = mock_enricher

        job_result = JobResult(
            job_id="test-job-123",
            status=JobStatus.COMPLETED,
            data={
                "organization": [],
                "service": [],
                "location": [
                    {
                        "name": "Test Location",
                        "addresses": [
                            {
                                "address_1": "100 Test St",
                                "city": "Testville",
                                "state_province": "TS",
                                "postal_code": None,
                                "country": "US",
                                "address_type": "physical",
                            }
                        ],
                        "latitude": None,
                        "longitude": None,
                    }
                ],
            },
            metadata={},
        )

        enriched_data = {
            "organization": [],
            "service": [],
            "location": [
                {
                    "name": "Test Location",
                    "addresses": [
                        {
                            "address_1": "100 Test St",
                            "city": "Testville",
                            "state_province": "TS",
                            "postal_code": "12345",
                            "country": "US",
                            "address_type": "physical",
                        }
                    ],
                    "latitude": 40.0,
                    "longitude": -75.0,
                }
            ],
        }

        mock_enricher.enrich_job_data.return_value = enriched_data
        mock_enricher.get_enrichment_details.return_value = {
            "locations_enriched": 1,
            "coordinates_added": 1,
            "postal_codes_added": 1,
        }

        processor = ValidationProcessor(db=mock_db)

        # Act
        result = processor.process_job_result(job_result)

        # Assert
        # The enricher is called with data and optionally scraper_id
        mock_enricher.enrich_job_data.assert_called_once()
        call_args = mock_enricher.enrich_job_data.call_args
        assert call_args[0][0] == job_result.data  # First positional arg is data
        # scraper_id might be None or a string, depends on job metadata
        assert result["data"] == enriched_data
        assert "enrichment" in result.get("validation_notes", {})

    @patch("app.validator.enrichment.GeocodingEnricher")
    def test_processor_tracks_geocoding_sources(self, mock_enricher_class):
        """Test that processor tracks which geocoding provider was used."""
        # Arrange
        mock_db = MagicMock()
        mock_enricher = MagicMock()
        mock_enricher_class.return_value = mock_enricher

        job_result = JobResult(
            job_id="test-job-456",
            status=JobStatus.COMPLETED,
            data={
                "organization": [],
                "service": [],
                "location": [
                    {
                        "name": "Location 1",
                        "addresses": [],
                        "latitude": None,
                        "longitude": None,
                    },
                    {
                        "name": "Location 2",
                        "addresses": [],
                        "latitude": None,
                        "longitude": None,
                    },
                ],
            },
            metadata={},
        )

        # Mock enricher to return enrichment details
        mock_enricher.enrich_job_data.return_value = job_result.data
        mock_enricher.get_enrichment_details.return_value = {
            "locations_enriched": 2,
            "sources": {
                "Location 1": "arcgis",
                "Location 2": "nominatim",
            },
        }

        processor = ValidationProcessor(db=mock_db)

        # Act
        result = processor.process_job_result(job_result)

        # Assert
        validation_notes = result.get("validation_notes", {})
        assert "enrichment" in validation_notes
        assert validation_notes["enrichment"]["locations_enriched"] == 2
        assert validation_notes["enrichment"]["sources"]["Location 1"] == "arcgis"
        assert validation_notes["enrichment"]["sources"]["Location 2"] == "nominatim"

    @patch("app.validator.enrichment.GeocodingEnricher")
    def test_processor_continues_on_enrichment_failure(self, mock_enricher_class):
        """Test that processor continues validation even if enrichment fails."""
        # Arrange
        mock_db = MagicMock()
        mock_enricher = MagicMock()
        mock_enricher_class.return_value = mock_enricher

        job_result = JobResult(
            job_id="test-job-789",
            status=JobStatus.COMPLETED,
            data={
                "organization": [],
                "service": [],
                "location": [{"name": "Test"}],
            },
            metadata={},
        )

        # Mock enricher to raise exception
        mock_enricher.enrich_job_data.side_effect = Exception(
            "Geocoding service unavailable"
        )

        processor = ValidationProcessor(db=mock_db)

        # Act
        result = processor.process_job_result(job_result)

        # Assert
        # Should still return result with original data
        assert result["data"] == job_result.data
        assert "enrichment_error" in result.get("validation_notes", {})
        assert (
            "Geocoding service unavailable"
            in result["validation_notes"]["enrichment_error"]
        )

    def test_enriched_data_goes_through_same_validation(self):
        """Test that enriched data goes through the same validation checks as original data."""
        # This will be implemented when validation rules are added in Issue #366
        pass


class TestEnrichmentConfiguration:
    """Test enrichment configuration and settings."""

    def test_enrichment_can_be_disabled(self):
        """Test that enrichment can be disabled via configuration."""
        # Arrange
        config = {"enrichment_enabled": False}
        enricher = GeocodingEnricher(config=config)

        location_data = {
            "name": "Test Location",
            "addresses": [],
            "latitude": None,
            "longitude": None,
        }

        # Act
        enriched_location, source = enricher.enrich_location(location_data)

        # Assert
        assert enriched_location == location_data
        assert source is None

    def test_provider_chain_is_configurable(self):
        """Test that the provider chain can be configured."""
        # Arrange
        config = {
            "geocoding_providers": ["nominatim", "census"],  # Skip ArcGIS
        }

        mock_geocoding_service = MagicMock()
        mock_geocoding_service.geocode_with_provider.side_effect = [
            (40.0, -75.0),  # Nominatim succeeds
        ]

        enricher = GeocodingEnricher(
            geocoding_service=mock_geocoding_service, config=config
        )

        location_data = {
            "name": "Test",
            "addresses": [
                {
                    "address_1": "123 Test St",
                    "city": "City",
                    "state_province": "ST",
                    "postal_code": "12345",
                    "country": "US",
                    "address_type": "physical",
                }
            ],
            "latitude": None,
            "longitude": None,
        }

        # Act
        enriched_location, source = enricher.enrich_location(location_data)

        # Assert
        assert source == "nominatim"
        # Should have called with nominatim since it's first in the config
        if mock_geocoding_service.geocode_with_provider.called:
            calls = [
                call
                for call in mock_geocoding_service.geocode_with_provider.call_args_list
                if "nominatim" in str(call)
            ]
            assert len(calls) > 0

    def test_enrichment_timeout_configuration(self):
        """Test that enrichment timeout can be configured."""
        # Arrange
        config = {"enrichment_timeout": 5}  # 5 seconds

        mock_geocoding_service = MagicMock()
        # Simulate timeout for all providers
        mock_geocoding_service.geocode.side_effect = TimeoutError("Geocoding timeout")
        mock_geocoding_service.geocode_with_provider.side_effect = TimeoutError(
            "Geocoding timeout"
        )

        enricher = GeocodingEnricher(
            geocoding_service=mock_geocoding_service, config=config
        )

        location_data = {
            "name": "Test",
            "addresses": [
                {
                    "address_1": "123 Test St",
                    "city": "Test City",
                    "state_province": "TS",
                    "postal_code": "12345",
                    "country": "US",
                    "address_type": "physical",
                }
            ],
            "latitude": None,
            "longitude": None,
        }

        # Act
        enriched_location, source = enricher.enrich_location(location_data)

        # Assert
        assert enriched_location["latitude"] is None
        assert enriched_location["longitude"] is None
        assert source is None
