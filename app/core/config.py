"""Application configuration."""

import urllib.parse
import warnings
from typing import Any, Dict

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

try:
    from config import load_defaults as _load_shared_defaults  # type: ignore[attr-defined]

    _SHARED = _load_shared_defaults()
except ImportError:
    _SHARED = None  # config module not on sys.path; use inline defaults
except Exception as _exc:
    warnings.warn(f"Failed to load shared config defaults: {_exc}", stacklevel=1)
    _SHARED = None

if _SHARED is None:
    _SHARED = {
        "LLM_TEMPERATURE": 0.7,
        "LLM_MAX_TOKENS": 16384,
        "LLM_TIMEOUT": 30,
        "LLM_RETRIES": 3,
        "VALIDATOR_ENABLED": True,
        "VALIDATION_REJECTION_THRESHOLD": 10,
        "VALIDATOR_ENRICHMENT_ENABLED": True,
        "ENRICHMENT_CACHE_TTL": 86400,
        "ENRICHMENT_TIMEOUT": 30,
        "ENRICHMENT_GEOCODING_PROVIDERS": [
            "amazon-location",
            "arcgis",
            "nominatim",
            "census",
        ],
        "GEOCODING_PROVIDER": "arcgis",
        "GEOCODING_ENABLE_FALLBACK": True,
        "GEOCODING_MAX_RETRIES": 3,
        "GEOCODING_TIMEOUT": 10,
        "CONTENT_STORE_ENABLED": True,
        "RECONCILER_LOCATION_TOLERANCE": 0.0001,
        "SUBMARINE_ENABLED": True,
        "SUBMARINE_CRAWL_TIMEOUT": 30,
        "SUBMARINE_MAX_PAGES_PER_SITE": 3,
        "SUBMARINE_MIN_CRAWL_DELAY": 5,
        "SUBMARINE_MAX_ATTEMPTS": 3,
        "SUBMARINE_COOLDOWN_SUCCESS_DAYS": 30,
        "SUBMARINE_COOLDOWN_NO_DATA_DAYS": 90,
        "SUBMARINE_COOLDOWN_ERROR_DAYS": 14,
    }


