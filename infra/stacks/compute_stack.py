"""Compute Stack for Pantry Pirate Radio.

Creates ECS Fargate cluster and services for running LLM workers.
"""

import aws_cdk as cdk
from aws_cdk import Duration, RemovalPolicy, Stack
from aws_cdk import aws_applicationautoscaling as appscaling
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_cdk import aws_sqs as sqs
from constructs import Construct


class ComputeStack(Stack):
    """Compute infrastructure for LLM job processing.

    Creates:
    - VPC with public/private subnets
    - ECS Fargate cluster
    - Fargate service for LLM workers
    - IAM roles with necessary permissions

    Attributes:
        vpc: VPC for ECS resources
        cluster: ECS Fargate cluster
        worker_service: ECS Fargate service for LLM workers
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        environment_name: str = "dev",
        worker_cpu: int = 1024,
        worker_memory_mib: int = 2048,
        desired_count: int = 1,
        max_capacity: int = 10,
        ecr_repository_name: str | None = None,
        ecr_repository: ecr.IRepository | None = None,
        image_tag: str = "latest",
        llm_queue_url: str | None = None,
        llm_dlq_url: str | None = None,
        sqs_jobs_table_name: str | None = None,
        validator_queue_url: str | None = None,
        content_bucket_name: str | None = None,
        content_index_table_name: str | None = None,
        **kwargs,
    ) -> None:
        """Initialize ComputeStack.

        Args:
            scope: CDK scope
            construct_id: Unique identifier for this construct
            environment_name: Environment name (dev, staging, prod)
            worker_cpu: CPU units for worker task (1024 = 1 vCPU)
            worker_memory_mib: Memory in MiB for worker task
            desired_count: Desired number of worker tasks
            max_capacity: Maximum number of worker tasks for scaling
            ecr_repository_name: Name of ECR repository for worker image
            ecr_repository: ECR repository object for worker image (auto-grants pull permissions)
            image_tag: Docker image tag to deploy
            llm_queue_url: SQS queue URL for LLM jobs
            sqs_jobs_table_name: DynamoDB table name for job status tracking
            validator_queue_url: SQS queue URL for forwarding results to validator
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        self.environment_name = environment_name
        self.worker_cpu = worker_cpu
        self.worker_memory_mib = worker_memory_mib
        self.desired_count = desired_count
        self.max_capacity = max_capacity
        self.ecr_repository_name = (
            ecr_repository_name or f"pantry-pirate-radio-worker-{environment_name}"
        )
        self.ecr_repository = ecr_repository
        self.image_tag = image_tag
        self.llm_queue_url = llm_queue_url
        self.llm_dlq_url = llm_dlq_url
        self.sqs_jobs_table_name = sqs_jobs_table_name
        self.content_bucket_name = content_bucket_name
        self.content_index_table_name = content_index_table_name
        self.validator_queue_url = validator_queue_url

        # Create VPC
        self.vpc = self._create_vpc()

        # Create VPC Endpoints (reduce NAT Gateway traffic and cost)
        self._create_vpc_endpoints()

        # Create ECS cluster
        self.cluster = self._create_cluster()

        # Create log group
        self.log_group = self._create_log_group()

        # Create task execution role
        self.task_execution_role = self._create_task_execution_role()

        # Create task role (for Fargate worker permissions)
        self.task_role = self._create_task_role()

        # Create task definition
        self.task_definition = self._create_task_definition()

        # Create Fargate service
        self.worker_service = self._create_worker_service()

        # Expose worker security group for database wiring
        self.worker_security_group = self.worker_service.connections.security_groups[0]

        # Service-level tag for cost attribution
        cdk.Tags.of(self.worker_service).add("Service", "worker")

    def _create_vpc(self) -> ec2.Vpc:
        """Create VPC for ECS resources.

        Uses a single NAT Instance (t4g.nano, ~$3/mo) for cost savings.
        Managed NAT Gateways ($32+/mo each) are not worth it for this workload.
        """
        nat_provider = ec2.NatProvider.instance_v2(
            instance_type=ec2.InstanceType("t4g.nano"),
            default_allowed_traffic=ec2.NatTrafficDirection.INBOUND_AND_OUTBOUND,
        )

        vpc = ec2.Vpc(
            self,
            "WorkerVPC",
            vpc_name=f"pantry-pirate-radio-{self.environment_name}",
            max_azs=2,
            nat_gateways=1,
            nat_gateway_provider=nat_provider,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
            ],
        )

        return vpc

    def _create_vpc_endpoints(self) -> None:
        """Create VPC endpoints to reduce NAT Gateway data transfer costs.

        Gateway endpoints (free, no hourly charge):
        - S3: Content store, batch bucket, exports bucket, ECR image layers
        - DynamoDB: Jobs table, content index, geocoding cache

        Interface endpoints (~$14.40/month each in 2 AZs):
        - ECR API + DKR: Docker image pull auth/metadata (layers via S3 gateway)
        - CloudWatch Logs: All Fargate container log writes

        At ~$43/month total, these save $150-200/month in NAT data transfer
        from ECR image pulls and log writes across all Fargate services.
        """
        self.vpc.add_gateway_endpoint(
            "S3Endpoint",
            service=ec2.GatewayVpcEndpointAwsService.S3,
        )
        self.vpc.add_gateway_endpoint(
            "DynamoDBEndpoint",
            service=ec2.GatewayVpcEndpointAwsService.DYNAMODB,
        )

        # Interface endpoints for ECR and CloudWatch Logs
        # These route high-volume traffic privately, bypassing NAT Gateway
        self.vpc.add_interface_endpoint(
            "EcrApiEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.ECR,
            private_dns_enabled=True,
        )
        self.vpc.add_interface_endpoint(
            "EcrDkrEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.ECR_DOCKER,
            private_dns_enabled=True,
        )
        self.vpc.add_interface_endpoint(
            "CloudWatchLogsEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS,
            private_dns_enabled=True,
        )

    def _create_cluster(self) -> ecs.Cluster:
        """Create ECS Fargate cluster."""
        cluster = ecs.Cluster(
            self,
            "WorkerCluster",
            cluster_name=f"pantry-pirate-radio-{self.environment_name}",
            vpc=self.vpc,
            container_insights_v2=ecs.ContainerInsights.ENABLED,
        )

        return cluster

    def _create_log_group(self) -> logs.LogGroup:
        """Create CloudWatch log group for worker logs."""
        log_group = logs.LogGroup(
            self,
            "WorkerLogs",
            log_group_name=f"/ecs/pantry-pirate-radio-worker-{self.environment_name}",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=(
                RemovalPolicy.RETAIN
                if self.environment_name == "prod"
                else RemovalPolicy.DESTROY
            ),
        )

        return log_group

    def _create_task_execution_role(self) -> iam.Role:
        """Create IAM role for ECS task execution.

        This role is used by ECS to pull images and write logs.
        """
        role = iam.Role(
            self,
            "TaskExecutionRole",
            role_name=f"pantry-pirate-radio-execution-{self.environment_name}",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonECSTaskExecutionRolePolicy"
                ),
            ],
        )

        return role

    def _create_task_role(self) -> iam.Role:
        """Create IAM role for Fargate worker tasks.

        This role grants permissions needed by the worker:
        - SQS: Read/delete messages, change visibility
        - DynamoDB: Read/write job status
        - S3: Read/write content store
        - Bedrock: Invoke LLM models
        - Secrets Manager: Read API keys (if used)
        """
        role = iam.Role(
            self,
            "TaskRole",
            role_name=f"pantry-pirate-radio-task-{self.environment_name}",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )

        # SQS permissions - will be granted by QueueStack
        # DynamoDB permissions - will be granted by StorageStack
        # S3 permissions - will be granted by StorageStack

        # Bedrock permissions for LLM invocation - scoped to specific model families
        role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                ],
                resources=[
                    f"arn:aws:bedrock:{self.region}::foundation-model/anthropic.claude-*",
                    f"arn:aws:bedrock:{self.region}::foundation-model/amazon.titan-*",
                    f"arn:aws:bedrock:{self.region}:{self.account}:inference-profile/us.anthropic.*",
                ],
            )
        )

        return role

    def _create_task_definition(self) -> ecs.FargateTaskDefinition:
        """Create ECS Fargate task definition for worker."""
        task_definition = ecs.FargateTaskDefinition(
            self,
            "WorkerTaskDef",
            family=f"pantry-pirate-radio-worker-{self.environment_name}",
            cpu=self.worker_cpu,
            memory_limit_mib=self.worker_memory_mib,
            execution_role=self.task_execution_role,
            task_role=self.task_role,
        )

        # Grant ECR pull permissions to execution role
        # GetAuthorizationToken requires resources=["*"]
        self.task_execution_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["ecr:GetAuthorizationToken"],
                resources=["*"],
            )
        )
        # Other ECR actions scoped to the specific repository
        self.task_execution_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:BatchGetImage",
                ],
                resources=[
                    f"arn:aws:ecr:{self.region}:{self.account}:repository/{self.ecr_repository_name}"
                ],
            )
        )

        # Add container
        if self.ecr_repository:
            worker_image = ecs.ContainerImage.from_ecr_repository(
                self.ecr_repository, tag=self.image_tag
            )
        else:
            worker_image = ecs.ContainerImage.from_registry(
                f"{self.account}.dkr.ecr.{self.region}.amazonaws.com/"
                f"{self.ecr_repository_name}:{self.image_tag}"
            )
        container = task_definition.add_container(
            "WorkerContainer",
            container_name="worker",
            image=worker_image,
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="worker",
                log_group=self.log_group,
            ),
            command=["python", "-m", "app.llm.queue.fargate_worker"],
            environment={
                k: v
                for k, v in {
                    "ENVIRONMENT": self.environment_name,
                    "QUEUE_BACKEND": "sqs",
                    "LLM_PROVIDER": "bedrock",
                    "LLM_MODEL_NAME": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
                    "SQS_QUEUE_URL": self.llm_queue_url,
                    "LLM_DLQ_URL": self.llm_dlq_url,
                    "SQS_JOBS_TABLE": self.sqs_jobs_table_name,
                    "VALIDATOR_QUEUE_URL": self.validator_queue_url,
                    "CONTENT_STORE_BACKEND": "s3",
                    "CONTENT_STORE_ENABLED": "true",
                    "CONTENT_STORE_PATH": "/tmp/content_store",
                    "CONTENT_STORE_S3_BUCKET": self.content_bucket_name,
                    "CONTENT_STORE_DYNAMODB_TABLE": self.content_index_table_name,
                }.items()
                if v is not None
            },
            # Health check: use /proc/1/cmdline instead of pgrep
            # (procps is not installed in python:3.11-slim-bullseye)
            health_check=ecs.HealthCheck(
                command=[
                    "CMD-SHELL",
                    "cat /proc/1/cmdline | tr '\\0' ' ' | grep -q worker || exit 1",
                ],
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                retries=3,
                start_period=Duration.seconds(60),
            ),
        )

        return task_definition

    def _create_worker_service(self) -> ecs.FargateService:
        """Create ECS Fargate service for workers."""
        service = ecs.FargateService(
            self,
            "WorkerService",
            service_name=f"pantry-pirate-radio-worker-{self.environment_name}",
            cluster=self.cluster,
            task_definition=self.task_definition,
            desired_count=self.desired_count,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            assign_public_ip=False,
            enable_execute_command=True,  # Allow debugging via ECS Exec
            circuit_breaker=ecs.DeploymentCircuitBreaker(
                rollback=True,
            ),
            min_healthy_percent=100,  # Keep all tasks healthy during deployment
            max_healthy_percent=200,  # Allow rolling deployment
        )

        return service

    def grant_queue_access(self, queue) -> None:
        """Grant worker service access to SQS queue.

        Args:
            queue: SQS queue to grant access to
        """
        queue.grant_consume_messages(self.task_role)
        queue.grant_send_messages(self.task_role)

    def grant_storage_access(self, bucket, jobs_table, content_index_table) -> None:
        """Grant worker service access to storage resources.

        Args:
            bucket: S3 bucket for content store
            jobs_table: DynamoDB table for job status
            content_index_table: DynamoDB table for content index
        """
        bucket.grant_read_write(self.task_role)
        jobs_table.grant_read_write_data(self.task_role)
        content_index_table.grant_read_write_data(self.task_role)

    def configure_auto_scaling(self, llm_queue: sqs.IQueue) -> None:
        """Configure SQS queue-depth-driven auto-scaling for the worker service.

        Uses visible + not_visible message count to avoid premature scale-down
        while messages are in-flight.

        Args:
            llm_queue: SQS queue to monitor for scaling decisions
        """
        scaling = self.worker_service.auto_scale_task_count(
            min_capacity=0,
            max_capacity=self.max_capacity,
        )

        total_messages = cloudwatch.MathExpression(
            expression="visible + not_visible",
            using_metrics={
                "visible": llm_queue.metric_approximate_number_of_messages_visible(
                    period=Duration.seconds(60),
                    statistic="Average",
                ),
                "not_visible": llm_queue.metric_approximate_number_of_messages_not_visible(
                    period=Duration.seconds(60),
                    statistic="Average",
                ),
            },
            period=Duration.seconds(60),
        )

        scaling.scale_on_metric(
            "WorkerQueueDepthScaling",
            metric=total_messages,
            scaling_steps=[
                appscaling.ScalingInterval(upper=0, change=-1),
                appscaling.ScalingInterval(lower=0, upper=5, change=1),
                appscaling.ScalingInterval(lower=5, upper=20, change=2),
                appscaling.ScalingInterval(lower=20, upper=50, change=5),
                appscaling.ScalingInterval(lower=50, change=10),
            ],
            adjustment_type=appscaling.AdjustmentType.CHANGE_IN_CAPACITY,
            cooldown=Duration.seconds(120),
            metric_aggregation_type=appscaling.MetricAggregationType.AVERAGE,
            evaluation_periods=1,
            datapoints_to_alarm=1,
        )

        # Prevent INSUFFICIENT_DATA during idle periods (no metric data).
        # Without this, alarms may not evaluate properly when scaling from zero.
        # Walk the construct tree to find the CloudWatch alarms created by
        # scale_on_metric (it returns None, so we access them via the tree).
        for child in scaling.node.find_all():
            if isinstance(child, cloudwatch.CfnAlarm):
                child.treat_missing_data = "notBreaching"
