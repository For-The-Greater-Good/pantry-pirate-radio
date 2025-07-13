"""Base types for LLM functionality."""

from dataclasses import dataclass


@dataclass
class BaseModelConfig:
    """Base configuration for LLM models."""

    context_length: int
    max_tokens: int | None
    default_temp: float = 0.7
    supports_functions: bool = False
    supports_json: bool = True
    supports_vision: bool = False
    supports_structured: bool = False

    def __post_init__(self) -> None:
        """Validate configuration parameters."""
        if self.context_length <= 0:
            raise ValueError("Context length must be positive")
        if self.max_tokens is not None and self.max_tokens <= 0:
            raise ValueError("Max tokens must be positive")
        if not 0 <= self.default_temp <= 1:
            raise ValueError("Temperature must be between 0 and 1")
