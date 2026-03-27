"""Environment variable and secret builders for pipeline services.

Extracted from ServicesStack to keep file sizes under the 600-line
Constitution IX limit. Each function takes a ServiceConfig and returns
the dict expected by ECS container definitions.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

from aws_cdk import aws_ecs as ecs
from shared_config import SHARED

if TYPE_CHECKING:
    from stacks.services_stack import ServiceConfig


def _warn_missing_required(service: str, required: dict[str, str]) -> None:
    """Warn if any required environment values are empty strings.

    Args:
        service: Service name for the warning message
        required: Dict of {env_var_name: value} to check
    """
    missing = [k for k, v in required.items() if not v]
    if missing:
        warnings.warn(
            f"{service} service: required config values are empty: "
            f"{', '.join(missing)}. Service may not function correctly.",
            stacklevel=3,
        )


def get_validator_environment(config: ServiceConfig) -> dict[str, str]:
    """Get environment variables for the Validator service."""
    env = {
        "QUEUE_BACKEND": "sqs",
        "CONTENT_STORE_BACKEND": "s3",
        # Shared pipeline config — geocoding and validation
        "GEOCODING_PROVIDER": SHARED["GEOCODING_PROVIDER"],
        "GEOCODING_ENABLE_FALLBACK": SHARED["GEOCODING_ENABLE_FALLBACK"],
        "GEOCODING_MAX_RETRIES": SHARED["GEOCODING_MAX_RETRIES"],
        "GEOCODING_TIMEOUT": SHARED["GEOCODING_TIMEOUT"],
        "ENRICHMENT_GEOCODING_PROVIDERS": SHARED["ENRICHMENT_GEOCODING_PROVIDERS"],
        "ENRICHMENT_CACHE_TTL": SHARED["ENRICHMENT_CACHE_TTL"],
        "ENRICHMENT_TIMEOUT": SHARED["ENRICHMENT_TIMEOUT"],
        "VALIDATOR_ENABLED": SHARED["VALIDATOR_ENABLED"],
        "VALIDATION_REJECTION_THRESHOLD": SHARED["VALIDATION_REJECTION_THRESHOLD"],
        "VALIDATOR_ENRICHMENT_ENABLED": SHARED["VALIDATOR_ENRICHMENT_ENABLED"],
    }
    # ARCGIS_API_KEY is passed as a secret via get_validator_secrets()
    if config.database_host:
        env["DATABASE_HOST"] = config.database_host
    if config.database_name:
        env["DATABASE_NAME"] = config.database_name
    if config.database_user:
        env["DATABASE_USER"] = config.database_user
    if config.queue_urls.get("validator"):
        env["VALIDATOR_QUEUE_URL"] = config.queue_urls["validator"]
    if config.queue_urls.get("reconciler"):
        env["RECONCILER_QUEUE_URL"] = config.queue_urls["reconciler"]
    if config.content_bucket_name:
        env["CONTENT_STORE_S3_BUCKET"] = config.content_bucket_name
    if config.content_index_table_name:
        env["CONTENT_STORE_DYNAMODB_TABLE"] = config.content_index_table_name
    if config.geocoding_cache_table_name:
        env["GEOCODING_CACHE_TABLE"] = config.geocoding_cache_table_name
    if config.place_index_name:
        env["AMAZON_LOCATION_INDEX"] = config.place_index_name
        env["GEOCODING_PROVIDER"] = "amazon-location"
    _warn_missing_required(
        "Validator",
        {
            "VALIDATOR_QUEUE_URL": config.queue_urls.get("validator", ""),
            "RECONCILER_QUEUE_URL": config.queue_urls.get("reconciler", ""),
        },
    )
    return env


def get_validator_secrets(config: ServiceConfig) -> dict[str, ecs.Secret]:
    """Get secrets for the Validator service."""
    secrets: dict[str, ecs.Secret] = {}
    if config.database_secret:
        secrets["DATABASE_PASSWORD"] = ecs.Secret.from_secrets_manager(
            config.database_secret, "password"
        )
    if config.llm_api_keys_secret:
        secrets["ARCGIS_API_KEY"] = ecs.Secret.from_secrets_manager(
            config.llm_api_keys_secret, "ARCGIS_API_KEY"
        )
    return secrets


def get_reconciler_environment(config: ServiceConfig) -> dict[str, str]:
    """Get environment variables for the Reconciler service."""
    env: dict[str, str] = {
        "QUEUE_BACKEND": "sqs",
    }
    if config.database_host:
        env["DATABASE_HOST"] = config.database_host
    if config.database_name:
        env["DATABASE_NAME"] = config.database_name
    if config.database_user:
        env["DATABASE_USER"] = config.database_user
    if config.queue_urls.get("reconciler"):
        env["RECONCILER_QUEUE_URL"] = config.queue_urls["reconciler"]
    if config.queue_urls.get("recorder"):
        env["RECORDER_QUEUE_URL"] = config.queue_urls["recorder"]
    _warn_missing_required(
        "Reconciler",
        {
            "RECONCILER_QUEUE_URL": config.queue_urls.get("reconciler", ""),
            "RECORDER_QUEUE_URL": config.queue_urls.get("recorder", ""),
        },
    )
    return env


def get_reconciler_secrets(config: ServiceConfig) -> dict[str, ecs.Secret]:
    """Get secrets for the Reconciler service."""
    secrets: dict[str, ecs.Secret] = {}
    if config.database_secret:
        secrets["DATABASE_PASSWORD"] = ecs.Secret.from_secrets_manager(
            config.database_secret, "password"
        )
    return secrets


def get_publisher_environment(
    config: ServiceConfig, environment_name: str
) -> dict[str, str]:
    """Get environment variables for the Publisher task."""
    env = {
        "ENVIRONMENT": environment_name,
        "SERVICE_NAME": "publisher",
    }
    if config.database_host:
        env["DATABASE_HOST"] = config.database_host
    if config.database_name:
        env["DATABASE_NAME"] = config.database_name
    if config.database_user:
        env["DATABASE_USER"] = config.database_user
    if config.exports_bucket_name:
        env["EXPORT_S3_BUCKET"] = config.exports_bucket_name
    return env


def get_publisher_secrets(config: ServiceConfig) -> dict[str, ecs.Secret]:
    """Get secrets for the Publisher task."""
    secrets: dict[str, ecs.Secret] = {}
    if config.database_secret:
        secrets["DATABASE_PASSWORD"] = ecs.Secret.from_secrets_manager(
            config.database_secret, "password"
        )
    return secrets


def get_recorder_environment(config: ServiceConfig) -> dict[str, str]:
    """Get environment variables for the Recorder service."""
    env: dict[str, str] = {
        "QUEUE_BACKEND": "sqs",
        "CONTENT_STORE_BACKEND": "s3",
    }
    if config.queue_urls.get("recorder"):
        env["RECORDER_QUEUE_URL"] = config.queue_urls["recorder"]
    if config.content_bucket_name:
        env["CONTENT_STORE_S3_BUCKET"] = config.content_bucket_name
        env["RECORDER_S3_BUCKET"] = config.content_bucket_name
    if config.content_index_table_name:
        env["CONTENT_STORE_DYNAMODB_TABLE"] = config.content_index_table_name
    _warn_missing_required(
        "Recorder",
        {
            "RECORDER_QUEUE_URL": config.queue_urls.get("recorder", ""),
        },
    )
    return env


def get_recorder_secrets(config: ServiceConfig) -> dict[str, ecs.Secret]:
    """Get secrets for the Recorder service."""
    # Recorder doesn't need any secrets
    return {}


def get_submarine_environment(config: ServiceConfig) -> dict[str, str]:
    """Get environment variables for the Submarine service."""
    env: dict[str, str] = {
        "QUEUE_BACKEND": "sqs",
    }
    if config.database_host:
        env["DATABASE_HOST"] = config.database_host
    if config.database_name:
        env["DATABASE_NAME"] = config.database_name
    if config.database_user:
        env["DATABASE_USER"] = config.database_user
    if config.queue_urls.get("submarine"):
        env["SUBMARINE_QUEUE_URL"] = config.queue_urls["submarine"]
    if config.queue_urls.get("reconciler"):
        env["RECONCILER_QUEUE_URL"] = config.queue_urls["reconciler"]
    _warn_missing_required(
        "Submarine",
        {
            "SUBMARINE_QUEUE_URL": config.queue_urls.get("submarine", ""),
            "RECONCILER_QUEUE_URL": config.queue_urls.get("reconciler", ""),
        },
    )
    return env


def get_submarine_secrets(config: ServiceConfig) -> dict[str, ecs.Secret]:
    """Get secrets for the Submarine service."""
    secrets: dict[str, ecs.Secret] = {}
    if config.database_secret:
        secrets["DATABASE_PASSWORD"] = ecs.Secret.from_secrets_manager(
            config.database_secret, "password"
        )
    if config.llm_api_keys_secret:
        secrets["ANTHROPIC_API_KEY"] = ecs.Secret.from_secrets_manager(
            config.llm_api_keys_secret, "ANTHROPIC_API_KEY"
        )
    return secrets


def get_scraper_environment(
    config: ServiceConfig, environment_name: str
) -> dict[str, str]:
    """Get environment variables for the Scraper tasks."""
    env = {
        "ENVIRONMENT": environment_name,
        "SERVICE_TYPE": "scraper",
        "SERVICE_NAME": "scraper",
        "SCRAPER_NAME": "placeholder",  # Overridden at runtime by Step Functions
        "QUEUE_BACKEND": "sqs",
        "CONTENT_STORE_BACKEND": "s3",
        "CONTENT_STORE_ENABLED": "true",
        "CONTENT_STORE_PATH": "/tmp/content_store",
    }
    if config.database_host:
        env["DATABASE_HOST"] = config.database_host
    if config.database_name:
        env["DATABASE_NAME"] = config.database_name
    if config.database_user:
        env["DATABASE_USER"] = config.database_user
    if config.queue_urls.get("llm"):
        env["LLM_QUEUE_URL"] = config.queue_urls["llm"]
        env["SQS_QUEUE_URL"] = config.queue_urls["llm"]
    if config.jobs_table_name:
        env["SQS_JOBS_TABLE"] = config.jobs_table_name
    if config.content_bucket_name:
        env["CONTENT_STORE_S3_BUCKET"] = config.content_bucket_name
    if config.content_index_table_name:
        env["CONTENT_STORE_DYNAMODB_TABLE"] = config.content_index_table_name
    _warn_missing_required(
        "Scraper",
        {
            "SQS_QUEUE_URL": config.queue_urls.get("llm", ""),
        },
    )
    return env


def get_scraper_secrets(config: ServiceConfig) -> dict[str, ecs.Secret]:
    """Get secrets for the Scraper tasks."""
    secrets: dict[str, ecs.Secret] = {}
    if config.database_secret:
        secrets["DATABASE_PASSWORD"] = ecs.Secret.from_secrets_manager(
            config.database_secret, "password"
        )
    return secrets
