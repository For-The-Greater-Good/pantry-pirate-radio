"""Tests for reconciler metrics."""

import pytest
from prometheus_client import CollectorRegistry

from app.reconciler.metrics import (
    LOCATION_MATCHES,
    RECONCILER_JOBS,
    RECORD_VERSIONS,
    SERVICE_LOCATION_LINKS,
    SERVICE_RECORDS,
)


@pytest.fixture
def registry():
    """Create a new registry for each test."""
    return CollectorRegistry()


def test_metrics_registration(registry):
    """Test metrics are registered correctly."""
    # Register metrics with test registry
    for metric in [
        LOCATION_MATCHES,
        RECONCILER_JOBS,
        RECORD_VERSIONS,
        SERVICE_RECORDS,
        SERVICE_LOCATION_LINKS,
    ]:
        registry.register(metric)

    # Verify metrics are collected
    collected = list(registry.collect())
    assert len(collected) == 5


def test_location_match_metrics(registry):
    """Test location match metrics."""
    registry.register(LOCATION_MATCHES)

    # Reset metrics before test
    LOCATION_MATCHES._metrics.clear()

    LOCATION_MATCHES.labels(match_type="exact").inc()
    LOCATION_MATCHES.labels(match_type="none").inc()
    LOCATION_MATCHES.labels(match_type="none").inc()

    sample_pairs = {
        sample.labels["match_type"]: sample.value
        for metric in registry.collect()
        for sample in metric.samples
        if sample.name == "reconciler_location_matches_total"
    }

    assert sample_pairs["exact"] == 1
    assert sample_pairs["none"] == 2


def test_service_metrics(registry):
    """Test service metrics."""
    registry.register(SERVICE_RECORDS)

    # Reset metrics before test
    SERVICE_RECORDS._metrics.clear()

    # Test metrics
    SERVICE_RECORDS.labels(has_organization="true").inc()
    SERVICE_RECORDS.labels(has_organization="false").inc()
    SERVICE_RECORDS.labels(has_organization="true").inc()

    sample_pairs = {
        sample.labels["has_organization"]: sample.value
        for metric in registry.collect()
        for sample in metric.samples
        if sample.name == "reconciler_service_records_total"
    }

    assert sample_pairs["true"] == 2
    assert sample_pairs["false"] == 1


def test_service_location_link_metrics(registry):
    """Test service-location link metrics."""
    registry.register(SERVICE_LOCATION_LINKS)

    # Reset metrics before test
    SERVICE_LOCATION_LINKS._metrics.clear()

    # Test metrics
    SERVICE_LOCATION_LINKS.labels(location_match_type="exact").inc()
    SERVICE_LOCATION_LINKS.labels(location_match_type="exact").inc()

    sample_pairs = {
        sample.labels["location_match_type"]: sample.value
        for metric in registry.collect()
        for sample in metric.samples
        if sample.name == "reconciler_service_location_links_total"
    }

    assert sample_pairs["exact"] == 2


def test_record_version_metrics(registry):
    """Test record version metrics."""
    registry.register(RECORD_VERSIONS)

    # Reset metrics before test
    RECORD_VERSIONS._metrics.clear()

    RECORD_VERSIONS.labels(record_type="organization").inc()
    RECORD_VERSIONS.labels(record_type="location").inc()
    RECORD_VERSIONS.labels(record_type="service").inc()
    RECORD_VERSIONS.labels(record_type="service_at_location").inc()

    sample_pairs = {
        sample.labels["record_type"]: sample.value
        for metric in registry.collect()
        for sample in metric.samples
        if sample.name == "reconciler_record_versions_total"
    }

    assert sample_pairs["organization"] == 1
    assert sample_pairs["location"] == 1
    assert sample_pairs["service"] == 1
    assert sample_pairs["service_at_location"] == 1


def test_job_metrics(registry):
    """Test job processing metrics."""
    registry.register(RECONCILER_JOBS)

    RECONCILER_JOBS.labels(scraper_id="test", status="success").inc()
    RECONCILER_JOBS.labels(scraper_id="test", status="failure").inc()
    RECONCILER_JOBS.labels(scraper_id="test", status="success").inc()

    samples = [
        (sample.labels["scraper_id"], sample.labels["status"], sample.value)
        for metric in registry.collect()
        for sample in metric.samples
        if sample.name == "reconciler_jobs_total"
    ]

    success_value = next(
        value for sid, status, value in samples if sid == "test" and status == "success"
    )
    failure_value = next(
        value for sid, status, value in samples if sid == "test" and status == "failure"
    )

    assert success_value == 2
    assert failure_value == 1
