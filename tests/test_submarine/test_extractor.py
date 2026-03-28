"""Tests for submarine LLM field extractor."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.submarine.extractor import ExtractionError, SubmarineExtractor

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "test_site"


class TestSubmarineExtractor:
    """Tests for the SubmarineExtractor."""

    @pytest.fixture
    def extractor(self):
        return SubmarineExtractor()

    def test_build_prompt_includes_missing_fields(self, extractor):
        """Prompt tells the LLM which fields to extract."""
        prompt = extractor._build_prompt(
            markdown="Some page content",
            missing_fields=["phone", "hours"],
        )
        assert "phone" in prompt
        assert "hours" in prompt

    def test_build_prompt_includes_content(self, extractor):
        """Prompt includes the crawled markdown content."""
        prompt = extractor._build_prompt(
            markdown="# Grace Community Church\nOpen Mon-Fri 9-5",
            missing_fields=["hours"],
        )
        assert "Grace Community Church" in prompt

    def test_build_prompt_only_requested_fields(self, extractor):
        """Prompt only asks for fields that are actually missing."""
        prompt = extractor._build_prompt(
            markdown="Some content",
            missing_fields=["phone"],
        )
        assert "phone" in prompt
        # Should not ask for fields that aren't missing
        # (email/hours/description are not in missing_fields)

    @pytest.mark.asyncio
    async def test_extract_parses_json_response(self, extractor):
        """Extractor parses JSON from LLM response."""
        mock_response = MagicMock()
        mock_response.text = json.dumps(
            {
                "phone": "(555) 234-5678",
                "hours": [
                    {"day": "Tuesday", "opens_at": "10:00", "closes_at": "14:00"},
                    {"day": "Thursday", "opens_at": "10:00", "closes_at": "14:00"},
                ],
                "email": "info@gracechurchspringfield.org",
                "description": None,
            }
        )

        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock(return_value=mock_response)

        result = await extractor.extract(
            markdown="Some content about a food bank",
            missing_fields=["phone", "hours", "email", "description"],
            provider=mock_provider,
        )

        assert result["phone"] == "(555) 234-5678"
        assert len(result["hours"]) == 2
        assert result["email"] == "info@gracechurchspringfield.org"
        # Null values should be excluded
        assert "description" not in result

    @pytest.mark.asyncio
    async def test_extract_handles_no_data(self, extractor):
        """Extractor returns empty dict when LLM finds nothing."""
        mock_response = MagicMock()
        mock_response.text = json.dumps(
            {
                "phone": None,
                "hours": None,
                "email": None,
                "description": None,
            }
        )

        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock(return_value=mock_response)

        result = await extractor.extract(
            markdown="This page has nothing about a food bank",
            missing_fields=["phone", "hours", "email", "description"],
            provider=mock_provider,
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_extract_handles_malformed_json(self, extractor):
        """Extractor returns empty dict on unparseable LLM response."""
        mock_response = MagicMock()
        mock_response.text = "I couldn't find any data on this page."

        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock(return_value=mock_response)

        result = await extractor.extract(
            markdown="Some content",
            missing_fields=["phone"],
            provider=mock_provider,
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_extract_with_fixture_content(self, extractor):
        """Extractor works with realistic Grace Church fixture content."""
        # Combine fixture pages like the crawler would
        pages = ["food-pantry.html", "contact.html"]
        combined = ""
        for page in pages:
            content = (FIXTURES_DIR / page).read_text()
            combined += f"\n\n# Page: {page}\n\n{content}"

        mock_response = MagicMock()
        mock_response.text = json.dumps(
            {
                "phone": "(555) 234-5678",
                "hours": [
                    {"day": "Tuesday", "opens_at": "10:00", "closes_at": "14:00"},
                    {"day": "Thursday", "opens_at": "10:00", "closes_at": "14:00"},
                    {"day": "Saturday", "opens_at": "09:00", "closes_at": "12:00"},
                ],
                "email": "pantry@gracechurchspringfield.org",
                "description": "Community food pantry serving over 200 families monthly",
            }
        )

        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock(return_value=mock_response)

        result = await extractor.extract(
            markdown=combined,
            missing_fields=["phone", "hours", "email", "description"],
            provider=mock_provider,
        )

        assert result["phone"] == "(555) 234-5678"
        assert len(result["hours"]) == 3
        assert result["email"] == "pantry@gracechurchspringfield.org"
        assert "200 families" in result["description"]

    @pytest.mark.asyncio
    async def test_extract_strips_null_fields(self, extractor):
        """Only non-null fields are returned."""
        mock_response = MagicMock()
        mock_response.text = json.dumps(
            {
                "phone": "(555) 234-5678",
                "hours": None,
            }
        )

        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock(return_value=mock_response)

        result = await extractor.extract(
            markdown="Some content",
            missing_fields=["phone", "hours"],
            provider=mock_provider,
        )
        assert "phone" in result
        assert "hours" not in result

    @pytest.mark.asyncio
    async def test_extract_raises_extraction_error_on_provider_failure(self, extractor):
        """ExtractionError raised when LLM provider throws an exception."""
        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock(side_effect=RuntimeError("Provider down"))

        with pytest.raises(ExtractionError, match="Provider down"):
            await extractor.extract(
                markdown="Some content",
                missing_fields=["phone"],
                provider=mock_provider,
            )

    @pytest.mark.asyncio
    async def test_extract_raises_on_missing_text_attribute(self, extractor):
        """ExtractionError raised when provider returns object without .text."""
        mock_response = MagicMock(spec=[])  # spec=[] means no attributes
        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock(return_value=mock_response)

        with pytest.raises(ExtractionError, match="no text attribute"):
            await extractor.extract(
                markdown="Some content",
                missing_fields=["phone"],
                provider=mock_provider,
            )

    def test_parse_response_markdown_code_block(self, extractor):
        """Response wrapped in ```json ... ``` code block is parsed correctly."""
        response_text = '```json\n{"phone": "(555) 123-4567"}\n```'
        result = extractor._parse_response(response_text, ["phone"])
        assert result == {"phone": "(555) 123-4567"}

    def test_parse_response_non_dict_returns_empty(self, extractor):
        """JSON array response returns empty dict (not a dict)."""
        response_text = '[{"phone": "555-1234"}]'
        result = extractor._parse_response(response_text, ["phone"])
        assert result == {}

    def test_parse_response_filters_to_requested_fields(self, extractor):
        """Only fields in missing_fields are included, even if LLM returns extra."""
        response_text = json.dumps(
            {
                "phone": "(555) 999-0000",
                "email": "extra@example.com",
                "hours": [{"day": "Monday", "opens_at": "09:00", "closes_at": "17:00"}],
            }
        )
        result = extractor._parse_response(response_text, ["phone"])
        assert result == {"phone": "(555) 999-0000"}
        assert "email" not in result
        assert "hours" not in result


class TestFoodRelevanceSignal:
    """Tests for the LLM is_food_related relevance signal."""

    @pytest.fixture
    def extractor(self):
        return SubmarineExtractor()

    def test_rejects_non_food_content_via_llm(self, extractor):
        """When LLM says is_food_related=false, return empty dict."""
        response_text = json.dumps(
            {
                "is_food_related": False,
                "phone": "(555) 999-0000",
                "hours": None,
            }
        )
        result = extractor._parse_response(response_text, ["phone"])
        assert result == {}

    def test_accepts_food_content_and_strips_flag(self, extractor):
        """When LLM says is_food_related=true, return fields without the flag."""
        response_text = json.dumps(
            {
                "is_food_related": True,
                "phone": "(555) 234-5678",
            }
        )
        result = extractor._parse_response(response_text, ["phone"])
        assert result == {"phone": "(555) 234-5678"}
        assert "is_food_related" not in result

    def test_defaults_to_accept_when_field_omitted(self, extractor):
        """When LLM omits is_food_related, extraction proceeds normally."""
        response_text = json.dumps(
            {
                "phone": "(555) 111-2222",
            }
        )
        result = extractor._parse_response(response_text, ["phone"])
        assert result == {"phone": "(555) 111-2222"}
