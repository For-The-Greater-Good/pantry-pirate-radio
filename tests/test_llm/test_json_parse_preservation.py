"""Regression test: JSON parse failure must not replace content with error string."""

from app.llm.providers.openai import OpenAIProvider, OpenAIConfig


class TestJsonParsePreservation:
    def test_malformed_json_preserves_content(self):
        """When json.loads fails, original content must be returned, not 'Invalid JSON response'."""
        config = OpenAIConfig(model_name="test", temperature=0.7)
        provider = OpenAIProvider(config)

        malformed = '{"name": "Test Food Bank", "description": "A food bank",}'
        format_schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
        }

        content, parsed = provider._process_json_content(
            malformed, format_schema
        )

        assert content != "Invalid JSON response"
        assert "Test Food Bank" in content
        assert parsed is None

    def test_valid_json_still_parses(self):
        """Valid JSON must still be parsed correctly."""
        config = OpenAIConfig(model_name="test", temperature=0.7)
        provider = OpenAIProvider(config)

        valid = '{"name": "Test"}'
        content, parsed = provider._process_json_content(
            valid, {"type": "object"}
        )

        assert content == '{"name": "Test"}'
        assert parsed == {"name": "Test"}
