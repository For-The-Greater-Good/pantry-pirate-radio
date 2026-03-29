"""Submarine staging model for batch inference pipeline.

Represents a crawled website ready for LLM extraction. Enqueued to the
submarine-staging SQS queue after a successful crawl + relevance gate.
The batcher Lambda drains these messages and submits Bedrock batch jobs.
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class SubmarineStagingMessage(BaseModel):
    """Message enqueued to submarine staging queue after successful crawl.

    Contains the pre-built extraction prompt AND the original SubmarineJob
    context so the result processor can build a JobResult without DB access.
    """

    job_id: str
    location_id: str
    submarine_job: dict[str, Any] = Field(
        description="Serialized SubmarineJob for result building after extraction"
    )
    prompt: list[dict[str, str]] = Field(
        description="Chat messages for LLM extraction: [{role, content}, ...]"
    )
    missing_fields: list[str] = Field(
        description="Which fields to extract, e.g. ['phone', 'hours']"
    )
    crawl_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Crawl provenance: url, pages_crawled, links_followed",
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
