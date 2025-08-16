"""Configuration for validator service."""

import os
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional


@dataclass
class ValidatorConfig:
    """Validator configuration.

    This dataclass holds all configuration parameters for the validator service.
    It provides validation, serialization, and easy access to settings.
    """

    enabled: bool = True
    queue_name: str = "validator"
    redis_ttl: int = 3600
    log_data_flow: bool = False
    only_hsds: bool = True
    confidence_threshold: float = 0.7

    # Additional configuration fields
    max_retries: int = 3
    retry_delay: int = 1  # seconds
    batch_size: int = 100
    timeout: int = 600  # seconds

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        self._validate()

    def _validate(self) -> None:
        """Validate configuration values.

        Raises:
            ValueError: If configuration is invalid
        """
        if not 0 <= self.confidence_threshold <= 1:
            raise ValueError(
                f"confidence_threshold must be between 0 and 1, got {self.confidence_threshold}"
            )

        if self.redis_ttl < 0:
            raise ValueError(f"redis_ttl must be non-negative, got {self.redis_ttl}")

        if self.max_retries < 0:
            raise ValueError(
                f"max_retries must be non-negative, got {self.max_retries}"
            )

        if self.batch_size <= 0:
            raise ValueError(f"batch_size must be positive, got {self.batch_size}")

        if self.timeout <= 0:
            raise ValueError(f"timeout must be positive, got {self.timeout}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Configuration as dictionary
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ValidatorConfig":
        """Create configuration from dictionary.

        Args:
            data: Configuration dictionary

        Returns:
            ValidatorConfig instance
        """
        # Filter only known fields
        known_fields = {
            "enabled",
            "queue_name",
            "redis_ttl",
            "log_data_flow",
            "only_hsds",
            "confidence_threshold",
            "max_retries",
            "retry_delay",
            "batch_size",
            "timeout",
        }
        filtered_data = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered_data)

    def merge(self, overrides: Dict[str, Any]) -> "ValidatorConfig":
        """Create new config with overrides applied.

        Args:
            overrides: Values to override

        Returns:
            New ValidatorConfig with overrides
        """
        config_dict = self.to_dict()
        config_dict.update(overrides)
        return self.from_dict(config_dict)


def get_validator_config() -> ValidatorConfig:
    """Get validator configuration from settings and environment.

    Priority order:
    1. Environment variables (highest)
    2. Settings module
    3. Default values (lowest)

    Returns:
        Validator configuration instance
    """
    from app.core.config import settings

    # Helper to get config value with priority
    def get_config_value(
        env_key: str, settings_key: str, default: Any, converter: type = str
    ) -> Any:
        """Get configuration value with priority handling.

        Args:
            env_key: Environment variable key
            settings_key: Settings attribute key
            default: Default value
            converter: Type converter function

        Returns:
            Configuration value
        """
        # Check environment first
        env_value = os.environ.get(env_key)
        if env_value is not None:
            try:
                if converter == bool:
                    return env_value.lower() not in ("false", "0", "no", "off")
                return converter(env_value)
            except (ValueError, TypeError):
                pass

        # Check settings
        if hasattr(settings, settings_key):
            return getattr(settings, settings_key)

        # Return default
        return default

    config = ValidatorConfig(
        enabled=get_config_value("VALIDATOR_ENABLED", "VALIDATOR_ENABLED", True, bool),
        queue_name=get_config_value(
            "VALIDATOR_QUEUE_NAME", "VALIDATOR_QUEUE_NAME", "validator", str
        ),
        redis_ttl=get_config_value(
            "VALIDATOR_REDIS_TTL", "VALIDATOR_REDIS_TTL", 3600, int
        ),
        log_data_flow=get_config_value(
            "VALIDATOR_LOG_DATA_FLOW", "VALIDATOR_LOG_DATA_FLOW", False, bool
        ),
        only_hsds=get_config_value(
            "VALIDATOR_ONLY_HSDS", "VALIDATOR_ONLY_HSDS", True, bool
        ),
        confidence_threshold=get_config_value(
            "VALIDATOR_CONFIDENCE_THRESHOLD",
            "VALIDATOR_CONFIDENCE_THRESHOLD",
            0.7,
            float,
        ),
        max_retries=get_config_value(
            "VALIDATOR_MAX_RETRIES", "VALIDATOR_MAX_RETRIES", 3, int
        ),
        retry_delay=get_config_value(
            "VALIDATOR_RETRY_DELAY", "VALIDATOR_RETRY_DELAY", 1, int
        ),
        batch_size=get_config_value(
            "VALIDATOR_BATCH_SIZE", "VALIDATOR_BATCH_SIZE", 100, int
        ),
        timeout=get_config_value("VALIDATOR_TIMEOUT", "VALIDATOR_TIMEOUT", 600, int),
    )

    return config


