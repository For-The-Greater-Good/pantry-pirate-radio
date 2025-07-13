"""Type definitions for configuration."""

from dataclasses import dataclass


@dataclass
class Settings:
    """Application settings."""

    DATABASE_URL: str
    REDIS_URL: str
    DEBUG: bool = False
    TESTING: bool = False
    DB_ECHO: bool = False
    LLM_MODEL_NAME: str = "test-model"


def get_test_settings() -> Settings:
    """Get test settings."""
    return Settings(
        DATABASE_URL="postgresql+psycopg2://postgres:pirate@db:5432/pantry_pirate_radio",
        REDIS_URL="redis://cache:6379/0",
        DEBUG=True,
        TESTING=True,
        DB_ECHO=True,
        LLM_MODEL_NAME="test-model",
    )
