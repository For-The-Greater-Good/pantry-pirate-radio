"""Content store implementation for deduplicating scraped content."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import structlog

if TYPE_CHECKING:
    import redis

logger = structlog.get_logger(__name__)

from app.content_store.backend import ContentStoreBackend, FileContentStoreBackend
from app.content_store.models import ContentEntry


class ContentStore:
    """Stores and deduplicates scraped content using SHA-256 hashing.

    Supports pluggable storage backends via the ContentStoreBackend protocol.
    Default is FileContentStoreBackend (filesystem + SQLite).
    """

    # SHA-256 produces 64 hex characters
    _HASH_PATTERN = re.compile(r"^[a-f0-9]{64}$")

    def __init__(
        self,
        store_path: Optional[Path] = None,
        redis_url: Optional[str] = "redis://cache:6379",
        backend: Optional[ContentStoreBackend] = None,
    ):
        """Initialize content store.

        Args:
            store_path: Base path for content store (backward compat, creates FileBackend)
            redis_url: Redis connection URL for checking job status (None to skip Redis)
            backend: Storage backend (if None, FileContentStoreBackend is created from store_path)

        Raises:
            ValueError: If neither store_path nor backend is provided
        """
        if backend is not None:
            self._backend = backend
        elif store_path is not None:
            self._backend = FileContentStoreBackend(store_path=store_path)
            self._backend.initialize()
        else:
            raise ValueError("Either store_path or backend must be provided")

        self.redis_conn: Optional[redis.Redis[bytes]] = None
        if redis_url:
            import redis as _redis

            self.redis_conn = _redis.from_url(redis_url)

    @property
    def backend(self) -> ContentStoreBackend:
        """Get the storage backend."""
        return self._backend

    @property
    def store_path(self) -> Path:
        """Base path for the store (backward compat property).

        Note: ContentStore always wraps a filesystem backend, so Path is safe.
        S3 backends are used directly, not through ContentStore.
        """
        path = self._backend.store_path
        return path if isinstance(path, Path) else Path(path)

    @property
    def content_store_path(self) -> Path:
        """Path to the content_store subdirectory (backward compat property).

        Note: ContentStore always wraps a filesystem backend, so Path is safe.
        S3 backends are used directly, not through ContentStore.
        """
        path = self._backend.content_store_path
        return path if isinstance(path, Path) else Path(path)

    def hash_content(self, content: str) -> str:
        """Generate SHA-256 hash of content.

        Args:
            content: Content to hash

        Returns:
            Hex string of SHA-256 hash
        """
        return hashlib.sha256(content.encode()).hexdigest()

    def _is_job_active(self, job_id: str) -> bool:
        """Check if a job is still active (queued or running).

        Args:
            job_id: RQ job ID

        Returns:
            True if job is queued or running, False otherwise
        """
        import redis as _redis
        from rq.exceptions import NoSuchJobError
        from rq.job import Job

        if self.redis_conn is None:
            # Without Redis (SQS mode), can't check RQ job status.
            # Return False to allow reprocessing (SQS has its own dedup).
            return False
        try:
            job = Job.fetch(job_id, connection=self.redis_conn)
            status = job.get_status()
            return status in ["queued", "started", "deferred", "scheduled"]
        except NoSuchJobError:
            # Job doesn't exist - expected for old/expired jobs
            return False
        except _redis.ConnectionError as e:
            logger.warning(
                "redis_connection_failed_checking_job",
                job_id=job_id,
                error=str(e),
            )
            # Conservative: assume job might be active to prevent duplicate processing
            return True
        except Exception as e:
            logger.error(
                "unexpected_error_checking_job",
                job_id=job_id,
                error_type=type(e).__name__,
                error=str(e),
            )
            raise

    def has_content(self, content_hash: str) -> bool:
        """Check if content exists in store.

        Args:
            content_hash: SHA-256 hash of content

        Returns:
            True if content exists

        Raises:
            ValueError: If hash format is invalid
        """
        self._validate_hash(content_hash)
        return self._backend.index_has_content(content_hash)

    def get_result(self, content_hash: str) -> Optional[str]:
        """Get processing result for content if available.

        Args:
            content_hash: SHA-256 hash of content

        Returns:
            Result JSON string if processed, None otherwise

        Raises:
            ValueError: If hash format is invalid
        """
        self._validate_hash(content_hash)
        result_data = self._backend.read_result(content_hash)

        if result_data:
            data = json.loads(result_data)
            return data["result"]

        return None

    def store_content(self, content: str, metadata: dict) -> ContentEntry:
        """Store content and check if already processed.

        Args:
            content: Raw content to store
            metadata: Additional metadata (scraper_id, etc.)

        Returns:
            ContentEntry with status and result if available
        """
        content_hash = self.hash_content(content)

        # Check if we have a result for this content
        result_data = self._backend.read_result(content_hash)
        if result_data:
            data = json.loads(result_data)
            return ContentEntry(
                hash=content_hash,
                status="completed",
                result=data["result"],
                job_id=data.get("job_id"),
            )

        # Check if content already exists with a job_id (for cleanup only)
        existing_job_id = self.get_job_id(content_hash)
        if existing_job_id and not self._is_job_active(existing_job_id):
            # Job is no longer active (failed, expired, etc.)
            # Clear the old job_id so content can be reprocessed
            self.clear_job_id(content_hash)

        # Store content if not already stored
        if not self._backend.content_exists(content_hash):
            # Write content
            content_data = {
                "content": content,
                "metadata": metadata,
                "timestamp": datetime.now(UTC).isoformat(),
            }
            content_path = self._backend.write_content(
                content_hash, json.dumps(content_data, indent=2)
            )

            # Update index
            self._backend.index_insert_content(
                content_hash, content_path, datetime.now(UTC)
            )

        # Return pending status without job_id (allow new processing)
        return ContentEntry(
            hash=content_hash, status="pending", result=None, job_id=None
        )

    def store_result(self, content_hash: str, result: str, job_id: str) -> None:
        """Store processing result for content.

        Args:
            content_hash: SHA-256 hash of content
            result: Processing result JSON
            job_id: Job ID that produced this result

        Raises:
            ValueError: If hash format is invalid
        """
        self._validate_hash(content_hash)

        # Write result
        result_data = {
            "result": result,
            "job_id": job_id,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        result_path = self._backend.write_result(
            content_hash, json.dumps(result_data, indent=2)
        )

        # Update index
        self._backend.index_update_result(
            content_hash, result_path, job_id, datetime.now(UTC)
        )

    def get_job_id(self, content_hash: str) -> Optional[str]:
        """Get job ID for a content hash.

        Args:
            content_hash: SHA-256 hash of content

        Returns:
            Job ID if found, None otherwise

        Raises:
            ValueError: If hash format is invalid
        """
        self._validate_hash(content_hash)
        return self._backend.index_get_job_id(content_hash)

    def clear_job_id(self, content_hash: str) -> None:
        """Clear job ID for a content hash.

        Args:
            content_hash: SHA-256 hash of content

        Raises:
            ValueError: If hash format is invalid
        """
        self._validate_hash(content_hash)
        self._backend.index_clear_job_id(content_hash)

    def link_job(self, content_hash: str, job_id: str) -> None:
        """Link a job ID to a content hash.

        Args:
            content_hash: SHA-256 hash of content
            job_id: Job ID processing this content

        Raises:
            ValueError: If hash format is invalid
        """
        self._validate_hash(content_hash)
        self._backend.index_set_job_id(content_hash, job_id)

    def get_statistics(self) -> dict:
        """Get statistics about stored content.

        Returns:
            Dictionary with statistics
        """
        stats = self._backend.index_get_statistics()
        total = stats["total_content"]

        # Calculate store size - skip for performance if store is large
        if total < 1000:
            store_size = self._backend.get_store_size_bytes()
        else:
            # For large stores, estimate: ~1KB per file average
            store_size = total * 1024

        return {
            **stats,
            "store_size_bytes": store_size,
        }

    def _validate_hash(self, content_hash: str) -> None:
        """Validate hash format for security.

        Args:
            content_hash: Hash to validate

        Raises:
            ValueError: If hash format is invalid
        """
        if not self._HASH_PATTERN.match(content_hash):
            raise ValueError(
                f"Invalid hash format: expected 64 hex characters, got: {content_hash}"
            )

    def _get_content_path(self, content_hash: str) -> Path:
        """Get path for content file (backward compat helper).

        Args:
            content_hash: SHA-256 hash

        Returns:
            Path to content file

        Raises:
            ValueError: If hash format is invalid
        """
        self._validate_hash(content_hash)
        prefix = content_hash[:2]
        return self.content_store_path / "content" / prefix / f"{content_hash}.json"

    def _get_result_path(self, content_hash: str) -> Path:
        """Get path for result file (backward compat helper).

        Args:
            content_hash: SHA-256 hash

        Returns:
            Path to result file

        Raises:
            ValueError: If hash format is invalid
        """
        self._validate_hash(content_hash)
        prefix = content_hash[:2]
        return self.content_store_path / "results" / prefix / f"{content_hash}.json"
