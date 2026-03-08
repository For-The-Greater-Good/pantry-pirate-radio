"""Content store backend abstraction.

This module defines the ContentStoreBackend protocol and provides a filesystem
implementation. The protocol allows for alternative backends (e.g., S3+DynamoDB)
to be plugged in without changing the ContentStore logic.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import NewType, Optional, Protocol, TypedDict, Union, runtime_checkable

import structlog

from app.content_store.retry import with_connection_retry

logger = structlog.get_logger(__name__)

# Type-safe wrapper for SHA-256 content hash strings.
# NewType creates a distinct type for static type checkers while remaining
# a plain str at runtime, so this is fully backward compatible.
ContentHash = NewType("ContentHash", str)


class ContentStoreStatistics(TypedDict):
    """Statistics returned by index_get_statistics().

    Attributes:
        total_content: Total number of content entries
        processed_content: Number of completed/processed entries
        pending_content: Number of pending entries
    """

    total_content: int
    processed_content: int
    pending_content: int


@runtime_checkable
class ContentStoreBackend(Protocol):
    """Protocol defining the storage backend interface for ContentStore.

    Implementations must provide blob storage for content/results and an
    index for tracking content status and job associations.
    """

    # Return type is Union[Path, str] to support both filesystem paths (Path)
    # and cloud URIs (str like "s3://bucket/prefix"). Using Path for S3 URIs
    # was an LSP violation because Path normalizes "s3://" to "s3:/".
    # FileContentStoreBackend returns Path; S3ContentStoreBackend returns str.
    @property
    def store_path(self) -> Union[Path, str]:
        """Base path or URI for the store."""
        ...

    @property
    def content_store_path(self) -> Union[Path, str]:
        """Path or URI for the content_store subdirectory."""
        ...

    def initialize(self) -> None:
        """Initialize storage (create directories, tables, etc.)."""
        ...

    def write_content(self, content_hash: str, data: str) -> str:
        """Write content blob.

        Args:
            content_hash: SHA-256 hash of the content
            data: JSON string to store

        Returns:
            Path or key where content was stored
        """
        ...

    def read_content(self, content_hash: str) -> Optional[str]:
        """Read content blob.

        Args:
            content_hash: SHA-256 hash of the content

        Returns:
            JSON string if exists, None otherwise
        """
        ...

    def content_exists(self, content_hash: str) -> bool:
        """Check if content blob exists.

        Args:
            content_hash: SHA-256 hash of the content

        Returns:
            True if content file exists
        """
        ...

    def write_result(self, content_hash: str, data: str) -> str:
        """Write result blob.

        Args:
            content_hash: SHA-256 hash of the original content
            data: JSON string to store

        Returns:
            Path or key where result was stored
        """
        ...

    def read_result(self, content_hash: str) -> Optional[str]:
        """Read result blob.

        Args:
            content_hash: SHA-256 hash of the original content

        Returns:
            JSON string if exists, None otherwise
        """
        ...

    def index_has_content(self, content_hash: str) -> bool:
        """Check if content is indexed.

        Args:
            content_hash: SHA-256 hash

        Returns:
            True if content hash exists in index
        """
        ...

    def index_insert_content(
        self, content_hash: str, content_path: str, created_at: datetime
    ) -> None:
        """Insert content entry into index.

        Args:
            content_hash: SHA-256 hash
            content_path: Path/key to content blob
            created_at: Timestamp of creation
        """
        ...

    def index_update_result(
        self,
        content_hash: str,
        result_path: str,
        job_id: str,
        processed_at: datetime,
    ) -> None:
        """Update index with result information.

        Args:
            content_hash: SHA-256 hash
            result_path: Path/key to result blob
            job_id: Job ID that produced the result
            processed_at: Timestamp of processing
        """
        ...

    def index_get_job_id(self, content_hash: str) -> Optional[str]:
        """Get job ID for content.

        Args:
            content_hash: SHA-256 hash

        Returns:
            Job ID if set, None otherwise
        """
        ...

    def index_set_job_id(self, content_hash: str, job_id: str) -> None:
        """Set job ID for content.

        Args:
            content_hash: SHA-256 hash
            job_id: Job ID to associate
        """
        ...

    def index_clear_job_id(self, content_hash: str) -> None:
        """Clear job ID for content.

        Args:
            content_hash: SHA-256 hash
        """
        ...

    def index_get_statistics(self) -> ContentStoreStatistics:
        """Get index statistics.

        Returns:
            ContentStoreStatistics with total_content, processed_content, pending_content
        """
        ...

    def get_store_size_bytes(self) -> int:
        """Get total size of stored content in bytes.

        Returns:
            Total size in bytes
        """
        ...


class FileContentStoreBackend:
    """Filesystem + SQLite implementation of ContentStoreBackend.

    Stores content and results as JSON files organized by hash prefix.
    Uses SQLite for the content index with WAL mode for concurrent access.
    """

    def __init__(self, store_path: Path):
        """Initialize file content store backend.

        Args:
            store_path: Base path for content store
        """
        self._store_path = store_path
        self._content_store_path = store_path / "content_store"

    @property
    def store_path(self) -> Path:
        """Base path for the store."""
        return self._store_path

    @property
    def content_store_path(self) -> Path:
        """Path to the content_store subdirectory."""
        return self._content_store_path

    def initialize(self) -> None:
        """Create directory structure and initialize SQLite database."""
        self._init_directories()
        self._init_database()

    def _init_directories(self) -> None:
        """Create necessary directory structure."""
        (self._content_store_path / "content").mkdir(parents=True, exist_ok=True)
        (self._content_store_path / "results").mkdir(parents=True, exist_ok=True)

    @with_connection_retry
    def _init_database(self) -> None:
        """Initialize SQLite database for content index."""
        db_path = self._content_store_path / "index.db"

        with sqlite3.connect(db_path) as conn:
            # Enable WAL mode for better concurrent access
            conn.execute("PRAGMA journal_mode=WAL")

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS content_index (
                    hash TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    content_path TEXT NOT NULL,
                    result_path TEXT,
                    job_id TEXT,
                    created_at TIMESTAMP NOT NULL,
                    processed_at TIMESTAMP
                )
            """
            )
            conn.commit()

    def _get_content_path(self, content_hash: str) -> Path:
        """Get path for content file."""
        prefix = content_hash[:2]
        return self._content_store_path / "content" / prefix / f"{content_hash}.json"

    def _get_result_path(self, content_hash: str) -> Path:
        """Get path for result file."""
        prefix = content_hash[:2]
        return self._content_store_path / "results" / prefix / f"{content_hash}.json"

    def write_content(self, content_hash: str, data: str) -> str:
        """Write content blob to filesystem."""
        content_path = self._get_content_path(content_hash)
        content_path.parent.mkdir(parents=True, exist_ok=True)
        content_path.write_text(data)
        return str(content_path)

    def read_content(self, content_hash: str) -> Optional[str]:
        """Read content blob from filesystem."""
        content_path = self._get_content_path(content_hash)
        if content_path.exists():
            return content_path.read_text()
        return None

    def content_exists(self, content_hash: str) -> bool:
        """Check if content file exists."""
        return self._get_content_path(content_hash).exists()

    def write_result(self, content_hash: str, data: str) -> str:
        """Write result blob to filesystem."""
        result_path = self._get_result_path(content_hash)
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(data)
        return str(result_path)

    def read_result(self, content_hash: str) -> Optional[str]:
        """Read result blob from filesystem."""
        result_path = self._get_result_path(content_hash)
        if result_path.exists():
            return result_path.read_text()
        return None

    @with_connection_retry
    def index_has_content(self, content_hash: str) -> bool:
        """Check if content exists in SQLite index."""
        db_path = self._content_store_path / "index.db"

        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                "SELECT 1 FROM content_index WHERE hash = ?", (content_hash,)
            )
            return cursor.fetchone() is not None

    @with_connection_retry
    def index_insert_content(
        self, content_hash: str, content_path: str, created_at: datetime
    ) -> None:
        """Insert content entry into SQLite index."""
        db_path = self._content_store_path / "index.db"

        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO content_index
                (hash, status, content_path, created_at)
                VALUES (?, ?, ?, ?)
            """,
                (content_hash, "pending", content_path, created_at),
            )
            conn.commit()

    @with_connection_retry
    def index_update_result(
        self,
        content_hash: str,
        result_path: str,
        job_id: str,
        processed_at: datetime,
    ) -> None:
        """Update index with result information."""
        db_path = self._content_store_path / "index.db"

        with sqlite3.connect(db_path) as conn:
            # Try to update existing entry
            cursor = conn.execute(
                """
                UPDATE content_index
                SET status = ?, result_path = ?, job_id = ?, processed_at = ?
                WHERE hash = ?
            """,
                ("completed", result_path, job_id, processed_at, content_hash),
            )

            # If no rows updated, insert new entry
            if cursor.rowcount == 0:
                content_path = str(self._get_content_path(content_hash))
                conn.execute(
                    """
                    INSERT INTO content_index
                    (hash, status, content_path, result_path, job_id, created_at, processed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        content_hash,
                        "completed",
                        content_path,
                        result_path,
                        job_id,
                        processed_at,
                        processed_at,
                    ),
                )

            conn.commit()

    @with_connection_retry
    def index_get_job_id(self, content_hash: str) -> Optional[str]:
        """Get job ID for content from index."""
        db_path = self._content_store_path / "index.db"

        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                "SELECT job_id FROM content_index WHERE hash = ?", (content_hash,)
            )
            result = cursor.fetchone()
            return result[0] if result and result[0] else None

    @with_connection_retry
    def index_set_job_id(self, content_hash: str, job_id: str) -> None:
        """Set job ID for content in index."""
        db_path = self._content_store_path / "index.db"

        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "UPDATE content_index SET job_id = ? WHERE hash = ?",
                (job_id, content_hash),
            )
            conn.commit()

    @with_connection_retry
    def index_clear_job_id(self, content_hash: str) -> None:
        """Clear job ID for content in index."""
        db_path = self._content_store_path / "index.db"

        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "UPDATE content_index SET job_id = NULL WHERE hash = ?",
                (content_hash,),
            )
            conn.commit()

    @with_connection_retry
    def index_get_statistics(self) -> ContentStoreStatistics:
        """Get statistics from SQLite index."""
        db_path = self._content_store_path / "index.db"

        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                """
                SELECT
                    COUNT(*) as total_content,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as processed_content,
                    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending_content
                FROM content_index
            """
            )

            row = cursor.fetchone()
            return {
                "total_content": row[0] or 0,
                "processed_content": row[1] or 0,
                "pending_content": row[2] or 0,
            }

    def get_store_size_bytes(self) -> int:
        """Calculate total size of stored files."""
        total_size = 0
        try:
            for f in self._content_store_path.rglob("*.json"):
                total_size += f.stat().st_size
        except Exception as e:
            logger.warning("failed_to_calculate_store_size", error=str(e))
        return total_size
