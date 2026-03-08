"""Batcher Lambda for Bedrock Batch Inference.

Invoked by Step Functions after all scrapers complete. Drains the staging
SQS queue, counts records, and decides:
  - >= BATCH_THRESHOLD records: Build JSONL, submit Bedrock batch job (50% off)
  - < BATCH_THRESHOLD records: Re-enqueue each job to the LLM queue for
    on-demand Fargate processing

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
from datetime import UTC, datetime
from typing import Any

import structlog

from app.llm.providers.bedrock import build_converse_request
from app.pipeline.sqs_sender import send_to_sqs

logger = structlog.get_logger(__name__)

BATCH_THRESHOLD = int(os.environ.get("BATCH_THRESHOLD", "100"))


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


def _drain_staging_queue(
    sqs_client: Any,
    queue_url: str,
    max_iterations: int = 1000,
) -> list[dict[str, Any]]:
    """Drain all messages from the staging queue.

    Receives messages in batches of 10, deletes each after reading.

    Args:
        sqs_client: boto3 SQS client
        queue_url: SQS queue URL
        max_iterations: Safety limit on receive_message calls

    Returns:
        List of parsed message bodies
    """
    all_messages: list[dict[str, Any]] = []

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

        for msg in messages:
            try:
                body = json.loads(msg["Body"])
                all_messages.append(body)
                sqs_client.delete_message(
                    QueueUrl=queue_url,
                    ReceiptHandle=msg["ReceiptHandle"],
                )
            except (json.JSONDecodeError, KeyError) as e:
                logger.error(
                    "failed_to_parse_staging_message",
                    message_id=msg.get("MessageId"),
                    error=str(e),
                )

    logger.info("staging_queue_drained", total_messages=len(all_messages))
    return all_messages


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda handler invoked by Step Functions after scrapers complete.

    Args:
        event: {"execution_id": "...", "scrapers": [...]}
        context: Lambda context (unused)

    Returns:
        {"mode": "batch"|"on-demand", ...}
    """
    execution_id = event.get("execution_id", "unknown")
    # Extract the UUID portion from the Step Functions ARN for S3-safe paths.
    # ARN format: arn:aws:states:...:execution:name:uuid
    s3_safe_id = (
        execution_id.rsplit(":", 1)[-1] if ":" in execution_id else execution_id
    )
    staging_queue_url = os.environ.get("STAGING_QUEUE_URL", "")
    llm_queue_url = os.environ.get("LLM_QUEUE_URL", "")
    batch_bucket = os.environ.get("BATCH_BUCKET", "")
    model_id = os.environ.get(
        "BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    )
    service_role_arn = os.environ.get("BEDROCK_SERVICE_ROLE_ARN", "")
    temperature = float(os.environ.get("LLM_TEMPERATURE", "0.7"))
    max_tokens = int(os.environ.get("LLM_MAX_TOKENS", "8192"))
    jobs_table = os.environ.get("SQS_JOBS_TABLE", "")

    sqs, s3, bedrock, dynamodb = _get_clients()

    # 1. Drain staging queue
    records = _drain_staging_queue(sqs, staging_queue_url)
    record_count = len(records)

    # 2. Decide batch vs on-demand
    decision = "batch" if record_count >= BATCH_THRESHOLD else "on-demand"

    logger.info(
        "batch_decision",
        record_count=record_count,
        decision=decision,
        execution_id=execution_id,
        threshold=BATCH_THRESHOLD,
    )

    if record_count == 0:
        return {"mode": "on-demand", "count": 0}

    if decision == "on-demand":
        # Re-enqueue each job to LLM queue for Fargate processing
        for record in records:
            job_data = record.get("job", {})
            scraper_id = job_data.get("metadata", {}).get("scraper_id", "default")
            send_to_sqs(
                queue_url=llm_queue_url,
                message_body=record,
                message_group_id=scraper_id,
                deduplication_id=record.get("job_id", ""),
                source="batcher-lambda",
            )
        return {"mode": "on-demand", "count": record_count}

    # 3. Build JSONL for batch job
    jsonl_lines = []
    original_jobs = {}  # Map recordId -> original SQS message for error recovery
    for record in records:
        job_data = record.get("job", {})
        job_id = job_data.get("id", record.get("job_id", ""))

        converse_body = build_converse_request(
            prompt=job_data.get("prompt", ""),
            format_schema=job_data.get("format") or None,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        jsonl_record = {
            "recordId": job_id,
            "modelInput": converse_body,
        }
        jsonl_lines.append(json.dumps(jsonl_record))
        original_jobs[job_id] = record

    jsonl_content = "\n".join(jsonl_lines)

    # 4. Upload JSONL to S3
    input_key = f"input/{s3_safe_id}/input.jsonl"
    output_key_prefix = f"output/{s3_safe_id}/"

    s3.put_object(
        Bucket=batch_bucket,
        Key=input_key,
        Body=jsonl_content,
        ContentType="application/jsonl",
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
        modelInvocationType="Converse",
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

    # 6. Store original jobs in S3 (too large for DynamoDB 400KB limit)
    original_jobs_key = f"input/{s3_safe_id}/original_jobs.json"
    s3.put_object(
        Bucket=batch_bucket,
        Key=original_jobs_key,
        Body=json.dumps(original_jobs),
        ContentType="application/json",
    )

    # 7. Store batch job metadata in DynamoDB for result processor
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

    return {
        "mode": "batch",
        "job_arn": job_arn,
        "record_count": record_count,
    }
