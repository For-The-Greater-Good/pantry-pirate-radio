"""Tests for reconciler metrics module."""

from unittest.mock import patch, MagicMock
import pytest
from prometheus_client import REGISTRY, Counter

from app.reconciler.metrics import (
    RECONCILER_JOBS,
    LOCATION_MATCHES,
    RECORD_VERSIONS,
    SERVICE_RECORDS,
    SERVICE_LOCATION_LINKS,
    register_metrics,
)


class TestReconcilerMetrics:
    """Tests for reconciler metrics definitions."""

    def test_reconciler_jobs_metric(self):
        """Test RECONCILER_JOBS metric definition."""
        assert isinstance(RECONCILER_JOBS, Counter)
        # Test that the metric can be used with expected labels
        labeled_metric = RECONCILER_JOBS.labels(scraper_id="test", status="success")
        assert labeled_metric is not None

    def test_location_matches_metric(self):
        """Test LOCATION_MATCHES metric definition."""
        assert isinstance(LOCATION_MATCHES, Counter)
        labeled_metric = LOCATION_MATCHES.labels(match_type="exact")
        assert labeled_metric is not None

    def test_record_versions_metric(self):
        """Test RECORD_VERSIONS metric definition."""
        assert isinstance(RECORD_VERSIONS, Counter)
        labeled_metric = RECORD_VERSIONS.labels(record_type="organization")
        assert labeled_metric is not None

    def test_service_records_metric(self):
        """Test SERVICE_RECORDS metric definition."""
        assert isinstance(SERVICE_RECORDS, Counter)
        labeled_metric = SERVICE_RECORDS.labels(has_organization="true")
        assert labeled_metric is not None

    def test_service_location_links_metric(self):
        """Test SERVICE_LOCATION_LINKS metric definition."""
        assert isinstance(SERVICE_LOCATION_LINKS, Counter)
        labeled_metric = SERVICE_LOCATION_LINKS.labels(location_match_type="exact")
        assert labeled_metric is not None

    def test_metrics_functionality(self):
        """Test that metrics can be incremented and read."""
        # Get initial values
        initial_jobs = RECONCILER_JOBS.labels(
            scraper_id="test", status="success"
        )._value._value
        initial_matches = LOCATION_MATCHES.labels(match_type="exact")._value._value
        initial_versions = RECORD_VERSIONS.labels(
            record_type="organization"
        )._value._value
        initial_services = SERVICE_RECORDS.labels(has_organization="true")._value._value
        initial_links = SERVICE_LOCATION_LINKS.labels(
            location_match_type="exact"
        )._value._value

        # Increment metrics
        RECONCILER_JOBS.labels(scraper_id="test", status="success").inc()
        LOCATION_MATCHES.labels(match_type="exact").inc()
        RECORD_VERSIONS.labels(record_type="organization").inc()
        SERVICE_RECORDS.labels(has_organization="true").inc()
        SERVICE_LOCATION_LINKS.labels(location_match_type="exact").inc()

        # Verify increments
        assert (
            RECONCILER_JOBS.labels(scraper_id="test", status="success")._value._value
            == initial_jobs + 1
        )
        assert (
            LOCATION_MATCHES.labels(match_type="exact")._value._value
            == initial_matches + 1
        )
        assert (
            RECORD_VERSIONS.labels(record_type="organization")._value._value
            == initial_versions + 1
        )
        assert (
            SERVICE_RECORDS.labels(has_organization="true")._value._value
            == initial_services + 1
        )
        assert (
            SERVICE_LOCATION_LINKS.labels(location_match_type="exact")._value._value
            == initial_links + 1
        )

    def test_metrics_with_different_labels(self):
        """Test metrics with different label values."""
        # Test RECONCILER_JOBS with different labels
        RECONCILER_JOBS.labels(scraper_id="scraper1", status="success").inc()
        RECONCILER_JOBS.labels(scraper_id="scraper1", status="failure").inc()
        RECONCILER_JOBS.labels(scraper_id="scraper2", status="success").inc()

        # Test LOCATION_MATCHES with different match types
        LOCATION_MATCHES.labels(match_type="exact").inc()
        LOCATION_MATCHES.labels(match_type="nearby").inc()
        LOCATION_MATCHES.labels(match_type="none").inc()

        # Test RECORD_VERSIONS with different record types
        RECORD_VERSIONS.labels(record_type="organization").inc()
        RECORD_VERSIONS.labels(record_type="service").inc()
        RECORD_VERSIONS.labels(record_type="location").inc()
        RECORD_VERSIONS.labels(record_type="service_at_location").inc()

        # Test SERVICE_RECORDS with different organization flags
        SERVICE_RECORDS.labels(has_organization="true").inc()
        SERVICE_RECORDS.labels(has_organization="false").inc()

        # Test SERVICE_LOCATION_LINKS with different match types
        SERVICE_LOCATION_LINKS.labels(location_match_type="exact").inc()
        SERVICE_LOCATION_LINKS.labels(location_match_type="none").inc()

        # All increments should work without errors
        # Values should be independent for different label combinations
        assert True  # If we get here, all increments worked


