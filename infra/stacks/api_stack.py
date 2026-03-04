"""API Stack for Pantry Pirate Radio.

Creates Application Load Balancer and ECS Fargate service
for the FastAPI application.
"""

from aws_cdk import Duration, Stack
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_ecs_patterns as ecs_patterns
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from constructs import Construct


class APIStack(Stack):
    """API infrastructure for Pantry Pirate Radio.

    Creates:
    - Application Load Balancer with HTTPS
    - ECS Fargate service for FastAPI
    - Auto-scaling based on CPU/request count

    Attributes:
        alb: Application Load Balancer
        api_service: ECS Fargate service for API
        api_url: URL of the API endpoint
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.IVpc,
        cluster: ecs.ICluster,
        environment_name: str = "dev",
        api_cpu: int = 512,
        api_memory_mib: int = 1024,
        desired_count: int = 2,
        min_capacity: int = 1,
        max_capacity: int = 10,
        certificate_arn: str | None = None,
        domain_name: str | None = None,
        ecr_repository_name: str | None = None,
        image_tag: str = "latest",
        **kwargs,
    ) -> None:
        """Initialize APIStack.

        Args:
            scope: CDK scope
            construct_id: Unique identifier for this construct
            vpc: VPC to deploy into
            cluster: ECS cluster to use
            environment_name: Environment name (dev, staging, prod)
            api_cpu: CPU units for API task (512 = 0.5 vCPU)
            api_memory_mib: Memory in MiB for API task
            desired_count: Desired number of API tasks
            min_capacity: Minimum tasks for auto-scaling
            max_capacity: Maximum tasks for auto-scaling
            certificate_arn: ACM certificate ARN for HTTPS
            domain_name: Custom domain name for API
            ecr_repository_name: Name of ECR repository for API image
            image_tag: Docker image tag to deploy
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        self.environment_name = environment_name
        self.vpc = vpc
        self.cluster = cluster
        self.api_cpu = api_cpu
        self.api_memory_mib = api_memory_mib
        self.desired_count = desired_count
        self.min_capacity = min_capacity
        self.max_capacity = max_capacity
        self.certificate_arn = certificate_arn
        self.domain_name = domain_name
        self.ecr_repository_name = (
            ecr_repository_name or f"pantry-pirate-radio-api-{environment_name}"
        )
        self.image_tag = image_tag

        # Create log group
        self.log_group = self._create_log_group()

        # Create task role for API
        self.task_role = self._create_task_role()

        # Create ALB Fargate service
        self.api_service = self._create_api_service()

        # Configure auto-scaling
        self._configure_auto_scaling()

        # Store the API URL
        self.api_url = self._get_api_url()

    def _create_log_group(self) -> logs.LogGroup:
        """Create CloudWatch log group for API logs."""
        return logs.LogGroup(
            self,
            "APILogs",
            log_group_name=f"/ecs/pantry-pirate-radio-api-{self.environment_name}",
            retention=logs.RetentionDays.ONE_MONTH,
        )

    def _create_task_role(self) -> iam.Role:
        """Create IAM role for API tasks.

        The API needs read access to:
        - DynamoDB for job status queries
        - S3 for content retrieval (if needed)
        """
        role = iam.Role(
            self,
            "APITaskRole",
            role_name=f"pantry-pirate-radio-api-task-{self.environment_name}",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )

        return role

    def _create_api_service(self) -> ecs_patterns.ApplicationLoadBalancedFargateService:
        """Create ALB + Fargate service for API."""
        # Determine if we should use HTTPS
        certificate = None
        redirect_http = False
        protocol = elbv2.ApplicationProtocol.HTTP

        if self.certificate_arn:
            certificate = acm.Certificate.from_certificate_arn(
                self, "Certificate", self.certificate_arn
            )
            redirect_http = True
            protocol = elbv2.ApplicationProtocol.HTTPS

        service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "APIService",
            service_name=f"pantry-pirate-radio-api-{self.environment_name}",
            cluster=self.cluster,
            cpu=self.api_cpu,
            memory_limit_mib=self.api_memory_mib,
            desired_count=self.desired_count,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_registry(
                    f"{self.account}.dkr.ecr.{self.region}.amazonaws.com/"
                    f"{self.ecr_repository_name}:{self.image_tag}"
                ),
                container_port=8000,
                task_role=self.task_role,
                log_driver=ecs.LogDrivers.aws_logs(
                    stream_prefix="api",
                    log_group=self.log_group,
                ),
                environment={
                    "ENVIRONMENT": self.environment_name,
                    "PORT": "8000",
                },
            ),
            public_load_balancer=True,
            certificate=certificate,
            redirect_http=redirect_http,
            protocol=protocol,
            health_check_grace_period=Duration.seconds(60),
            enable_execute_command=True,
            circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True),
            min_healthy_percent=100,
            max_healthy_percent=200,
        )

        # Configure health check
        service.target_group.configure_health_check(
            path="/health",
            healthy_threshold_count=2,
            unhealthy_threshold_count=3,
            timeout=Duration.seconds(5),
            interval=Duration.seconds(30),
        )

        # Add ECR pull permissions to execution role
        service.task_definition.execution_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ecr:GetAuthorizationToken",
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:BatchGetImage",
                ],
                resources=["*"],
            )
        )

        return service

    def _configure_auto_scaling(self) -> None:
        """Configure auto-scaling for the API service."""
        scaling = self.api_service.service.auto_scale_task_count(
            min_capacity=self.min_capacity,
            max_capacity=self.max_capacity,
        )

        # Scale based on CPU utilization
        scaling.scale_on_cpu_utilization(
            "CPUScaling",
            target_utilization_percent=70,
            scale_in_cooldown=Duration.seconds(60),
            scale_out_cooldown=Duration.seconds(60),
        )

        # Scale based on request count
        scaling.scale_on_request_count(
            "RequestScaling",
            requests_per_target=1000,
            target_group=self.api_service.target_group,
            scale_in_cooldown=Duration.seconds(60),
            scale_out_cooldown=Duration.seconds(60),
        )

    def _get_api_url(self) -> str:
        """Get the API URL."""
        if self.domain_name:
            protocol = "https" if self.certificate_arn else "http"
            return f"{protocol}://{self.domain_name}"
        return f"http://{self.api_service.load_balancer.load_balancer_dns_name}"

    def grant_database_read(self, jobs_table, content_index_table) -> None:
        """Grant API read access to database tables.

        Args:
            jobs_table: DynamoDB table for job status
            content_index_table: DynamoDB table for content index
        """
        jobs_table.grant_read_data(self.task_role)
        content_index_table.grant_read_data(self.task_role)

    def grant_queue_write(self, queue) -> None:
        """Grant API write access to job queue.

        Args:
            queue: SQS queue for submitting jobs
        """
        queue.grant_send_messages(self.task_role)