class Settings(BaseSettings):
    """
    Application settings.

    Environment variables will be loaded and validated using Pydantic.
    Shared pipeline defaults are loaded from config/defaults.yml.
    """

    app_name: str = "Pantry Pirate Radio"
    version: str = "0.1.0"
    api_prefix: str = "/api/v1"

    # CORS Settings
    cors_origins: list[str] = ["*"]  # Default to allow all in development
    cors_allow_credentials: bool = False

    # Database Settings
    DATABASE_URL: str = "postgresql://user:password@localhost/db"
    MAX_CONNECTIONS: int = 10

    # Redis Settings
    REDIS_URL: str = "redis://localhost:6379"
    REDIS_POOL_SIZE: int = 10
    REDIS_TTL_SECONDS: int = Field(
        default=2592000, ge=0
    )  # 30 days default TTL for job results and failures

    # Logging Settings
    LOG_LEVEL: str = "INFO"
    JSON_LOGS: bool = True

    # LLM Settings
    LLM_PROVIDER: str = "openai"  # Default to openai
    LLM_MODEL_NAME: str = "gpt-4o-mini"
    LLM_TEMPERATURE: float = _SHARED["LLM_TEMPERATURE"]
    LLM_MAX_TOKENS: int | None = _SHARED["LLM_MAX_TOKENS"]
    LLM_TIMEOUT: int = _SHARED["LLM_TIMEOUT"]
    LLM_RETRIES: int = _SHARED["LLM_RETRIES"]
    LLM_WORKER_COUNT: int = 2
    LLM_QUEUE_KEY: str = "llm:jobs"
    LLM_CONSUMER_GROUP: str = "llm-workers"

    # API Keys
    OPENROUTER_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None

    # AWS Bedrock Settings
    AWS_DEFAULT_REGION: str | None = None
    AWS_PROFILE: str | None = None

    # Claude Quota Management
    CLAUDE_QUOTA_RETRY_DELAY: int = 3600  # 1 hour initial delay when quota exceeded
    CLAUDE_QUOTA_MAX_DELAY: int = 14400  # 4 hours max delay
    CLAUDE_QUOTA_BACKOFF_MULTIPLIER: float = 1.5  # Exponential backoff multiplier

    # Reconciler Settings
    RECONCILER_LOCATION_TOLERANCE: float = Field(
        default=_SHARED["RECONCILER_LOCATION_TOLERANCE"],
        description="Coordinate matching tolerance in degrees for location deduplication. "
        "0.0001 = ~11 meters (default, good for precise matching), "
        "0.001 = ~111 meters (looser matching for sparse areas), "
        "0.00001 = ~1.1 meters (very precise, may create duplicates)",
        ge=0.00001,  # ~1.1 meters minimum
        le=0.01,  # ~1.1 km maximum
    )

    # Validator Settings
    VALIDATOR_ENABLED: bool = _SHARED["VALIDATOR_ENABLED"]
    VALIDATOR_QUEUE_NAME: str = "validator"
    VALIDATOR_REDIS_TTL: int = 3600
    VALIDATOR_LOG_DATA_FLOW: bool = False
    VALIDATOR_ONLY_HSDS: bool = True
    VALIDATOR_CONFIDENCE_THRESHOLD: float = 0.7

    # Validation Rules Settings
    VALIDATION_REJECTION_THRESHOLD: int = Field(
        default=_SHARED["VALIDATION_REJECTION_THRESHOLD"],
        description="Confidence score below this threshold triggers rejection. "
        "Default of 10 filters out clearly invalid data (0,0 coords, missing data) "
        "while preserving borderline cases for review",
        ge=0,
        le=100,
    )
    VALIDATION_STRICT_MODE: bool = False  # Enable stricter validation in production
    VALIDATION_TEST_DATA_PATTERNS: list[str] = Field(
        default_factory=lambda: [
            "test",
            "demo",
            "example",
            "sample",
            "dummy",
            "fake",
            "anytown",
            "unknown",
        ]
    )
    VALIDATION_PLACEHOLDER_PATTERNS: list[str] = Field(
        default_factory=lambda: [
            r"^\d{1,3}\s+(main|first|second|third|test|example)\s+(st|street|ave|avenue|rd|road)",
            r"^1\s+.+\s+(street|avenue|road|lane|way|drive|court|place)$",
        ]
    )
    VALIDATION_RULES_CONFIG: dict = Field(
        default_factory=lambda: {
            "check_coordinates": True,
            "check_us_bounds": True,
            "check_state_match": True,
            "detect_test_data": True,
            "detect_placeholders": True,
        }
    )

    # Enrichment Settings
    VALIDATOR_ENRICHMENT_ENABLED: bool = _SHARED["VALIDATOR_ENRICHMENT_ENABLED"]
    ENRICHMENT_GEOCODING_PROVIDERS: list[str] = Field(
        default=_SHARED["ENRICHMENT_GEOCODING_PROVIDERS"],
        description="Geocoding providers in priority order. ArcGIS is fastest and most reliable, "
        "Nominatim is open-source but rate-limited, Census is US government data.",
    )
    ENRICHMENT_TIMEOUT: int = _SHARED["ENRICHMENT_TIMEOUT"]
    ENRICHMENT_CACHE_TTL: int = _SHARED["ENRICHMENT_CACHE_TTL"]

    # Provider-specific configuration
    ENRICHMENT_PROVIDER_CONFIG: Dict[str, Dict[str, Any]] = Field(
        default={
            "amazon-location": {
                "timeout": 10,  # AWS internal service, low latency
                "max_retries": 3,
                "rate_limit": 50,  # requests per second
                "circuit_breaker_threshold": 5,  # failures before opening circuit
                "circuit_breaker_cooldown": 300,  # cooldown in seconds
            },
            "arcgis": {
                "timeout": 10,  # Fast commercial service
                "max_retries": 3,
                "rate_limit": 100,  # requests per second
                "circuit_breaker_threshold": 5,  # failures before opening circuit
                "circuit_breaker_cooldown": 300,  # cooldown in seconds
            },
            "nominatim": {
                "timeout": 15,  # Open-source, can be slower
                "max_retries": 2,
                "rate_limit": 1,  # strict rate limit for free tier
                "circuit_breaker_threshold": 3,
                "circuit_breaker_cooldown": 600,  # longer cooldown for rate-limited service
            },
            "census": {
                "timeout": 10,  # US government service
                "max_retries": 3,
                "rate_limit": 50,  # moderate rate limit
                "circuit_breaker_threshold": 5,
                "circuit_breaker_cooldown": 300,
            },
        },
        description="Per-provider configuration for timeouts, retries, and circuit breaker settings",
    )

    # Submarine Settings
    SUBMARINE_ENABLED: bool = _SHARED["SUBMARINE_ENABLED"]
    SUBMARINE_CRAWL_TIMEOUT: int = Field(
        default=_SHARED["SUBMARINE_CRAWL_TIMEOUT"], ge=1
    )
    SUBMARINE_MAX_PAGES_PER_SITE: int = Field(
        default=_SHARED["SUBMARINE_MAX_PAGES_PER_SITE"], ge=1, le=10
    )
    SUBMARINE_MIN_CRAWL_DELAY: int = Field(
        default=_SHARED["SUBMARINE_MIN_CRAWL_DELAY"], ge=0
    )
    SUBMARINE_MAX_ATTEMPTS: int = Field(default=_SHARED["SUBMARINE_MAX_ATTEMPTS"], ge=1)
    SUBMARINE_COOLDOWN_SUCCESS_DAYS: int = Field(
        default=_SHARED["SUBMARINE_COOLDOWN_SUCCESS_DAYS"], ge=0
    )
    SUBMARINE_COOLDOWN_NO_DATA_DAYS: int = Field(
        default=_SHARED["SUBMARINE_COOLDOWN_NO_DATA_DAYS"], ge=0
    )
    SUBMARINE_COOLDOWN_ERROR_DAYS: int = Field(
        default=_SHARED["SUBMARINE_COOLDOWN_ERROR_DAYS"], ge=0
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="allow",  # Allow extra fields in environment
    )

    @model_validator(mode="after")
    def build_database_url_from_components(self) -> "Settings":
        """Build DATABASE_URL from individual env vars if DATABASE_HOST is set.

        Supports AWS Secrets Manager: if DATABASE_SECRET_ARN is set, fetches
        the password from Secrets Manager instead of DATABASE_PASSWORD.
        """
        import json
        import os

        db_host = os.environ.get("DATABASE_HOST")
        if db_host and "localhost" in self.DATABASE_URL:
            db_name = os.environ.get("DATABASE_NAME", "pantry_pirate_radio")
            db_user = os.environ.get("DATABASE_USER", "postgres")
            db_port = os.environ.get("DATABASE_PORT", "5432")

            # Fetch password from Secrets Manager if ARN is provided
            secret_arn = os.environ.get("DATABASE_SECRET_ARN")
            if secret_arn:
                try:
                    import boto3
                except ImportError as exc:
                    raise ValueError(
                        "boto3 is required when DATABASE_SECRET_ARN is set"
                    ) from exc

                import botocore.exceptions

                try:
                    client = boto3.client("secretsmanager")
                    response = client.get_secret_value(SecretId=secret_arn)
                except botocore.exceptions.ClientError as exc:
                    error_code = exc.response["Error"]["Code"]
                    raise ValueError(
                        f"Failed to fetch secret from Secrets Manager "
                        f"(ARN: {secret_arn}, error code: {error_code}): {exc}"
                    ) from exc

                try:
                    secret = json.loads(response["SecretString"])
                except (KeyError, json.JSONDecodeError) as exc:
                    raise ValueError(
                        "Secrets Manager response missing or invalid SecretString"
                    ) from exc

                if "password" not in secret:
                    raise ValueError("Secret does not contain expected 'password' key")
                db_password = secret["password"]
            else:
                db_password = os.environ.get("DATABASE_PASSWORD", "")

            encoded_password = urllib.parse.quote_plus(db_password)
            self.DATABASE_URL = f"postgresql://{db_user}:{encoded_password}@{db_host}:{db_port}/{db_name}"
        return self

    @model_validator(mode="after")
    def validate_origins(self) -> "Settings":
        """Validate CORS origins."""
        if self.cors_origins == ["*"]:
            self.cors_origins = [
                "http://localhost",
                "http://localhost:8000",
                "http://localhost:3000",
            ]
        return self

    @model_validator(mode="after")
    def use_test_configs_for_testing(self) -> "Settings":
        """Use test database and Redis for tests to ensure isolation."""
        import os

        if os.getenv("TESTING") == "true":
            # Use TEST_DATABASE_URL if provided
            test_database_url = os.getenv("TEST_DATABASE_URL")
            if test_database_url:
                self.DATABASE_URL = test_database_url
            elif "test_" not in self.DATABASE_URL:
                # Add test_ prefix to database name if not already present
                # This is a safety measure to avoid using production database
                import re

                # Match postgresql://user:pass@host:port/dbname pattern
                match = re.match(r"(.*/)([^/]+)$", self.DATABASE_URL)
                if match:
                    base_url = match.group(1)
                    db_name = match.group(2)
                    if not db_name.startswith("test_"):
                        self.DATABASE_URL = f"{base_url}test_{db_name}"

            # Use TEST_REDIS_URL if provided, otherwise switch to database 1
            test_redis_url = os.getenv("TEST_REDIS_URL")
            if test_redis_url:
                self.REDIS_URL = test_redis_url
            elif "/0" in self.REDIS_URL:
                # Switch from database 0 to database 1 for tests
                self.REDIS_URL = self.REDIS_URL.replace("/0", "/1")
            elif not self.REDIS_URL.endswith("/1"):
                # Add database 1 if no database specified
                if self.REDIS_URL.endswith("/"):
                    self.REDIS_URL = self.REDIS_URL + "1"
                else:
                    self.REDIS_URL = self.REDIS_URL + "/1"
        return self


# Create settings instance
settings = Settings()
