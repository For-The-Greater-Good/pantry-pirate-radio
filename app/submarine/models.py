"""Submarine job and result models."""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SubmarineStatus(str, Enum):
    """Status values for submarine crawl results.

    Used in SubmarineResult.status, CrawlResult.status, location.submarine_last_status,
    and the adaptive cooldown logic in SubmarineDispatcher.
    """

    SUCCESS = "success"
    PARTIAL = "partial"
    NO_DATA = "no_data"
    ERROR = "error"
    BLOCKED = "blocked"


SUBMARINE_TARGET_FIELDS = frozenset({"phone", "hours", "email", "description"})
"""Canonical set of fields that submarine can extract. Used by the dispatcher,
extractor, and scanner to ensure consistency."""


class SubmarineJob(BaseModel):
    """A job to crawl a food bank website and extract missing data fields.

    Created by the SubmarineDispatcher (automatic) or Scanner (manual)
    when a location has a website URL but is missing key fields.
    """

    id: str
    location_id: str
    organization_id: str | None = None
    website_url: str
    missing_fields: list[str] = Field(
        description="Fields to extract, e.g. ['phone', 'hours', 'email', 'description']"
    )
    source_scraper_id: str = Field(
        description="Original scraper that created this location"
    )
    # Carried from DB so result builder can construct valid HSDS location dict
    location_name: str = ""
    latitude: float | None = None
    longitude: float | None = None
    attempt: int = 0
    max_attempts: int = 3
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class SubmarineResult(BaseModel):
    """Result of a Submarine crawl and extraction attempt."""

    job_id: str
    location_id: str
    status: SubmarineStatus
    extracted_fields: dict[str, Any] = Field(
        default_factory=dict,
        description="Extracted data keyed by field name, e.g. {'phone': '555-1234'}",
    )
    crawl_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="URL crawled, pages visited, content hash, etc.",
    )
    error: str | None = None
