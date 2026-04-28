"""Stream JSONL directly to S3 without buffering on disk or in full memory.

Lambda /tmp is capped at 4 GiB; large drains exceed it. This writer uploads
records as multipart-upload parts as the buffer fills, keeping memory
constant regardless of total payload size.

Falls back to a single PutObject when the total content is smaller than
the configured part size, so small payloads do not pay the multipart
overhead.
"""

import json
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# S3 multipart parts must be >= 5 MiB except the last. 8 MiB gives headroom
# without inflating the in-flight buffer too much.
_DEFAULT_PART_SIZE = 8 * 1024 * 1024


class S3JsonlWriter:
    """Stream JSONL records to S3 via multipart upload.

    Use as a context manager. On exception, the in-progress multipart
    upload is aborted so orphan parts do not accumulate billing.
    """

    def __init__(
        self,
        s3_client: Any,
        bucket: str,
        key: str,
        part_size: int = _DEFAULT_PART_SIZE,
    ) -> None:
        self._s3 = s3_client
        self._bucket = bucket
        self._key = key
        self._part_size = part_size
        self._buffer: list[bytes] = []
        self._buffer_size = 0
        self._upload_id: str | None = None
        self._parts: list[dict[str, Any]] = []
        self._part_number = 0
        self._closed = False
        self.record_count = 0

    @property
    def bucket(self) -> str:
        return self._bucket

    @property
    def key(self) -> str:
        return self._key

    def write_record(self, record: dict[str, Any]) -> None:
        """Encode `record` as a JSON line and append to the upload buffer."""
        line = (json.dumps(record, default=str) + "\n").encode("utf-8")
        self._buffer.append(line)
        self._buffer_size += len(line)
        self.record_count += 1
        if self._buffer_size >= self._part_size:
            self._flush_part()

    def _flush_part(self) -> None:
        if self._upload_id is None:
            resp = self._s3.create_multipart_upload(
                Bucket=self._bucket,
                Key=self._key,
                ContentType="application/jsonl",
            )
            self._upload_id = resp["UploadId"]
        self._part_number += 1
        body = b"".join(self._buffer)
        self._buffer = []
        self._buffer_size = 0
        resp = self._s3.upload_part(
            Bucket=self._bucket,
            Key=self._key,
            PartNumber=self._part_number,
            UploadId=self._upload_id,
            Body=body,
        )
        self._parts.append({"ETag": resp["ETag"], "PartNumber": self._part_number})

    def close(self) -> None:
        """Finalize the upload. Single PutObject if buffer never hit a part."""
        if self._closed:
            return
        self._closed = True
        if self._upload_id is None:
            body = b"".join(self._buffer)
            self._buffer = []
            self._buffer_size = 0
            self._s3.put_object(
                Bucket=self._bucket,
                Key=self._key,
                Body=body,
                ContentType="application/jsonl",
            )
            return
        if self._buffer_size > 0:
            self._flush_part()
        self._s3.complete_multipart_upload(
            Bucket=self._bucket,
            Key=self._key,
            UploadId=self._upload_id,
            MultipartUpload={"Parts": self._parts},
        )

    def abort(self) -> None:
        """Abort an in-progress multipart upload (no-op if not started)."""
        if self._upload_id is None or self._closed:
            return
        self._closed = True
        try:
            self._s3.abort_multipart_upload(
                Bucket=self._bucket,
                Key=self._key,
                UploadId=self._upload_id,
            )
        except Exception as e:
            logger.error(
                "s3_jsonl_abort_failed",
                bucket=self._bucket,
                key=self._key,
                upload_id=self._upload_id,
                error=str(e),
            )

    def __enter__(self) -> "S3JsonlWriter":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            self.abort()
        else:
            self.close()


def iter_s3_jsonl(s3_client: Any, bucket: str, key: str):
    """Yield parsed JSON records from an S3 JSONL object, line by line."""
    resp = s3_client.get_object(Bucket=bucket, Key=key)
    for raw in resp["Body"].iter_lines():
        if not raw:
            continue
        yield json.loads(raw)