class TestRegisterMetrics:
    """Tests for register_metrics function."""

    @patch("app.reconciler.metrics.REGISTRY")
    def test_register_metrics_success(self, mock_registry):
        """Test successful metric registration."""
        mock_registry.register = MagicMock()

        register_metrics()

        # Verify all metrics were registered
        assert mock_registry.register.call_count == 5

        # Verify the correct metrics were registered
        registered_metrics = [
            call[0][0] for call in mock_registry.register.call_args_list
        ]
        assert RECONCILER_JOBS in registered_metrics
        assert LOCATION_MATCHES in registered_metrics
        assert RECORD_VERSIONS in registered_metrics
        assert SERVICE_RECORDS in registered_metrics
        assert SERVICE_LOCATION_LINKS in registered_metrics

    @patch("app.reconciler.metrics.REGISTRY")
    def test_register_metrics_already_registered(self, mock_registry):
        """Test metric registration when metrics are already registered."""
        # Mock registry to raise ValueError (already registered)
        mock_registry.register.side_effect = ValueError("Metric already registered")

        # Should not raise an exception
        register_metrics()

        # Verify register was called for each metric
        assert mock_registry.register.call_count == 5

    @patch("app.reconciler.metrics.REGISTRY")
    def test_register_metrics_mixed_scenario(self, mock_registry):
        """Test metric registration with some already registered."""

        def register_side_effect(metric):
            if metric == RECONCILER_JOBS:
                raise ValueError("Already registered")
            # Others register successfully
            return None

        mock_registry.register.side_effect = register_side_effect

        # Should not raise an exception
        register_metrics()

        # Verify register was called for each metric
        assert mock_registry.register.call_count == 5

    def test_metrics_module_imports_register_automatically(self):
        """Test that metrics are registered on module import."""
        # This test verifies that register_metrics() is called during module import
        # Since the module is already imported, we can test that the metrics exist
        # and are properly configured

        # All metrics should be defined and accessible
        assert RECONCILER_JOBS is not None
        assert LOCATION_MATCHES is not None
        assert RECORD_VERSIONS is not None
        assert SERVICE_RECORDS is not None
        assert SERVICE_LOCATION_LINKS is not None

        # Metrics should be Counter instances
        assert isinstance(RECONCILER_JOBS, Counter)
        assert isinstance(LOCATION_MATCHES, Counter)
        assert isinstance(RECORD_VERSIONS, Counter)
        assert isinstance(SERVICE_RECORDS, Counter)
        assert isinstance(SERVICE_LOCATION_LINKS, Counter)

    def test_metric_names_unique(self):
        """Test that all metrics have unique names."""
        metric_names = [
            RECONCILER_JOBS._name,
            LOCATION_MATCHES._name,
            RECORD_VERSIONS._name,
            SERVICE_RECORDS._name,
            SERVICE_LOCATION_LINKS._name,
        ]

        # All names should be unique
        assert len(metric_names) == len(set(metric_names))

    def test_metric_label_configurations(self):
        """Test that metrics have the expected label configurations."""
        # Test expected label combinations work
        test_cases = [
            (RECONCILER_JOBS, {"scraper_id": "test", "status": "success"}),
            (LOCATION_MATCHES, {"match_type": "exact"}),
            (RECORD_VERSIONS, {"record_type": "organization"}),
            (SERVICE_RECORDS, {"has_organization": "true"}),
            (SERVICE_LOCATION_LINKS, {"location_match_type": "exact"}),
        ]

        for metric, labels in test_cases:
            # Should not raise an exception
            labeled_metric = metric.labels(**labels)
            assert labeled_metric is not None
