"""Application configuration."""

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings.

    Environment variables will be loaded and validated using Pydantic.
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
    LLM_TEMPERATURE: float = 0.7
    LLM_MAX_TOKENS: int | None = None
    LLM_TIMEOUT: int = 30
    LLM_RETRIES: int = 3
    LLM_WORKER_COUNT: int = 2
    LLM_QUEUE_KEY: str = "llm:jobs"
    LLM_CONSUMER_GROUP: str = "llm-workers"

    # API Keys
    OPENROUTER_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None

    # Claude Quota Management
    CLAUDE_QUOTA_RETRY_DELAY: int = 3600  # 1 hour initial delay when quota exceeded
    CLAUDE_QUOTA_MAX_DELAY: int = 14400  # 4 hours max delay
    CLAUDE_QUOTA_BACKOFF_MULTIPLIER: float = 1.5  # Exponential backoff multiplier

    # Validator Settings
    VALIDATOR_ENABLED: bool = True  # Enable validator service by default
    VALIDATOR_QUEUE_NAME: str = "validator"
    VALIDATOR_REDIS_TTL: int = 3600
    VALIDATOR_LOG_DATA_FLOW: bool = False
    VALIDATOR_ONLY_HSDS: bool = True
    VALIDATOR_CONFIDENCE_THRESHOLD: float = 0.7

    # Enrichment Settings
    VALIDATOR_ENRICHMENT_ENABLED: bool = True  # Enable geocoding enrichment
    ENRICHMENT_GEOCODING_PROVIDERS: list[str] = Field(
        default=["arcgis", "nominatim", "census"],
        description="Geocoding providers in priority order",
    )
    ENRICHMENT_TIMEOUT: int = 30  # Timeout for enrichment operations in seconds
    ENRICHMENT_CACHE_SIZE: int = 1000  # Maximum number of cached geocoding results

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="allow",  # Allow extra fields in environment
    )

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
