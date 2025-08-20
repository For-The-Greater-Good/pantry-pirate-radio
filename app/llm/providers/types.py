"""Type definitions for LLM providers."""

import copy
import json
import os
from dataclasses import dataclass
from typing import Any, Union

from pydantic import BaseModel, Field, field_validator
from typing_extensions import TypedDict

# Response format types
ResponseFormat = dict[str, str | dict[str, Any]]


class Choice(TypedDict, total=False):
    """Type for LLM response choice."""

    index: int
    text: str
    logprobs: dict[str, Any] | None


MetadataValue = Union[str, dict[str, Any]]
NestedMetadata = dict[str, MetadataValue]


class RawResponse(TypedDict, total=False):
    """Type for raw LLM response data."""

    extra: str
    metadata: NestedMetadata
    choices: list[Choice]
    model: str
    created: int
    usage: dict[str, int]
    id: str
    object: str


@dataclass
class GenerateConfig:
    """Configuration for generation requests."""

    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 40
    max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "8192"))
    stop: list[str] | None = None
    stream: bool = False
    format: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        """Validate configuration parameters."""
        if not 0 <= self.temperature <= 1:
            raise ValueError("Temperature must be between 0 and 1")
        if not 0 <= self.top_p <= 1:
            raise ValueError("Top-p must be between 0 and 1")
        if self.top_k < 1:
            raise ValueError("Top-k must be positive")
        if self.max_tokens < 1:
            raise ValueError("Max tokens must be positive")
        if self.stop is not None:
            if any(not s for s in self.stop):
                raise ValueError("Stop sequences cannot be empty")


class ValidationDetails(BaseModel):
    """Validation details for LLM response."""

    hallucination_detected: bool = Field(
        description="Whether hallucination was detected"
    )
    mismatched_fields: list[str] = Field(description="List of mismatched fields")
    suggested_corrections: dict[str, str | None] = Field(
        description="Suggested corrections", default_factory=dict
    )
    feedback: str | None = Field(description="Validation feedback message")


class LLMResponse(BaseModel):
    """Standard response format for LLM generations."""

    text: str = Field(description="Generated text content")
    model: str = Field(description="Name of the model used")
    usage: dict[str, int] = Field(description="Token usage statistics")
    raw: dict[str, Any] | None = Field(
        default_factory=lambda: {}, description="Raw response data"
    )
    parsed: Any | None = Field(
        default=None, description="Parsed structured output if format was specified"
    )
    validation_details: ValidationDetails | None = Field(
        default=None, description="Validation details if validation was performed"
    )

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        """Validate text field."""
        if not v or v.isspace():
            raise ValueError("Response text cannot be empty")
        return v

    @field_validator("model")
    @classmethod
    def validate_model(cls, v: str) -> str:
        """Validate model field."""
        if not v or v.isspace():
            raise ValueError("Model name cannot be empty")
        return v

    @field_validator("usage", mode="before")
    @classmethod
    def validate_usage(cls, v: dict[str, Any]) -> dict[str, int]:
        """Validate usage statistics."""
        if not v:
            raise ValueError("Usage statistics cannot be empty")
        result: dict[str, int] = {}
        for key, value in v.items():
            try:
                if value is None:
                    raise ValueError("Usage values must be integers")
                # Check for integer type
                if not isinstance(value, int | float):
                    raise ValueError("Usage values must be integers")
                # Convert to float first to check if it's a whole number
                float_value = float(value)
                int_value = int(float_value)
                if float_value != int_value:
                    raise ValueError("Usage values must be integers")
                if int_value < 0:
                    raise ValueError("Usage values must be non-negative")
                result[key] = int_value
            except (TypeError, ValueError) as e:
                # Re-raise with our custom message if it's not already one of
                # ours
                if str(e) not in (
                    "Usage values must be integers",
                    "Usage values must be non-negative",
                ):
                    raise ValueError("Usage values must be integers")
                raise
        return result

    def model_post_init(self, _: Any) -> None:
        """Post-initialization processing."""
        # Ensure immutability of nested structures
        if self.raw is None:
            self.raw = {}
        elif self.raw:
            self.raw = copy.deepcopy(self.raw)
        if self.parsed:
            self.parsed = copy.deepcopy(self.parsed)
        if self.usage:
            self.usage = dict(self.usage)

    @property
    def content(self) -> str:
        """Get the generated text content."""
        return self.text

    def __str__(self) -> str:
        """String representation of the response."""
        return self.text

    def model_dump_json(self, **kwargs: Any) -> str:
        """Override to handle serialization."""
        data = self.model_dump(exclude_none=True)
        if self.parsed:
            # Handle parsed data based on type
            if isinstance(self.parsed, dict):
                # For validation results, keep as dict if it's a valid JSON object
                parsed_data: dict[str, Any] = self.parsed
                try:
                    # Test if entire dict is JSON serializable
                    json.dumps(parsed_data)
                    data["parsed"] = parsed_data
                except (TypeError, ValueError):
                    data["parsed"] = str(parsed_data)
            else:
                data["parsed"] = str(self.parsed)
        if self.validation_details:
            # Include validation details in both top level and parsed data
            validation_data = self.validation_details.model_dump(exclude_none=True)
            data["validation_details"] = validation_data
            if isinstance(data.get("parsed"), dict):
                data["parsed"]["validation_details"] = validation_data
        return json.dumps(data, indent=2)

    def __eq__(self, other: object) -> bool:
        """Compare LLMResponse objects for equality."""
        if not isinstance(other, LLMResponse):
            return NotImplemented
        return (
            self.text == other.text
            and self.model == other.model
            and self.usage == other.usage
            and self.parsed == other.parsed
            and self.validation_details == other.validation_details
        )

    def __hash__(self) -> int:
        """Hash the LLMResponse object."""
        validation_hash = None
        if self.validation_details:
            validation_hash = hash(
                (
                    self.validation_details.hallucination_detected,
                    tuple(sorted(self.validation_details.mismatched_fields)),
                    tuple(
                        sorted(
                            (k, v)
                            for k, v in self.validation_details.suggested_corrections.items()
                        )
                    ),
                    self.validation_details.feedback,
                )
            )
        return hash(
            (
                self.text,
                self.model,
                tuple(sorted(self.usage.items())),
                str(self.parsed) if self.parsed is not None else None,
                validation_hash,
            )
        )


LLMInput = Union[str, list[dict[str, Any]]]  # Text or chat messages
