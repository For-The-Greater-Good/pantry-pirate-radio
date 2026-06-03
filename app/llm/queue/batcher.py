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

# LLM-2: durable-checkpoint constants.
# Each drained batch is mirrored to S3 under recovery/{source}/{recovery_id}/
# BEFORE it is deleted from the staging queue, so a Lambda crash between drain
# and durable handoff (Bedrock submit / on-demand re-enqueue) can be recovered.
_RECOVERY_PREFIX = "recovery"
# An orphaned checkpoint prefix is only replayed once it is older than this.
# The batcher Lambda timeout is 900s, so a prefix whose newest object is younger
# than this CANNOT belong to a crashed run — it belongs to a still-running
# (possibly concurrent) execution mid-handoff, which must not be replayed.
_ORPHAN_MIN_AGE_S = 1200


def _checkpoint_batch(
    s3_client: Any,
    bucket: str,
    source: str,
    recovery_id: str,
    batch_seq: int,
    raw_bodies: list[str],
) -> None:
    """Durably persist one drained batch to S3 BEFORE deleting it from SQS.

    Stores the raw SQS message Body strings VERBATIM (one per line) so recovery
    can replay byte-identical staging messages — never re-serialized through a
    different envelope. A single put_object is atomic and durable on return
    (the batch is ~10 messages, far under the multipart floor).

    Raises on failure so the caller can skip the SQS delete (messages then
    return via visibility timeout — no loss).
    """
    key = f"{_RECOVERY_PREFIX}/{source}/{recovery_id}/{batch_seq:06d}.jsonl"
    body = ("\n".join(raw_bodies) + "\n").encode("utf-8")
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        ContentType="application/x-ndjson",
    )


def _delete_checkpoint_prefix(
    s3_client: Any, bucket: str, source: str, recovery_id: str
) -> None:
    """Delete this invocation's checkpoint objects after a durable handoff.

    Best-effort: a leftover checkpoint only causes a bounded, idempotent replay
    on a later run (never loss), and the bucket's 7-day lifecycle rule is the
    final backstop. Never raises — cleanup must not fail the handler.
    """
    prefix = f"{_RECOVERY_PREFIX}/{source}/{recovery_id}/"
    try:
        token: str | None = None
        while True:
            kwargs: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix}
            if token:
                kwargs["ContinuationToken"] = token
            resp = s3_client.list_objects_v2(**kwargs)
            contents = resp.get("Contents") or []
            keys = [{"Key": obj["Key"]} for obj in contents if obj.get("Key")]
            for i in range(0, len(keys), 1000):
                s3_client.delete_objects(
                    Bucket=bucket, Delete={"Objects": keys[i : i + 1000]}
                )
            if resp.get("IsTruncated"):
                token = resp.get("NextContinuationToken")
            else:
                break
    except Exception as e:
        logger.warning(
            "checkpoint_cleanup_failed",
            bucket=bucket,
            prefix=prefix,
            error=str(e),
        )


def _replay_group_id(source: str, raw_body: str) -> str:
    """Derive the FIFO MessageGroupId for a verbatim replay of a staged body.

    Scraper records group by their scraper_id (nested at job.metadata.scraper_id
    — NOT a top-level field; a wrong path collapses all replays into one FIFO
    group and serializes the whole replay). Submarine uses a single group.
    """
    if source == "submarine":
        return "submarine"
    try:
        parsed = json.loads(raw_body)
        group = parsed.get("job", {}).get("metadata", {}).get("scraper_id")
        return group or "default"
    except (json.JSONDecodeError, AttributeError):
        return "default"


