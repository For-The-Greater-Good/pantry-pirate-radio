"""HSDS validation provider.

This module provides the validation provider that uses LLMs to validate
HSDS data mappings and detect potential issues.
"""

import json
from pathlib import Path
from typing import Any, Generic, TypeVar, cast

from app.core.logging import get_logger
from app.llm.config import LLMConfig
from app.llm.hsds_aligner.field_validator import FieldValidator
from app.llm.hsds_aligner.type_defs import (
    HSDSDataDict,
    KnownFieldsDict,
)
from app.llm.hsds_aligner.validation import ValidationConfig, ValidationResult
from app.llm.providers.base import BaseLLMProvider
from app.llm.providers.types import GenerateConfig, LLMResponse

logger = get_logger().bind(module="hsds_validator")


# Make ModelType covariant to allow assigning providers with different but
# compatible model types
ModelType = TypeVar("ModelType", covariant=True)
ConfigType = TypeVar("ConfigType", bound=LLMConfig)


class ValidationProvider(Generic[ModelType, ConfigType]):
    """Provider for LLM-based HSDS validation."""

    def __init__(
        self,
        # Use Any for model type to accept any provider
        provider: BaseLLMProvider[Any, ConfigType],
        config: ValidationConfig | None = None,
    ) -> None:
        """Initialize validation provider.

        Args:
            provider: LLM provider to use for validation
            config: Optional validation configuration
        """
        self.provider = provider
        self.config = config or ValidationConfig()
        self.field_validator = FieldValidator()
        self._load_prompt()

    def _load_prompt(self) -> None:
        """Load the validation prompt template."""
        prompt_path = Path(__file__).parent / "prompts" / "validation_prompt.prompt"
        self.prompt_template = prompt_path.read_text()

    def _prepare_prompt(self, input_data: str, hsds_output: HSDSDataDict) -> str:
        """Prepare the validation prompt.

        Args:
            input_data: Original raw input data
            hsds_output: Generated HSDS output to validate

        Returns:
            str: Formatted prompt for validation
        """
        # Create a copy of the template with escaped braces
        template = self.prompt_template.replace("{", "{{").replace("}", "}}")
        # Un-escape the placeholder braces
        template = template.replace("{{input_data}}", "{input_data}")
        template = template.replace("{{hsds_output}}", "{hsds_output}")

        # Use json.dumps with default=str to handle any serialization issues
        hsds_json = json.dumps(
            hsds_output,
            indent=2,
            default=str,  # Convert any non-serializable objects to strings
        )

        return template.format(input_data=input_data, hsds_output=hsds_json)

    async def validate(
        self,
        input_data: str,
        hsds_output: HSDSDataDict,
        known_fields: KnownFieldsDict | None = None,
    ) -> ValidationResult:
        """Validate HSDS mapping using LLM.

        Args:
            input_data: Original raw input data
            hsds_output: Generated HSDS output to validate

        Returns:
            ValidationResult: Validation results with confidence score and feedback

        Raises:
            ValueError: If validation fails or response is invalid
        """
        logger.info("Starting HSDS validation...")
        prompt = self._prepare_prompt(input_data, hsds_output)
        logger.info("Prepared validation prompt")

        # First validate required fields
        logger.info("Validating required fields...")
        missing_fields = self.field_validator.validate_required_fields(
            hsds_output, known_fields
        )
        field_confidence = self.field_validator.calculate_confidence(
            missing_fields, known_fields
        )
        field_feedback = self.field_validator.generate_feedback(missing_fields)

        # Configure structured output for validation response
        logger.debug("Configuring validation schema")
        validation_schema: dict[str, Any] = {
            "type": "object",
            "properties": {
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "feedback": {"type": ["string", "null"]},
                "hallucination_detected": {"type": "boolean"},
                "mismatched_fields": {
                    "type": ["array", "null"],
                    "items": {"type": "string"},
                },
                "suggested_corrections": {
                    "type": ["object", "null"],
                    "additionalProperties": {"type": "string"},
                },
                "missing_required_fields": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": [
                "confidence",
                "hallucination_detected",
                "missing_required_fields",
            ],
            "additionalProperties": False,
        }

        config = GenerateConfig(
            temperature=0.7,  # Low temperature for consistent validation
            max_tokens=4000,
            format={
                "type": "json_schema",
                "schema": validation_schema,
                "strict": True,
            },
        )

        # When using format parameter, we just need the prompt directly
        logger.info("Sending validation request to provider...")
        logger.debug("Validation prompt: %s", prompt)
        logger.debug(
            "Validation config: %s",
            json.dumps(
                {
                    "temperature": config.temperature,
                    "max_tokens": config.max_tokens,
                    "format": config.format,
                }
            ),
        )
        response = await self.provider.generate(prompt, config=config)
        logger.info("Received validation response")
        if isinstance(response, LLMResponse):
            logger.debug("Raw validation response: %s", response.text)

        if isinstance(response, LLMResponse):
            logger.debug("Processing validation response")
            if response.parsed is not None:
                validation_data = cast(dict[str, Any], response.parsed)
                logger.info("Validation result: %s", validation_data)

                # Combine LLM validation with field validation
                validation_data["missing_required_fields"] = missing_fields
                validation_data["confidence"] = min(
                    validation_data["confidence"], field_confidence
                )

                # Combine feedback if present
                if field_feedback:
                    if validation_data.get("feedback"):
                        validation_data["feedback"] = (
                            f"{validation_data['feedback']}\n\n{field_feedback}"
                        )
                    else:
                        validation_data["feedback"] = field_feedback

                return ValidationResult.model_validate(validation_data)
            else:
                try:
                    # Try to parse the response text as JSON first
                    validation_data = cast(dict[str, Any], json.loads(response.text))

                    # Add field validation results
                    validation_data["missing_required_fields"] = missing_fields
                    validation_data["confidence"] = min(
                        validation_data.get("confidence", 1.0), field_confidence
                    )

                    # Add field validation feedback
                    if field_feedback:
                        if validation_data.get("feedback"):
                            validation_data["feedback"] = (
                                f"{validation_data['feedback']}\n\n{field_feedback}"
                            )
                        else:
                            validation_data["feedback"] = field_feedback

                    return ValidationResult.model_validate(validation_data)
                except json.JSONDecodeError as e:
                    raise ValueError(f"Invalid JSON in validation response: {e!s}")
                except Exception as e:
                    raise ValueError(f"Invalid validation response: {e!s}")
        else:
            raise ValueError("Streaming responses not supported for validation")
