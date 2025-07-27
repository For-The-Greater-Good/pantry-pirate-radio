"""Configuration for content store."""

import os
from pathlib import Path
from typing import Optional

from app.content_store.store import ContentStore

# Global instance
_content_store_instance: Optional[ContentStore] = None
_content_store_initialized = False


def get_content_store() -> ContentStore | None:
    """Get the configured content store instance.

    Reads configuration from environment variables:
    - CONTENT_STORE_PATH: Path to store content (required for enablement)
    - CONTENT_STORE_ENABLED: Explicitly enable/disable (default: enabled if path set)

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

    # Create directory if it doesn't exist
    store_path.mkdir(parents=True, exist_ok=True)

    return ContentStore(store_path=store_path)
