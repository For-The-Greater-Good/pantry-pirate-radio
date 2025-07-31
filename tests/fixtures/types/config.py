"""Type definitions for configuration."""

import os
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
    # Use TEST_ prefixed environment variables for test isolation
    test_database_url = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+psycopg2://postgres:pirate@db:5432/test_pantry_pirate_radio",
    )
    test_redis_url = os.getenv("TEST_REDIS_URL", "redis://cache:6379/1")

    # Safety check: ensure we're not using production URLs
    prod_database_url = os.getenv("DATABASE_URL", "")
    prod_redis_url = os.getenv("REDIS_URL", "")

    if test_database_url == prod_database_url and prod_database_url:
        raise ValueError(
            "TEST_DATABASE_URL is the same as DATABASE_URL! "
            "Tests must use a separate database to avoid data loss."
        )

    if test_redis_url == prod_redis_url and prod_redis_url:
        raise ValueError(
            "TEST_REDIS_URL is the same as REDIS_URL! "
            "Tests must use a separate Redis instance to avoid data loss."
        )

    return Settings(
        DATABASE_URL=test_database_url,
        REDIS_URL=test_redis_url,
        DEBUG=True,
        TESTING=True,
        DB_ECHO=True,
        LLM_MODEL_NAME=os.getenv("LLM_MODEL_NAME", "test-model"),
    )
