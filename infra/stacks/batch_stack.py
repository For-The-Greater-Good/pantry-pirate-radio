"""Batch Inference Stack for Pantry Pirate Radio.

Creates infrastructure for Bedrock Batch Inference:
- SQS staging queue (scrapers enqueue here instead of LLM queue)
- S3 bucket for batch I/O (JSONL input/output)
- IAM service role for Bedrock batch jobs
- Batcher Lambda (drains staging queue, decides batch vs on-demand)
- Result Processor Lambda (routes batch output downstream)
- EventBridge rule for batch job completion detection
"""

import aws_cdk as cdk
from aws_cdk import Duration, RemovalPolicy, Size, Stack
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
        submarine_staging_queue: sqs.IQueue | None = None,
        submarine_extraction_queue: sqs.IQueue | None = None,
        content_index_table: dynamodb.ITable | None = None,
        database_proxy_endpoint: str | None = None,
        database_secret: object | None = None,
        proxy_security_group: ec2.ISecurityGroup | None = None,
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
            submarine_staging_queue: SQS queue for submarine batch staging (optional)
            submarine_extraction_queue: SQS queue for submarine on-demand extraction (optional)
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        self.environment_name = environment_name
        self.ecr_repository = ecr_repository
        self.submarine_staging_queue = submarine_staging_queue
        self.submarine_extraction_queue = submarine_extraction_queue
        self._vpc = vpc
        self._content_index_table = content_index_table
        self._database_proxy_endpoint = database_proxy_endpoint
        self._database_secret = database_secret
        self._proxy_security_group = proxy_security_group

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
            content_bucket=content_bucket,
        )

        # Service-level tags for cost attribution
        cdk.Tags.of(self.batcher_lambda).add("Service", "batcher")
        cdk.Tags.of(self.result_processor_lambda).add("Service", "result-processor")

        # Create EventBridge rule for batch job completion
        self._create_eventbridge_rule()

        # Grant permissions
        self._grant_permissions(
            llm_queue=llm_queue,
            validator_queue=validator_queue,
            reconciler_queue=reconciler_queue,
            recorder_queue=recorder_queue,
            jobs_table=jobs_table,
            content_bucket=content_bucket,
        )

    def _create_staging_dlq(self) -> sqs.Queue:
        """Create dead-letter queue for staging queue."""
        dlq = sqs.Queue(
            self,
            "StagingDLQ",
            queue_name=f"pantry-pirate-radio-staging-{self.environment_name}-dlq.fifo",
            fifo=True,
            content_based_deduplication=True,
            retention_period=Duration.days(14),
            encryption=sqs.QueueEncryption.SQS_MANAGED,
        )
        cfn_dlq = dlq.node.default_child
        cfn_dlq.add_property_override("DeduplicationScope", "messageGroup")
        cfn_dlq.add_property_override("FifoThroughputLimit", "perMessageGroupId")
        return dlq

    def _create_staging_queue(self) -> sqs.Queue:
        """Create SQS FIFO staging queue for scraper output.

        Matches the existing queue patterns (FIFO, content-based dedup).
        """
        queue = sqs.Queue(
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
        cfn_queue = queue.node.default_child
        cfn_queue.add_property_override("DeduplicationScope", "messageGroup")
        cfn_queue.add_property_override("FifoThroughputLimit", "perMessageGroupId")
        return queue

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

        # Bedrock InvokeModel scoped to specific model families.
        # Cross-region inference profiles (us.*) route to foundation models
        # in us-east-1, us-east-2, and us-west-2 — all three regions must
        # be permitted or batch inference fails with "no permissions".
        us_regions = ["us-east-1", "us-east-2", "us-west-2"]
        foundation_model_arns = [
            f"arn:aws:bedrock:{r}::foundation-model/anthropic.claude-*"
            for r in us_regions
        ] + [
            f"arn:aws:bedrock:{self.region}::foundation-model/amazon.titan-*",
        ]
        role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["bedrock:InvokeModel"],
                resources=foundation_model_arns
                + [
                    f"arn:aws:bedrock:{self.region}:{self.account}:inference-profile/us.anthropic.*",
                ],
            )
        )

        return role

    def _create_docker_image_code(self, cmd: list[str]) -> _lambda.DockerImageCode:
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
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=(
                RemovalPolicy.RETAIN
                if self.environment_name == "prod"
                else RemovalPolicy.DESTROY
            ),
        )

        batcher_env: dict[str, str] = {
            "STAGING_QUEUE_URL": self.staging_queue.queue_url,
            "STAGING_DLQ_URL": self.staging_dlq.queue_url,
            "LLM_QUEUE_URL": llm_queue.queue_url,
            "BATCH_BUCKET": self.batch_bucket.bucket_name,
            "BEDROCK_MODEL_ID": bedrock_model_id,
            "BEDROCK_SERVICE_ROLE_ARN": self.bedrock_service_role.role_arn,
            "LLM_TEMPERATURE": SHARED["LLM_TEMPERATURE"],
            "LLM_MAX_TOKENS": SHARED["LLM_MAX_TOKENS"],
            "SQS_JOBS_TABLE": jobs_table.table_name,
            "BATCH_THRESHOLD": str(batch_threshold),
        }
        if self.submarine_staging_queue:
            batcher_env["SUBMARINE_STAGING_QUEUE_URL"] = (
                self.submarine_staging_queue.queue_url
            )
        if self.submarine_extraction_queue:
            batcher_env["SUBMARINE_EXTRACTION_QUEUE_URL"] = (
                self.submarine_extraction_queue.queue_url
            )

        fn = _lambda.DockerImageFunction(
            self,
            "BatcherLambda",
            # function_name removed: CF can't replace custom-named resources in-place
            # (Function → DockerImageFunction). CDK auto-generates the name.
            code=self._create_docker_image_code(
                cmd=["app.llm.queue.batcher.handler"],
            ),
            timeout=Duration.seconds(900),
            memory_size=3008,
            ephemeral_storage_size=Size.gibibytes(4),
            tracing=_lambda.Tracing.ACTIVE,
            environment=batcher_env,
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
        content_bucket: s3.IBucket | None = None,
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
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=(
                RemovalPolicy.RETAIN
                if self.environment_name == "prod"
                else RemovalPolicy.DESTROY
            ),
        )

        result_processor_env: dict[str, str] = {
            "BATCH_BUCKET": self.batch_bucket.bucket_name,
            "VALIDATOR_QUEUE_URL": validator_queue.queue_url,
            "RECONCILER_QUEUE_URL": reconciler_queue.queue_url,
            "RECORDER_QUEUE_URL": recorder_queue.queue_url,
            "LLM_QUEUE_URL": llm_queue.queue_url,
            "VALIDATOR_ENABLED": SHARED["VALIDATOR_ENABLED"],
            "SQS_JOBS_TABLE": jobs_table.table_name,
            "BEDROCK_MODEL_ID": bedrock_model_id,
        }
        if content_bucket:
            result_processor_env["CONTENT_STORE_BACKEND"] = "s3"
            result_processor_env["CONTENT_STORE_ENABLED"] = "true"
            result_processor_env["CONTENT_STORE_S3_BUCKET"] = content_bucket.bucket_name
        if self._content_index_table:
            result_processor_env["CONTENT_STORE_DYNAMODB_TABLE"] = (
                self._content_index_table.table_name
            )
        if self.submarine_extraction_queue:
            result_processor_env["SUBMARINE_EXTRACTION_QUEUE_URL"] = (
                self.submarine_extraction_queue.queue_url
            )

        # Database access for submarine cooldown updates
        if self._database_proxy_endpoint:
            result_processor_env["DATABASE_PROXY_ENDPOINT"] = (
                self._database_proxy_endpoint
            )
            result_processor_env["DATABASE_NAME"] = "pantry_pirate_radio"
            result_processor_env["DATABASE_USER"] = "pantry_pirate"
        if self._database_secret:
            result_processor_env["DATABASE_SECRET_ARN"] = (
                self._database_secret.secret_arn
            )

        # VPC config for RDS Proxy access
        vpc_kwargs = {}
        if self._proxy_security_group:
            rp_sg = ec2.SecurityGroup(
                self, "ResultProcessorSG",
                vpc=self._vpc,
                description="Result processor Lambda - DB access",
            )
            vpc_kwargs["vpc"] = self._vpc
            vpc_kwargs["vpc_subnets"] = ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
            )
            vpc_kwargs["security_groups"] = [rp_sg]

        fn = _lambda.DockerImageFunction(
            self,
            "ResultProcessorLambda",
            # function_name removed: CF can't replace custom-named resources in-place
            code=self._create_docker_image_code(
                cmd=["app.llm.queue.batch_result_processor.handler"],
            ),
            timeout=Duration.seconds(900),
            memory_size=1769,
            ephemeral_storage_size=Size.gibibytes(4),
            tracing=_lambda.Tracing.ACTIVE,
            dead_letter_queue_enabled=True,
            dead_letter_queue=result_processor_dlq,
            environment=result_processor_env,
            log_group=result_processor_log_group,
            **vpc_kwargs,
        )

        # Grant DB secret read access
        if self._database_secret:
            self._database_secret.grant_read(fn)

        # Store SG for cross-stack ingress rule
        self.result_processor_security_group = (
            rp_sg if self._proxy_security_group else None
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
                    "batchJobName": [
                        {"prefix": "ppr-batch-"},
                        {"prefix": "ppr-sub-batch-"},
                    ],
                },
            ),
        )

        rule.add_target(targets.LambdaFunction(self.result_processor_lambda))

        self.eventbridge_rule = rule
        return rule

    def _grant_permissions(
        self,
        llm_queue: sqs.IQueue,
        validator_queue: sqs.IQueue,
        reconciler_queue: sqs.IQueue,
        recorder_queue: sqs.IQueue,
        jobs_table: dynamodb.ITable,
        content_bucket: s3.IBucket | None = None,
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
        self.staging_dlq.grant_send_messages(self.batcher_lambda)
        llm_queue.grant_send_messages(self.batcher_lambda)
        self.batch_bucket.grant_read_write(self.batcher_lambda)
        jobs_table.grant_read_write_data(self.batcher_lambda)

        # Batcher Lambda: submarine queue permissions (optional)
        if self.submarine_staging_queue:
            self.submarine_staging_queue.grant_consume_messages(self.batcher_lambda)
        if self.submarine_extraction_queue:
            self.submarine_extraction_queue.grant_send_messages(self.batcher_lambda)

        # Result Processor Lambda permissions
        self.batch_bucket.grant_read(self.result_processor_lambda)
        validator_queue.grant_send_messages(self.result_processor_lambda)
        reconciler_queue.grant_send_messages(self.result_processor_lambda)
        recorder_queue.grant_send_messages(self.result_processor_lambda)
        llm_queue.grant_send_messages(self.result_processor_lambda)
        jobs_table.grant_read_write_data(self.result_processor_lambda)
        # Content store: write results back to prevent re-processing
        if content_bucket:
            content_bucket.grant_read_write(self.result_processor_lambda)
        if self._content_index_table:
            self._content_index_table.grant_read_write_data(
                self.result_processor_lambda
            )

        # Result Processor Lambda: submarine extraction queue (optional)
        if self.submarine_extraction_queue:
            self.submarine_extraction_queue.grant_send_messages(
                self.result_processor_lambda
            )