def _recover_orphaned_checkpoints(
    s3_client: Any,
    sqs_client: Any,
    bucket: str,
    staging_queue_url: str,
    source: str,
    current_recovery_id: str,
) -> int:
    """Replay orphaned checkpoints from prior crashed runs back to staging.

    Lists recovery/{source}/ prefixes (scoped to this source so it never
    mis-routes another pipeline's records), groups by recovery_id, and replays
    a prefix ONLY when (a) it is not the current invocation and (b) its newest
    object is older than _ORPHAN_MIN_AGE_S — so an in-flight prefix from a
    concurrent execution mid-handoff is never grabbed. Each record is re-sent
    VERBATIM via raw send_message (no envelope wrapping), then its checkpoint
    object is deleted. Best-effort: never raises (records stay in the
    checkpoint for the next attempt if anything fails); never aborts the drain.

    Returns the number of records replayed.
    """
    prefix = f"{_RECOVERY_PREFIX}/{source}/"
    replayed = 0
    try:
        # Group objects by recovery_id with the newest LastModified per group.
        groups: dict[str, dict[str, Any]] = {}
        token: str | None = None
        while True:
            kwargs: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix}
            if token:
                kwargs["ContinuationToken"] = token
            resp = s3_client.list_objects_v2(**kwargs)
            for obj in resp.get("Contents") or []:
                key = obj.get("Key", "")
                # key = recovery/{source}/{recovery_id}/{seq}.jsonl
                parts = key[len(prefix) :].split("/")
                if len(parts) < 2 or not parts[1]:
                    continue
                rid = parts[0]
                g = groups.setdefault(rid, {"keys": [], "newest": None})
                g["keys"].append(key)
                lm = obj.get("LastModified")
                if lm is not None and (g["newest"] is None or lm > g["newest"]):
                    g["newest"] = lm
            if resp.get("IsTruncated"):
                token = resp.get("NextContinuationToken")
            else:
                break

        now = datetime.now(UTC)
        for rid, g in groups.items():
            if rid == current_recovery_id:
                continue
            newest = g["newest"]
            if newest is not None:
                age = (now - newest).total_seconds()
                if age < _ORPHAN_MIN_AGE_S:
                    # Too young — belongs to a still-running invocation.
                    continue
            for key in sorted(g["keys"]):
                obj = s3_client.get_object(Bucket=bucket, Key=key)
                payload = obj["Body"].read()
                if isinstance(payload, bytes):
                    payload = payload.decode("utf-8")
                for line in payload.splitlines():
                    if not line.strip():
                        continue
                    send_kwargs: dict[str, Any] = {
                        "QueueUrl": staging_queue_url,
                        "MessageBody": line,
                        "MessageGroupId": _replay_group_id(source, line),
                    }
                    if staging_queue_url.endswith(".fifo"):
                        try:
                            jid = json.loads(line).get("job_id") or str(uuid4())
                        except (json.JSONDecodeError, AttributeError):
                            jid = str(uuid4())
                        send_kwargs["MessageDeduplicationId"] = jid
                    sqs_client.send_message(**send_kwargs)
                    replayed += 1
                # Delete each object only after its records are re-sent, so a
                # mid-recovery crash leaves the not-yet-replayed objects intact.
                s3_client.delete_object(Bucket=bucket, Key=key)

        if replayed:
            logger.warning(
                "batcher_recovery_replayed",
                source=source,
                replayed=replayed,
                orphan_prefixes=len([r for r in groups if r != current_recovery_id]),
            )
    except Exception as e:
        logger.error(
            "batcher_recovery_scan_failed",
            source=source,
            error=str(e),
            replayed=replayed,
        )
    return replayed


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
    *,
    s3_client: Any,
    bucket: str,
    recovery_id: str,
    source: str,
    dlq_url: str = "",
    remaining_time_fn: Any = None,
    drain_budget_ms: int = 720_000,
) -> tuple[int, str, bool]:
    """Drain messages from the staging queue to a temp file.

    Receives messages in batches of 10. Each batch is deleted immediately
    after parsing to unlock the FIFO message group for subsequent receives.
    Without immediate deletion, in-flight messages block the entire group
    and the drain stalls after the first batch.

    **Durable checkpoint (LLM-2):** before deleting each batch from SQS, the
    batch's raw message bodies are written VERBATIM to a durable S3 checkpoint
    (recovery/{source}/{recovery_id}/{seq}.jsonl). The delete still happens
    per-batch (FIFO group keeps progressing) — just AFTER the durable put. If a
    crash occurs after delete but before the batch is handed off to Bedrock /
    on-demand, the next invocation replays the checkpoint (no loss). If the
    checkpoint put itself fails, this batch's delete is SKIPPED and the loop
    continues — the messages return via visibility timeout and are retried
    (one transient S3 error degrades throughput, it never loses or wedges).

    Records are written one-per-line as JSONL to a temp file so memory stays
    constant regardless of queue depth.

    Malformed (unparseable) messages are forwarded to the DLQ for inspection.

    Uses a time-based budget rather than an iteration cap so the drain adapts
    to Lambda timeout and queue depth. Reserves time for the batch submission
    step that follows.

    Args:
        sqs_client: boto3 SQS client
        queue_url: SQS queue URL
        s3_client: boto3 S3 client for durable checkpointing
        bucket: S3 bucket for checkpoints (BATCH_BUCKET)
        recovery_id: globally-unique-per-invocation id for the checkpoint prefix
        source: "scraper" or "submarine" — scopes the checkpoint prefix
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

    logger.info(
        "staging_queue_drain_starting",
        queue_url=queue_url,
        note="Each batch is checkpointed to S3 before SQS delete (recoverable)",
    )

    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".jsonl",
        delete=False,
    )
    record_count = 0
    poison_pill_count = 0
    queue_empty = False
    batch_seq = 0

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
            # Raw, verbatim message bodies for the durable checkpoint — stored
            # exactly as received so recovery can replay byte-identical messages.
            checkpoint_bodies: list[str] = []
            # Parsed bodies buffered for the temp file. Written only AFTER the
            # checkpoint succeeds, so a failed checkpoint (skipped delete) never
            # leaves records in the working file that this invocation would hand
            # off while they remain on the queue.
            parsed_for_tmp: list[dict[str, Any]] = []

            for idx, msg in enumerate(messages):
                try:
                    body = json.loads(msg["Body"])
                    parsed_for_tmp.append(body)
                    checkpoint_bodies.append(msg["Body"])
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

            # Durably checkpoint this batch to S3 BEFORE deleting from SQS, so
            # a crash after delete (but before handoff) is recoverable. If the
            # put fails, SKIP the delete and CONTINUE — the messages return via
            # visibility timeout and a later invocation retries them (no loss,
            # no FIFO wedge from aborting the whole drain). The temp-file write
            # and record_count happen only on a successful checkpoint, so a
            # skipped batch is never handed off while still on the queue.
            if checkpoint_bodies:
                try:
                    _checkpoint_batch(
                        s3_client,
                        bucket,
                        source,
                        recovery_id,
                        batch_seq,
                        checkpoint_bodies,
                    )
                    batch_seq += 1
                except Exception as e:
                    logger.error(
                        "checkpoint_put_failed",
                        recovery_id=recovery_id,
                        batch_seq=batch_seq,
                        records=len(checkpoint_bodies),
                        error=str(e),
                    )
                    continue

                for body in parsed_for_tmp:
                    tmp.write(json.dumps(body) + "\n")
                record_count += len(parsed_for_tmp)

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

    # LLM-2: a GLOBALLY-unique-per-invocation id for the durable checkpoint
    # prefix. The Lambda request id is unique across drain-loop re-invocations,
    # same-second invocations, and Step Functions retries (which get a fresh id)
    # — unlike the second-granularity s3_safe_id, which can collide and let one
    # invocation overwrite another's checkpoint.
    recovery_id = f"{base_id}_{getattr(context, 'aws_request_id', None) or uuid4().hex}"

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

    # 0. LLM-2: recover any orphaned checkpoints from a prior crashed run by
    #    replaying them (verbatim) back onto the staging queue BEFORE draining,
    #    so this invocation's drain picks them up. Best-effort and age-gated so
    #    it never grabs an in-flight prefix from a concurrent execution.
    _recover_orphaned_checkpoints(
        s3,
        sqs,
        batch_bucket,
        staging_queue_url,
        source,
        recovery_id,
    )

    # 1. Drain staging queue to a temp file. Each batch is checkpointed to S3
    #    (recovery/{source}/{recovery_id}/) BEFORE its SQS delete, then deleted
    #    per batch to unlock FIFO message groups for subsequent receives.
    remaining_time_fn = context.get_remaining_time_in_millis if context else None
    record_count, staging_file, queue_empty = _drain_staging_queue(
        sqs,
        staging_queue_url,
        s3_client=s3,
        bucket=batch_bucket,
        recovery_id=recovery_id,
        source=source,
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
            # Nothing drained this invocation; clear any checkpoints defensively.
            _delete_checkpoint_prefix(s3, batch_bucket, source, recovery_id)
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
                # LLM-2: a failed re-enqueue means those records are NOT durably
                # handed off. Leave the checkpoint so a later invocation replays
                # them (byte-identical, downstream-deduped). Only a fully clean
                # re-enqueue is a completed handoff.
            else:
                _delete_checkpoint_prefix(s3, batch_bucket, source, recovery_id)

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

            # 6. LLM-2 commit point: the batch is now durably handed off
            #    (input in S3, Bedrock job submitted, metadata in DynamoDB).
            #    Deleting the checkpoint prefix is the LAST step — a surviving
            #    checkpoint therefore always means the handoff did NOT complete,
            #    which is what makes recovery-replay safe.
            _delete_checkpoint_prefix(s3, batch_bucket, source, recovery_id)

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
