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
from app.llm.queue.s3_jsonl_writer import S3JsonlWriter
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
    remaining_time_fn: Any = None,
    drain_budget_ms: int = 720_000,
) -> tuple[int, str, bool]:
    """Drain messages from the staging queue to a temp file.

    **DATA LOSS RISK**: Messages are deleted from SQS during drain to unlock
    the FIFO message group. If this Lambda crashes after drain but before the
    batch is submitted to Bedrock, the drained records are unrecoverable.
    A future improvement could checkpoint records to S3 before deleting from SQS.

    Receives messages in batches of 10. Each batch is deleted immediately
    after parsing to unlock the FIFO message group for subsequent receives.
    Without immediate deletion, in-flight messages block the entire group
    and the drain stalls after the first batch.

    Records are written one-per-line as JSONL to a temp file so memory stays
    constant regardless of queue depth.

    Malformed (unparseable) messages are forwarded to the DLQ for inspection.

    Uses a time-based budget rather than an iteration cap so the drain adapts
    to Lambda timeout and queue depth. Reserves time for the batch submission
    step that follows.

    Args:
        sqs_client: boto3 SQS client
        queue_url: SQS queue URL
        dlq_url: DLQ URL for poison pill forwarding
        remaining_time_fn: Callable returning remaining Lambda time in ms
            (typically context.get_remaining_time_in_millis)
        drain_budget_ms: Fallback time budget in ms if remaining_time_fn
            is not provided (default: 720s = 12 min, leaving 3 min for
            batch submission on a 15 min Lambda)

    Returns:
        (record_count, temp_file_path, queue_empty) — caller must delete
        the temp file. queue_empty indicates whether the queue was fully
        drained or if more records remain.
    """
    # Reserve 120s (2 min) for batch build + S3 upload + Bedrock submission
    _RESERVE_MS = 120_000

    logger.warning(
        "staging_queue_drain_starting",
        queue_url=queue_url,
        note="Messages deleted during drain are unrecoverable if Lambda crashes before batch submission",
    )

    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".jsonl",
        delete=False,
    )
    record_count = 0
    poison_pill_count = 0
    queue_empty = False

    try:
        while True:
            # Time budget check
            if remaining_time_fn:
                remaining = remaining_time_fn()
                if remaining < _RESERVE_MS:
                    logger.info(
                        "drain_time_budget_exhausted",
                        remaining_ms=remaining,
                        reserve_ms=_RESERVE_MS,
                        records_so_far=record_count,
                    )
                    break
            elif record_count >= (drain_budget_ms // 100) * 10:
                # Rough fallback: ~100ms per receive of 10 msgs
                break
            response = sqs_client.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=1,
                VisibilityTimeout=300,
            )

            messages = response.get("Messages", [])
            if not messages:
                queue_empty = True
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
                batch_resp = sqs_client.delete_message_batch(
                    QueueUrl=queue_url,
                    Entries=batch_delete_entries,
                )
                failed = batch_resp.get("Failed", [])
                if failed:
                    logger.warning(
                        "delete_message_batch_partial_failure",
                        failed_count=len(failed),
                        failed_ids=[f["Id"] for f in failed],
                        error_codes=[f.get("Code", "") for f in failed],
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

    logger.info(
        "staging_queue_drained",
        total_messages=record_count,
        queue_empty=queue_empty,
    )
    return record_count, tmp.name, queue_empty


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda handler invoked by Step Functions after scrapers complete.

    Args:
        event: {"execution_id": "...", "scrapers": [...]}
        context: Lambda context (unused)

    Returns:
        {"mode": "batch"|"on-demand", ...}
    """
    # Validate required environment variables up front
    # STAGING_QUEUE_URL and LLM_QUEUE_URL are only required for scraper source;
    # submarine uses its own queue URLs from get_submarine_batcher_config().
    _required_env_vars = {
        "BATCH_BUCKET": os.environ.get("BATCH_BUCKET", ""),
        "BEDROCK_SERVICE_ROLE_ARN": os.environ.get("BEDROCK_SERVICE_ROLE_ARN", ""),
    }
    _scraper_env_vars = {
        "STAGING_QUEUE_URL": os.environ.get("STAGING_QUEUE_URL", ""),
        "LLM_QUEUE_URL": os.environ.get("LLM_QUEUE_URL", ""),
    }
    _required_env_vars.update(_scraper_env_vars)
    source = event.get("source", "scraper")
    check_vars = (
        _required_env_vars
        if source != "submarine"
        else {
            k: v
            for k, v in _required_env_vars.items()
            if k not in ("STAGING_QUEUE_URL", "LLM_QUEUE_URL")
        }
    )
    missing = [name for name, val in check_vars.items() if not val]
    if missing:
        raise ValueError(
            f"Missing required environment variables: {', '.join(sorted(missing))}"
        )

    execution_id = event.get("execution_id", "unknown")
    source = event.get("source", "scraper")

    # Extract the UUID portion from the Step Functions ARN for S3-safe paths.
    # ARN format: arn:aws:states:...:execution:name:uuid
    # Append a timestamp so re-invocations within the same execution
    # (drain loop) get unique S3 prefixes and Bedrock job names.
    base_id = execution_id.rsplit(":", 1)[-1] if ":" in execution_id else execution_id
    batch_ts = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    s3_safe_id = f"{base_id}_{batch_ts}"

    # Source-specific queue routing
    if source == "submarine":
        from app.llm.queue.submarine_batch import get_submarine_batcher_config

        sub_config = get_submarine_batcher_config()
        staging_queue_url = sub_config["staging_queue_url"]
        on_demand_queue_url = sub_config["on_demand_queue_url"]
        job_name_prefix = sub_config["job_name_prefix"]
    else:
        staging_queue_url = _required_env_vars["STAGING_QUEUE_URL"]
        on_demand_queue_url = _required_env_vars["LLM_QUEUE_URL"]
        job_name_prefix = "ppr-batch"

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
    remaining_time_fn = context.get_remaining_time_in_millis if context else None
    record_count, staging_file, queue_empty = _drain_staging_queue(
        sqs,
        staging_queue_url,
        dlq_url=staging_dlq_url,
        remaining_time_fn=remaining_time_fn,
    )

    # Pre-bind so the outer except's logger.error never NameErrors and masks
    # the real exception even if a future refactor moves work above the assignment.
    decision = "unknown"

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
            return {
                "mode": "on-demand",
                "record_count": 0,
                "failed": 0,
                "queue_empty": True,
            }

        if decision == "on-demand":
            # Re-enqueue each job to the appropriate on-demand queue.
            # Staging messages were already deleted during drain.
            succeeded = 0
            failed_count = 0

            with open(staging_file) as f:
                for line in f:
                    record = json.loads(line)
                    try:
                        if source == "submarine":
                            from app.llm.queue.submarine_batch import (
                                requeue_submarine_on_demand,
                            )

                            requeue_submarine_on_demand(record, on_demand_queue_url)
                        else:
                            job_data = record.get("job", {})
                            scraper_id = job_data.get("metadata", {}).get(
                                "scraper_id", "default"
                            )
                            send_to_sqs(
                                queue_url=on_demand_queue_url,
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
                "record_count": succeeded,
                "failed": failed_count,
                "queue_empty": queue_empty,
            }

        # 3. Stream JSONL + original_jobs directly to S3.
        #    /tmp on Lambda is capped at 4 GiB; large drains exceed that.
        #    S3JsonlWriter buffers ~8 MiB and uploads multipart, keeping
        #    memory constant regardless of payload size.
        input_key = f"input/{s3_safe_id}/input.jsonl"
        output_key_prefix = f"output/{s3_safe_id}/"
        original_jobs_key = f"input/{s3_safe_id}/original_jobs.jsonl"

        input_writer = S3JsonlWriter(s3, batch_bucket, input_key)
        original_jobs_writer = S3JsonlWriter(s3, batch_bucket, original_jobs_key)

        try:
            with input_writer, original_jobs_writer:
                with open(staging_file) as sf:
                    for line in sf:
                        record = json.loads(line)

                        if source == "submarine":
                            from app.llm.queue.submarine_batch import (
                                extract_submarine_record,
                            )

                            job_id, messages_body = extract_submarine_record(record)
                        else:
                            job_data = record.get("job", {})
                            job_id = job_data.get("id", record.get("job_id", ""))
                            messages_body = build_messages_api_request(
                                prompt=job_data.get("prompt", ""),
                                format_schema=job_data.get("format") or None,
                                temperature=temperature,
                                max_tokens=max_tokens,
                            )

                        if not job_id:
                            job_id = f"unknown-{uuid4()}"
                            logger.warning(
                                "empty_job_id_fallback",
                                generated_id=job_id,
                                record_keys=list(record.keys()),
                            )

                        input_writer.write_record(
                            {"recordId": job_id, "modelInput": messages_body}
                        )
                        original_jobs_writer.write_record({"k": job_id, "v": record})

            logger.info(
                "batch_jsonl_uploaded",
                bucket=batch_bucket,
                key=input_key,
                record_count=record_count,
            )

            # 4. Submit Bedrock batch job
            now = datetime.now(UTC)
            job_name = (
                f"{job_name_prefix}-{s3_safe_id[-8:]}-{now.strftime('%Y%m%d%H%M%S')}"
            )
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

            # 5. Store batch job metadata in DynamoDB for result processor.
            #    original_jobs was already uploaded by the streaming writer above.
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
                    "source": {"S": source},
                    "created_at": {"S": now.isoformat()},
                },
            )

            # 6. Staging messages were already deleted during drain
            return {
                "mode": "batch",
                "job_arn": job_arn,
                "record_count": record_count,
                "queue_empty": queue_empty,
            }

        except Exception:
            # Abort any in-progress multipart uploads to avoid orphan parts.
            input_writer.abort()
            original_jobs_writer.abort()
            raise

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
