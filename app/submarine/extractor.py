"""LLM-based field extraction from crawled web content.

Takes markdown content from the crawler and uses the project's LLM
provider to extract structured HSDS fields (phone, hours, email, description).
"""

import json
import structlog
from typing import Any

from app.llm.providers.base import BaseLLMProvider
from app.llm.providers.types import GenerateConfig

logger = structlog.get_logger(__name__)

EXTRACTION_SYSTEM_PROMPT = """You are a data extraction assistant for a food bank directory.
You extract structured contact information from food bank and food pantry websites.
You ONLY return valid JSON. No explanations, no markdown, no extra text."""

EXTRACTION_USER_PROMPT = """Extract the following fields from this food bank website content.
Return ONLY a JSON object with the requested fields. Use null for fields not found.

Fields to extract: {fields_description}

Website content:
---
{content}
---

Return JSON only:"""

FIELD_DESCRIPTIONS = {
    "phone": '"phone": "main phone number as a string, e.g. (555) 234-5678"',
    "hours": (
        '"hours": [list of schedule objects with '
        '{"day": "weekday name", "opens_at": "HH:MM", "closes_at": "HH:MM"}] '
        "or null if not found"
    ),
    "email": '"email": "primary contact email address"',
    "description": (
        '"description": "brief description of the food pantry/food bank services '
        '(1-2 sentences, focus on what they provide and who they serve)"'
    ),
}


class ExtractionError(Exception):
    """LLM extraction failed (distinct from 'no data found in content')."""

    pass


class SubmarineExtractor:
    """Extracts structured HSDS fields from crawled markdown using LLM."""

    async def extract(
        self,
        markdown: str,
        missing_fields: list[str],
        provider: BaseLLMProvider[Any, Any],
    ) -> dict[str, Any]:
        """Extract missing fields from crawled content using LLM.

        Args:
            markdown: Combined markdown from the crawler.
            missing_fields: Which fields to extract (e.g. ["phone", "hours"]).
            provider: LLM provider instance to use for extraction.

        Returns:
            Dict of extracted field values. Only non-null fields included.

        Raises:
            ExtractionError: If the LLM call fails (provider error, bad response).
                Callers should map this to status="error" (14-day cooldown),
                not "no_data" (90-day cooldown).
        """
        prompt = self._build_prompt(markdown, missing_fields)

        config = GenerateConfig(
            temperature=0.1,  # Low temp for factual extraction
            max_tokens=2048,
        )

        try:
            response = await provider.generate(
                prompt=[
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                config=config,
            )
        except Exception as e:
            logger.warning(
                "submarine_extraction_failed",
                extra={"error": str(e), "fields": missing_fields},
            )
            raise ExtractionError(str(e)) from e

        if not hasattr(response, "text"):
            logger.error(
                "submarine_extraction_unexpected_response",
                extra={
                    "response_type": type(response).__name__,
                    "fields": missing_fields,
                },
            )
            raise ExtractionError(
                f"LLM response has no text attribute (type: {type(response).__name__})"
            )

        return self._parse_response(response.text, missing_fields)  # type: ignore[union-attr]

    @staticmethod
    def _build_prompt(markdown: str, missing_fields: list[str]) -> str:
        """Build the extraction prompt for the LLM."""
        fields_desc = "\n".join(
            FIELD_DESCRIPTIONS.get(f, f'"{f}": "value or null"') for f in missing_fields
        )

        # ~3000 tokens at ~4 chars/token, leaving headroom for system prompt + response
        max_content_len = 12000
        content = markdown[:max_content_len]
        if len(markdown) > max_content_len:
            content += "\n\n[... content truncated ...]"

        return EXTRACTION_USER_PROMPT.format(
            fields_description=fields_desc,
            content=content,
        )

    @staticmethod
    def _parse_response(
        response_text: str, missing_fields: list[str]
    ) -> dict[str, Any]:
        """Parse the LLM JSON response, returning only non-null fields."""
        # Try to extract JSON from the response
        text = response_text.strip()

        # Handle markdown code blocks
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last lines (``` markers)
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON object in the response
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    data = json.loads(text[start:end])
                except json.JSONDecodeError:
                    logger.warning(
                        "submarine_extraction_parse_failed",
                        extra={"response_preview": text[:200]},
                    )
                    return {}
            else:
                logger.warning(
                    "submarine_extraction_no_json",
                    extra={"response_preview": text[:200]},
                )
                return {}

        if not isinstance(data, dict):
            logger.warning(
                "submarine_extraction_unexpected_type",
                extra={"data_type": type(data).__name__},
            )
            return {}

        # Filter to only requested fields with non-null values
        result = {}
        for field in missing_fields:
            value = data.get(field)
            if value is not None:
                result[field] = value

        return result
