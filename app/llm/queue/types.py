"""Shared queue types and models."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel

from app.llm.providers.types import LLMResponse
from app.llm.queue.job import LLMJob


class JobStatus(str, Enum):
    """Job status enum."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobResult(BaseModel):
    """Job result model."""

    job_id: str
    job: Optional[LLMJob] = None  # Made optional for validator compatibility
    status: JobStatus
    result: LLMResponse | None = None
    error: str | None = None
    completed_at: datetime | None = None
    processing_time: float | None = None
    retry_count: int = 0
    data: Optional[Dict[str, Any]] = None  # Added for validator data
    metadata: Optional[Dict[str, Any]] = None  # Added for validator metadata
