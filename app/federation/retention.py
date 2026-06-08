"""Archive tiering + retention prune for the verifiable federation log (§6.2g).

The log recomputes every checkpoint root and proof on demand from the full
``preimage_canonical`` leaf bytes (no persisted Merkle frontier), so a leaf can
never simply be destroyed. Retention here is **archive-then-trim**: the prune
writes each over-SLA leaf's EXACT signed bytes to a never-expiring archive tier
BEFORE deleting its live Postgres row, and :func:`app.federation.log.leaf_data`
reads below-floor leaves back from that tier — so root@N and consistency proofs
across the trim boundary stay valid forever, while ``/export`` serves only the
live window (below the floor it 410s and points at the archive snapshot).

Dual-env (Principle XV): the archive tier is a bouy-mounted local filesystem path
in Docker (``FEDERATION_ARCHIVE_BACKEND=file``) and an S3 bucket with no lifecycle
expiry on AWS (``=s3``). One ``prune_to_horizon`` is shared by both the bouy worker
and the EventBridge-scheduled Lambda.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol, runtime_checkable

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.federation import log

logger = structlog.get_logger(__name__)


@runtime_checkable
class ArchiveBackend(Protocol):
    """The never-destroyed leaf archive. Keys are dense sequences; values are the
    EXACT ``preimage_canonical`` bytes that were hashed and signed at append time
    (so a read-back leaf is byte-identical and proofs verify)."""

    def put(self, sequence: int, preimage: bytes) -> None:
        """Durably store the leaf bytes for ``sequence`` (raise on failure)."""
        ...

    def get(self, sequence: int) -> bytes:
        """Return the stored leaf bytes for ``sequence`` (raise if absent)."""
        ...

    def has(self, sequence: int) -> bool:
        """True iff ``sequence`` is present in the archive."""
        ...


class LocalFsArchiveBackend:
    """Filesystem archive (the Docker realization). One file per sequence; writes
    are atomic (temp + ``os.replace``) so a crash mid-write never leaves a partial
    leaf that would corrupt a read-back."""

    def __init__(self, root: str) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, sequence: int) -> Path:
        return self._root / f"{sequence}.jsonl"

    def put(self, sequence: int, preimage: bytes) -> None:
        path = self._path(sequence)
        tmp = path.with_suffix(".jsonl.tmp")
        with open(tmp, "wb") as fh:
            fh.write(preimage)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        # fsync the directory so the RENAME (not just the file content) is durable
        # before put() returns — prune_to_horizon DELETEs the live row trusting this
        # put as proof of durability, so a crash here must not lose the rename.
        dir_fd = os.open(str(self._root), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

    def get(self, sequence: int) -> bytes:
        return self._path(sequence).read_bytes()

    def has(self, sequence: int) -> bool:
        return self._path(sequence).is_file()


class S3ArchiveBackend:
    """S3 archive (the AWS realization). The bucket MUST have no lifecycle expiry
    (§6.2g: never destroyed). ``boto3`` is imported lazily so the slim read Lambda
    and local Docker do not pay for it unless this backend is selected."""

    def __init__(self, bucket: str, prefix: str = "federation-log-archive") -> None:
        import boto3

        self._bucket = bucket
        self._prefix = prefix.rstrip("/")
        self._s3 = boto3.client("s3")

    def _key(self, sequence: int) -> str:
        return f"{self._prefix}/{sequence}.jsonl"

    def put(self, sequence: int, preimage: bytes) -> None:
        self._s3.put_object(Bucket=self._bucket, Key=self._key(sequence), Body=preimage)

    def get(self, sequence: int) -> bytes:
        resp = self._s3.get_object(Bucket=self._bucket, Key=self._key(sequence))
        return resp["Body"].read()

    def has(self, sequence: int) -> bool:
        from botocore.exceptions import ClientError

        try:
            self._s3.head_object(Bucket=self._bucket, Key=self._key(sequence))
            return True
        except ClientError as exc:
            # Only a genuine 404 means "absent". A transient/permission error must
            # PROPAGATE (retryable) — never be mistaken for permanent leaf loss,
            # which would degrade an available checkpoint/proof to a false 410.
            err = exc.response.get("Error", {}) if hasattr(exc, "response") else {}
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if err.get("Code") in ("404", "NoSuchKey", "NotFound") or status == 404:
                return False
            raise


def resolve_archive_backend() -> ArchiveBackend | None:
    """The configured archive tier, or ``None`` when unconfigured (pre-prune
    behavior: a missing leaf is a hard error, never silently dropped)."""
    from app.core.config import settings

    if settings.FEDERATION_ARCHIVE_BACKEND == "s3":
        if not settings.FEDERATION_ARCHIVE_S3_BUCKET:
            return None
        return S3ArchiveBackend(
            settings.FEDERATION_ARCHIVE_S3_BUCKET, settings.FEDERATION_ARCHIVE_S3_PREFIX
        )
    if settings.FEDERATION_ARCHIVE_PATH:
        return LocalFsArchiveBackend(settings.FEDERATION_ARCHIVE_PATH)
    return None


@dataclass
class PruneResult:
    archived_count: int
    retention_horizon_sequence: int


def _parse_rfc3339(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def prune_to_horizon(
    session: Session,
    *,
    backend: ArchiveBackend,
    retention_days: int,
    now: str | None = None,
) -> PruneResult:
    """Archive then trim every leaf older than the SLA, contiguously from the floor.

    Write-ahead: each leaf is archived (durably) BEFORE its live row is deleted; on
    an archive-put failure the prune halts at that sequence (no leaf loss, no wedge —
    the still-live rows are returned by visibility on the next run). The live window
    keeps a contiguous-suffix shape, so ``retention_horizon_sequence`` (= the new
    ``live_window_floor``) is well-defined. No-op when federation is disabled
    (kill switch §6.2d) or when nothing is older than the SLA.
    """
    from app.core.config import settings

    if not settings.FEDERATION_ENABLED:
        return PruneResult(0, log.live_window_floor(session))

    now_dt = _parse_rfc3339(now) if now else datetime.now().astimezone()
    cutoff = now_dt - timedelta(days=retention_days)

    # The oldest leaf still WITHIN the SLA; everything below it is trimmable. If
    # every leaf is over-SLA we conservatively keep them (never empty the live
    # window / orphan the head checkpoint) rather than trim the whole log.
    first_survivor = session.execute(
        text("SELECT MIN(sequence) FROM federation_log WHERE published_at >= :cutoff"),
        {"cutoff": cutoff},
    ).scalar()
    if first_survivor is None:
        return PruneResult(0, log.live_window_floor(session))

    candidates = session.execute(
        text(
            "SELECT sequence, preimage_canonical FROM federation_log"
            " WHERE sequence < :fs ORDER BY sequence"
        ),
        {"fs": first_survivor},
    ).all()

    archived: list[int] = []
    for row in candidates:
        try:
            backend.put(int(row.sequence), bytes(row.preimage_canonical))
        except (
            Exception
        ) as exc:  # noqa: BLE001 — halt, never delete an un-archived leaf
            logger.warning(
                "federation_archive_failed", sequence=int(row.sequence), error=str(exc)
            )
            break
        archived.append(int(row.sequence))

    if archived:
        session.execute(
            text("DELETE FROM federation_log WHERE sequence <= :hi"),
            {"hi": archived[-1]},
        )
        session.commit()

    horizon = log.live_window_floor(session)
    logger.info(
        "federation_archive_tiered",
        archived_count=len(archived),
        retention_horizon_sequence=horizon,
    )
    return PruneResult(len(archived), horizon)
