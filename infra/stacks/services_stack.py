"""Services Stack for Pantry Pirate Radio.

Creates Fargate services for the data processing pipeline:
- Validator: Data enrichment and confidence scoring
- Reconciler: Canonical record creation (single instance)
- Recorder: Job result archiving

And task definitions for one-shot tasks:
- Publisher: SQLite export to S3 (daily scheduled)
- Scraper: Web scraping tasks (triggered by Step Functions)
"""

from dataclasses import dataclass, field

from aws_cdk import Duration, RemovalPolicy, Stack
from aws_cdk import aws_applicationautoscaling as appscaling
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_cdk import aws_secretsmanager as secretsmanager
from aws_cdk import aws_sqs as sqs
from constructs import Construct


@dataclass
class ServiceConfig:
    """Configuration for service environment variables and secrets."""

    # Database configuration
    database_host: str = ""
    database_name: str = "pantry_pirate_radio"
    database_user: str = "pantry_pirate"
    database_secret: secretsmanager.ISecret | None = None

    # Queue URLs
    queue_urls: dict[str, str] = field(default_factory=dict)

    # Storage configuration
    content_bucket_name: str = ""
    content_index_table_name: str = ""
    geocoding_cache_table_name: str = ""

    # Secrets
    github_pat_secret: secretsmanager.ISecret | None = None
    llm_api_keys_secret: secretsmanager.ISecret | None = None

    # Job status tracking
    jobs_table_name: str = ""

    # Data repository URL
    data_repo_url: str = "https://github.com/For-The-Greater-Good/HAARRRvest.git"

    # Exports bucket for publisher
    exports_bucket_name: str = ""


