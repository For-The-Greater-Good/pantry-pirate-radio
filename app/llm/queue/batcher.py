"""Batcher Lambda for Bedrock Batch Inference.

Invoked by Step Functions after all scrapers complete. Drains the staging
SQS queue, counts records, and decides:
  - >= BATCH_THRESHOLD records: Build JSONL, submit Bedrock batch job (50% off)
  - < BATCH_THRESHOLD records: Re-enqueue each job to the LLM queue for
    on-demand Fargate processing

All record data is streamed through temp files on disk so memory usage stays
constant regardless of queue depth (designed for 100k+ records).

Environment variables:
    STAGING_QUEUE_URL: SQS staging queue URL
    LLM_QUEUE_URL: SQS LLM queue URL (for on-demand fallback)
    BATCH_BUCKET: S3 bucket for batch I/O
    BEDROCK_MODEL_ID: Cross-region model identifier
    BEDROCK_SERVICE_ROLE_ARN: IAM role ARN for Bedrock batch jobs
    LLM_TEMPERATURE: Sampling temperature (default: 0.7)
    LLM_MAX_TOKENS: Max tokens (default: 8192)
    SQS_JOBS_TABLE: DynamoDB table for batch job tracking
    BATCH_THRESHOLD: Override the default batch threshold (default: 100)
"""

import json
import os
import tempfile
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import structlog

from app.llm.providers.bedrock import build_messages_api_request
from app.pipeline.sqs_sender import send_to_sqs

logger = structlog.get_logger(__name__)

_DEFAULT_BATCH_THRESHOLD = 100


def _get_clients() -> tuple:
    """Create and return AWS service clients."""
    import boto3

    region = os.environ.get("AWS_DEFAULT_REGION")
    kwargs = {"region_name": region} if region else {}
    sqs = boto3.client("sqs", **kwargs)
    s3 = boto3.client("s3", **kwargs)
    bedrock = boto3.client("bedrock", **kwargs)
    dynamodb = boto3.client("dynamodb", **kwargs)
    return sqs, s3, bedrock, dynamodb


def _forward_to_dlq(
    sqs_client: Any,
    dlq_url: str,
    original_body: str,
    message_id: str,
    error: str,
) -> None:
    """Forward a poison pill message to the staging DLQ.

    Args:
        sqs_client: boto3 SQS client
        dlq_url: Staging DLQ URL
        original_body: Original message body (raw string)
        message_id: Original SQS message ID
        error: Error description
    """
    dlq_envelope = json.dumps(
        {
            "original_body": original_body,
            "original_message_id": message_id,
            "error": error,
            "source": "batcher-poison-pill",
        },
        default=str,
    )
    sqs_client.send_message(
        QueueUrl=dlq_url,
        MessageBody=dlq_envelope,
        MessageGroupId="poison-pills",
    )
    logger.warning(
        "poison_pill_forwarded_to_dlq",
        message_id=message_id,
        error=error,
    )


