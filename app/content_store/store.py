"""Content store implementation for deduplicating scraped content."""

import hashlib
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

import redis
from rq import Queue
from rq.job import Job

from app.content_store.models import ContentEntry


class ContentStore:
    """Stores and deduplicates scraped content using SHA-256 hashing."""

    # SHA-256 produces 64 hex characters
    _HASH_PATTERN = re.compile(r"^[a-f0-9]{64}$")

    def __init__(self, store_path: Path, redis_url: str = "redis://cache:6379"):
        """Initialize content store.

        Args:
            store_path: Base path for content store (e.g., HAARRRvest repo path)
            redis_url: Redis connection URL for checking job status
        """
        self.store_path = store_path
        self.content_store_path = store_path / "content_store"
        self.redis_conn = redis.from_url(redis_url)

        # Create directory structure
        self._init_directories()

        # Initialize SQLite index
        self._init_database()

    def _init_directories(self):
        """Create necessary directory structure."""
        (self.content_store_path / "content").mkdir(parents=True, exist_ok=True)
        (self.content_store_path / "results").mkdir(parents=True, exist_ok=True)

    def _init_database(self):
        """Initialize SQLite database for content index."""
        db_path = self.content_store_path / "index.db"

        with sqlite3.connect(db_path) as conn:
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
        try:
            job = Job.fetch(job_id, connection=self.redis_conn)
            status = job.get_status()
            return status in ["queued", "started", "deferred", "scheduled"]
        except Exception:
            # Job doesn't exist or can't be fetched
            return False

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
        db_path = self.content_store_path / "index.db"

        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                "SELECT 1 FROM content_index WHERE hash = ?", (content_hash,)
            )
            return cursor.fetchone() is not None

    def get_result(self, content_hash: str) -> Optional[str]:
        """Get processing result for content if available.

        Args:
            content_hash: SHA-256 hash of content

        Returns:
            Result JSON string if processed, None otherwise

        Raises:
            ValueError: If hash format is invalid

        Note:
            Uses synchronous file I/O. For high-throughput scenarios,
            consider async version (would require API changes).
        """
        result_path = self._get_result_path(content_hash)

        if result_path.exists():
            # TODO: Consider aiofiles for async I/O in high-throughput scenarios
            data = json.loads(result_path.read_text())
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
        if result := self.get_result(content_hash):
            # Get job_id from result file
            result_path = self._get_result_path(content_hash)
            result_data = json.loads(result_path.read_text())

            return ContentEntry(
                hash=content_hash,
                status="completed",
                result=result,
                job_id=result_data.get("job_id"),
            )

        # Check if content already exists with a job_id (for cleanup only)
        existing_job_id = self.get_job_id(content_hash)
        if existing_job_id and not self._is_job_active(existing_job_id):
            # Job is no longer active (failed, expired, etc.)
            # Clear the old job_id so content can be reprocessed
            self.clear_job_id(content_hash)

        # Store content if not already stored
        content_path = self._get_content_path(content_hash)

        if not content_path.exists():
            # Create directory if needed
            content_path.parent.mkdir(parents=True, exist_ok=True)

            # Write content
            content_data = {
                "content": content,
                "metadata": metadata,
                "timestamp": datetime.utcnow().isoformat(),
            }
            content_path.write_text(json.dumps(content_data, indent=2))

            # Update index
            db_path = self.content_store_path / "index.db"
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO content_index
                    (hash, status, content_path, created_at)
                    VALUES (?, ?, ?, ?)
                """,
                    (content_hash, "pending", str(content_path), datetime.utcnow()),
                )
                conn.commit()

        # Return pending status without job_id (allow new processing)
        return ContentEntry(
            hash=content_hash, status="pending", result=None, job_id=None
        )

    def store_result(self, content_hash: str, result: str, job_id: str):
        """Store processing result for content.

        Args:
            content_hash: SHA-256 hash of content
            result: Processing result JSON
            job_id: Job ID that produced this result

        Raises:
            ValueError: If hash format is invalid
        """
        result_path = self._get_result_path(content_hash)

        # Create directory if needed
        result_path.parent.mkdir(parents=True, exist_ok=True)

        # Write result
        result_data = {
            "result": result,
            "job_id": job_id,
            "timestamp": datetime.utcnow().isoformat(),
        }
        result_path.write_text(json.dumps(result_data, indent=2))

        # Update index - use INSERT OR REPLACE to handle missing entries
        db_path = self.content_store_path / "index.db"
        with sqlite3.connect(db_path) as conn:
            # First try to update existing entry
            cursor = conn.execute(
                """
                UPDATE content_index
                SET status = ?, result_path = ?, job_id = ?, processed_at = ?
                WHERE hash = ?
            """,
                (
                    "completed",
                    str(result_path),
                    job_id,
                    datetime.utcnow(),
                    content_hash,
                ),
            )

            # If no rows were updated, insert a new entry
            if cursor.rowcount == 0:
                # Entry doesn't exist - this can happen if content was processed
                # without going through store_content first
                # Create a placeholder content path based on the hash
                content_path = self._get_content_path(content_hash)
                conn.execute(
                    """
                    INSERT INTO content_index
                    (hash, status, content_path, result_path, job_id, created_at, processed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        content_hash,
                        "completed",
                        str(
                            content_path
                        ),  # Use expected content path even if file doesn't exist
                        str(result_path),
                        job_id,
                        datetime.utcnow(),
                        datetime.utcnow(),
                    ),
                )

            conn.commit()

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
        db_path = self.content_store_path / "index.db"

        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                "SELECT job_id FROM content_index WHERE hash = ?", (content_hash,)
            )
            result = cursor.fetchone()
            return result[0] if result and result[0] else None

    def clear_job_id(self, content_hash: str):
        """Clear job ID for a content hash.

        Args:
            content_hash: SHA-256 hash of content

        Raises:
            ValueError: If hash format is invalid
        """
        self._validate_hash(content_hash)
        db_path = self.content_store_path / "index.db"

        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "UPDATE content_index SET job_id = NULL WHERE hash = ?", (content_hash,)
            )
            conn.commit()

    def link_job(self, content_hash: str, job_id: str):
        """Link a job ID to a content hash.

        Args:
            content_hash: SHA-256 hash of content
            job_id: Job ID processing this content

        Raises:
            ValueError: If hash format is invalid
        """
        self._validate_hash(content_hash)
        db_path = self.content_store_path / "index.db"

        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                UPDATE content_index
                SET job_id = ?
                WHERE hash = ?
            """,
                (job_id, content_hash),
            )
            conn.commit()

    def get_statistics(self) -> dict:
        """Get statistics about stored content.

        Returns:
            Dictionary with statistics
        """
        db_path = self.content_store_path / "index.db"

        with sqlite3.connect(db_path) as conn:
            # Total content
            total = conn.execute("SELECT COUNT(*) FROM content_index").fetchone()[0]

            # Processed content
            processed = conn.execute(
                "SELECT COUNT(*) FROM content_index WHERE status = 'completed'"
            ).fetchone()[0]

            # Pending content
            pending = conn.execute(
                "SELECT COUNT(*) FROM content_index WHERE status = 'pending'"
            ).fetchone()[0]

        # Calculate store size
        store_size = sum(
            f.stat().st_size for f in self.content_store_path.rglob("*.json")
        )

        return {
            "total_content": total,
            "processed_content": processed,
            "pending_content": pending,
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
        """Get path for content file.

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
        """Get path for result file.

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
