"""AWS SQS queue backend for production deployment.

This module provides an SQS-based queue backend with DynamoDB for job status
tracking, enabling cloud-native deployment of the job queue system.

Usage:
    Set environment variables:
        QUEUE_BACKEND=sqs
        SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/123456789/my-queue
        SQS_JOBS_TABLE=my-jobs-table

    Then use get_queue_backend() as normal.
"""

import json
import time
from datetime import UTC, datetime
from typing import Any, Optional

import structlog

from app.llm.providers.base import BaseLLMProvider
from app.llm.providers.types import LLMResponse
from app.llm.queue.job import LLMJob
from app.llm.queue.types import JobResult, JobStatus

logger = structlog.get_logger(__name__)


class SQSQueueBackend:
    """AWS SQS + DynamoDB queue backend implementation.

    Uses SQS for job message delivery and DynamoDB for job status tracking.
    Suitable for production AWS deployments with Fargate workers.

    Args:
        queue_url: Full SQS queue URL
        dynamodb_table: DynamoDB table name for job status tracking
        region_name: AWS region (optional, uses default credential chain)
        visibility_timeout: SQS visibility timeout in seconds (default: 300)
    """

    def __init__(
        self,
        queue_url: str,
        dynamodb_table: str,
        region_name: Optional[str] = None,
        visibility_timeout: int = 300,
    ) -> None:
        """Initialize SQSQueueBackend."""
        # Validate visibility_timeout is within SQS limits (0-43200 seconds)
        if not (0 <= visibility_timeout <= 43200):
            raise ValueError(
                f"visibility_timeout must be between 0 and 43200 seconds "
                f"(SQS limit), got {visibility_timeout}"
            )

        # TODO(M33): Consider making config fields private with read-only properties
        # to prevent accidental mutation after construction. Deferred because external
        # code (including tests) currently reads these fields directly.
        self.queue_url = queue_url
        self.dynamodb_table = dynamodb_table
        self.region_name = region_name
        self.visibility_timeout = visibility_timeout

        # Extract queue name from URL
        self._queue_name = queue_url.rstrip("/").split("/")[-1]

        self._sqs_client: Any = None
        self._dynamodb_client: Any = None
        self._initialized = False

    @property
    def queue_name(self) -> str:
        """Name of the queue (extracted from URL)."""
        return self._queue_name

    def _get_sqs_client(self) -> Any:
        """Get or create SQS client."""
        if self._sqs_client is None:
            try:
                import boto3
            except ImportError as e:
                raise ImportError(
                    "boto3 is required for SQSQueueBackend. "
                    "Install it with: pip install boto3"
                ) from e

            if self.region_name:
                self._sqs_client = boto3.client("sqs", region_name=self.region_name)
            else:
                self._sqs_client = boto3.client("sqs")
        return self._sqs_client

    def _get_dynamodb_client(self) -> Any:
        """Get or create DynamoDB client."""
        if self._dynamodb_client is None:
            try:
                import boto3
            except ImportError as e:
                raise ImportError(
                    "boto3 is required for SQSQueueBackend. "
                    "Install it with: pip install boto3"
                ) from e

            if self.region_name:
                self._dynamodb_client = boto3.client(
                    "dynamodb", region_name=self.region_name
                )
            else:
                self._dynamodb_client = boto3.client("dynamodb")
        return self._dynamodb_client

    def setup(self) -> None:
        """Initialize backend and verify AWS resources exist.

        Raises:
            ConnectionError: If SQS queue or DynamoDB table don't exist.
        """
        if self._initialized:
            return

        from botocore.exceptions import ClientError

        sqs = self._get_sqs_client()
        dynamodb = self._get_dynamodb_client()

        # Verify SQS queue exists
        try:
            sqs.get_queue_attributes(
                QueueUrl=self.queue_url, AttributeNames=["QueueArn"]
            )
            logger.info("sqs_queue_verified", queue_url=self.queue_url)
        except ClientError as e:
            logger.error(
                "sqs_queue_not_found",
                queue_url=self.queue_url,
                error=str(e),
            )
            raise ConnectionError(
                f"SQS queue not found: {self.queue_url}. "
                f"Error: {e.response['Error']['Code']}"
            ) from e

        # Verify DynamoDB table exists
        try:
            dynamodb.describe_table(TableName=self.dynamodb_table)
            logger.info("dynamodb_table_verified", table=self.dynamodb_table)
        except ClientError as e:
            logger.error(
                "dynamodb_table_not_found",
                table=self.dynamodb_table,
                error=str(e),
            )
            raise ConnectionError(
                f"DynamoDB table not found: {self.dynamodb_table}. "
                f"Error: {e.response['Error']['Code']}"
            ) from e

        self._initialized = True

    def enqueue(
        self,
        job: LLMJob,
        provider: BaseLLMProvider[Any, Any] | None = None,
    ) -> str:
        """Enqueue a job for processing.

        Sends job message to SQS and creates status record in DynamoDB.

        Args:
            job: The LLM job to enqueue
            provider: Optional LLM provider configuration (serialized to message)

        Returns:
            Job ID for tracking
        """
        sqs = self._get_sqs_client()
        dynamodb = self._get_dynamodb_client()

        now = datetime.now(UTC)

        # Prepare message body
        message_body = {
            "job_id": job.id,
            "job": job.model_dump(mode="json"),
            "provider_config": {
                "model_name": provider.model_name if provider else None,
            },
            "enqueued_at": now.isoformat(),
        }

        # Build send_message kwargs
        send_kwargs: dict[str, Any] = {
            "QueueUrl": self.queue_url,
            "MessageBody": json.dumps(message_body),
        }

        # Add FIFO queue attributes if needed.
        # We use job.id as the dedup ID intentionally — each job should be
        # processed exactly once. Re-enqueue with the same job.id is a no-op
        # within the 5-minute FIFO dedup window. Retries that need to bypass
        # dedup (e.g., batch_result_processor) append a UUID suffix.
        if self.queue_url.endswith(".fifo"):
            # SQS FIFO dedup IDs must be <=128 chars, alphanumeric + punctuation.
            # Job IDs are UUIDs (36 chars) but truncate defensively.
            send_kwargs["MessageDeduplicationId"] = job.id[:128]
            send_kwargs["MessageGroupId"] = job.metadata.get("scraper_id", "default")

        # NOTE (M26): SQS send and DynamoDB write are not atomic. We send to
        # SQS first because a lost DynamoDB write is recoverable (the message
        # will still be processed), whereas a lost SQS message would mean the
        # job is silently dropped. In the worst case, a DynamoDB write failure
        # means get_status() returns None for a job that is actually queued.
        sqs.send_message(**send_kwargs)
        logger.info("job_enqueued_to_sqs", job_id=job.id, queue=self.queue_name)

        # Create job record in DynamoDB with retry (SQS message is already sent,
        # so we must make a best-effort attempt to write the status record).
        dynamodb_item = {
            "job_id": {"S": job.id},
            "status": {"S": "queued"},
            "job_data": {"S": job.model_dump_json()},
            "created_at": {"S": now.isoformat()},
            "queue_name": {"S": self.queue_name},
        }
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                dynamodb.put_item(
                    TableName=self.dynamodb_table,
                    Item=dynamodb_item,
                )
                logger.info("job_status_created", job_id=job.id, status="queued")
                break
            except Exception as e:
                if attempt < max_attempts - 1:
                    delay = 0.1 * (2**attempt)  # 0.1s, 0.2s
                    logger.warning(
                        "dynamodb_put_item_retry",
                        job_id=job.id,
                        attempt=attempt + 1,
                        max_attempts=max_attempts,
                        delay=delay,
                        error=str(e),
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        "dynamodb_put_item_failed",
                        job_id=job.id,
                        attempts=max_attempts,
                        error=str(e),
                    )
                    raise

        return job.id

    def get_status(self, job_id: str) -> JobResult | None:
        """Get the status of a job.

        Retrieves job status and data from DynamoDB.

        Args:
            job_id: ID of the job to check

        Returns:
            JobResult if job exists, None otherwise
        """
        dynamodb = self._get_dynamodb_client()

        response = dynamodb.get_item(
            TableName=self.dynamodb_table,
            Key={"job_id": {"S": job_id}},
        )

        item = response.get("Item")
        if not item:
            return None

        # Parse job data
        job_data_str = item.get("job_data", {}).get("S")
        if not job_data_str:
            logger.warning(
                "corrupted_job_data_in_dynamodb",
                job_id=job_id,
                raw_item_keys=list(item.keys()),
            )
            return None

        llm_job = LLMJob.model_validate_json(job_data_str)

        # Map status string to enum
        status_str = item.get("status", {}).get("S", "queued")
        status_map = {
            "queued": JobStatus.QUEUED,
            "processing": JobStatus.PROCESSING,
            "completed": JobStatus.COMPLETED,
            "failed": JobStatus.FAILED,
        }
        status = status_map.get(status_str, JobStatus.QUEUED)

        # Parse result if completed
        result = None
        result_data_str = item.get("result_data", {}).get("S")
        if result_data_str and status == JobStatus.COMPLETED:
            try:
                result_dict = json.loads(result_data_str)
                result = LLMResponse(**result_dict)
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(
                    "failed_to_parse_result",
                    job_id=job_id,
                    error=str(e),
                )

        # Parse error if failed
        error = item.get("error", {}).get("S")

        # Parse timestamps
        completed_at = None
        completed_at_str = item.get("completed_at", {}).get("S")
        if completed_at_str:
            try:
                completed_at = datetime.fromisoformat(completed_at_str)
            except ValueError:
                logger.warning(
                    "failed_to_parse_completed_at",
                    job_id=job_id,
                    completed_at_str=completed_at_str,
                )

        # Calculate processing time
        processing_time = None
        started_at_str = item.get("started_at", {}).get("S")
        if started_at_str and completed_at_str:
            try:
                started_at = datetime.fromisoformat(started_at_str)
                completed_at_dt = datetime.fromisoformat(completed_at_str)
                processing_time = (completed_at_dt - started_at).total_seconds()
            except ValueError:
                logger.warning(
                    "failed_to_parse_processing_timestamps",
                    job_id=job_id,
                    started_at_str=started_at_str,
                    completed_at_str=completed_at_str,
                )

        return JobResult(
            job_id=job_id,
            job=llm_job,
            status=status,
            result=result,
            error=error,
            completed_at=completed_at,
            processing_time=processing_time,
            retry_count=int(item.get("retry_count", {}).get("N", "0")),
        )

    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        result: LLMResponse | None = None,
        error: str | None = None,
    ) -> None:
        """Update job status in DynamoDB.

        Called by workers to update job progress.

        Args:
            job_id: ID of the job to update
            status: New status
            result: Optional result (for completed jobs)
            error: Optional error message (for failed jobs)
        """
        dynamodb = self._get_dynamodb_client()

        now = datetime.now(UTC)

        # Build update expression
        update_parts = ["#status = :status"]
        expr_names = {"#status": "status"}
        expr_values: dict[str, dict[str, str]] = {":status": {"S": status.value}}

        if status == JobStatus.PROCESSING:
            update_parts.append("started_at = :started_at")
            expr_values[":started_at"] = {"S": now.isoformat()}

        if status in (JobStatus.COMPLETED, JobStatus.FAILED):
            update_parts.append("completed_at = :completed_at")
            expr_values[":completed_at"] = {"S": now.isoformat()}

        if result is not None:
            update_parts.append("result_data = :result_data")
            result_dict = {
                "text": result.text,
                "model": result.model,
                "usage": result.usage,
            }
            expr_values[":result_data"] = {"S": json.dumps(result_dict)}

        if error is not None:
            update_parts.append("#error = :error")
            expr_names["#error"] = "error"
            expr_values[":error"] = {"S": error}

        dynamodb.update_item(
            TableName=self.dynamodb_table,
            Key={"job_id": {"S": job_id}},
            UpdateExpression="SET " + ", ".join(update_parts),
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values,
        )

        logger.info(
            "job_status_updated",
            job_id=job_id,
            status=status.value,
        )

    def receive_messages(
        self,
        max_messages: int = 1,
        wait_time_seconds: int = 20,
    ) -> list[dict[str, Any]]:
        """Receive messages from SQS queue.

        Used by Fargate workers to poll for jobs.

        Args:
            max_messages: Maximum number of messages to receive (1-10)
            wait_time_seconds: Long polling wait time (0-20)

        Returns:
            List of message dictionaries with job data and receipt handle
        """
        sqs = self._get_sqs_client()

        response = sqs.receive_message(
            QueueUrl=self.queue_url,
            MaxNumberOfMessages=min(max_messages, 10),
            WaitTimeSeconds=wait_time_seconds,
            VisibilityTimeout=self.visibility_timeout,
            AttributeNames=["All"],
        )

        messages = []
        for msg in response.get("Messages", []):
            try:
                body = json.loads(msg["Body"])
                messages.append(
                    {
                        "message_id": msg["MessageId"],
                        "receipt_handle": msg["ReceiptHandle"],
                        "job_id": body["job_id"],
                        "job": LLMJob.model_validate(body["job"]),
                        "enqueued_at": body.get("enqueued_at"),
                    }
                )
            except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
                # Log the malformed message with context for debugging
                logger.error(
                    "failed_to_parse_sqs_message",
                    message_id=msg.get("MessageId"),
                    receipt_handle=msg.get("ReceiptHandle"),
                    raw_body=msg.get("Body", "")[:500],  # Truncate for logs
                    error=str(e),
                    error_type=type(e).__name__,
                )
                # Log full message body for audit trail before deletion
                logger.warning(
                    "poison_pill_message_deleted",
                    message_body=msg.get("Body", ""),
                    message_id=msg.get("MessageId"),
                )
                # Delete poison pill message to prevent infinite retry loop
                try:
                    sqs.delete_message(
                        QueueUrl=self.queue_url,
                        ReceiptHandle=msg["ReceiptHandle"],
                    )
                    logger.info(
                        "deleted_malformed_sqs_message",
                        message_id=msg.get("MessageId"),
                    )
                except Exception as delete_error:
                    logger.error(
                        "failed_to_delete_malformed_message",
                        message_id=msg.get("MessageId"),
                        error=str(delete_error),
                    )

        return messages

    def delete_message(self, receipt_handle: str) -> None:
        """Delete a message from SQS after successful processing.

        Args:
            receipt_handle: SQS receipt handle from receive_messages
        """
        sqs = self._get_sqs_client()

        sqs.delete_message(
            QueueUrl=self.queue_url,
            ReceiptHandle=receipt_handle,
        )

        logger.debug("sqs_message_deleted")

    def change_visibility(
        self,
        receipt_handle: str,
        visibility_timeout: int,
    ) -> None:
        """Extend visibility timeout for a message.

        Used to extend processing time for long-running jobs.

        Args:
            receipt_handle: SQS receipt handle
            visibility_timeout: New visibility timeout in seconds
        """
        sqs = self._get_sqs_client()

        sqs.change_message_visibility(
            QueueUrl=self.queue_url,
            ReceiptHandle=receipt_handle,
            VisibilityTimeout=visibility_timeout,
        )

        logger.debug(
            "sqs_visibility_extended",
            timeout=visibility_timeout,
        )
