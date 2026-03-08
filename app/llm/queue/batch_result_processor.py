"""Batch Result Processor Lambda for Bedrock Batch Inference.

Triggered by EventBridge when a Bedrock batch job completes (Completed,
PartiallyCompleted, or Failed). Reads output JSONL from S3, parses each
result using parse_converse_response(), and routes downstream:

  - Successful records -> validator queue (if enabled) or reconciler queue
  - Error records -> LLM queue for on-demand retry
  - Failed jobs -> all original jobs re-enqueued to LLM queue
  - All successful records -> recorder queue (copy)

Environment variables:
    BATCH_BUCKET: S3 bucket for batch I/O
    VALIDATOR_QUEUE_URL: SQS validator queue URL
    RECONCILER_QUEUE_URL: SQS reconciler queue URL
    RECORDER_QUEUE_URL: SQS recorder queue URL
    LLM_QUEUE_URL: SQS LLM queue URL (for error retry)
    SQS_JOBS_TABLE: DynamoDB table for batch job tracking
    VALIDATOR_ENABLED: Whether to route through validator
"""

import json
import os
from datetime import UTC, datetime
from typing import Any

import structlog

from app.core.config import settings
from app.llm.providers.bedrock import parse_converse_response
from app.llm.queue.types import JobResult, JobStatus
from app.pipeline.sqs_sender import send_to_sqs

logger = structlog.get_logger(__name__)


def _get_clients() -> tuple:
    """Create and return AWS service clients."""
    import boto3

    region = os.environ.get("AWS_DEFAULT_REGION")
    kwargs = {"region_name": region} if region else {}
    s3 = boto3.client("s3", **kwargs)
    dynamodb = boto3.client("dynamodb", **kwargs)
    return s3, dynamodb


def _get_batch_metadata(
    dynamodb: Any, s3: Any, jobs_table: str, batch_bucket: str, job_arn: str
) -> dict[str, Any]:
    """Retrieve batch job metadata from DynamoDB + original jobs from S3.

    Args:
        dynamodb: boto3 DynamoDB client
        s3: boto3 S3 client
        jobs_table: DynamoDB table name
        batch_bucket: S3 bucket for batch I/O
        job_arn: Bedrock batch job ARN

    Returns:
        Dict with output_key_prefix and original_jobs
    """
    response = dynamodb.get_item(
        TableName=jobs_table,
        Key={"job_id": {"S": f"batch:{job_arn}"}},
    )
    item = response.get("Item", {})
    output_key_prefix = item.get("output_key_prefix", {}).get("S", "")
    original_jobs_key = item.get("original_jobs_key", {}).get("S", "")

    # Read original jobs from S3
    original_jobs = {}
    if original_jobs_key:
        obj = s3.get_object(Bucket=batch_bucket, Key=original_jobs_key)
        original_jobs = json.loads(obj["Body"].read().decode("utf-8"))

    return {
        "output_key_prefix": output_key_prefix,
        "original_jobs": original_jobs,
    }


def _read_output_jsonl(
    s3: Any, bucket: str, output_key_prefix: str
) -> list[dict[str, Any]]:
    """Read all output JSONL files from S3.

    Args:
        s3: boto3 S3 client
        bucket: S3 bucket name
        output_key_prefix: S3 key prefix for output files

    Returns:
        List of parsed output records
    """
    records: list[dict[str, Any]] = []

    list_response = s3.list_objects_v2(Bucket=bucket, Prefix=output_key_prefix)

    for obj in list_response.get("Contents", []):
        key = obj["Key"]
        if not key.endswith(".jsonl.out") and not key.endswith(".jsonl"):
            continue

        response = s3.get_object(Bucket=bucket, Key=key)
        body = response["Body"].read().decode("utf-8")

        for line in body.strip().split("\n"):
            if line.strip():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as e:
                    logger.error(
                        "failed_to_parse_output_record",
                        key=key,
                        error=str(e),
                    )

    return records


def _route_success(
    record_id: str,
    output: dict[str, Any],
    original_job: dict[str, Any],
    model_id: str,
    validator_queue_url: str,
    reconciler_queue_url: str,
    recorder_queue_url: str,
) -> None:
    """Route a successful batch result downstream.

    Mirrors the routing logic in processor.py lines 242-327.

    Args:
        record_id: Job ID / record ID
        output: Bedrock modelOutput dict
        original_job: Original SQS message body
        model_id: Model identifier
        validator_queue_url: Validator queue URL
        reconciler_queue_url: Reconciler queue URL
        recorder_queue_url: Recorder queue URL
    """
    job_data = original_job.get("job", {})
    scraper_id = job_data.get("metadata", {}).get("scraper_id", "default")
    format_schema = job_data.get("format") or None

    # Parse the Converse response
    llm_response = parse_converse_response(
        response=output,
        model_id=model_id,
        format_schema=format_schema,
    )

    from app.llm.queue.job import LLMJob

    llm_job = LLMJob.model_validate(job_data)

    job_result = JobResult(
        job_id=record_id,
        job=llm_job,
        status=JobStatus.COMPLETED,
        result=llm_response,
        completed_at=datetime.now(UTC),
    )

    # Route to validator or reconciler (mirrors processor.py)
    if getattr(settings, "VALIDATOR_ENABLED", False):
        target_queue = validator_queue_url
    else:
        target_queue = reconciler_queue_url

    send_to_sqs(
        queue_url=target_queue,
        message_body=job_result.model_dump(mode="json"),
        message_group_id=scraper_id,
        deduplication_id=record_id,
        source="batch-result-processor",
    )

    # Send copy to recorder queue
    if recorder_queue_url:
        recorder_data = {
            "job_id": record_id,
            "job": job_data,
            "result": llm_response.model_dump(mode="json"),
            "error": None,
        }
        try:
            send_to_sqs(
                queue_url=recorder_queue_url,
                message_body=recorder_data,
                message_group_id=scraper_id,
                source="batch-result-processor",
            )
        except Exception as e:
            logger.error(
                "failed_to_send_to_recorder",
                job_id=record_id,
                error=str(e),
            )


