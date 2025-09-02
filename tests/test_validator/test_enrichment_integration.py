"""Integration tests for geocoding enrichment in the validation pipeline."""

import pytest
from unittest.mock import MagicMock, patch, call
from decimal import Decimal

from app.llm.queue.models import JobResult, JobStatus
from app.validator.enrichment import GeocodingEnricher
from app.validator.job_processor import ValidationProcessor, process_validation_job


class TestEnrichmentIntegration:
    """Test full integration of enrichment in the validation pipeline."""

    @patch("app.validator.job_processor.enqueue_to_reconciler")
    @patch("app.validator.job_processor.get_db_session")
    @patch("app.validator.enrichment.GeocodingService")
    def test_full_pipeline_with_enrichment(
        self, mock_geocoding_class, mock_get_db, mock_enqueue
    ):
        """Test complete flow: LLM → Validator (with enrichment) → Reconciler."""
        # Arrange
        mock_db = MagicMock()
        mock_get_db.return_value.__enter__.return_value = mock_db
        mock_get_db.return_value.__exit__.return_value = None

        mock_geocoding = MagicMock()
        mock_geocoding_class.return_value = mock_geocoding
        mock_geocoding.geocode.return_value = (40.7128, -74.0060)

        mock_enqueue.return_value = "reconciler-job-123"

        job_result = JobResult(
            job_id="llm-job-456",
            status=JobStatus.COMPLETED,
            data={
                "organization": [
                    {
                        "name": "NYC Food Bank",
                        "description": "Food distribution center",
                    }
                ],
                "service": [
                    {
                        "name": "Food Pantry",
                        "description": "Weekly food distribution",
                    }
                ],
                "location": [
                    {
                        "name": "Main Distribution Center",
                        "location_type": "physical",
                        "addresses": [
                            {
                                "address_1": "123 Broadway",
                                "city": "New York",
                                "state_province": "NY",
                                "postal_code": "10001",
                                "country": "US",
                                "address_type": "physical",
                            }
                        ],
                        "latitude": None,  # Missing coordinates
                        "longitude": None,
                        "phones": [],
                        "schedules": [],
                        "languages": [],
                        "accessibility": [],
                        "contacts": [],
                        "metadata": [],
                    }
                ],
            },
            metadata={"source": "nyc_efap_programs"},
        )

        # Act
        result = process_validation_job(job_result)

        # Assert
        # Check that enrichment occurred
        assert result["data"]["location"][0]["latitude"] == 40.7128
        assert result["data"]["location"][0]["longitude"] == -74.0060

        # Check that reconciler was called with enriched data
        mock_enqueue.assert_called_once()
        enqueued_job = mock_enqueue.call_args[0][0]
        assert enqueued_job.data["location"][0]["latitude"] == 40.7128
        assert enqueued_job.data["location"][0]["longitude"] == -74.0060

        # Check validation notes
        assert "validation_notes" in result
        # Note: validation_notes structure will be defined in implementation

    @patch("app.validator.job_processor.enqueue_to_reconciler")
    @patch("app.validator.job_processor.get_db_session")
    @patch("app.validator.enrichment.GeocodingService")
    def test_multiple_location_scenarios(
        self, mock_geocoding_class, mock_get_db, mock_enqueue
    ):
        """Test enrichment with various data scenarios."""
        # Arrange
        mock_db = MagicMock()
        mock_get_db.return_value.__enter__.return_value = mock_db
        mock_get_db.return_value.__exit__.return_value = None

        mock_geocoding = MagicMock()
        mock_geocoding_class.return_value = mock_geocoding

        # Setup different responses for different scenarios
        mock_geocoding.geocode.return_value = (40.7128, -74.0060)
        mock_geocoding.reverse_geocode.return_value = {
            "address": "456 Park Ave",
            "city": "New York",
            "state": "NY",
            "postal_code": "10016",
        }

        job_result = JobResult(
            job_id="test-multi-123",
            status=JobStatus.COMPLETED,
            data={
                "organization": [],
                "service": [],
                "location": [
                    # Scenario 1: Missing coordinates
                    {
                        "name": "Location 1",
                        "location_type": "physical",
                        "addresses": [
                            {
                                "address_1": "789 First Ave",
                                "city": "Brooklyn",
                                "state_province": "NY",
                                "postal_code": "11201",
                                "country": "US",
                                "address_type": "physical",
                            }
                        ],
                        "latitude": None,
                        "longitude": None,
                        "phones": [],
                        "schedules": [],
                        "languages": [],
                        "accessibility": [],
                        "contacts": [],
                        "metadata": [],
                    },
                    # Scenario 2: Missing address
                    {
                        "name": "Location 2",
                        "location_type": "physical",
                        "addresses": [],
                        "latitude": 40.7580,
                        "longitude": -73.9855,
                        "phones": [],
                        "schedules": [],
                        "languages": [],
                        "accessibility": [],
                        "contacts": [],
                        "metadata": [],
                    },
                    # Scenario 3: Complete data (no enrichment needed)
                    {
                        "name": "Location 3",
                        "location_type": "physical",
                        "addresses": [
                            {
                                "address_1": "100 Complete St",
                                "city": "Queens",
                                "state_province": "NY",
                                "postal_code": "11101",
                                "country": "US",
                                "address_type": "physical",
                            }
                        ],
                        "latitude": 40.7282,
                        "longitude": -73.9348,
                        "phones": [],
                        "schedules": [],
                        "languages": [],
                        "accessibility": [],
                        "contacts": [],
                        "metadata": [],
                    },
                    # Scenario 4: Neither coords nor address (cannot enrich)
                    {
                        "name": "Location 4",
                        "location_type": "virtual",
                        "addresses": [],
                        "latitude": None,
                        "longitude": None,
                        "phones": [],
                        "schedules": [],
                        "languages": [],
                        "accessibility": [],
                        "contacts": [],
                        "metadata": [],
                    },
                ],
            },
            metadata={},
        )

        # Act
        result = process_validation_job(job_result)

        # Assert
        locations = result["data"]["location"]

        # Location 1: Should have coordinates added
        assert locations[0]["latitude"] is not None
        assert locations[0]["longitude"] is not None

        # Location 2: Should have address added
        assert len(locations[1]["addresses"]) == 1
        assert locations[1]["addresses"][0]["address_1"] == "456 Park Ave"
        assert locations[1]["addresses"][0]["postal_code"] == "10016"

        # Location 3: Should remain unchanged
        assert locations[2]["latitude"] == 40.7282
        assert locations[2]["longitude"] == -73.9348

        # Location 4: Should remain unchanged (cannot enrich)
        # Virtual locations might not be enriched
        assert locations[3]["latitude"] is None
        assert locations[3]["longitude"] is None
        assert len(locations[3]["addresses"]) == 0

    @patch("app.validator.job_processor.enqueue_to_reconciler")
    @patch("app.validator.job_processor.get_db_session")
    @patch("app.validator.enrichment.GeocodingService")
    @patch("app.validator.enrichment.redis.from_url")
    def test_provider_fallback_in_pipeline(
        self, mock_redis_from_url, mock_geocoding_class, mock_get_db, mock_enqueue
    ):
        """Test provider fallback chain in real pipeline."""
        # Arrange
        mock_db = MagicMock()
        mock_get_db.return_value.__enter__.return_value = mock_db
        mock_get_db.return_value.__exit__.return_value = None

        # Setup Redis mock to avoid circuit breaker interference
        mock_redis = MagicMock()
        mock_redis.get.return_value = None  # No cached values or circuit breaker state
        mock_redis.ping.return_value = True
        mock_redis_from_url.return_value = mock_redis

        mock_geocoding = MagicMock()
        mock_geocoding_class.return_value = mock_geocoding

        # Simulate ArcGIS failure, Nominatim success
        # ArcGIS via geocode fails
        mock_geocoding.geocode.side_effect = Exception("ArcGIS service unavailable")

        # Nominatim via geocode_with_provider succeeds
        def geocode_with_provider_side_effect(address, provider):
            if provider == "nominatim":
                return (40.7128, -74.0060)
            return None

        mock_geocoding.geocode_with_provider.side_effect = (
            geocode_with_provider_side_effect
        )

        job_result = JobResult(
            job_id="test-fallback-123",
            status=JobStatus.COMPLETED,
            data={
                "organization": [],
                "service": [],
                "location": [
                    {
                        "name": "Test Location",
                        "location_type": "physical",
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
                        "phones": [],
                        "schedules": [],
                        "languages": [],
                        "accessibility": [],
                        "contacts": [],
                        "metadata": [],
                    }
                ],
            },
            metadata={},
        )

        # Act
        result = process_validation_job(job_result)

        # Assert
        # Should eventually succeed with Nominatim
        assert result["data"]["location"][0]["latitude"] == 40.7128
        assert result["data"]["location"][0]["longitude"] == -74.0060

        # Check that fallback was attempted
        # Verify that geocoding was attempted - could be geocode or geocode_with_provider
        assert (
            mock_geocoding.geocode.called or mock_geocoding.geocode_with_provider.called
        ), "Geocoding should have been attempted"

    @pytest.mark.skip(
        reason="Database tracking not implemented in current enrichment design"
    )
    @patch("app.validator.job_processor.enqueue_to_reconciler")
    @patch("app.validator.job_processor.get_db_session")
    def test_enrichment_with_database_tracking(self, mock_get_db, mock_enqueue):
        """Test that enrichment updates database fields correctly."""
        # Arrange
        mock_db = MagicMock()
        mock_get_db.return_value.__enter__.return_value = mock_db
        mock_get_db.return_value.__exit__.return_value = None

        # Mock location model
        mock_location = MagicMock()
        mock_location.id = "loc-123"
        mock_location.geocoding_source = None
        mock_location.validation_notes = {}

        mock_db.query.return_value.filter_by.return_value.first.return_value = (
            mock_location
        )

        job_result = JobResult(
            job_id="test-db-tracking",
            status=JobStatus.COMPLETED,
            data={
                "organization": [],
                "service": [],
                "location": [
                    {
                        "id": "loc-123",
                        "name": "Test Location",
                        "location_type": "physical",
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
                        "phones": [],
                        "schedules": [],
                        "languages": [],
                        "accessibility": [],
                        "contacts": [],
                        "metadata": [],
                    }
                ],
            },
            metadata={},
        )

        # Act
        with patch("app.validator.enrichment.GeocodingService") as mock_geocoding_class:
            mock_geocoding = MagicMock()
            mock_geocoding_class.return_value = mock_geocoding
            mock_geocoding.geocode.return_value = (40.7128, -74.0060)

            result = process_validation_job(job_result)

        # Assert
        # Check that database fields were updated
        assert mock_location.geocoding_source == "arcgis"
        assert "enrichment" in mock_location.validation_notes
        mock_db.commit.assert_called()

    @patch("app.validator.job_processor.enqueue_to_reconciler")
    @patch("app.validator.job_processor.get_db_session")
    @patch("app.validator.enrichment.GeocodingService")
    @patch("app.validator.enrichment.redis.from_url")
    def test_enrichment_performance_with_caching(
        self, mock_redis_from_url, mock_geocoding_class, mock_get_db, mock_enqueue
    ):
        """Test that enrichment uses caching for repeated addresses."""
        # Arrange
        mock_db = MagicMock()
        mock_get_db.return_value.__enter__.return_value = mock_db
        mock_get_db.return_value.__exit__.return_value = None

        # Setup Redis mock for caching behavior
        mock_redis = MagicMock()
        cache_calls = {}

        def redis_get_side_effect(key):
            return cache_calls.get(key)

        def redis_setex_side_effect(key, ttl, value):
            # Store with TTL (ttl parameter is required for setex signature)
            _ = ttl  # Mark as intentionally unused - required for method signature
            cache_calls[key] = value

        mock_redis.get.side_effect = redis_get_side_effect
        mock_redis.setex.side_effect = redis_setex_side_effect
        mock_redis.ping.return_value = True
        mock_redis_from_url.return_value = mock_redis

        mock_geocoding = MagicMock()
        mock_geocoding_class.return_value = mock_geocoding
        mock_geocoding.geocode.return_value = (40.7128, -74.0060)

        # Job with duplicate addresses
        job_result = JobResult(
            job_id="test-caching",
            status=JobStatus.COMPLETED,
            data={
                "organization": [],
                "service": [],
                "location": [
                    {
                        "name": "Location A",
                        "location_type": "physical",
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
                        "phones": [],
                        "schedules": [],
                        "languages": [],
                        "accessibility": [],
                        "contacts": [],
                        "metadata": [],
                    },
                    {
                        "name": "Location B",
                        "location_type": "physical",
                        "addresses": [
                            {
                                "address_1": "123 Main St",  # Same address
                                "city": "Springfield",
                                "state_province": "IL",
                                "postal_code": "62701",
                                "country": "US",
                                "address_type": "physical",
                            }
                        ],
                        "latitude": None,
                        "longitude": None,
                        "phones": [],
                        "schedules": [],
                        "languages": [],
                        "accessibility": [],
                        "contacts": [],
                        "metadata": [],
                    },
                ],
            },
            metadata={},
        )

        # Act
        result = process_validation_job(job_result)

        # Assert
        # Both locations should have same coordinates
        assert result["data"]["location"][0]["latitude"] == 40.7128
        assert result["data"]["location"][0]["longitude"] == -74.0060
        assert result["data"]["location"][1]["latitude"] == 40.7128
        assert result["data"]["location"][1]["longitude"] == -74.0060

        # But geocoding should only be called once (caching)
        mock_geocoding.geocode.assert_called_once()

    @patch("app.validator.job_processor.enqueue_to_reconciler")
    @patch("app.validator.job_processor.get_db_session")
    @patch("app.validator.enrichment.GeocodingService")
    def test_enrichment_respects_configuration(
        self, mock_geocoding_class, mock_get_db, mock_enqueue
    ):
        """Test that enrichment can be disabled via configuration."""
        # Arrange
        mock_db = MagicMock()
        mock_get_db.return_value.__enter__.return_value = mock_db
        mock_get_db.return_value.__exit__.return_value = None

        # Disable enrichment via environment
        with patch(
            "app.validator.job_processor.getattr",
            side_effect=lambda obj, attr, default=None: (
                False
                if attr == "VALIDATOR_ENRICHMENT_ENABLED"
                else getattr(obj, attr, default)
            ),
        ):
            job_result = JobResult(
                job_id="test-disabled",
                status=JobStatus.COMPLETED,
                data={
                    "organization": [],
                    "service": [],
                    "location": [
                        {
                            "name": "Test Location",
                            "location_type": "physical",
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
                            "latitude": None,  # Should remain None
                            "longitude": None,
                            "phones": [],
                            "schedules": [],
                            "languages": [],
                            "accessibility": [],
                            "contacts": [],
                            "metadata": [],
                        }
                    ],
                },
                metadata={},
            )

            # Act
            result = process_validation_job(job_result)

            # Assert
            # Coordinates should remain None (no enrichment)
            assert result["data"]["location"][0]["latitude"] is None
            assert result["data"]["location"][0]["longitude"] is None

            # Geocoding should not be called
            mock_geocoding_class.assert_not_called()

    @patch("app.validator.job_processor.enqueue_to_reconciler")
    @patch("app.validator.job_processor.get_db_session")
    @patch("app.validator.enrichment.redis.from_url")  # Mock Redis
    @patch("app.validator.enrichment.GeocodingService")
    def test_enrichment_handles_partial_failures(
        self, mock_geocoding_class, mock_redis_from_url, mock_get_db, mock_enqueue
    ):
        """Test that partial enrichment failures don't break the pipeline."""
        # Mock Redis to avoid caching
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_redis_from_url.return_value = mock_redis

        # Arrange
        mock_db = MagicMock()
        mock_get_db.return_value.__enter__.return_value = mock_db
        mock_get_db.return_value.__exit__.return_value = None

        mock_geocoding = MagicMock()
        mock_geocoding_class.return_value = mock_geocoding

        def geocode_side_effect(address):
            # Check the address to determine which location we're geocoding
            if "123 First St" in address or "City1" in address:
                # First location succeeds
                return (40.7128, -74.0060)
            elif "456 Second St" in address or "City2" in address:
                # Second location fails
                raise Exception("Service unavailable")
            elif "789 Third St" in address or "City3" in address:
                # Third location succeeds
                return (41.8781, -87.6298)
            else:
                return None

        mock_geocoding.geocode.side_effect = geocode_side_effect

        # Also mock geocode_with_provider to fail for second location
        def geocode_with_provider_side_effect(address, provider):
            # Check if this is the second location's address
            if "456 Second St" in address or "City2" in address:
                # All providers fail for location 2
                raise Exception("Service unavailable")
            elif "123 First St" in address or "City1" in address:
                # If the main geocode doesn't work, fallback providers might work
                return None  # Let main geocode handle it
            elif "789 Third St" in address or "City3" in address:
                # If the main geocode doesn't work, fallback providers might work
                return None  # Let main geocode handle it
            else:
                return None

        mock_geocoding.geocode_with_provider.side_effect = (
            geocode_with_provider_side_effect
        )

        job_result = JobResult(
            job_id="test-partial-failure",
            status=JobStatus.COMPLETED,
            data={
                "organization": [],
                "service": [],
                "location": [
                    {
                        "name": "Location 1",
                        "location_type": "physical",
                        "addresses": [
                            {
                                "address_1": "123 First St",
                                "city": "City1",
                                "state_province": "ST",
                                "postal_code": "11111",
                                "country": "US",
                                "address_type": "physical",
                            }
                        ],
                        "latitude": None,
                        "longitude": None,
                        "phones": [],
                        "schedules": [],
                        "languages": [],
                        "accessibility": [],
                        "contacts": [],
                        "metadata": [],
                    },
                    {
                        "name": "Location 2",
                        "location_type": "physical",
                        "addresses": [
                            {
                                "address_1": "456 Second St",
                                "city": "City2",
                                "state_province": "ST",
                                "postal_code": "22222",
                                "country": "US",
                                "address_type": "physical",
                            }
                        ],
                        "latitude": None,
                        "longitude": None,
                        "phones": [],
                        "schedules": [],
                        "languages": [],
                        "accessibility": [],
                        "contacts": [],
                        "metadata": [],
                    },
                    {
                        "name": "Location 3",
                        "location_type": "physical",
                        "addresses": [
                            {
                                "address_1": "789 Third St",
                                "city": "City3",
                                "state_province": "ST",
                                "postal_code": "33333",
                                "country": "US",
                                "address_type": "physical",
                            }
                        ],
                        "latitude": None,
                        "longitude": None,
                        "phones": [],
                        "schedules": [],
                        "languages": [],
                        "accessibility": [],
                        "contacts": [],
                        "metadata": [],
                    },
                ],
            },
            metadata={},
        )

        # Act
        result = process_validation_job(job_result)

        # Assert
        locations = result["data"]["location"]

        # First location should be enriched
        assert locations[0]["latitude"] == 40.7128
        assert locations[0]["longitude"] == -74.0060

        # Second location should remain unchanged (failed)
        assert locations[1]["latitude"] is None
        assert locations[1]["longitude"] is None

        # Third location should be enriched
        assert locations[2]["latitude"] == 41.8781
        assert locations[2]["longitude"] == -87.6298

        # Pipeline should complete successfully
        mock_enqueue.assert_called_once()