def _drain_staging_queue(
    sqs_client: Any,
    queue_url: str,
    dlq_url: str = "",
    max_iterations: int = 1000,
) -> tuple[int, str]:
    """Drain all messages from the staging queue to a temp file.

    Receives messages in batches of 10. Each batch is deleted immediately
    after parsing to unlock the FIFO message group for subsequent receives.
    Without immediate deletion, in-flight messages block the entire group
    and the drain stalls after the first batch.

    Records are written one-per-line as JSONL to a temp file so memory stays
    constant regardless of queue depth.

    Malformed (unparseable) messages are forwarded to the DLQ for inspection.

    Args:
        sqs_client: boto3 SQS client
        queue_url: SQS queue URL
        dlq_url: DLQ URL for poison pill forwarding
        max_iterations: Safety limit on receive_message calls

    Returns:
        (record_count, temp_file_path) — caller must delete the temp file.
    """
    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".jsonl",
        delete=False,
    )
    record_count = 0
    poison_pill_count = 0

    try:
        for _ in range(max_iterations):
            response = sqs_client.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=1,
                VisibilityTimeout=300,
            )

            messages = response.get("Messages", [])
            if not messages:
                break

            batch_delete_entries: list[dict[str, str]] = []

            for idx, msg in enumerate(messages):
                try:
                    body = json.loads(msg["Body"])
                    tmp.write(json.dumps(body) + "\n")
                    record_count += 1
                    batch_delete_entries.append(
                        {"Id": str(idx), "ReceiptHandle": msg["ReceiptHandle"]}
                    )
                except (json.JSONDecodeError, KeyError) as e:
                    poison_pill_count += 1
                    logger.error(
                        "failed_to_parse_staging_message",
                        message_id=msg.get("MessageId"),
                        error=str(e),
                    )
                    # C2 FIX: Forward poison pills to DLQ for inspection
                    if dlq_url:
                        try:
                            _forward_to_dlq(
                                sqs_client,
                                dlq_url,
                                msg.get("Body", ""),
                                msg.get("MessageId", "unknown"),
                                str(e),
                            )
                        except Exception as dlq_error:
                            logger.error(
                                "failed_to_forward_poison_pill_to_dlq",
                                message_id=msg.get("MessageId"),
                                error=str(dlq_error),
                            )
                    # Delete poison pill individually
                    sqs_client.delete_message(
                        QueueUrl=queue_url,
                        ReceiptHandle=msg["ReceiptHandle"],
                    )

            # Batch-delete valid messages to unlock the FIFO message group
            if batch_delete_entries:
                sqs_client.delete_message_batch(
                    QueueUrl=queue_url,
                    Entries=batch_delete_entries,
                )

        tmp.close()
    except Exception:
        tmp.close()
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise

    if poison_pill_count > 0:
        logger.warning(
            "staging_queue_poison_pills",
            count=poison_pill_count,
        )

    logger.info("staging_queue_drained", total_messages=record_count)
    return record_count, tmp.name