def _requeue_to_llm(original_job: dict[str, Any], llm_queue_url: str) -> None:
    """Re-enqueue an original job to the LLM queue for on-demand retry.

    Args:
        original_job: Original SQS message body
        llm_queue_url: LLM queue URL
    """
    job_data = original_job.get("job", {})
    scraper_id = job_data.get("metadata", {}).get("scraper_id", "default")
    job_id = job_data.get("id", original_job.get("job_id", ""))

    send_to_sqs(
        queue_url=llm_queue_url,
        message_body=original_job,
        message_group_id=scraper_id,
        deduplication_id=f"{job_id}-retry",
        source="batch-result-processor",
    )


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda handler triggered by EventBridge on batch job state change.

    Args:
        event: EventBridge event with detail.jobArn and detail.status
        context: Lambda context (unused)

    Returns:
        Summary dict with processed/errors/requeued counts
    """
    detail = event.get("detail", {})
    job_arn = detail.get("batchJobArn", "")
    status = detail.get("status", "")

    batch_bucket = os.environ.get("BATCH_BUCKET", "")
    validator_queue_url = os.environ.get("VALIDATOR_QUEUE_URL", "")
    reconciler_queue_url = os.environ.get("RECONCILER_QUEUE_URL", "")
    recorder_queue_url = os.environ.get("RECORDER_QUEUE_URL", "")
    llm_queue_url = os.environ.get("LLM_QUEUE_URL", "")
    jobs_table = os.environ.get("SQS_JOBS_TABLE", "")
    model_id = os.environ.get(
        "BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    )

    s3, dynamodb = _get_clients()

    logger.info(
        "batch_result_received",
        batch_job_arn=job_arn,
        status=status,
        event_detail_keys=list(detail.keys()),
    )

    # Get batch metadata from DynamoDB
    metadata = _get_batch_metadata(dynamodb, s3, jobs_table, batch_bucket, job_arn)
    original_jobs = metadata["original_jobs"]
    output_key_prefix = metadata["output_key_prefix"]

    # Handle full failure: re-enqueue all original jobs
    if status == "Failed":
        requeued = 0
        for _job_id, original_job in original_jobs.items():
            _requeue_to_llm(original_job, llm_queue_url)
            requeued += 1

        logger.info(
            "batch_failed_all_requeued",
            batch_job_arn=job_arn,
            requeued=requeued,
        )
        return {"status": "Failed", "requeued": requeued}

    # Read output JSONL from S3
    output_records = _read_output_jsonl(s3, batch_bucket, output_key_prefix)

    processed = 0
    errors = 0

    for record in output_records:
        record_id = record.get("recordId", "")

        if "error" in record:
            # Per-record error: re-enqueue for on-demand retry
            errors += 1
            original_job = original_jobs.get(record_id)
            if original_job:
                logger.warning(
                    "batch_record_error",
                    batch_job_arn=job_arn,
                    record_id=record_id,
                    error_code=record["error"].get("errorCode"),
                    error_message=record["error"].get("errorMessage"),
                )
                _requeue_to_llm(original_job, llm_queue_url)
            continue

        # Successful record: route downstream
        model_output = record.get("modelOutput", {})
        original_job = original_jobs.get(record_id, {})

        try:
            _route_success(
                record_id=record_id,
                output=model_output,
                original_job=original_job,
                model_id=model_id,
                validator_queue_url=validator_queue_url,
                reconciler_queue_url=reconciler_queue_url,
                recorder_queue_url=recorder_queue_url,
            )
            processed += 1
        except Exception as e:
            errors += 1
            logger.error(
                "batch_record_routing_failed",
                batch_job_arn=job_arn,
                record_id=record_id,
                error=str(e),
            )
            if original_job:
                _requeue_to_llm(original_job, llm_queue_url)

    logger.info(
        "batch_result_processing_complete",
        batch_job_arn=job_arn,
        status=status,
        processed=processed,
        errors=errors,
    )

    return {
        "status": status,
        "processed": processed,
        "errors": errors,
    }
