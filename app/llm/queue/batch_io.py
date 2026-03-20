"""Streaming I/O helpers for Bedrock batch inference.

Functions for downloading, indexing, and looking up original job records
and output JSONL files from S3. Used by the batch result processor Lambda.
"""

import json
import tempfile
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def build_original_jobs_index(
    s3: Any, bucket: str, key: str
) -> tuple[dict[str, tuple[int, int]], str]:
    """Download original_jobs.jsonl and build byte-offset index.

    Each line is a JSON object with "k" (record ID) and "v" (original job).
    The index maps record_id -> (byte_offset, byte_length) for O(1) lookups.

    Memory: O(N) for the index — only record IDs and byte offsets stored.

    Args:
        s3: boto3 S3 client
        bucket: S3 bucket name
        key: S3 key for original_jobs.jsonl

    Returns:
        (index, temp_file_path) where index maps record_id to (offset, length)
    """
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jsonl")
    tmp.close()
    s3.download_file(bucket, key, tmp.name)

    index: dict[str, tuple[int, int]] = {}
    with open(tmp.name, "rb") as f:
        while True:
            offset = f.tell()
            line = f.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            index[record["k"]] = (offset, len(line) + 1)

    return index, tmp.name


def lookup_original_job(
    filepath: str, index: dict[str, tuple[int, int]], record_id: str
) -> dict[str, Any] | None:
    """Look up a single original job by record_id using byte-offset index.

    Args:
        filepath: Path to the original_jobs.jsonl temp file
        index: Byte-offset index from build_original_jobs_index
        record_id: Record ID to look up

    Returns:
        Original job dict, or None if not found
    """
    entry = index.get(record_id)
    if not entry:
        return None
    offset, length = entry
    with open(filepath, "rb") as f:
        f.seek(offset)
        line = f.read(length)
    return json.loads(line)["v"]


def load_original_jobs_legacy(s3: Any, bucket: str, key: str) -> dict[str, Any]:
    """Load original_jobs.json (legacy JSON dict format) into memory.

    Backward compatibility for batch jobs created before the JSONL change.

    Args:
        s3: boto3 S3 client
        bucket: S3 bucket name
        key: S3 key for original_jobs.json

    Returns:
        Dict mapping record_id to original job
    """
    obj = s3.get_object(Bucket=bucket, Key=key)
    return json.loads(obj["Body"].read().decode("utf-8"))


def download_output_jsonl(
    s3: Any, bucket: str, output_key_prefix: str
) -> tuple[str, int, int]:
    """Download all output JSONL files to a single temp file.

    Args:
        s3: boto3 S3 client
        bucket: S3 bucket name
        output_key_prefix: S3 key prefix for output files

    Returns:
        (temp_file_path, record_count, unparseable_count)
    """
    tmp = tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".jsonl")
    record_count = 0
    unparseable_count = 0

    try:
        continuation_token = None
        while True:
            kwargs: dict[str, Any] = {"Bucket": bucket, "Prefix": output_key_prefix}
            if continuation_token:
                kwargs["ContinuationToken"] = continuation_token

            list_response = s3.list_objects_v2(**kwargs)

            for obj in list_response.get("Contents", []):
                key = obj["Key"]
                if not key.endswith(".jsonl.out") and not key.endswith(".jsonl"):
                    continue

                response = s3.get_object(Bucket=bucket, Key=key)
                body = response["Body"].read()

                for raw_line in body.split(b"\n"):
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        json.loads(line)  # Validate JSON
                        tmp.write(line + b"\n")
                        record_count += 1
                    except json.JSONDecodeError as e:
                        unparseable_count += 1
                        logger.error(
                            "failed_to_parse_output_record",
                            key=key,
                            error=str(e),
                        )

            if not list_response.get("IsTruncated"):
                break
            continuation_token = list_response.get("NextContinuationToken")

        tmp.close()
    except Exception:
        tmp.close()
        import os

        os.unlink(tmp.name)
        raise

    if unparseable_count > 0:
        logger.warning(
            "batch_output_unparseable_records_summary",
            unparseable_count=unparseable_count,
            total_parsed=record_count,
        )

    return tmp.name, record_count, unparseable_count
