"""HSDS aligner implementation.

This module implements alignment of input data to HSDS format using LLMs
with structured output support.
"""

import json
from pathlib import Path
from typing import Any, Generic, TypeVar, cast

from app.llm.config import LLMConfig
from app.llm.hsds_aligner.schema_converter import LLMJsonSchema, SchemaConverter
from app.llm.hsds_aligner.type_defs import (
    AlignmentOutputDict,
    HSDSDataDict,
    KnownFieldsDict,
    ParsedHSDSDataDict,
    ValidationDetailsDict,
)
from app.llm.hsds_aligner.types import (
    AlignmentAttemptDict,
    FieldRelationship,
)
from app.llm.hsds_aligner.validation import ValidationConfig, ValidationResult
from app.llm.hsds_aligner.validator import ValidationProvider
from app.llm.providers.base import BaseLLMProvider
from app.llm.providers.types import GenerateConfig, LLMResponse

ModelType = TypeVar("ModelType")
ConfigType = TypeVar("ConfigType", bound=LLMConfig)


class HSDSAligner(Generic[ModelType, ConfigType]):
    """Aligns input data to HSDS format using LLM"""

    MAX_RETRIES = 5
    REQUIRED_FIELDS: dict[str, list[str]] = {
        "top_level": ["organization", "service", "location"],
        "organization": ["name", "description", "services"],
        "service": ["name", "description"],
        "location": ["name", "addresses"],
    }

    FIELD_DESCRIPTIONS: dict[str, str] = {
        "organization": "A list containing at least one organization object",
        "service": "A list containing at least one service object",
        "location": "A list containing at least one location object",
        "services": "A list of service objects associated with this organization",
        "name": "The name of this entity",
        "description": "A description of this entity",
        "addresses": "The physical or mailing address information",
    }

    FIELD_RELATIONSHIPS: dict[str, FieldRelationship] = {
        "services": {
            "parent": "organization",
            "target": "service",
            "description": "Lists all services provided by this organization. Required to show what services this organization offers.",
        },
        "location": {
            "parent": "top_level",
            "target": None,
            "description": "Contains physical locations where services are provided. Required for geographic search and accessibility.",
        },
        "addresses": {
            "parent": "location",
            "target": None,
            "description": "Physical address information for this location. Required for mapping and directions.",
        },
    }

    def __init__(
        self,
        provider: BaseLLMProvider[ModelType, ConfigType],
        schema_path: Path,
        validation_config: ValidationConfig | None = None,
        validation_provider: BaseLLMProvider[Any, ConfigType] | None = None,
    ) -> None:
        """Initialize the HSDS aligner

        Args:
            provider: The LLM provider to use
            schema_path: Path to the HSDS schema.csv file
            validation_config: Optional validation configuration
            validation_provider: Optional different provider for validation
        """
        self.provider = provider
        self.schema_converter = SchemaConverter(schema_path)
        self.system_prompt = self._load_prompt()
        self.attempts: list[AlignmentAttemptDict] = []

        # Convert schema for structured output
        self.hsds_schema: LLMJsonSchema = self.schema_converter.convert_to_llm_schema(
            "organization"
        )

        # Setup validation
        self.validation_config = validation_config or ValidationConfig()
        val_provider = validation_provider or provider
        self.validator = ValidationProvider[Any, ConfigType](
            val_provider, self.validation_config
        )

    def _load_prompt(self) -> str:
        """Load the system prompt from file

        Returns:
            str: The system prompt
        """
        prompt_path = Path(__file__).parent / "prompts" / "food_pantry_mapper.prompt"
        return prompt_path.read_text()

    def _prepare_input(self, raw_data: str, feedback: str | None = None) -> str:
        """Prepare the input data for the LLM

        Args:
            raw_data (str): The raw input data to prepare
            feedback (Optional[str]): Feedback from previous attempt

        Returns:
            str: The prepared prompt
        """
        prompt = f"{self.system_prompt}\n\nInput Data:\n{raw_data}"

        if feedback:
            prompt += "\n\nPrevious attempt had the following issues:"
            prompt += f"\nPrevious Output: {self.attempts[-1]['response'] if self.attempts else 'No previous output'}"
            for issue in feedback.split("\n"):
                field = issue.split("'")[1] if "'" in issue else None
                if field and field in self.FIELD_RELATIONSHIPS:
                    relationship = self.FIELD_RELATIONSHIPS[field]
                    prompt += f"\n- {issue}"
                    prompt += f"\n  • {relationship['description']}"
                    if relationship["target"]:
                        prompt += f"\n  • Required to link {relationship['parent']} with {relationship['target']}"
                elif field and field in self.FIELD_DESCRIPTIONS:
                    prompt += f"\n- {issue} ({self.FIELD_DESCRIPTIONS[field]})"
                else:
                    prompt += f"\n- {issue}"

        return prompt

    def _get_feedback_message(self, validation_result: ValidationResult) -> str | None:
        """Get simplified feedback message from validation result.

        Args:
            validation_result: The validation result

        Returns:
            Optional[str]: Simplified feedback message or None
        """
        if not validation_result.feedback:
            return None

        # Extract field name from feedback
        if "organization description" in validation_result.feedback.lower():
            return "Missing organization description"

        return validation_result.feedback

    def _check_model_refusal(self, response_text: str) -> bool:
        """Check if the model refused to generate a response.

        Args:
            response_text: The response text to check

        Returns:
            bool: True if model refused, False otherwise
        """
        refusal_phrases = [
            "I'm sorry, I cannot",
            "I apologize, but I cannot",
            "I cannot assist with",
            "I am unable to",
            "I must decline",
        ]
        return any(phrase in response_text for phrase in refusal_phrases)

    def _parse_response(self, response: LLMResponse) -> ParsedHSDSDataDict:
        """Parse the LLM response into HSDS data.

        Args:
            response: The LLM response to parse

        Returns:
            ParsedHSDSDataDict: The parsed HSDS data with validation details

        Raises:
            ValueError: If response cannot be parsed
        """
        if response.parsed is not None:
            return cast(ParsedHSDSDataDict, response.parsed)

        try:
            hsds_data = cast(HSDSDataDict, json.loads(response.text))
            # Create default validation details
            suggested_corrections: dict[str, str | None] = {}
            validation_details: ValidationDetailsDict = {
                "hallucination_detected": False,
                "mismatched_fields": [],
                "suggested_corrections": suggested_corrections,
                "feedback": None,
            }

            # Update validation details if available
            if response.validation_details:
                suggested_corrections = (
                    response.validation_details.suggested_corrections or {}
                )
                validation_details = {
                    "hallucination_detected": bool(
                        response.validation_details.hallucination_detected
                    ),
                    "mismatched_fields": list(
                        response.validation_details.mismatched_fields or []
                    ),
                    "suggested_corrections": suggested_corrections,
                    "feedback": (
                        str(response.validation_details.feedback)
                        if response.validation_details.feedback
                        else None
                    ),
                }

            # Create ParsedHSDSDataDict
            return {
                "organization": hsds_data["organization"],
                "service": hsds_data["service"],
                "location": hsds_data["location"],
                "validation_details": validation_details,
            }
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON response: {e!s}")

    def _record_validation_attempt(
        self,
        validation_result: ValidationResult,
        attempts_remaining: int,
    ) -> None:
        """Record validation attempt details.

        Args:
            validation_result: The validation result to record
            attempts_remaining: Number of attempts remaining
        """
        feedback_message = self._get_feedback_message(validation_result)
        self.attempts.append(
            {
                "attempt": self.MAX_RETRIES - attempts_remaining,
                "prompt": "",  # Prompt is added elsewhere
                "response": "",  # Response is added elsewhere
                "cleaned_response": "",  # Response is added elsewhere
                "is_valid": validation_result.confidence
                >= self.validation_config.min_confidence,
                "feedback": feedback_message,
                "score": validation_result.confidence,
            }
        )

    def _create_success_output(
        self,
        hsds_data: HSDSDataDict,
        confidence_score: float,
        validation_result: ValidationResult | None = None,
    ) -> tuple[AlignmentOutputDict, None]:
        """Create success output dictionary.

        Args:
            hsds_data: The validated HSDS data
            confidence_score: The validation confidence score
            validation_result: Optional validation result details

        Returns:
            Tuple of (success output dict, None)
        """
        output: AlignmentOutputDict = {
            "hsds_data": hsds_data,
            "confidence_score": confidence_score,
        }

        if validation_result:
            validation_details: ValidationDetailsDict = {
                "hallucination_detected": validation_result.hallucination_detected,
                "mismatched_fields": validation_result.mismatched_fields or [],
                "suggested_corrections": cast(
                    dict[str, str | None], validation_result.suggested_corrections or {}
                ),
                "feedback": validation_result.feedback,
            }
            output["validation_details"] = validation_details

        return (output, None)

    def _build_feedback_message(self, validation_result: ValidationResult) -> str:
        """Build feedback message from validation result.

        Args:
            validation_result: The validation result to process

        Returns:
            str: Combined feedback message
        """
        feedback_parts: list[str] = []
        if validation_result.feedback:
            feedback_parts.append(str(validation_result.feedback))
        if validation_result.hallucination_detected:
            feedback_parts.append("Remove any hallucinated data not present in input")
        if validation_result.mismatched_fields:
            feedback_parts.append(
                f"Fix mismatched fields: {', '.join(validation_result.mismatched_fields)}"
            )
        return "\n".join(feedback_parts)

    def _log_validation_failure(self, validation_result: ValidationResult) -> None:
        """Log validation failure details.

        Args:
            validation_result: The failed validation result
        """
        print("\nValidation Failed:")
        if validation_result.feedback:
            print(f"Feedback: {validation_result.feedback}")
        if validation_result.hallucination_detected:
            print("Warning: Hallucinated data detected")
        if validation_result.mismatched_fields:
            print(
                f"Mismatched fields: {', '.join(validation_result.mismatched_fields)}"
            )
        print()

    async def _process_validation_result(
        self,
        validation_result: ValidationResult,
        hsds_data: HSDSDataDict,
        attempts_remaining: int,
    ) -> tuple[AlignmentOutputDict | None, str | None]:
        """Process validation result and determine next steps.

        Args:
            validation_result: The validation result to process
            hsds_data: The current HSDS data
            attempts_remaining: Number of attempts remaining

        Returns:
            Tuple of (AlignmentOutputDict if complete, feedback string if retry needed)
        """
        self._record_validation_attempt(validation_result, attempts_remaining)

        # Print validation details
        print(f"\nConfidence Score: {validation_result.confidence}")
        print("Validation Details:")
        print(f"- Hallucination Detected: {validation_result.hallucination_detected}")
        if validation_result.mismatched_fields:
            print(
                f"- Mismatched Fields: {', '.join(validation_result.mismatched_fields)}"
            )
        if validation_result.suggested_corrections:
            print("- Suggested Corrections:")
            for field, value in validation_result.suggested_corrections.items():
                print(f"  • {field}: {value}")
        print()

        # Check if validation passed minimum confidence threshold
        if validation_result.confidence >= self.validation_config.min_confidence:
            print("\nValidation Successful!")
            return self._create_success_output(
                hsds_data, validation_result.confidence, validation_result
            )

        # Handle validation failure
        print("\nValidation Failed:")
        print(
            f"Score {validation_result.confidence} below minimum threshold {self.validation_config.min_confidence}"
        )
        self._log_validation_failure(validation_result)

        # Continue retrying if we have attempts left
        if attempts_remaining > 0:
            print(f"Retrying... ({attempts_remaining} attempts remaining)")
            return None, self._build_feedback_message(validation_result)

        # On final attempt, raise error
        raise ValueError(
            f"Failed to achieve minimum confidence score of {self.validation_config.min_confidence} after {self.MAX_RETRIES} attempts. Final confidence: {validation_result.confidence}"
        )

    async def align(
        self,
        raw_data: str,
        known_fields: KnownFieldsDict | None = None,
    ) -> AlignmentOutputDict:
        """Align input data to HSDS format

        Args:
            raw_data (str): The raw input data to align

        Returns:
            AlignmentOutputDict: The aligned HSDS data and confidence score

        Raises:
            ValueError: If alignment fails after max retries
        """
        attempts_remaining = self.MAX_RETRIES
        feedback: str | None = None

        print("\nStarting HSDS alignment...\n")

        while attempts_remaining > 0:
            attempts_remaining -= 1
            print(
                f"[Attempt {self.MAX_RETRIES - attempts_remaining}/{self.MAX_RETRIES}]"
            )

            try:
                # Prepare input and generate response
                prompt = self._prepare_input(raw_data, feedback)
                print(f"\nPrompt:\n{prompt}\n")

                config = GenerateConfig(
                    temperature=0.7,
                    max_tokens=64768,
                    format={
                        "type": "json_schema",
                        "schema": cast(dict[str, Any], self.hsds_schema["json_schema"]),
                        "strict": True,
                    },
                )

                response = await self.provider.generate(prompt, config=config)

                if not isinstance(response, LLMResponse):
                    raise ValueError("Streaming responses not supported")

                print(f"\nLLM Response:\n{response.text}\n")

                # Check for model refusal
                if self._check_model_refusal(response.text):
                    print(f"\nModel refused to generate: {response.text}\n")
                    if attempts_remaining == 0:
                        raise ValueError(
                            f"Model refused to generate after {self.MAX_RETRIES} attempts: {response.text}"
                        )
                    feedback = "Model refused to generate. Adjusting prompt..."
                    continue

                # Parse response
                try:
                    hsds_data = self._parse_response(response)
                except ValueError as e:
                    if attempts_remaining == 0:
                        raise
                    feedback = str(e)
                    print(f"\nError:\n{feedback}\n")
                    continue

                # Validate mapping
                validation_result = await self.validator.validate(
                    raw_data, hsds_data, known_fields
                )

                # Process validation result
                result, new_feedback = await self._process_validation_result(
                    validation_result, hsds_data, attempts_remaining
                )
                if result:
                    return result
                feedback = new_feedback
                continue

            except Exception as e:
                feedback = f"Error processing response: {e!s}"
                print(f"\nError:\n{feedback}\n")
                if attempts_remaining == 0:
                    raise ValueError(feedback)

        raise ValueError(
            f"Maximum retries ({self.MAX_RETRIES}) exceeded without valid result"
        )
