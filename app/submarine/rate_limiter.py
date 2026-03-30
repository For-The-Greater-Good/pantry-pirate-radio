"""Per-domain rate limiter for submarine web crawling.

Enforces minimum delays between requests to the same domain to avoid
overwhelming food bank websites (typically small-org shared hosting).
"""

import asyncio
import time
from urllib.parse import urlparse


class SubmarineRateLimiter:
    """Per-domain request throttling for polite web crawling.

    Tracks the last request timestamp per domain and enforces a minimum
    delay between consecutive requests to the same domain.
    """

    user_agent: str = (
        "PantryPirateRadio/1.0 "
        "(+https://github.com/For-The-Greater-Good/pantry-pirate-radio; "
        "food-bank-data-aggregator)"
    )

    def __init__(self, min_delay_seconds: float = 5.0):
        self.min_delay_seconds = min_delay_seconds
        self._domain_timestamps: dict[str, float] = {}

    def get_delay(self, url: str) -> float:
        """Get the delay needed before requesting this URL.

        Returns:
            Seconds to wait (0 if no delay needed).
        """
        domain = self._extract_domain(url)
        last_request = self._domain_timestamps.get(domain)
        if last_request is None:
            return 0
        elapsed = time.monotonic() - last_request
        remaining = self.min_delay_seconds - elapsed
        return max(0, remaining)

    def record_request(self, url: str) -> None:
        """Record that a request was made to this URL's domain."""
        domain = self._extract_domain(url)
        self._domain_timestamps[domain] = time.monotonic()

    async def wait_and_record(self, url: str) -> None:
        """Wait for the rate limit then record the request.

        Convenience method that combines get_delay + sleep + record.
        """
        delay = self.get_delay(url)
        if delay > 0:
            await asyncio.sleep(delay)
        self.record_request(url)

    @staticmethod
    def _extract_domain(url: str) -> str:
        """Extract the domain (netloc) from a URL."""
        parsed = urlparse(url)
        return parsed.netloc
