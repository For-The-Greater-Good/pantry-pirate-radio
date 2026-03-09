"""Prometheus metric definitions.

Extracted from events.py to allow middleware/metrics.py to import counters
without pulling in Redis, RQ, and LLM dependencies transitively.
"""

from prometheus_client import Counter

REQUESTS_TOTAL = Counter(
    "app_http_requests_total",
    "Total number of HTTP requests",
    labelnames=["method", "path"],
)

RESPONSES_TOTAL = Counter(
    "app_http_responses_total",
    "Total number of HTTP responses",
    labelnames=["status_code"],
)
