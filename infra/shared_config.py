"""Shared pipeline config for CDK stacks.

Loads shared defaults from config/defaults.yml and API keys from .env.
Provides SHARED (all values as strings for CDK env dicts) and SECRETS
(API keys read from .env at synth time).
"""

import sys
import warnings
from pathlib import Path
from typing import Any


def _load_shared_defaults() -> dict[str, str]:
    """Load shared pipeline config, returning string values for CDK env dicts.

    Imports config.load_defaults() to get canonical values, then converts
    all values to strings suitable for Fargate/Lambda environment dicts.

    Falls back to hardcoded string defaults if the config module is not
    importable (e.g., CDK Docker container without config/ mounted).
    """
    config_path = Path(__file__).parent.parent / "config"
    if config_path.exists() and (config_path / "__init__.py").exists():
        sys.path.insert(0, str(config_path.parent))
        try:
            from config import load_defaults

            raw = load_defaults()
            return {k: _to_env_string(v) for k, v in raw.items()}
        finally:
            sys.path.pop(0)

    warnings.warn(
        "config/ module not found — using hardcoded defaults. "
        "Values may drift from config/defaults.yml.",
        stacklevel=2,
    )
    return _hardcoded_string_defaults()


def _to_env_string(value: Any) -> str:
    """Convert a Python value to its environment variable string form.

    Booleans become lowercase "true"/"false".
    Lists become JSON-encoded strings.
    Everything else uses str().
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        import json

        return json.dumps(value)
    return str(value)


def _hardcoded_string_defaults() -> dict[str, str]:
    """Hardcoded string fallback for CDK when config module is unavailable."""
    return {
        "LLM_TEMPERATURE": "0.7",
        "LLM_MAX_TOKENS": "64768",
        "LLM_TIMEOUT": "30",
        "LLM_RETRIES": "3",
        "VALIDATOR_ENABLED": "true",
        "VALIDATION_REJECTION_THRESHOLD": "10",
        "VALIDATOR_ENRICHMENT_ENABLED": "true",
        "ENRICHMENT_CACHE_TTL": "86400",
        "ENRICHMENT_TIMEOUT": "30",
        "ENRICHMENT_GEOCODING_PROVIDERS": '["amazon-location", "arcgis", "nominatim", "census"]',
        "GEOCODING_PROVIDER": "arcgis",
        "GEOCODING_ENABLE_FALLBACK": "true",
        "GEOCODING_MAX_RETRIES": "3",
        "GEOCODING_TIMEOUT": "10",
        "CONTENT_STORE_ENABLED": "true",
        "RECONCILER_LOCATION_TOLERANCE": "0.0001",
        "TIGHTBEAM_ENABLED": "true",
    }


def _load_dotenv_secrets() -> dict[str, str]:
    """Load API keys from .env file at synth time.

    CDK reads these to pass to Fargate task environments or store in
    Secrets Manager. Returns only secret-category variables.
    """
    try:
        from dotenv import dotenv_values
    except ImportError:
        warnings.warn(
            "python-dotenv not installed — cannot load secrets from .env file.",
            stacklevel=2,
        )
        return {}

    for path in [
        Path(__file__).parent.parent / ".env",
        Path("/app/.env"),
    ]:
        if path.exists():
            values = dotenv_values(path)
            loaded = {k: v for k, v in values.items() if k in _SECRET_KEYS and v}
            missing = _SECRET_KEYS - set(loaded.keys())
            if missing:
                warnings.warn(
                    f"Missing secret keys in .env: {', '.join(sorted(missing))}. "
                    f"Some services may not have API keys configured.",
                    stacklevel=2,
                )
            return loaded

    warnings.warn(
        "No .env file found at project root or /app/.env — secrets not loaded.",
        stacklevel=2,
    )
    return {}


_SECRET_KEYS = {
    "ARCGIS_API_KEY",
    "OPENROUTER_API_KEY",
    "ANTHROPIC_API_KEY",
    "DATA_REPO_TOKEN",
    "TIGHTBEAM_API_KEYS",
}

SHARED: dict[str, str] = _load_shared_defaults()
SECRETS: dict[str, str] = _load_dotenv_secrets()
