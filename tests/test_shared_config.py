"""Tests for shared pipeline configuration (config/ module)."""

import os
from pathlib import Path
from unittest.mock import mock_open, patch

import pytest
import yaml


class TestDefaultsYaml:
    """Tests for config/defaults.yml content and structure."""

    @pytest.fixture
    def yaml_path(self):
        """Path to defaults.yml."""
        return Path(__file__).parent.parent / "config" / "defaults.yml"

    @pytest.fixture
    def yaml_data(self, yaml_path):
        """Parsed YAML data."""
        with open(yaml_path) as f:
            return yaml.safe_load(f)

    def test_yaml_file_exists(self, yaml_path):
        """defaults.yml must exist as single source of truth."""
        assert yaml_path.exists(), "config/defaults.yml is missing"

    def test_has_all_expected_sections(self, yaml_data):
        """YAML must have all required top-level sections."""
        expected = {
            "llm",
            "validation",
            "enrichment",
            "geocoding",
            "content_store",
            "reconciler",
        }
        assert set(yaml_data.keys()) == expected

    def test_llm_section(self, yaml_data):
        """LLM section has correct keys and types."""
        llm = yaml_data["llm"]
        assert llm["temperature"] == 0.7
        assert llm["max_tokens"] == 16384
        assert llm["timeout"] == 30
        assert llm["retries"] == 3

    def test_validation_section(self, yaml_data):
        """Validation section has correct keys."""
        val = yaml_data["validation"]
        assert val["enabled"] is True
        assert val["rejection_threshold"] == 10

    def test_enrichment_section(self, yaml_data):
        """Enrichment section has correct keys."""
        enr = yaml_data["enrichment"]
        assert enr["enabled"] is True
        assert enr["cache_ttl"] == 86400
        assert enr["timeout"] == 30
        assert enr["geocoding_providers"] == [
            "amazon-location",
            "arcgis",
            "nominatim",
            "census",
        ]

    def test_geocoding_section(self, yaml_data):
        """Geocoding section has correct keys."""
        geo = yaml_data["geocoding"]
        assert geo["provider"] == "arcgis"
        assert geo["enable_fallback"] is True
        assert geo["max_retries"] == 3
        assert geo["timeout"] == 10

    def test_content_store_section(self, yaml_data):
        """Content store section has correct keys."""
        assert yaml_data["content_store"]["enabled"] is True

    def test_reconciler_section(self, yaml_data):
        """Reconciler section has correct keys."""
        assert yaml_data["reconciler"]["location_tolerance"] == 0.0001

    def test_no_secrets_in_yaml(self, yaml_data):
        """YAML keys must NOT contain secret-like names."""
        secret_patterns = ["api_key", "password", "secret_arn", "credential"]

        def check_keys(data, path=""):
            if isinstance(data, dict):
                for key, value in data.items():
                    full_path = f"{path}.{key}" if path else key
                    for pattern in secret_patterns:
                        assert pattern not in key.lower(), (
                            f"Found '{pattern}' in YAML key '{full_path}' — "
                            f"secrets must not go here"
                        )
                    check_keys(value, full_path)

        check_keys(yaml_data)


class TestLoadDefaults:
    """Tests for config.load_defaults() function."""

    def test_load_returns_all_expected_keys(self):
        """load_defaults() must return all Category 1 env var names."""
        from config import load_defaults

        defaults = load_defaults()
        expected_keys = {
            "LLM_TEMPERATURE",
            "LLM_MAX_TOKENS",
            "LLM_TIMEOUT",
            "LLM_RETRIES",
            "VALIDATOR_ENABLED",
            "VALIDATION_REJECTION_THRESHOLD",
            "VALIDATOR_ENRICHMENT_ENABLED",
            "ENRICHMENT_CACHE_TTL",
            "ENRICHMENT_TIMEOUT",
            "ENRICHMENT_GEOCODING_PROVIDERS",
            "GEOCODING_PROVIDER",
            "GEOCODING_ENABLE_FALLBACK",
            "GEOCODING_MAX_RETRIES",
            "GEOCODING_TIMEOUT",
            "CONTENT_STORE_ENABLED",
            "RECONCILER_LOCATION_TOLERANCE",
        }
        assert set(defaults.keys()) == expected_keys

    def test_load_returns_correct_types(self):
        """Values must have correct Python types."""
        from config import load_defaults

        defaults = load_defaults()
        assert isinstance(defaults["LLM_TEMPERATURE"], float)
        assert isinstance(defaults["LLM_MAX_TOKENS"], int)
        assert isinstance(defaults["LLM_TIMEOUT"], int)
        assert isinstance(defaults["LLM_RETRIES"], int)
        assert isinstance(defaults["VALIDATOR_ENABLED"], bool)
        assert isinstance(defaults["VALIDATION_REJECTION_THRESHOLD"], int)
        assert isinstance(defaults["VALIDATOR_ENRICHMENT_ENABLED"], bool)
        assert isinstance(defaults["ENRICHMENT_CACHE_TTL"], int)
        assert isinstance(defaults["ENRICHMENT_TIMEOUT"], int)
        assert isinstance(defaults["ENRICHMENT_GEOCODING_PROVIDERS"], list)
        assert isinstance(defaults["GEOCODING_PROVIDER"], str)
        assert isinstance(defaults["GEOCODING_ENABLE_FALLBACK"], bool)
        assert isinstance(defaults["GEOCODING_MAX_RETRIES"], int)
        assert isinstance(defaults["GEOCODING_TIMEOUT"], int)
        assert isinstance(defaults["CONTENT_STORE_ENABLED"], bool)
        assert isinstance(defaults["RECONCILER_LOCATION_TOLERANCE"], float)

    def test_hardcoded_fallback_matches_yaml(self):
        """Hardcoded fallback must match YAML exactly."""
        from config import _hardcoded_defaults, load_defaults

        yaml_defaults = load_defaults()
        hardcoded = _hardcoded_defaults()
        assert yaml_defaults == hardcoded, (
            f"Hardcoded defaults drift from YAML:\n"
            f"  YAML: {yaml_defaults}\n"
            f"  Hardcoded: {hardcoded}"
        )

    def test_falls_back_to_hardcoded_when_yaml_missing(self):
        """When YAML is not found, hardcoded defaults are returned."""
        from config import _hardcoded_defaults, load_defaults

        with patch("config._find_yaml", return_value=None):
            defaults = load_defaults()
        assert defaults == _hardcoded_defaults()

    def test_max_tokens_is_16384(self):
        """LLM_MAX_TOKENS canonical value must be 16384."""
        from config import load_defaults

        assert load_defaults()["LLM_MAX_TOKENS"] == 16384