def _delete_messages(
    sqs_client: Any,
    queue_url: str,
    receipt_handles: list[str],
) -> int:
    """Delete messages from SQS by receipt handle.

    Called only after successful downstream processing to ensure
    no data loss on failure.

    Args:
        sqs_client: boto3 SQS client
        queue_url: SQS queue URL
        receipt_handles: List of SQS receipt handles to delete

    Returns:
        Number of messages that failed to delete.
    """
    failed_deletes = 0
    for handle in receipt_handles:
        try:
            sqs_client.delete_message(
                QueueUrl=queue_url,
                ReceiptHandle=handle,
            )
        except Exception as e:
            failed_deletes += 1
            logger.error(
                "delete_message_failed",
                receipt_handle=handle[:40],
                error=str(e),
                error_type=type(e).__name__,
            )

    logger.info(
        "staging_messages_deleted",
        count=len(receipt_handles),
        failed=failed_deletes,
    )
    return failed_deletes


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda handler invoked by Step Functions after scrapers complete.

    Args:
        event: {"execution_id": "...", "scrapers": [...]}
        context: Lambda context (unused)

    Returns:
        {"mode": "batch"|"on-demand", ...}
    """
    # Validate required environment variables up front
    _required_env_vars = {
        "STAGING_QUEUE_URL": os.environ.get("STAGING_QUEUE_URL", ""),
        "LLM_QUEUE_URL": os.environ.get("LLM_QUEUE_URL", ""),
        "BATCH_BUCKET": os.environ.get("BATCH_BUCKET", ""),
        "BEDROCK_SERVICE_ROLE_ARN": os.environ.get("BEDROCK_SERVICE_ROLE_ARN", ""),
    }
    missing = [name for name, val in _required_env_vars.items() if not val]
    if missing:
        raise ValueError(
            f"Missing required environment variables: {', '.join(sorted(missing))}"
        )

    execution_id = event.get("execution_id", "unknown")
    # Extract the UUID portion from the Step Functions ARN for S3-safe paths.
    # ARN format: arn:aws:states:...:execution:name:uuid
    s3_safe_id = (
        execution_id.rsplit(":", 1)[-1] if ":" in execution_id else execution_id
    )
    staging_queue_url = _required_env_vars["STAGING_QUEUE_URL"]
    llm_queue_url = _required_env_vars["LLM_QUEUE_URL"]
    batch_bucket = _required_env_vars["BATCH_BUCKET"]
    model_id = os.environ.get(
        "BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    )
    service_role_arn = _required_env_vars["BEDROCK_SERVICE_ROLE_ARN"]
    temperature = float(os.environ.get("LLM_TEMPERATURE", "0.7"))
    max_tokens = int(os.environ.get("LLM_MAX_TOKENS", "8192"))
    jobs_table = os.environ.get("SQS_JOBS_TABLE", "")
    # M4 FIX: Read per invocation so env var changes take effect without redeployment
    batch_threshold = int(
        os.environ.get("BATCH_THRESHOLD", str(_DEFAULT_BATCH_THRESHOLD))
    )
    # C2: DLQ URL for poison pill forwarding
    staging_dlq_url = os.environ.get("STAGING_DLQ_URL", "")

    sqs, s3, bedrock, dynamodb = _get_clients()

    # 1. Drain staging queue to a temp file — messages are deleted immediately
    #    per batch to unlock FIFO message groups for subsequent receives
    record_count, staging_file = _drain_staging_queue(
        sqs, staging_queue_url, dlq_url=staging_dlq_url
    )

    try:
        # 2. Decide batch vs on-demand
        decision = "batch" if record_count >= batch_threshold else "on-demand"

        logger.info(
            "batch_decision",
            record_count=record_count,
            decision=decision,
            execution_id=execution_id,
            threshold=batch_threshold,
        )

        if record_count == 0:
            return {"mode": "on-demand", "count": 0}

        if decision == "on-demand":
            # Re-enqueue each job to LLM queue for Fargate processing.
            # Staging messages were already deleted during drain.
            succeeded = 0
            failed_count = 0

            with open(staging_file) as f:
                for line in f:
                    record = json.loads(line)
                    try:
                        job_data = record.get("job", {})
                        scraper_id = job_data.get("metadata", {}).get(
                            "scraper_id", "default"
                        )
                        send_to_sqs(
                            queue_url=llm_queue_url,
                            message_body=record,
                            message_group_id=scraper_id,
                            deduplication_id=record.get("job_id", ""),
                            source="batcher-lambda",
                        )
                        succeeded += 1
                    except Exception as e:
                        failed_count += 1
                        logger.error(
                            "on_demand_reenqueue_failed",
                            job_id=record.get("job_id", "unknown"),
                            error=str(e),
                            error_type=type(e).__name__,
                        )

            if failed_count > 0:
                logger.warning(
                    "on_demand_partial_failure",
                    total=record_count,
                    succeeded=succeeded,
                    failed=failed_count,
                    execution_id=execution_id,
                )

            return {
                "mode": "on-demand",
                "count": succeeded,
                "failed": failed_count,
            }

        # 3. Build JSONL + original_jobs to temp files (constant memory)
        input_key = f"input/{s3_safe_id}/input.jsonl"
        output_key_prefix = f"output/{s3_safe_id}/"
        original_jobs_key = f"input/{s3_safe_id}/original_jobs.jsonl"

        input_jsonl = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".jsonl",
            delete=False,
        )
        original_jobs_f = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".jsonl",
            delete=False,
        )
        input_jsonl_path = input_jsonl.name
        original_jobs_path = original_jobs_f.name

        try:
            # Stream records: read staging file line by line, write JSONL and
            # original_jobs simultaneously. Only one record in memory at a time.
            with open(staging_file) as sf:
                for line in sf:
                    record = json.loads(line)
                    job_data = record.get("job", {})
                    job_id = job_data.get("id", record.get("job_id", ""))

                    if not job_id:
                        job_id = f"unknown-{uuid4()}"
                        logger.warning(
                            "empty_job_id_fallback",
                            generated_id=job_id,
                            record_keys=list(record.keys()),
                        )

                    messages_body = build_messages_api_request(
                        prompt=job_data.get("prompt", ""),
                        format_schema=job_data.get("format") or None,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )

                    jsonl_record = {
                        "recordId": job_id,
                        "modelInput": messages_body,
                    }
                    input_jsonl.write(json.dumps(jsonl_record) + "\n")

                    # Write original job as JSONL (one record per line, streamable)
                    original_jobs_f.write(json.dumps({"k": job_id, "v": record}) + "\n")
            input_jsonl.close()
            original_jobs_f.close()

            # 4. Upload to S3 — streams from disk, no memory spike
            s3.upload_file(
                Filename=input_jsonl_path,
                Bucket=batch_bucket,
                Key=input_key,
                ExtraArgs={"ContentType": "application/jsonl"},
            )

            logger.info(
                "batch_jsonl_uploaded",
                bucket=batch_bucket,
                key=input_key,
                record_count=record_count,
            )

            # 5. Submit Bedrock batch job
            now = datetime.now(UTC)
            job_name = f"ppr-batch-{s3_safe_id[-8:]}-{now.strftime('%Y%m%d%H%M%S')}"
            # Job names must be <= 63 chars and match [a-zA-Z0-9][-a-zA-Z0-9]*
            job_name = job_name[:63]

            response = bedrock.create_model_invocation_job(
                jobName=job_name,
                modelId=model_id,
                roleArn=service_role_arn,
                inputDataConfig={
                    "s3InputDataConfig": {
                        "s3Uri": f"s3://{batch_bucket}/{input_key}",
                        "s3InputFormat": "JSONL",
                    }
                },
                outputDataConfig={
                    "s3OutputDataConfig": {
                        "s3Uri": f"s3://{batch_bucket}/{output_key_prefix}",
                    }
                },
            )

            job_arn = response["jobArn"]

            logger.info(
                "batch_job_submitted",
                job_arn=job_arn,
                job_name=job_name,
                model_id=model_id,
                record_count=record_count,
                execution_id=execution_id,
            )

            # 6. Store recovery data BEFORE returning.
            #    Original jobs for the result processor to map outputs back.

            # 6a. Upload original jobs to S3 (streams from disk)
            s3.upload_file(
                Filename=original_jobs_path,
                Bucket=batch_bucket,
                Key=original_jobs_key,
                ExtraArgs={"ContentType": "application/jsonl"},
            )

            # 6b. Store batch job metadata in DynamoDB for result processor
            dynamodb.put_item(
                TableName=jobs_table,
                Item={
                    "job_id": {"S": f"batch:{job_arn}"},
                    "batch_job_arn": {"S": job_arn},
                    "execution_id": {"S": execution_id},
                    "status": {"S": "submitted"},
                    "record_count": {"N": str(record_count)},
                    "input_key": {"S": input_key},
                    "output_key_prefix": {"S": output_key_prefix},
                    "original_jobs_key": {"S": original_jobs_key},
                    "created_at": {"S": now.isoformat()},
                },
            )

            # 7. Staging messages were already deleted during drain
            return {
                "mode": "batch",
                "job_arn": job_arn,
                "record_count": record_count,
            }

        finally:
            for path in (input_jsonl_path, original_jobs_path):
                try:
                    os.unlink(path)
                except OSError:
                    pass

    except Exception:
        logger.error(
            "handler_failed",
            execution_id=execution_id,
            record_count=record_count,
            decision=decision,
            exc_info=True,
        )
        raise

    finally:
        try:
            os.unlink(staging_file)
        except OSError:
            pass