def is_validator_enabled() -> bool:
    """Check if validator is enabled.

    This is a convenience function that checks the configuration.

    Returns:
        Whether validator is enabled
    """
    config = get_validator_config()
    return config.enabled


def should_log_data_flow() -> bool:
    """Check if data flow logging is enabled.

    This is a convenience function for checking logging configuration.

    Returns:
        Whether to log data flow
    """
    config = get_validator_config()
    return config.log_data_flow


def get_validation_thresholds() -> Dict[str, float]:
    """Get validation thresholds.

    These thresholds are used to determine validation pass/fail status.

    Returns:
        Dictionary of threshold values
    """
    config = get_validator_config()

    return {
        "confidence": config.confidence_threshold,
        "geocoding_accuracy": 10.0,  # meters
        "data_completeness": 0.8,
        "phone_validity": 0.9,
        "address_validity": 0.85,
    }


def get_feature_flags() -> Dict[str, bool]:
    """Get feature flags for validation features.

    These flags control which validation checks are performed.

    Returns:
        Dictionary of feature flags
    """
    from app.core.config import settings

    # Base flags with defaults
    flags = {
        "validate_geocoding": True,
        "validate_phone_numbers": True,
        "validate_schedules": True,
        "validate_services": True,
        "validate_addresses": True,
        "validate_emails": False,  # Disabled by default
        "validate_urls": False,  # Disabled by default
    }

    # Override from settings if available
    for flag_name in flags:
        settings_key = f"VALIDATOR_{flag_name.upper()}"
        if hasattr(settings, settings_key):
            flags[flag_name] = getattr(settings, settings_key)

    return flags


def get_queue_config() -> Dict[str, Any]:
    """Get queue configuration.

    Returns complete queue configuration for RQ.

    Returns:
        Queue configuration dictionary
    """
    config = get_validator_config()

    return {
        "name": config.queue_name,
        "connection": "redis",
        "default_timeout": f"{config.timeout}s",
        "result_ttl": config.redis_ttl,
        "failure_ttl": config.redis_ttl * 24,  # 24x longer for failures
        "max_jobs": 1000,
        "is_async": True,
        "serializer": "pickle",  # For complex Python objects
    }


def get_worker_config() -> Dict[str, Any]:
    """Get worker configuration.

    Returns complete worker configuration for RQ workers.

    Returns:
        Worker configuration dictionary
    """
    from app.core.config import settings

    config = get_validator_config()

    return {
        "num_workers": getattr(settings, "VALIDATOR_WORKERS", 1),
        "max_jobs_per_worker": config.batch_size,
        "log_level": getattr(settings, "LOG_LEVEL", "INFO"),
        "burst_mode": False,
        "with_scheduler": False,
        "job_timeout": config.timeout,
        "result_ttl": config.redis_ttl,
        "failure_ttl": config.redis_ttl * 24,
    }


def get_pipeline_config() -> Dict[str, Any]:
    """Get pipeline configuration.

    Returns the complete data processing pipeline configuration.

    Returns:
        Pipeline configuration dictionary
    """
    config = get_validator_config()

    base_stages = ["scraper", "llm"]

    if config.enabled:
        base_stages.append("validator")

    base_stages.append("reconciler")

    pipeline = {
        "stages": base_stages,
        "stage_configs": {
            "scraper": {"enabled": True},
            "llm": {"enabled": True},
            "validator": {
                "enabled": config.enabled,
                "config": config.to_dict() if config.enabled else {},
            },
            "reconciler": {"enabled": True},
        },
        "error_handling": {
            "max_retries": config.max_retries,
            "retry_delay": config.retry_delay,
            "dead_letter_queue": "failed_jobs",
        },
    }

    return pipeline


# Cache for configuration to avoid repeated lookups
_config_cache: Optional[ValidatorConfig] = None
_cache_timestamp: float = 0


def reload_config() -> None:
    """Reload configuration.

    Clears the configuration cache, forcing a fresh load on next access.
    """
    global _config_cache, _cache_timestamp
    _config_cache = None
    _cache_timestamp = 0

    import logging

    logger = logging.getLogger(__name__)
    logger.info("Validator configuration cache cleared")


def get_cached_config() -> ValidatorConfig:
    """Get cached configuration.

    Returns cached config or loads fresh if cache is empty.

    Returns:
        Cached or fresh ValidatorConfig
    """
    global _config_cache, _cache_timestamp
    import time

    # Cache for 5 minutes
    cache_ttl = 300
    current_time = time.time()

    if _config_cache is None or (current_time - _cache_timestamp) > cache_ttl:
        _config_cache = get_validator_config()
        _cache_timestamp = current_time

    return _config_cache
