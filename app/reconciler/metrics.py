"""Prometheus metrics for reconciler service."""

from prometheus_client import REGISTRY, Counter

# Job processing metrics
RECONCILER_JOBS = Counter(
    "reconciler_jobs_total",
    "Total number of jobs processed by reconciler",
    ["scraper_id", "status"],
)

# Location matching metrics
LOCATION_MATCHES = Counter(
    "reconciler_location_matches_total",
    "Total number of location matches found",
    ["match_type"],  # exact, nearby, none
)

# Version tracking metrics
RECORD_VERSIONS = Counter(
    "reconciler_record_versions_total",
    "Total number of record versions created",
    ["record_type"],  # organization, service, location, service_at_location
)

# Service metrics
SERVICE_RECORDS = Counter(
    "reconciler_service_records_total",
    "Total number of service records created",
    ["has_organization"],  # true, false
)

SERVICE_LOCATION_LINKS = Counter(
    "reconciler_service_location_links_total",
    "Total number of service-to-location links created",
    ["location_match_type"],  # exact, none
)


def register_metrics() -> None:
    """Register metrics with Prometheus."""
    metrics = [
        RECONCILER_JOBS,
        LOCATION_MATCHES,
        RECORD_VERSIONS,
        SERVICE_RECORDS,
        SERVICE_LOCATION_LINKS,
    ]
    for metric in metrics:
        try:
            REGISTRY.register(metric)
        except ValueError:
            # Metric already registered
            pass


# Register metrics on module import
register_metrics()
