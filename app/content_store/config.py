"""Configuration for content store."""

import os
from pathlib import Path
from typing import Optional

from app.content_store.backend import ContentStoreBackend, FileContentStoreBackend
from app.content_store.store import ContentStore

# Global instance
_content_store_instance: Optional[ContentStore] = None
_content_store_initialized = False


def get_content_store() -> ContentStore | None:
    """Get the configured content store instance.

    Reads configuration from environment variables:
    - CONTENT_STORE_PATH: Path to store content (required for enablement)
    - CONTENT_STORE_ENABLED: Explicitly enable/disable (default: enabled if path set)
    - CONTENT_STORE_BACKEND: Backend type ("file" or "s3", default: "file")

    Returns:
        ContentStore instance or None if not configured/disabled
    """
    global _content_store_instance, _content_store_initialized

    if not _content_store_initialized:
        _content_store_instance = _create_content_store()
        _content_store_initialized = True

    return _content_store_instance


def reset_content_store() -> None:
    """Reset content store singleton. Used for testing."""
    global _content_store_instance, _content_store_initialized
    _content_store_instance = None
    _content_store_initialized = False


def _create_backend(store_path: Path, backend_type: str) -> ContentStoreBackend:
    """Create the appropriate backend based on configuration.

    Args:
        store_path: Base path for content store (used for file backend)
        backend_type: Backend type ("file" or "s3")

    Returns:
        Configured backend instance

    Raises:
        ValueError: If backend_type is not supported or required env vars missing
    """
    backend: ContentStoreBackend
    if backend_type == "file":
        backend = FileContentStoreBackend(store_path=store_path)
        backend.initialize()
        return backend
    elif backend_type == "s3":
        from app.content_store.backend_s3 import S3ContentStoreBackend

        # S3 backend requires bucket and table names from environment
        s3_bucket = os.environ.get("CONTENT_STORE_S3_BUCKET")
        dynamodb_table = os.environ.get("CONTENT_STORE_DYNAMODB_TABLE")
        region_name = os.environ.get("AWS_DEFAULT_REGION")
        s3_prefix = os.environ.get("CONTENT_STORE_S3_PREFIX", "")

        if not s3_bucket:
            raise ValueError(
                "CONTENT_STORE_S3_BUCKET is required when using S3 backend. "
                "Set CONTENT_STORE_BACKEND=file for local development."
            )
        if not dynamodb_table:
            raise ValueError(
                "CONTENT_STORE_DYNAMODB_TABLE is required when using S3 backend. "
                "Set CONTENT_STORE_BACKEND=file for local development."
            )

        backend = S3ContentStoreBackend(
            s3_bucket=s3_bucket,
            dynamodb_table=dynamodb_table,
            region_name=region_name,
            s3_prefix=s3_prefix,
        )
        backend.initialize()
        return backend
    else:
        raise ValueError(
            f"Unknown CONTENT_STORE_BACKEND: {backend_type}. "
            "Supported values: file, s3"
        )


def _create_content_store() -> ContentStore | None:
    """Create content store based on environment configuration."""
    # Check if explicitly disabled
    enabled_str = os.environ.get("CONTENT_STORE_ENABLED", "").lower()
    if enabled_str in ["false", "0", "no"]:
        return None

    # Get store path
    store_path_str = os.environ.get("CONTENT_STORE_PATH")

    # If no path and not explicitly enabled, return None
    if not store_path_str and enabled_str not in ["true", "1", "yes"]:
        return None

    # Use default path if enabled but no path specified
    if not store_path_str:
        # Default to content_store directory in project root
        # More robust path resolution
        try:
            # Try to find the project root by looking for pyproject.toml
            current_path = Path(__file__).resolve()
            for parent in [current_path, *current_path.parents]:
                if (parent / "pyproject.toml").exists():
                    project_root = parent
                    break
            else:
                # Fallback to relative path from this file
                project_root = Path(__file__).resolve().parent.parent.parent

            store_path = project_root / "content_store"
        except Exception:
            # Ultimate fallback to working directory
            store_path = Path.cwd() / "content_store"
    else:
        store_path = Path(store_path_str)

    # Create directory if it doesn't exist (for file backend)
    store_path.mkdir(parents=True, exist_ok=True)

    # Get backend type from environment
    backend_type = os.environ.get("CONTENT_STORE_BACKEND", "file").lower()

    # Create backend
    backend = _create_backend(store_path, backend_type)

    # Get Redis URL from environment (only needed for Redis queue backend)
    queue_backend = os.environ.get("QUEUE_BACKEND", "redis").lower()
    if queue_backend == "redis":
        redis_url = os.getenv("REDIS_URL", "redis://cache:6379")
    else:
        redis_url = None

    return ContentStore(backend=backend, redis_url=redis_url)
