"""Application configuration."""

from pydantic import model_validator
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


# Create settings instance
settings = Settings()
