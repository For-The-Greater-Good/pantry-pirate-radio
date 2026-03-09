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
from uuid import uuid4

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
    if "Item" not in response:
        raise ValueError("Batch metadata not found in DynamoDB")
    item = response["Item"]
    output_key_prefix = item.get("output_key_prefix", {}).get("S", "")
    if not output_key_prefix:
        raise ValueError("output_key_prefix must not be empty")
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
) -> tuple[list[dict[str, Any]], int]:
    """Read all output JSONL files from S3.

    Args:
        s3: boto3 S3 client
        bucket: S3 bucket name
        output_key_prefix: S3 key prefix for output files

    Returns:
        Tuple of (parsed output records, unparseable record count)
    """
    records: list[dict[str, Any]] = []
    unparseable_count = 0

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
            body = response["Body"].read().decode("utf-8")

            for line in body.strip().split("\n"):
                if line.strip():
                    try:
                        records.append(json.loads(line))
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

    if unparseable_count > 0:
        logger.warning(
            "batch_output_unparseable_records_summary",
            unparseable_count=unparseable_count,
            total_parsed=len(records),
        )

    return records, unparseable_count


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

    # Store result in content store (mirrors processor.py)
    is_valid_response = (
        llm_response.text
        and llm_response.text.strip() != ""
        and llm_response.text != "No response from model"
        and llm_response.text != "Empty response from model"
    )

    from app.content_store.config import get_content_store

    content_store = get_content_store()
    if content_store and is_valid_response:
        content_hash = job_data.get("metadata", {}).get("content_hash")
        if content_hash:
            try:
                content_store.store_result(content_hash, llm_response.text, record_id)
                logger.info(
                    "batch_content_store_result_stored",
                    record_id=record_id,
                    content_hash=content_hash[:8],
                )
            except Exception as e:
                logger.error(
                    "batch_content_store_write_failed",
                    record_id=record_id,
                    error=str(e),
                )

    send_to_sqs(
        queue_url=target_queue,
        message_body=job_result.model_dump(mode="json"),
        message_group_id=scraper_id,
        deduplication_id=record_id,
        source="batch-result-processor",
    )

    # Send copy to recorder queue.
    # NOTE: Recorder send failures are intentionally non-critical. The record
    # has already been routed through the main pipeline (validator/reconciler)
    # above, so it is correctly counted as "processed" by the caller even if
    # the recorder copy fails. The recorder is an observability side-channel.
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
        deduplication_id=f"{job_id}-retry-{uuid4()}",
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

    # H4 FIX: Idempotency check — skip if already processed.
    # EventBridge may invoke this Lambda multiple times for the same event.
    # Use a conditional write to atomically claim processing.
    if jobs_table:
        try:
            dynamodb.update_item(
                TableName=jobs_table,
                Key={"job_id": {"S": f"batch:{job_arn}"}},
                UpdateExpression="SET processing_started_at = :ts",
                ConditionExpression="attribute_not_exists(processing_started_at)",
                ExpressionAttributeValues={
                    ":ts": {"S": datetime.now(UTC).isoformat()},
                },
            )
        except Exception as e:
            # Check if it's a ConditionalCheckFailedException (already processing)
            error_code = ""
            if hasattr(e, "response"):
                error_code = e.response.get("Error", {}).get("Code", "")  # type: ignore[union-attr]
            if error_code == "ConditionalCheckFailedException":
                logger.info(
                    "batch_result_already_processing",
                    batch_job_arn=job_arn,
                    status=status,
                )
                return {"status": "already_processed", "batch_job_arn": job_arn}
            # Other errors should not block processing
            logger.warning(
                "batch_idempotency_check_failed",
                batch_job_arn=job_arn,
                error=str(e),
            )

    # Get batch metadata from DynamoDB
    metadata = _get_batch_metadata(dynamodb, s3, jobs_table, batch_bucket, job_arn)
    original_jobs = metadata["original_jobs"]
    output_key_prefix = metadata["output_key_prefix"]

    # Handle full failure: re-enqueue all original jobs
    if status == "Failed":
        requeued = 0
        failed_requeue_count = 0
        for _job_id, original_job in original_jobs.items():
            try:
                _requeue_to_llm(original_job, llm_queue_url)
                requeued += 1
            except Exception as e:
                failed_requeue_count += 1
                logger.error(
                    "batch_requeue_failed",
                    batch_job_arn=job_arn,
                    job_id=_job_id,
                    error=str(e),
                )

        if failed_requeue_count > 0:
            logger.error(
                "batch_requeue_failures_summary",
                batch_job_arn=job_arn,
                failed_requeue_count=failed_requeue_count,
                successful_requeue_count=requeued,
            )

        logger.info(
            "batch_failed_all_requeued",
            batch_job_arn=job_arn,
            requeued=requeued,
        )
        return {"status": "Failed", "requeued": requeued}

    # Read output JSONL from S3
    output_records, unparseable_count = _read_output_jsonl(
        s3, batch_bucket, output_key_prefix
    )

    processed = 0
    errors = 0
    failed_requeue_count = 0

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
                try:
                    _requeue_to_llm(original_job, llm_queue_url)
                except Exception as e:
                    failed_requeue_count += 1
                    logger.error(
                        "batch_requeue_failed",
                        batch_job_arn=job_arn,
                        record_id=record_id,
                        error=str(e),
                    )
            else:
                logger.error(
                    "batch_error_record_missing_original_job",
                    record_id=record_id,
                )
            continue

        # Successful record: route downstream
        model_output = record.get("modelOutput", {})
        original_job = original_jobs.get(record_id)

        if not original_job:
            logger.error(
                "batch_record_missing_original_job",
                batch_job_arn=job_arn,
                record_id=record_id,
            )
            errors += 1
            continue

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
                try:
                    _requeue_to_llm(original_job, llm_queue_url)
                except Exception as requeue_err:
                    failed_requeue_count += 1
                    logger.error(
                        "batch_requeue_failed",
                        batch_job_arn=job_arn,
                        record_id=record_id,
                        error=str(requeue_err),
                    )

    if failed_requeue_count > 0:
        logger.error(
            "batch_requeue_failures_summary",
            batch_job_arn=job_arn,
            failed_requeue_count=failed_requeue_count,
        )

    # For PartiallyCompleted batches, re-enqueue any original jobs that did
    # not appear in the output (i.e., they were never processed by Bedrock).
    requeued = 0
    if status == "PartiallyCompleted":
        output_record_ids = {r.get("recordId", "") for r in output_records}
        missing_ids = set(original_jobs.keys()) - output_record_ids
        partial_failed_requeue_count = 0
        for missing_id in missing_ids:
            original_job = original_jobs[missing_id]
            try:
                _requeue_to_llm(original_job, llm_queue_url)
                requeued += 1
            except Exception as e:
                partial_failed_requeue_count += 1
                logger.error(
                    "batch_requeue_failed",
                    batch_job_arn=job_arn,
                    record_id=missing_id,
                    error=str(e),
                )
        if partial_failed_requeue_count > 0:
            logger.error(
                "batch_partial_requeue_failures_summary",
                batch_job_arn=job_arn,
                failed_requeue_count=partial_failed_requeue_count,
                successful_requeue_count=requeued,
            )
        if missing_ids:
            logger.warning(
                "batch_partially_completed_requeued_missing",
                batch_job_arn=job_arn,
                missing_count=len(missing_ids),
                missing_record_ids=sorted(missing_ids),
            )

    # Update DynamoDB job status to reflect processing outcome
    final_status = "completed" if errors == 0 else "failed"
    metadata_update_failed = False
    try:
        dynamodb.update_item(
            TableName=jobs_table,
            Key={"job_id": {"S": f"batch:{job_arn}"}},
            UpdateExpression="SET #s = :status, processed_at = :ts, processed_count = :pc, error_count = :ec",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":status": {"S": final_status},
                ":ts": {"S": datetime.now(UTC).isoformat()},
                ":pc": {"N": str(processed)},
                ":ec": {"N": str(errors)},
            },
        )
        logger.info(
            "batch_job_dynamodb_status_updated",
            batch_job_arn=job_arn,
            final_status=final_status,
            processed=processed,
            errors=errors,
        )
    except Exception as e:
        metadata_update_failed = True
        logger.critical(
            "batch_job_dynamodb_status_update_failed",
            batch_job_arn=job_arn,
            final_status=final_status,
            error=str(e),
        )

    logger.info(
        "batch_result_processing_complete",
        batch_job_arn=job_arn,
        status=status,
        processed=processed,
        errors=errors,
        requeued=requeued,
    )

    result: dict[str, Any] = {
        "status": status,
        "processed": processed,
        "errors": errors,
        "requeued": requeued,
        "unparseable_count": unparseable_count,
    }
    if metadata_update_failed:
        result["metadata_update_failed"] = True
    return result
