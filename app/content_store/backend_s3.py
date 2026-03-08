"""S3+DynamoDB content store backend for AWS deployment.

This module provides an S3-based storage backend with DynamoDB for indexing,
enabling cloud-native deployment of the content store.
"""

from datetime import datetime
from typing import Any, Optional

import structlog

from app.content_store.backend import ContentStoreStatistics
from app.content_store.retry import with_aws_retry

logger = structlog.get_logger(__name__)


class S3ContentStoreBackend:
    """S3+DynamoDB backend for ContentStore.

    Uses S3 for content/result file storage and DynamoDB for the index,
    replacing filesystem+SQLite for AWS deployment.

    Args:
        s3_bucket: S3 bucket name for storing content
        dynamodb_table: DynamoDB table name for the index
        region_name: AWS region (optional, uses default credential chain)
        s3_prefix: Prefix for S3 object keys (optional)
    """

    def __init__(
        self,
        s3_bucket: str,
        dynamodb_table: str,
        region_name: Optional[str] = None,
        s3_prefix: str = "",
    ) -> None:
        """Initialize S3ContentStoreBackend."""
        # TODO(M33): Consider making config fields private with read-only properties
        # to prevent accidental mutation after construction. Deferred because external
        # code (including tests) currently reads these fields directly.
        self.s3_bucket = s3_bucket
        self.dynamodb_table = dynamodb_table
        self.region_name = region_name
        self.s3_prefix = s3_prefix.rstrip("/") + "/" if s3_prefix else ""

        self._s3_client: Any = None
        self._dynamodb_client: Any = None
        self._initialized = False

    def _get_s3_client(self) -> Any:
        """Get or create S3 client."""
        if self._s3_client is None:
            try:
                import boto3
            except ImportError as e:
                raise ImportError(
                    "boto3 is required for S3ContentStoreBackend. "
                    "Install it with: pip install boto3"
                ) from e

            if self.region_name:
                self._s3_client = boto3.client("s3", region_name=self.region_name)
            else:
                self._s3_client = boto3.client("s3")
        return self._s3_client

    def _get_dynamodb_client(self) -> Any:
        """Get or create DynamoDB client."""
        if self._dynamodb_client is None:
            try:
                import boto3
            except ImportError as e:
                raise ImportError(
                    "boto3 is required for S3ContentStoreBackend. "
                    "Install it with: pip install boto3"
                ) from e

            if self.region_name:
                self._dynamodb_client = boto3.client(
                    "dynamodb", region_name=self.region_name
                )
            else:
                self._dynamodb_client = boto3.client("dynamodb")
        return self._dynamodb_client

    @property
    def store_path(self) -> str:
        """Return S3 URI for the store.

        Returns str instead of Path to avoid Path normalizing 's3://' to 's3:/'.
        """
        return f"s3://{self.s3_bucket}/{self.s3_prefix}"

    @property
    def content_store_path(self) -> str:
        """Return S3 URI for content store subdirectory."""
        return f"s3://{self.s3_bucket}/{self.s3_prefix}content_store"

    @with_aws_retry
    def initialize(self) -> None:
        """Verify S3 bucket and DynamoDB table exist.

        Lets ClientError propagate so @with_aws_retry can distinguish
        transient errors (throttling, timeouts) from permanent ones
        (AccessDenied, NoSuchBucket) and retry appropriately.
        """
        if self._initialized:
            return

        s3 = self._get_s3_client()
        dynamodb = self._get_dynamodb_client()

        # Verify S3 bucket exists - let ClientError propagate for retry decorator
        s3.head_bucket(Bucket=self.s3_bucket)
        logger.info("s3_bucket_verified", bucket=self.s3_bucket)

        # Verify DynamoDB table exists - let ClientError propagate for retry decorator
        dynamodb.describe_table(TableName=self.dynamodb_table)
        logger.info("dynamodb_table_verified", table=self.dynamodb_table)

        self._initialized = True

    def _ensure_initialized(self) -> None:
        """Raise RuntimeError if initialize() has not been called."""
        if not self._initialized:
            raise RuntimeError(
                "S3ContentStoreBackend.initialize() must be called before "
                "performing operations. Call initialize() after construction."
            )

    def _get_content_key(self, content_hash: str) -> str:
        """Get S3 object key for content."""
        prefix = content_hash[:2]
        return f"{self.s3_prefix}content_store/content/{prefix}/{content_hash}.json"

    def _get_result_key(self, content_hash: str) -> str:
        """Get S3 object key for result."""
        prefix = content_hash[:2]
        return f"{self.s3_prefix}content_store/results/{prefix}/{content_hash}.json"

    @with_aws_retry
    def write_content(self, content_hash: str, data: str) -> str:
        """Write content to S3.

        Args:
            content_hash: SHA-256 hash of content
            data: JSON string content

        Returns:
            S3 URI path to stored content
        """
        self._ensure_initialized()
        s3 = self._get_s3_client()
        key = self._get_content_key(content_hash)

        s3.put_object(
            Bucket=self.s3_bucket,
            Key=key,
            Body=data.encode("utf-8"),
            ContentType="application/json",
        )
        logger.debug("s3_content_written", key=key, size=len(data))

        return f"s3://{self.s3_bucket}/{key}"

    @with_aws_retry
    def read_content(self, content_hash: str) -> Optional[str]:
        """Read content from S3.

        Args:
            content_hash: SHA-256 hash of content

        Returns:
            JSON string content or None if not found
        """
        self._ensure_initialized()
        from botocore.exceptions import ClientError

        s3 = self._get_s3_client()
        key = self._get_content_key(content_hash)

        try:
            response = s3.get_object(Bucket=self.s3_bucket, Key=key)
            return response["Body"].read().decode("utf-8")
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                return None
            raise

    @with_aws_retry
    def content_exists(self, content_hash: str) -> bool:
        """Check if content exists in S3.

        Args:
            content_hash: SHA-256 hash of content

        Returns:
            True if content exists
        """
        self._ensure_initialized()
        from botocore.exceptions import ClientError

        s3 = self._get_s3_client()
        key = self._get_content_key(content_hash)

        try:
            s3.head_object(Bucket=self.s3_bucket, Key=key)
            return True
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            # Only return False for "not found" errors, re-raise other errors
            if error_code in ("404", "NoSuchKey"):
                return False
            logger.error(
                "s3_head_object_failed",
                bucket=self.s3_bucket,
                key=key,
                error_code=error_code,
                error=str(e),
            )
            raise

    @with_aws_retry
    def write_result(self, content_hash: str, data: str) -> str:
        """Write result to S3.

        Args:
            content_hash: SHA-256 hash of original content
            data: JSON string result

        Returns:
            S3 URI path to stored result
        """
        self._ensure_initialized()
        s3 = self._get_s3_client()
        key = self._get_result_key(content_hash)

        s3.put_object(
            Bucket=self.s3_bucket,
            Key=key,
            Body=data.encode("utf-8"),
            ContentType="application/json",
        )
        logger.debug("s3_result_written", key=key, size=len(data))

        return f"s3://{self.s3_bucket}/{key}"

    @with_aws_retry
    def read_result(self, content_hash: str) -> Optional[str]:
        """Read result from S3.

        Args:
            content_hash: SHA-256 hash of original content

        Returns:
            JSON string result or None if not found
        """
        self._ensure_initialized()
        from botocore.exceptions import ClientError

        s3 = self._get_s3_client()
        key = self._get_result_key(content_hash)

        try:
            response = s3.get_object(Bucket=self.s3_bucket, Key=key)
            return response["Body"].read().decode("utf-8")
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                return None
            raise

    @with_aws_retry
    def index_has_content(self, content_hash: str) -> bool:
        """Check if content exists in DynamoDB index.

        Args:
            content_hash: SHA-256 hash of content

        Returns:
            True if content exists in index
        """
        self._ensure_initialized()
        dynamodb = self._get_dynamodb_client()

        response = dynamodb.get_item(
            TableName=self.dynamodb_table,
            Key={"content_hash": {"S": content_hash}},
            ProjectionExpression="content_hash",
        )

        return "Item" in response

    @with_aws_retry
    def index_insert_content(
        self, content_hash: str, content_path: str, created_at: datetime
    ) -> None:
        """Insert content record into DynamoDB index.

        Args:
            content_hash: SHA-256 hash of content
            content_path: S3 URI path to content
            created_at: Timestamp when content was created
        """
        self._ensure_initialized()
        from botocore.exceptions import ClientError

        dynamodb = self._get_dynamodb_client()

        try:
            dynamodb.put_item(
                TableName=self.dynamodb_table,
                Item={
                    "content_hash": {"S": content_hash},
                    "content_path": {"S": content_path},
                    "status": {"S": "pending"},
                    "created_at": {"S": created_at.isoformat()},
                },
                ConditionExpression="attribute_not_exists(content_hash)",
            )
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "ConditionalCheckFailedException":
                # Item already exists - this is idempotent, like INSERT OR IGNORE
                logger.debug("content_already_indexed", content_hash=content_hash)
                return
            raise

    @with_aws_retry
    def index_update_result(
        self,
        content_hash: str,
        result_path: str,
        job_id: str,
        processed_at: datetime,
    ) -> None:
        """Update index with result information.

        Args:
            content_hash: SHA-256 hash of content
            result_path: S3 URI path to result
            job_id: Job ID that processed the content
            processed_at: Timestamp when content was processed
        """
        self._ensure_initialized()
        dynamodb = self._get_dynamodb_client()

        dynamodb.update_item(
            TableName=self.dynamodb_table,
            Key={"content_hash": {"S": content_hash}},
            UpdateExpression=(
                "SET result_path = :rp, job_id = :jid, processed_at = :pa, #st = :status"
            ),
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={
                ":rp": {"S": result_path},
                ":jid": {"S": job_id},
                ":pa": {"S": processed_at.isoformat()},
                ":status": {"S": "completed"},
            },
        )

    @with_aws_retry
    def index_get_job_id(self, content_hash: str) -> Optional[str]:
        """Get job ID for content from DynamoDB index.

        Args:
            content_hash: SHA-256 hash of content

        Returns:
            Job ID or None if not found
        """
        self._ensure_initialized()
        dynamodb = self._get_dynamodb_client()

        response = dynamodb.get_item(
            TableName=self.dynamodb_table,
            Key={"content_hash": {"S": content_hash}},
            ProjectionExpression="job_id",
        )

        item = response.get("Item")
        if item and "job_id" in item:
            return item["job_id"]["S"]
        return None

    @with_aws_retry
    def index_set_job_id(self, content_hash: str, job_id: str) -> None:
        """Set job ID for content in DynamoDB index.

        Args:
            content_hash: SHA-256 hash of content
            job_id: Job ID to associate with content
        """
        self._ensure_initialized()
        dynamodb = self._get_dynamodb_client()

        dynamodb.update_item(
            TableName=self.dynamodb_table,
            Key={"content_hash": {"S": content_hash}},
            UpdateExpression="SET job_id = :jid",
            ExpressionAttributeValues={":jid": {"S": job_id}},
        )

    @with_aws_retry
    def index_clear_job_id(self, content_hash: str) -> None:
        """Clear job ID for content in DynamoDB index.

        Args:
            content_hash: SHA-256 hash of content
        """
        self._ensure_initialized()
        dynamodb = self._get_dynamodb_client()

        dynamodb.update_item(
            TableName=self.dynamodb_table,
            Key={"content_hash": {"S": content_hash}},
            UpdateExpression="REMOVE job_id",
        )

    @with_aws_retry
    def index_get_statistics(self) -> ContentStoreStatistics:
        """Get statistics from DynamoDB index.

        Note:
            This performs a full DynamoDB table scan. This is acceptable for
            ops dashboards since the content index table is typically small
            (<10K items). If the table grows significantly, consider maintaining
            counters via DynamoDB atomic increments instead.

        Returns:
            ContentStoreStatistics with total_content, processed_content, pending_content
        """
        self._ensure_initialized()
        dynamodb = self._get_dynamodb_client()

        # Scan table with pagination to handle tables >1MB
        items: list = []
        params: dict = {
            "TableName": self.dynamodb_table,
            "ProjectionExpression": "content_hash, result_path",
        }

        while True:
            response = dynamodb.scan(**params)
            items.extend(response.get("Items", []))

            # Check if there are more items to fetch
            if "LastEvaluatedKey" not in response:
                break
            params["ExclusiveStartKey"] = response["LastEvaluatedKey"]

        total = len(items)
        processed = sum(1 for item in items if "result_path" in item)
        pending = total - processed

        return {
            "total_content": total,
            "processed_content": processed,
            "pending_content": pending,
        }

    @with_aws_retry
    def get_store_size_bytes(self) -> int:
        """Calculate total size of stored content in S3.

        Returns:
            Total size in bytes
        """
        self._ensure_initialized()
        s3 = self._get_s3_client()
        total_size = 0
        continuation_token = None

        while True:
            params: dict = {
                "Bucket": self.s3_bucket,
                "Prefix": f"{self.s3_prefix}content_store/",
            }
            if continuation_token:
                params["ContinuationToken"] = continuation_token

            response = s3.list_objects_v2(**params)

            for obj in response.get("Contents", []):
                total_size += obj["Size"]

            if not response.get("IsTruncated"):
                break

            continuation_token = response.get("NextContinuationToken")

        return total_size
