"""Batch Inference Stack for Pantry Pirate Radio.

Creates infrastructure for Bedrock Batch Inference:
- SQS staging queue (scrapers enqueue here instead of LLM queue)
- S3 bucket for batch I/O (JSONL input/output)
- IAM service role for Bedrock batch jobs
- Batcher Lambda (drains staging queue, decides batch vs on-demand)
- Result Processor Lambda (routes batch output downstream)
- EventBridge rule for batch job completion detection
"""

from aws_cdk import Duration, RemovalPolicy, Stack
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_sqs as sqs
from constructs import Construct
from shared_config import SHARED


class BatchInferenceStack(Stack):
    """Batch inference infrastructure for Bedrock cost optimization.

    Creates:
    - SQS staging queue for scrapers to enqueue to
    - S3 bucket for batch JSONL I/O
    - IAM service role for Bedrock batch jobs
    - Batcher Lambda (post-scraper decision: batch vs on-demand)
    - Result Processor Lambda (routes batch results downstream)
    - EventBridge rule for batch job state changes

    Attributes:
        staging_queue: SQS FIFO queue for scraper output staging
        batch_bucket: S3 bucket for batch I/O
        batcher_lambda: Lambda function for batch decision
        result_processor_lambda: Lambda function for result routing
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        environment_name: str = "dev",
        content_bucket: s3.IBucket,
        jobs_table: dynamodb.ITable,
        llm_queue: sqs.IQueue,
        validator_queue: sqs.IQueue,
        reconciler_queue: sqs.IQueue,
        recorder_queue: sqs.IQueue,
        vpc: ec2.IVpc,
        bedrock_model_id: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0",
        batch_threshold: int = 100,
        ecr_repository: ecr.IRepository | None = None,
        **kwargs,
    ) -> None:
        """Initialize BatchInferenceStack.

        Args:
            scope: CDK scope
            construct_id: Unique identifier
            environment_name: Environment name (dev, staging, prod)
            content_bucket: S3 bucket for content store
            jobs_table: DynamoDB table for job tracking
            llm_queue: SQS LLM queue (for on-demand fallback)
            validator_queue: SQS validator queue
            reconciler_queue: SQS reconciler queue
            recorder_queue: SQS recorder queue
            vpc: VPC for Lambda functions
            bedrock_model_id: Bedrock model ID for batch jobs
            batch_threshold: Minimum records for batch processing
            ecr_repository: ECR repository for batch Lambda Docker image
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        self.environment_name = environment_name
        self.ecr_repository = ecr_repository

        # Create staging queue
        self.staging_dlq = self._create_staging_dlq()
        self.staging_queue = self._create_staging_queue()

        # Create batch I/O bucket
        self.batch_bucket = self._create_batch_bucket()

        # Create Bedrock service role
        self.bedrock_service_role = self._create_bedrock_service_role()

        # Create Batcher Lambda
        self.batcher_lambda = self._create_batcher_lambda(
            llm_queue=llm_queue,
            jobs_table=jobs_table,
            bedrock_model_id=bedrock_model_id,
            batch_threshold=batch_threshold,
        )

        # Create Result Processor Lambda
        self.result_processor_lambda = self._create_result_processor_lambda(
            llm_queue=llm_queue,
            validator_queue=validator_queue,
            reconciler_queue=reconciler_queue,
            recorder_queue=recorder_queue,
            jobs_table=jobs_table,
            bedrock_model_id=bedrock_model_id,
        )

        # Create EventBridge rule for batch job completion
        self._create_eventbridge_rule()

        # Grant permissions
        self._grant_permissions(
            llm_queue=llm_queue,
            validator_queue=validator_queue,
            reconciler_queue=reconciler_queue,
            recorder_queue=recorder_queue,
            jobs_table=jobs_table,
        )

    def _create_staging_dlq(self) -> sqs.Queue:
        """Create dead-letter queue for staging queue."""
        return sqs.Queue(
            self,
            "StagingDLQ",
            queue_name=f"pantry-pirate-radio-staging-{self.environment_name}-dlq.fifo",
            fifo=True,
            content_based_deduplication=True,
            retention_period=Duration.days(14),
            encryption=sqs.QueueEncryption.SQS_MANAGED,
        )

    def _create_staging_queue(self) -> sqs.Queue:
        """Create SQS FIFO staging queue for scraper output.

        Matches the existing queue patterns (FIFO, content-based dedup).
        """
        return sqs.Queue(
            self,
            "StagingQueue",
            queue_name=f"pantry-pirate-radio-staging-{self.environment_name}.fifo",
            fifo=True,
            content_based_deduplication=True,
            visibility_timeout=Duration.seconds(300),
            retention_period=Duration.days(7),
            encryption=sqs.QueueEncryption.SQS_MANAGED,
            dead_letter_queue=sqs.DeadLetterQueue(
                queue=self.staging_dlq,
                max_receive_count=3,
            ),
        )

    def _create_batch_bucket(self) -> s3.Bucket:
        """Create S3 bucket for batch JSONL I/O.

        7-day lifecycle for automatic cleanup.
        """
        return s3.Bucket(
            self,
            "BatchBucket",
            bucket_name=f"pantry-pirate-radio-batch-{self.environment_name}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=(
                RemovalPolicy.RETAIN
                if self.environment_name == "prod"
                else RemovalPolicy.DESTROY
            ),
            auto_delete_objects=self.environment_name != "prod",
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="ExpireBatchData",
                    expiration=Duration.days(7),
                    enabled=True,
                ),
            ],
        )

    def _create_bedrock_service_role(self) -> iam.Role:
        """Create IAM service role for Bedrock batch jobs.

        Trusts bedrock.amazonaws.com, grants S3 and InvokeModel.
        """
        role = iam.Role(
            self,
            "BedrockBatchRole",
            role_name=f"pantry-pirate-radio-bedrock-batch-{self.environment_name}",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
        )

        # S3 read/write for batch I/O
        self.batch_bucket.grant_read_write(role)

        # Bedrock InvokeModel scoped to specific model families
        role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["bedrock:InvokeModel"],
                resources=[
                    f"arn:aws:bedrock:{self.region}::foundation-model/anthropic.claude-*",
                    f"arn:aws:bedrock:{self.region}::foundation-model/amazon.titan-*",
                    f"arn:aws:bedrock:{self.region}:{self.account}:inference-profile/us.anthropic.*",
                ],
            )
        )

        return role

    def _create_docker_image_code(
        self, cmd: list[str]
    ) -> _lambda.DockerImageCode:
        """Create Docker image code from ECR or local asset.

        Args:
            cmd: Lambda CMD override (e.g. ["app.llm.queue.batcher.handler"])

        Returns:
            DockerImageCode instance
        """
        if self.ecr_repository:
            return _lambda.DockerImageCode.from_ecr(
                repository=self.ecr_repository,
                tag_or_digest="latest",
                cmd=cmd,
            )
        return _lambda.DockerImageCode.from_image_asset(
            directory="..",
            file=".docker/images/batch-lambda/Dockerfile",
            cmd=cmd,
        )

    def _create_batcher_lambda(
        self,
        llm_queue: sqs.IQueue,
        jobs_table: dynamodb.ITable,
        bedrock_model_id: str,
        batch_threshold: int,
    ) -> _lambda.DockerImageFunction:
        """Create Batcher Lambda function.

        Drains staging queue, decides batch vs on-demand.
        """
        batcher_log_group = logs.LogGroup(
            self,
            "BatcherLambdaLogs",
            log_group_name=f"/aws/lambda/pantry-pirate-radio-batcher-{self.environment_name}",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )

        fn = _lambda.DockerImageFunction(
            self,
            "BatcherLambda",
            # function_name removed: CF can't replace custom-named resources in-place
            # (Function → DockerImageFunction). CDK auto-generates the name.
            code=self._create_docker_image_code(
                cmd=["app.llm.queue.batcher.handler"],
            ),
            timeout=Duration.seconds(300),
            memory_size=512,
            tracing=_lambda.Tracing.ACTIVE,
            environment={
                "STAGING_QUEUE_URL": self.staging_queue.queue_url,
                "LLM_QUEUE_URL": llm_queue.queue_url,
                "BATCH_BUCKET": self.batch_bucket.bucket_name,
                "BEDROCK_MODEL_ID": bedrock_model_id,
                "BEDROCK_SERVICE_ROLE_ARN": self.bedrock_service_role.role_arn,
                "LLM_TEMPERATURE": SHARED["LLM_TEMPERATURE"],
                "LLM_MAX_TOKENS": SHARED["LLM_MAX_TOKENS"],
                "SQS_JOBS_TABLE": jobs_table.table_name,
                "BATCH_THRESHOLD": str(batch_threshold),
            },
            log_group=batcher_log_group,
        )

        # Grant Bedrock batch job management
        fn.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:CreateModelInvocationJob",
                    "bedrock:GetModelInvocationJob",
                    "bedrock:ListModelInvocationJobs",
                ],
                resources=["*"],
            )
        )

        # Grant passing the Bedrock service role
        fn.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["iam:PassRole"],
                resources=[self.bedrock_service_role.role_arn],
            )
        )

        return fn

    def _create_result_processor_lambda(
        self,
        llm_queue: sqs.IQueue,
        validator_queue: sqs.IQueue,
        reconciler_queue: sqs.IQueue,
        recorder_queue: sqs.IQueue,
        jobs_table: dynamodb.ITable,
        bedrock_model_id: str,
    ) -> _lambda.DockerImageFunction:
        """Create Result Processor Lambda function.

        Routes batch output downstream.
        """
        # Create DLQ for result processor
        result_processor_dlq = sqs.Queue(
            self,
            "ResultProcessorDLQ",
            queue_name=f"pantry-pirate-radio-result-processor-dlq-{self.environment_name}",
            retention_period=Duration.days(14),
        )

        result_processor_log_group = logs.LogGroup(
            self,
            "ResultProcessorLambdaLogs",
            log_group_name=f"/aws/lambda/pantry-pirate-radio-result-processor-{self.environment_name}",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )

        fn = _lambda.DockerImageFunction(
            self,
            "ResultProcessorLambda",
            # function_name removed: CF can't replace custom-named resources in-place
            code=self._create_docker_image_code(
                cmd=["app.llm.queue.batch_result_processor.handler"],
            ),
            timeout=Duration.seconds(900),
            memory_size=1024,
            tracing=_lambda.Tracing.ACTIVE,
            dead_letter_queue_enabled=True,
            dead_letter_queue=result_processor_dlq,
            environment={
                "BATCH_BUCKET": self.batch_bucket.bucket_name,
                "VALIDATOR_QUEUE_URL": validator_queue.queue_url,
                "RECONCILER_QUEUE_URL": reconciler_queue.queue_url,
                "RECORDER_QUEUE_URL": recorder_queue.queue_url,
                "LLM_QUEUE_URL": llm_queue.queue_url,
                "VALIDATOR_ENABLED": SHARED["VALIDATOR_ENABLED"],
                "SQS_JOBS_TABLE": jobs_table.table_name,
                "BEDROCK_MODEL_ID": bedrock_model_id,
            },
            log_group=result_processor_log_group,
        )

        return fn

    def _create_eventbridge_rule(self) -> events.Rule:
        """Create EventBridge rule for Bedrock batch job state changes.

        Triggers result processor on Completed, PartiallyCompleted, Failed.
        """
        rule = events.Rule(
            self,
            "BatchJobStateChangeRule",
            rule_name=f"pantry-pirate-radio-batch-state-{self.environment_name}",
            description="Triggers result processor when Bedrock batch job completes",
            event_pattern=events.EventPattern(
                source=["aws.bedrock"],
                detail_type=["Batch Inference Job State Change"],
                detail={
                    "status": ["Completed", "PartiallyCompleted", "Failed"],
                },
            ),
        )

        rule.add_target(
            targets.LambdaFunction(self.result_processor_lambda)
        )

        self.eventbridge_rule = rule
        return rule

    def _grant_permissions(
        self,
        llm_queue: sqs.IQueue,
        validator_queue: sqs.IQueue,
        reconciler_queue: sqs.IQueue,
        recorder_queue: sqs.IQueue,
        jobs_table: dynamodb.ITable,
    ) -> None:
        """Grant cross-resource permissions.

        Args:
            llm_queue: LLM queue for on-demand fallback
            validator_queue: Validator queue for downstream routing
            reconciler_queue: Reconciler queue for downstream routing
            recorder_queue: Recorder queue for result copies
            jobs_table: DynamoDB table for job tracking
        """
        # Batcher Lambda permissions
        self.staging_queue.grant_consume_messages(self.batcher_lambda)
        llm_queue.grant_send_messages(self.batcher_lambda)
        self.batch_bucket.grant_read_write(self.batcher_lambda)
        jobs_table.grant_read_write_data(self.batcher_lambda)

        # Result Processor Lambda permissions
        self.batch_bucket.grant_read(self.result_processor_lambda)
        validator_queue.grant_send_messages(self.result_processor_lambda)
        reconciler_queue.grant_send_messages(self.result_processor_lambda)
        recorder_queue.grant_send_messages(self.result_processor_lambda)
        llm_queue.grant_send_messages(self.result_processor_lambda)
        jobs_table.grant_read_data(self.result_processor_lambda)
