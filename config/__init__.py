"""Shared pipeline configuration loader.

Loads defaults from config/defaults.yml and exposes them as a flat dict
mapping environment variable names to their default values.

Usage:
    from config import load_defaults

    defaults = load_defaults()
    # {"LLM_TEMPERATURE": 0.7, "LLM_MAX_TOKENS": 64768, ...}
"""

from pathlib import Path
from typing import Any


def _hardcoded_defaults() -> dict[str, Any]:
    """Hardcoded fallback matching config/defaults.yml exactly.

    Used when YAML file is not available (e.g., CDK Docker container
    without a mount). Tested for parity with the YAML file.
    """
    return {
        "LLM_TEMPERATURE": 0.7,
        "LLM_MAX_TOKENS": 64768,
        "LLM_TIMEOUT": 30,
        "LLM_RETRIES": 3,
        "VALIDATOR_ENABLED": True,
        "VALIDATION_REJECTION_THRESHOLD": 10,
        "VALIDATOR_ENRICHMENT_ENABLED": True,
        "ENRICHMENT_CACHE_TTL": 86400,
        "ENRICHMENT_TIMEOUT": 30,
        "ENRICHMENT_GEOCODING_PROVIDERS": ["arcgis", "nominatim", "census"],
        "GEOCODING_PROVIDER": "arcgis",
        "GEOCODING_ENABLE_FALLBACK": True,
        "GEOCODING_MAX_RETRIES": 3,
        "GEOCODING_TIMEOUT": 10,
        "CONTENT_STORE_ENABLED": True,
        "RECONCILER_LOCATION_TOLERANCE": 0.0001,
    }


# Mapping from YAML nested keys to flat environment variable names
_KEY_MAP: dict[str, str] = {
    "llm.temperature": "LLM_TEMPERATURE",
    "llm.max_tokens": "LLM_MAX_TOKENS",
    "llm.timeout": "LLM_TIMEOUT",
    "llm.retries": "LLM_RETRIES",
    "validation.enabled": "VALIDATOR_ENABLED",
    "validation.rejection_threshold": "VALIDATION_REJECTION_THRESHOLD",
    "enrichment.enabled": "VALIDATOR_ENRICHMENT_ENABLED",
    "enrichment.cache_ttl": "ENRICHMENT_CACHE_TTL",
    "enrichment.timeout": "ENRICHMENT_TIMEOUT",
    "enrichment.geocoding_providers": "ENRICHMENT_GEOCODING_PROVIDERS",
    "geocoding.provider": "GEOCODING_PROVIDER",
    "geocoding.enable_fallback": "GEOCODING_ENABLE_FALLBACK",
    "geocoding.max_retries": "GEOCODING_MAX_RETRIES",
    "geocoding.timeout": "GEOCODING_TIMEOUT",
    "content_store.enabled": "CONTENT_STORE_ENABLED",
    "reconciler.location_tolerance": "RECONCILER_LOCATION_TOLERANCE",
}


def _flatten(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert nested YAML structure to flat env-var-named dict.

    Args:
        raw: Parsed YAML dict with nested sections.

    Returns:
        Flat dict mapping env var names to values.
    """
    result: dict[str, Any] = {}
    for section_key, section in raw.items():
        if not isinstance(section, dict):
            continue
        for key, value in section.items():
            dotted = f"{section_key}.{key}"
            env_name = _KEY_MAP.get(dotted)
            if env_name:
                result[env_name] = value
    return result


def _find_yaml() -> Path | None:
    """Search for defaults.yml in known locations.

    Checks:
    1. Same directory as this module (config/defaults.yml)
    2. /config/defaults.yml (Docker mount)
    3. /app/config/defaults.yml (alternate Docker mount)
    """
    candidates = [
        Path(__file__).parent / "defaults.yml",
        Path("/config/defaults.yml"),
        Path("/app/config/defaults.yml"),
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def load_defaults() -> dict[str, Any]:
    """Load shared pipeline defaults.

    Tries to load from config/defaults.yml, falls back to hardcoded
    defaults if the YAML file is not found or PyYAML is not installed.

    Returns:
        Flat dict mapping env var names to default values.
    """
    yaml_path = _find_yaml()
    if yaml_path:
        try:
            import yaml

            with open(yaml_path) as f:
                raw = yaml.safe_load(f)
            if raw and isinstance(raw, dict):
                return _flatten(raw)
        except ImportError:
            pass
        except Exception:
            pass

    return _hardcoded_defaults()
