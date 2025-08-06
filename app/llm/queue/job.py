"""Job models."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class LLMJob(BaseModel):
    """LLM job model."""

    id: str
    prompt: str
    format: dict[str, Any] = Field(default_factory=dict)
    provider_config: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
