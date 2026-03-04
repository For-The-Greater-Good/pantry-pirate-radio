"""Storage Stack for Pantry Pirate Radio.

Creates S3 bucket for content store and DynamoDB tables for
job status tracking and content deduplication index.
"""

from aws_cdk import Duration, RemovalPolicy, Stack
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_s3 as s3
from constructs import Construct


class StorageStack(Stack):
    """Storage infrastructure for Pantry Pirate Radio.

    Creates:
    - S3 bucket for content store (scraped content deduplication)
    - DynamoDB table for LLM job status tracking
    - DynamoDB table for content store index

    Attributes:
        content_bucket: S3 bucket for storing deduplicated content
        jobs_table: DynamoDB table for LLM job status
        content_index_table: DynamoDB table for content hash lookups
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        environment_name: str = "dev",
        **kwargs,
    ) -> None:
        """Initialize StorageStack.

        Args:
            scope: CDK scope
            construct_id: Unique identifier for this construct
            environment_name: Environment name (dev, staging, prod)
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        self.environment_name = environment_name

        # Create S3 bucket for content store
        self.content_bucket = self._create_content_bucket()

        # Create DynamoDB tables
        self.jobs_table = self._create_jobs_table()
        self.content_index_table = self._create_content_index_table()

    def _create_content_bucket(self) -> s3.Bucket:
        """Create S3 bucket for content store.

        Features:
        - Server-side encryption with S3 managed keys
        - Versioning enabled for data protection
        - Lifecycle rules for cost optimization
        - Block all public access
        """
        bucket = s3.Bucket(
            self,
            "ContentStoreBucket",
            bucket_name=f"pantry-pirate-radio-content-{self.environment_name}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            versioned=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=(
                RemovalPolicy.RETAIN
                if self.environment_name == "prod"
                else RemovalPolicy.DESTROY
            ),
            auto_delete_objects=self.environment_name != "prod",
            lifecycle_rules=[
                # Transition old versions to cheaper storage
                s3.LifecycleRule(
                    id="TransitionOldVersions",
                    noncurrent_version_transitions=[
                        s3.NoncurrentVersionTransition(
                            storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                            transition_after=Duration.days(30),
                        ),
                        s3.NoncurrentVersionTransition(
                            storage_class=s3.StorageClass.GLACIER,
                            transition_after=Duration.days(90),
                        ),
                    ],
                ),
                # Delete old versions after 1 year
                s3.LifecycleRule(
                    id="DeleteOldVersions",
                    noncurrent_version_expiration=Duration.days(365),
                ),
                # Abort incomplete multipart uploads
                s3.LifecycleRule(
                    id="AbortIncompleteMultipartUploads",
                    abort_incomplete_multipart_upload_after=Duration.days(7),
                ),
            ],
        )

        return bucket

    def _create_jobs_table(self) -> dynamodb.Table:
        """Create DynamoDB table for LLM job status tracking.

        Schema:
        - job_id (PK): Unique job identifier
        - status: Job status (queued, processing, completed, failed)
        - created_at: Job creation timestamp
        - updated_at: Last status update timestamp
        - result: LLM response (on completion)
        - error: Error message (on failure)

        GSI:
        - status-created_at-index: Query jobs by status
        """
        table = dynamodb.Table(
            self,
            "LLMJobsTable",
            table_name=f"pantry-pirate-radio-jobs-{self.environment_name}",
            partition_key=dynamodb.Attribute(
                name="job_id",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=(
                RemovalPolicy.RETAIN
                if self.environment_name == "prod"
                else RemovalPolicy.DESTROY
            ),
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=self.environment_name == "prod"
            ),
            time_to_live_attribute="ttl",
        )

        # GSI for querying jobs by status
        table.add_global_secondary_index(
            index_name="status-created_at-index",
            partition_key=dynamodb.Attribute(
                name="status",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="created_at",
                type=dynamodb.AttributeType.STRING,
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        return table

    def _create_content_index_table(self) -> dynamodb.Table:
        """Create DynamoDB table for content store index.

        Schema:
        - content_hash (PK): SHA-256 hash of content
        - s3_key: S3 object key for the content
        - created_at: When content was first stored
        - content_type: MIME type of content
        - size_bytes: Content size in bytes
        - reference_count: Number of jobs referencing this content

        Used by S3ContentStoreBackend for deduplication lookups.
        """
        table = dynamodb.Table(
            self,
            "ContentIndexTable",
            table_name=f"pantry-pirate-radio-content-index-{self.environment_name}",
            partition_key=dynamodb.Attribute(
                name="content_hash",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=(
                RemovalPolicy.RETAIN
                if self.environment_name == "prod"
                else RemovalPolicy.DESTROY
            ),
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=self.environment_name == "prod"
            ),
        )

        return table
