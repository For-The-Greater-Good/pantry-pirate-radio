"""Job models."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class LLMJob(BaseModel):
    """LLM job model."""

    id: str
    prompt: str
    format: dict[str, Any] = {}
    provider_config: dict[str, Any] = {}
    metadata: dict[str, Any] = {}
    created_at: datetime
