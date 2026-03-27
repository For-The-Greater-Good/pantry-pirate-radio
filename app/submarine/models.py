"""Submarine job and result models."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


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
    status: str = Field(
        description="Outcome: 'success', 'partial', 'no_data', 'error', 'blocked'"
    )
    extracted_fields: dict[str, Any] = Field(
        default_factory=dict,
        description="Extracted data keyed by field name, e.g. {'phone': '555-1234'}",
    )
    crawl_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="URL crawled, pages visited, content hash, etc.",
    )
    error: str | None = None
