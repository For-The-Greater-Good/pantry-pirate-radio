"""Data models for content store."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ContentEntry:
    """Represents an entry in the content store."""

    hash: str
    status: str  # "pending" or "completed"
    result: Optional[str] = None
    job_id: Optional[str] = None