class TestMalformedYamlHandling:
    """Tests for T13: shared config handles malformed YAML sections gracefully."""

    def test_flatten_skips_non_dict_sections(self):
        """_flatten() should skip sections whose value is not a dict."""
        from config import _flatten

        raw = {
            "llm": {
                "temperature": 0.7,
                "max_tokens": 16384,
                "timeout": 30,
                "retries": 3,
            },
            "validation": "this-is-a-string-not-a-dict",  # Malformed
            "enrichment": 42,  # Also malformed (int instead of dict)
        }

        result = _flatten(raw)

        # Should have the llm keys but skip the malformed sections
        assert "LLM_TEMPERATURE" in result
        assert result["LLM_TEMPERATURE"] == 0.7
        assert "LLM_MAX_TOKENS" in result
        # Malformed sections should not cause any keys to appear or crash
        assert "VALIDATOR_ENABLED" not in result
        assert "ENRICHMENT_CACHE_TTL" not in result

    def test_flatten_handles_none_section_value(self):
        """_flatten() should handle None section values without crashing."""
        from config import _flatten

        raw = {
            "llm": None,  # Section exists but is None (empty YAML section)
            "geocoding": {
                "provider": "arcgis",
                "enable_fallback": True,
                "max_retries": 3,
                "timeout": 10,
            },
        }

        result = _flatten(raw)

        # Should skip the None section
        assert "LLM_TEMPERATURE" not in result
        # Valid section should still work
        assert result["GEOCODING_PROVIDER"] == "arcgis"

    def test_flatten_handles_list_section_value(self):
        """_flatten() should handle list section values without crashing."""
        from config import _flatten

        raw = {
            "llm": ["not", "a", "dict"],  # Malformed: list instead of dict
        }

        result = _flatten(raw)

        # Should return empty dict since list is not a dict
        assert result == {}

    def test_load_defaults_returns_hardcoded_on_malformed_yaml(self):
        """load_defaults() should fall back to hardcoded defaults for malformed YAML."""
        from config import _hardcoded_defaults, load_defaults

        # Mock a YAML file that parses to a string (not a dict)
        with patch("config._find_yaml", return_value=Path("/fake/defaults.yml")):
            with patch("builtins.open", mock_open(read_data="just a string")):
                defaults = load_defaults()

        # Since yaml.safe_load("just a string") returns a string (not dict),
        # load_defaults() should fall through to hardcoded defaults
        assert defaults == _hardcoded_defaults()

    def test_load_defaults_returns_hardcoded_on_empty_yaml(self):
        """load_defaults() should fall back to hardcoded defaults for empty YAML."""
        from config import _hardcoded_defaults, load_defaults

        # Mock an empty YAML file (yaml.safe_load returns None)
        with patch("config._find_yaml", return_value=Path("/fake/defaults.yml")):
            with patch("builtins.open", mock_open(read_data="")):
                defaults = load_defaults()

        assert defaults == _hardcoded_defaults()


class TestSettingsUsesSharedDefaults:
    """Tests that app/core/config.py Settings uses shared defaults."""

    def test_settings_llm_max_tokens_default(self):
        """Settings.LLM_MAX_TOKENS should default to shared value (16384)."""
        # Clear any env override to test the default
        env = os.environ.copy()
        env.pop("LLM_MAX_TOKENS", None)
        with patch.dict(os.environ, env, clear=True):
            # Force reimport to pick up defaults
            from app.core.config import Settings

            s = Settings()
            assert s.LLM_MAX_TOKENS == 16384

    def test_env_var_overrides_shared_default(self):
        """Environment variables must override shared defaults."""
        with patch.dict(os.environ, {"LLM_MAX_TOKENS": "4096"}):
            from app.core.config import Settings

            s = Settings()
            assert s.LLM_MAX_TOKENS == 4096