class ServicesStack(Stack):
    """Pipeline services infrastructure for Pantry Pirate Radio.

    Creates Fargate services for:
    - Validator: Data enrichment and confidence scoring (1-5 instances)
    - Reconciler: Canonical record creation (single instance only)
    - Recorder: Job result archiving (1-2 instances)

    Also creates task definitions for:
    - Publisher: SQLite export to S3 (daily EventBridge schedule)
    - Scraper: One-shot Fargate tasks (triggered by Step Functions)

    Attributes:
        validator_service: Validator Fargate service
        reconciler_service: Reconciler Fargate service
        recorder_service: Recorder Fargate service
        publisher_task_definition: Publisher task definition for scheduled export
        scraper_task_definition: Scraper task definition for one-shot tasks
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        environment_name: str = "dev",
        vpc: ec2.IVpc,
        cluster: ecs.ICluster,
        config: ServiceConfig | None = None,
        ecr_repositories: dict[str, ecr.IRepository] | None = None,
        **kwargs,
    ) -> None:
        """Initialize ServicesStack.

        Args:
            scope: CDK scope
            construct_id: Unique identifier for this construct
            environment_name: Environment name (dev, staging, prod)
            vpc: VPC for service placement
            cluster: ECS cluster for services
            config: Optional service configuration for environment variables and secrets
            ecr_repositories: ECR repositories by service name for container images
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        self.environment_name = environment_name
        self.config = config or ServiceConfig()
        self.ecr_repositories = ecr_repositories or {}

        # Environment-specific configuration
        is_prod = environment_name == "prod"
        log_retention = logs.RetentionDays.ONE_MONTH if is_prod else logs.RetentionDays.ONE_WEEK

        # Create services and expose security groups and task roles
        self.validator_service, self.validator_security_group, self.validator_task_role = (
            self._create_service(
                name="validator",
                cpu=512,
                memory_mib=1024,
                desired_count=1,
                log_retention=log_retention,
                cluster=cluster,
                vpc=vpc,
                environment=self._get_validator_environment(),
                secrets=self._get_validator_secrets(),
                command=["python", "-m", "app.validator.fargate_worker"],
            )
        )

        self.reconciler_service, self.reconciler_security_group, self.reconciler_task_role = (
            self._create_service(
                name="reconciler",
                cpu=512,
                memory_mib=1024,
                desired_count=1,  # Single instance only - critical for data consistency
                log_retention=log_retention,
                cluster=cluster,
                vpc=vpc,
                environment=self._get_reconciler_environment(),
                secrets=self._get_reconciler_secrets(),
                command=["python", "-m", "app.reconciler.fargate_worker"],
            )
        )

        # Publisher is a one-shot task (triggered by EventBridge schedule)
        # Exports Aurora data to SQLite and uploads to S3
        self.publisher_task_definition, self.publisher_security_group, self.publisher_task_role = (
            self._create_publisher_task_definition(
                log_retention=log_retention, vpc=vpc
            )
        )

        self.recorder_service, self.recorder_security_group, self.recorder_task_role = (
            self._create_service(
                name="recorder",
                cpu=256,
                memory_mib=512,
                desired_count=1,
                log_retention=log_retention,
                cluster=cluster,
                vpc=vpc,
                environment=self._get_recorder_environment(),
                secrets=self._get_recorder_secrets(),
                command=["python", "-m", "app.recorder.fargate_worker"],
            )
        )

        # Create scraper task definition (one-shot, triggered by Step Functions)
        self.scraper_task_definition, self.scraper_security_group, self.scraper_task_role = (
            self._create_scraper_task_definition(log_retention=log_retention, vpc=vpc)
        )

    def grant_database_access(self, proxy_security_group: ec2.ISecurityGroup) -> None:
        """Allow all pipeline services to connect to the RDS Proxy.

        Creates ingress rules on the proxy security group allowing connections
        from each service's security group. Rules are created as L1 constructs
        within this stack to avoid circular cross-stack references (since
        ServicesStack depends on DatabaseStack, the proxy SG's L2 add_ingress_rule
        would create a reverse reference back to ServicesStack).

        Args:
            proxy_security_group: RDS Proxy security group to allow connections to
        """
        service_sgs = {
            "Validator": self.validator_security_group,
            "Reconciler": self.reconciler_security_group,
            "Publisher": self.publisher_security_group,
            "Recorder": self.recorder_security_group,
            "Scraper": self.scraper_security_group,
        }
        for name, sg in service_sgs.items():
            ec2.CfnSecurityGroupIngress(
                self,
                f"{name}ToProxyIngress",
                group_id=proxy_security_group.security_group_id,
                source_security_group_id=sg.security_group_id,
                ip_protocol="tcp",
                from_port=5432,
                to_port=5432,
                description=f"Allow {name.lower()} to connect to RDS Proxy",
            )

    def configure_auto_scaling(
        self,
        validator_queue: sqs.IQueue | None = None,
        reconciler_queue: sqs.IQueue | None = None,
        recorder_queue: sqs.IQueue | None = None,
    ) -> None:
        """Configure SQS queue-depth-driven auto-scaling for pipeline services.

        Each service scales based on its input queue depth (visible + not_visible).
        Pass only the queues for services you want to auto-scale.

        Args:
            validator_queue: SQS queue for validator scaling (0-2 instances)
            reconciler_queue: SQS queue for reconciler scaling (0-1 instance)
            recorder_queue: SQS queue for recorder scaling (0-2 instances)
        """
        if validator_queue:
            self._configure_service_scaling(
                service=self.validator_service,
                queue=validator_queue,
                name="Validator",
                min_capacity=0,
                max_capacity=2,
                scaling_steps=[
                    appscaling.ScalingInterval(upper=0, change=-1),
                    appscaling.ScalingInterval(lower=0, upper=10, change=1),
                    appscaling.ScalingInterval(lower=10, change=2),
                ],
            )

        if reconciler_queue:
            self._configure_service_scaling(
                service=self.reconciler_service,
                queue=reconciler_queue,
                name="Reconciler",
                min_capacity=0,
                max_capacity=1,
                scaling_steps=[
                    appscaling.ScalingInterval(upper=0, change=-1),
                    appscaling.ScalingInterval(lower=0, change=1),
                ],
            )

        if recorder_queue:
            self._configure_service_scaling(
                service=self.recorder_service,
                queue=recorder_queue,
                name="Recorder",
                min_capacity=0,
                max_capacity=2,
                scaling_steps=[
                    appscaling.ScalingInterval(upper=0, change=-1),
                    appscaling.ScalingInterval(lower=0, upper=20, change=1),
                    appscaling.ScalingInterval(lower=20, change=2),
                ],
            )

    def _configure_service_scaling(
        self,
        service: ecs.FargateService,
        queue: sqs.IQueue,
        name: str,
        min_capacity: int,
        max_capacity: int,
        scaling_steps: list[appscaling.ScalingInterval],
    ) -> None:
        """Configure step scaling for a single service based on SQS queue depth.

        Args:
            service: ECS Fargate service to scale
            queue: SQS queue to monitor
            name: Service name for resource IDs
            min_capacity: Minimum task count
            max_capacity: Maximum task count
            scaling_steps: Step scaling intervals
        """
        scaling = service.auto_scale_task_count(
            min_capacity=min_capacity,
            max_capacity=max_capacity,
        )

        total_messages = cloudwatch.MathExpression(
            expression="visible + not_visible",
            using_metrics={
                "visible": queue.metric_approximate_number_of_messages_visible(
                    period=Duration.seconds(60),
                    statistic="Average",
                ),
                "not_visible": queue.metric_approximate_number_of_messages_not_visible(
                    period=Duration.seconds(60),
                    statistic="Average",
                ),
            },
            period=Duration.seconds(60),
        )

        scaling.scale_on_metric(
            f"{name}QueueDepthScaling",
            metric=total_messages,
            scaling_steps=scaling_steps,
            adjustment_type=appscaling.AdjustmentType.CHANGE_IN_CAPACITY,
            cooldown=Duration.seconds(120),
        )

    def _create_service(
        self,
        name: str,
        cpu: int,
        memory_mib: int,
        desired_count: int,
        log_retention: logs.RetentionDays,
        cluster: ecs.ICluster,
        vpc: ec2.IVpc,
        environment: dict[str, str] | None = None,
        secrets: dict[str, ecs.Secret] | None = None,
        command: list[str] | None = None,
    ) -> tuple[ecs.FargateService, ec2.ISecurityGroup, iam.IRole]:
        """Create a Fargate service.

        Args:
            name: Service name
            cpu: CPU units (256, 512, 1024, etc.)
            memory_mib: Memory in MiB
            desired_count: Desired number of tasks
            log_retention: CloudWatch log retention period
            cluster: ECS cluster
            vpc: VPC for service
            environment: Environment variables for the container
            secrets: Secrets for the container
            command: Container command override (bypasses entrypoint)

        Returns:
            Tuple of (Fargate service, security group, task role)
        """
        # Create log group
        log_group = logs.LogGroup(
            self,
            f"{name.title()}LogGroup",
            log_group_name=f"/ecs/pantry-pirate-radio/{name}-{self.environment_name}",
            retention=log_retention,
            removal_policy=(
                RemovalPolicy.RETAIN
                if self.environment_name == "prod"
                else RemovalPolicy.DESTROY
            ),
        )

        # Create task definition
        task_definition = ecs.FargateTaskDefinition(
            self,
            f"{name.title()}TaskDef",
            cpu=cpu,
            memory_limit_mib=memory_mib,
            family=f"pantry-pirate-radio-{name}-{self.environment_name}",
        )

        # Build environment variables
        env_vars = {
            "ENVIRONMENT": self.environment_name,
            "SERVICE_NAME": name,
        }
        if environment:
            env_vars.update(environment)

        # Add container with ECR image
        if name in self.ecr_repositories:
            image = ecs.ContainerImage.from_ecr_repository(
                self.ecr_repositories[name], tag="latest"
            )
        else:
            ecr_image = (
                f"{Stack.of(self).account}.dkr.ecr.{Stack.of(self).region}.amazonaws.com/"
                f"pantry-pirate-radio-{name}-{self.environment_name}:latest"
            )
            image = ecs.ContainerImage.from_registry(ecr_image)
        container_props: dict = {
            "image": image,
            "logging": ecs.LogDrivers.aws_logs(
                stream_prefix=name,
                log_group=log_group,
            ),
            "environment": env_vars,
            "secrets": secrets or {},
        }
        if command:
            container_props["command"] = command
        task_definition.add_container(
            f"{name.title()}Container",
            **container_props,
        )

        # Create security group for service
        security_group = ec2.SecurityGroup(
            self,
            f"{name.title()}SecurityGroup",
            vpc=vpc,
            description=f"Security group for {name} service - {self.environment_name}",
            allow_all_outbound=True,
        )

        # Create Fargate service
        service = ecs.FargateService(
            self,
            f"{name.title()}Service",
            cluster=cluster,
            task_definition=task_definition,
            desired_count=desired_count,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            assign_public_ip=False,
            service_name=f"pantry-pirate-radio-{name}-{self.environment_name}",
            enable_execute_command=True,  # Enable ECS Exec for debugging
            security_groups=[security_group],
        )

        return service, security_group, task_definition.task_role

    def _create_publisher_task_definition(
        self,
        log_retention: logs.RetentionDays,
        vpc: ec2.IVpc,
    ) -> tuple[ecs.FargateTaskDefinition, ec2.ISecurityGroup, iam.IRole]:
        """Create task definition for publisher one-shot export tasks.

        The publisher exports Aurora data to SQLite and uploads to S3.
        Triggered daily by EventBridge schedule.

        Args:
            log_retention: CloudWatch log retention period
            vpc: VPC for security group

        Returns:
            Tuple of (Fargate task definition, security group, task role)
        """
        log_group = logs.LogGroup(
            self,
            "PublisherLogGroup",
            log_group_name=f"/ecs/pantry-pirate-radio/publisher-{self.environment_name}",
            retention=log_retention,
            removal_policy=(
                RemovalPolicy.RETAIN
                if self.environment_name == "prod"
                else RemovalPolicy.DESTROY
            ),
        )

        task_definition = ecs.FargateTaskDefinition(
            self,
            "PublisherTaskDef",
            cpu=512,
            memory_limit_mib=1024,
            family=f"pantry-pirate-radio-publisher-{self.environment_name}",
        )

        publisher_env = self._get_publisher_environment()
        publisher_secrets = self._get_publisher_secrets()

        # Build command for the exporter
        command = [
            "python",
            "-m",
            "app.datasette.exporter",
            "--output",
            "/tmp/pantry_pirate_radio.sqlite",
            "--database-url-from-env",
        ]
        if self.config.exports_bucket_name:
            command.extend(["--s3-bucket", self.config.exports_bucket_name])

        if "publisher" in self.ecr_repositories:
            image = ecs.ContainerImage.from_ecr_repository(
                self.ecr_repositories["publisher"], tag="latest"
            )
        else:
            ecr_image = (
                f"{Stack.of(self).account}.dkr.ecr.{Stack.of(self).region}.amazonaws.com/"
                f"pantry-pirate-radio-publisher-{self.environment_name}:latest"
            )
            image = ecs.ContainerImage.from_registry(ecr_image)

        task_definition.add_container(
            "PublisherContainer",
            image=image,
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="publisher",
                log_group=log_group,
            ),
            environment=publisher_env,
            secrets=publisher_secrets,
            command=command,
        )

        security_group = ec2.SecurityGroup(
            self,
            "PublisherSecurityGroup",
            vpc=vpc,
            description=f"Security group for publisher tasks - {self.environment_name}",
            allow_all_outbound=True,
        )

        return task_definition, security_group, task_definition.task_role

    def _create_scraper_task_definition(
        self,
        log_retention: logs.RetentionDays,
        vpc: ec2.IVpc,
    ) -> tuple[ecs.FargateTaskDefinition, ec2.ISecurityGroup, iam.IRole]:
        """Create task definition for scraper one-shot tasks.

        Scrapers are triggered by Step Functions as ECS:RunTask.
        Each scraper run is independent and short-lived.

        Args:
            log_retention: CloudWatch log retention period
            vpc: VPC for security group

        Returns:
            Tuple of (Fargate task definition, security group, task role)
        """
        # Create log group
        log_group = logs.LogGroup(
            self,
            "ScraperLogGroup",
            log_group_name=f"/ecs/pantry-pirate-radio/scraper-{self.environment_name}",
            retention=log_retention,
            removal_policy=(
                RemovalPolicy.RETAIN
                if self.environment_name == "prod"
                else RemovalPolicy.DESTROY
            ),
        )

        # Create task definition
        task_definition = ecs.FargateTaskDefinition(
            self,
            "ScraperTaskDef",
            cpu=512,
            memory_limit_mib=1024,
            family=f"pantry-pirate-radio-scraper-{self.environment_name}",
        )

        # Build environment variables for scraper
        scraper_env = self._get_scraper_environment()
        scraper_secrets = self._get_scraper_secrets()

        # Add container with ECR image
        # SCRAPER_NAME will be overridden at runtime by Step Functions
        if "scraper" in self.ecr_repositories:
            scraper_image = ecs.ContainerImage.from_ecr_repository(
                self.ecr_repositories["scraper"], tag="latest"
            )
        else:
            ecr_image = (
                f"{Stack.of(self).account}.dkr.ecr.{Stack.of(self).region}.amazonaws.com/"
                f"pantry-pirate-radio-scraper-{self.environment_name}:latest"
            )
            scraper_image = ecs.ContainerImage.from_registry(ecr_image)
        task_definition.add_container(
            "ScraperContainer",
            image=scraper_image,
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="scraper",
                log_group=log_group,
            ),
            environment=scraper_env,
            secrets=scraper_secrets,
        )

        # Create security group for scraper tasks
        security_group = ec2.SecurityGroup(
            self,
            "ScraperSecurityGroup",
            vpc=vpc,
            description=f"Security group for scraper tasks - {self.environment_name}",
            allow_all_outbound=True,
        )

        return task_definition, security_group, task_definition.task_role

    def _get_validator_environment(self) -> dict[str, str]:
        """Get environment variables for the Validator service."""
        env = {
            "QUEUE_BACKEND": "sqs",
            "CONTENT_STORE_BACKEND": "s3",
        }
        if self.config.database_host:
            env["DATABASE_HOST"] = self.config.database_host
        if self.config.database_name:
            env["DATABASE_NAME"] = self.config.database_name
        if self.config.database_user:
            env["DATABASE_USER"] = self.config.database_user
        if self.config.queue_urls.get("validator"):
            env["VALIDATOR_QUEUE_URL"] = self.config.queue_urls["validator"]
        if self.config.queue_urls.get("reconciler"):
            env["RECONCILER_QUEUE_URL"] = self.config.queue_urls["reconciler"]
        if self.config.content_bucket_name:
            env["CONTENT_STORE_S3_BUCKET"] = self.config.content_bucket_name
        if self.config.content_index_table_name:
            env["CONTENT_STORE_DYNAMODB_TABLE"] = self.config.content_index_table_name
        if self.config.geocoding_cache_table_name:
            env["GEOCODING_CACHE_TABLE"] = self.config.geocoding_cache_table_name
        return env

    def _get_validator_secrets(self) -> dict[str, ecs.Secret]:
        """Get secrets for the Validator service."""
        secrets = {}
        if self.config.database_secret:
            secrets["DATABASE_PASSWORD"] = ecs.Secret.from_secrets_manager(
                self.config.database_secret, "password"
            )
        return secrets

    def _get_reconciler_environment(self) -> dict[str, str]:
        """Get environment variables for the Reconciler service."""
        env = {
            "QUEUE_BACKEND": "sqs",
        }
        if self.config.database_host:
            env["DATABASE_HOST"] = self.config.database_host
        if self.config.database_name:
            env["DATABASE_NAME"] = self.config.database_name
        if self.config.database_user:
            env["DATABASE_USER"] = self.config.database_user
        if self.config.queue_urls.get("reconciler"):
            env["RECONCILER_QUEUE_URL"] = self.config.queue_urls["reconciler"]
        if self.config.queue_urls.get("recorder"):
            env["RECORDER_QUEUE_URL"] = self.config.queue_urls["recorder"]
        return env

    def _get_reconciler_secrets(self) -> dict[str, ecs.Secret]:
        """Get secrets for the Reconciler service."""
        secrets = {}
        if self.config.database_secret:
            secrets["DATABASE_PASSWORD"] = ecs.Secret.from_secrets_manager(
                self.config.database_secret, "password"
            )
        return secrets

    def _get_publisher_environment(self) -> dict[str, str]:
        """Get environment variables for the Publisher task."""
        env = {
            "ENVIRONMENT": self.environment_name,
            "SERVICE_NAME": "publisher",
        }
        if self.config.database_host:
            env["DATABASE_HOST"] = self.config.database_host
        if self.config.database_name:
            env["DATABASE_NAME"] = self.config.database_name
        if self.config.database_user:
            env["DATABASE_USER"] = self.config.database_user
        if self.config.exports_bucket_name:
            env["EXPORT_S3_BUCKET"] = self.config.exports_bucket_name
        return env

    def _get_publisher_secrets(self) -> dict[str, ecs.Secret]:
        """Get secrets for the Publisher task."""
        secrets = {}
        if self.config.database_secret:
            secrets["DATABASE_PASSWORD"] = ecs.Secret.from_secrets_manager(
                self.config.database_secret, "password"
            )
        return secrets

    def _get_recorder_environment(self) -> dict[str, str]:
        """Get environment variables for the Recorder service."""
        env = {
            "QUEUE_BACKEND": "sqs",
            "CONTENT_STORE_BACKEND": "s3",
        }
        if self.config.queue_urls.get("recorder"):
            env["RECORDER_QUEUE_URL"] = self.config.queue_urls["recorder"]
        if self.config.content_bucket_name:
            env["CONTENT_STORE_S3_BUCKET"] = self.config.content_bucket_name
        if self.config.content_index_table_name:
            env["CONTENT_STORE_DYNAMODB_TABLE"] = self.config.content_index_table_name
        return env

    def _get_recorder_secrets(self) -> dict[str, ecs.Secret]:
        """Get secrets for the Recorder service."""
        # Recorder doesn't need any secrets
        return {}

    def _get_scraper_environment(self) -> dict[str, str]:
        """Get environment variables for the Scraper tasks."""
        env = {
            "ENVIRONMENT": self.environment_name,
            "SERVICE_TYPE": "scraper",
            "SERVICE_NAME": "scraper",
            "SCRAPER_NAME": "placeholder",  # Overridden at runtime by Step Functions
            "QUEUE_BACKEND": "sqs",
            "CONTENT_STORE_BACKEND": "s3",
            "CONTENT_STORE_ENABLED": "true",
            "CONTENT_STORE_PATH": "/tmp/content_store",
        }
        if self.config.database_host:
            env["DATABASE_HOST"] = self.config.database_host
        if self.config.database_name:
            env["DATABASE_NAME"] = self.config.database_name
        if self.config.database_user:
            env["DATABASE_USER"] = self.config.database_user
        if self.config.queue_urls.get("llm"):
            env["LLM_QUEUE_URL"] = self.config.queue_urls["llm"]
            env["SQS_QUEUE_URL"] = self.config.queue_urls["llm"]
        if self.config.jobs_table_name:
            env["SQS_JOBS_TABLE"] = self.config.jobs_table_name
        if self.config.content_bucket_name:
            env["CONTENT_STORE_S3_BUCKET"] = self.config.content_bucket_name
        if self.config.content_index_table_name:
            env["CONTENT_STORE_DYNAMODB_TABLE"] = self.config.content_index_table_name
        return env

    def _get_scraper_secrets(self) -> dict[str, ecs.Secret]:
        """Get secrets for the Scraper tasks."""
        secrets = {}
        if self.config.database_secret:
            secrets["DATABASE_PASSWORD"] = ecs.Secret.from_secrets_manager(
                self.config.database_secret, "password"
            )
        return secrets
