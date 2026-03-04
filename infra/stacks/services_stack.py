"""Services Stack for Pantry Pirate Radio.

Creates Fargate services for the data processing pipeline:
- Validator: Data enrichment and confidence scoring
- Reconciler: Canonical record creation (single instance)
- Publisher: HAARRRvest repository publishing
- Recorder: Job result archiving
- Scraper (task definition only): One-shot scraper tasks
"""

from dataclasses import dataclass, field

from aws_cdk import Duration, RemovalPolicy, Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_cdk import aws_secretsmanager as secretsmanager
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

    # Data repository URL
    data_repo_url: str = "https://github.com/For-The-Greater-Good/HAARRRvest.git"


class ServicesStack(Stack):
    """Pipeline services infrastructure for Pantry Pirate Radio.

    Creates Fargate services for:
    - Validator: Data enrichment and confidence scoring (1-5 instances)
    - Reconciler: Canonical record creation (single instance only)
    - Publisher: HAARRRvest repository publishing (1 instance)
    - Recorder: Job result archiving (1-2 instances)

    Also creates task definition for:
    - Scraper: One-shot Fargate tasks (triggered by Step Functions)

    Attributes:
        validator_service: Validator Fargate service
        reconciler_service: Reconciler Fargate service
        publisher_service: Publisher Fargate service
        recorder_service: Recorder Fargate service
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
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        self.environment_name = environment_name
        self.config = config or ServiceConfig()

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
            )
        )

        self.publisher_service, self.publisher_security_group, self.publisher_task_role = (
            self._create_service(
                name="publisher",
                cpu=256,
                memory_mib=512,
                desired_count=1,
                log_retention=log_retention,
                cluster=cluster,
                vpc=vpc,
                environment=self._get_publisher_environment(),
                secrets=self._get_publisher_secrets(),
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
            )
        )

        # Create scraper task definition (one-shot, triggered by Step Functions)
        self.scraper_task_definition, self.scraper_security_group, self.scraper_task_role = (
            self._create_scraper_task_definition(log_retention=log_retention, vpc=vpc)
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

        # Add container
        task_definition.add_container(
            f"{name.title()}Container",
            image=ecs.ContainerImage.from_registry(
                f"pantry-pirate-radio-{name}:latest"
            ),
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix=name,
                log_group=log_group,
            ),
            environment=env_vars,
            secrets=secrets or {},
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

        # Add container
        # SCRAPER_NAME will be overridden at runtime by Step Functions
        task_definition.add_container(
            "ScraperContainer",
            image=ecs.ContainerImage.from_registry(
                "pantry-pirate-radio-scraper:latest"
            ),
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
        """Get environment variables for the Publisher service."""
        env = {}
        if self.config.database_host:
            env["DATABASE_HOST"] = self.config.database_host
        if self.config.database_name:
            env["DATABASE_NAME"] = self.config.database_name
        if self.config.database_user:
            env["DATABASE_USER"] = self.config.database_user
        if self.config.data_repo_url:
            env["DATA_REPO_URL"] = self.config.data_repo_url
        return env

    def _get_publisher_secrets(self) -> dict[str, ecs.Secret]:
        """Get secrets for the Publisher service."""
        secrets = {}
        if self.config.database_secret:
            secrets["DATABASE_PASSWORD"] = ecs.Secret.from_secrets_manager(
                self.config.database_secret, "password"
            )
        if self.config.github_pat_secret:
            secrets["GITHUB_PAT"] = ecs.Secret.from_secrets_manager(
                self.config.github_pat_secret
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
            "SERVICE_NAME": "scraper",
            "SCRAPER_NAME": "placeholder",  # Overridden at runtime by Step Functions
            "QUEUE_BACKEND": "sqs",
            "CONTENT_STORE_BACKEND": "s3",
        }
        if self.config.database_host:
            env["DATABASE_HOST"] = self.config.database_host
        if self.config.database_name:
            env["DATABASE_NAME"] = self.config.database_name
        if self.config.database_user:
            env["DATABASE_USER"] = self.config.database_user
        if self.config.queue_urls.get("llm"):
            env["LLM_QUEUE_URL"] = self.config.queue_urls["llm"]
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
