"""Factory for creating Fargate services and task definitions.

Extracted from ServicesStack to keep file sizes under 600 lines.
"""

from aws_cdk import RemovalPolicy, Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from constructs import Construct


def create_fargate_service(
    scope: Construct,
    name: str,
    cpu: int,
    memory_mib: int,
    desired_count: int,
    log_retention: logs.RetentionDays,
    cluster: ecs.ICluster,
    vpc: ec2.IVpc,
    environment_name: str,
    ecr_repositories: dict[str, ecr.IRepository],
    environment: dict[str, str] | None = None,
    secrets: dict[str, ecs.Secret] | None = None,
    command: list[str] | None = None,
    max_healthy_percent: int | None = None,
    min_healthy_percent: int | None = None,
) -> tuple[ecs.FargateService, ec2.ISecurityGroup, iam.IRole]:
    """Create a Fargate service with log group, task definition, and security group.

    Args:
        scope: CDK construct scope
        name: Service name
        cpu: CPU units (256, 512, 1024, etc.)
        memory_mib: Memory in MiB
        desired_count: Desired number of tasks
        log_retention: CloudWatch log retention period
        cluster: ECS cluster
        vpc: VPC for service
        environment_name: Environment name (dev, staging, prod)
        ecr_repositories: ECR repositories by service name
        environment: Environment variables for the container
        secrets: Secrets for the container
        command: Container command override (bypasses entrypoint)
        max_healthy_percent: Maximum healthy percentage during deployment
        min_healthy_percent: Minimum healthy percentage during deployment

    Returns:
        Tuple of (Fargate service, security group, task role)
    """
    # Create log group
    log_group = logs.LogGroup(
        scope,
        f"{name.title()}LogGroup",
        log_group_name=f"/ecs/pantry-pirate-radio/{name}-{environment_name}",
        retention=log_retention,
        removal_policy=(
            RemovalPolicy.RETAIN
            if environment_name == "prod"
            else RemovalPolicy.DESTROY
        ),
    )

    # Create task definition
    task_definition = ecs.FargateTaskDefinition(
        scope,
        f"{name.title()}TaskDef",
        cpu=cpu,
        memory_limit_mib=memory_mib,
        family=f"pantry-pirate-radio-{name}-{environment_name}",
    )

    # Build environment variables
    env_vars = {
        "ENVIRONMENT": environment_name,
        "SERVICE_NAME": name,
    }
    if environment:
        env_vars.update(environment)

    # Add container with ECR image
    if name in ecr_repositories:
        image = ecs.ContainerImage.from_ecr_repository(
            ecr_repositories[name], tag="latest"
        )
    else:
        ecr_image = (
            f"{Stack.of(scope).account}.dkr.ecr.{Stack.of(scope).region}.amazonaws.com/"
            f"pantry-pirate-radio-{name}-{environment_name}:latest"
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
        scope,
        f"{name.title()}SecurityGroup",
        vpc=vpc,
        description=f"Security group for {name} service - {environment_name}",
        allow_all_outbound=True,
    )

    # Build optional deployment config kwargs
    deployment_kwargs: dict = {}
    if max_healthy_percent is not None:
        deployment_kwargs["max_healthy_percent"] = max_healthy_percent
    if min_healthy_percent is not None:
        deployment_kwargs["min_healthy_percent"] = min_healthy_percent

    # Create Fargate service
    service = ecs.FargateService(
        scope,
        f"{name.title()}Service",
        cluster=cluster,
        task_definition=task_definition,
        desired_count=desired_count,
        vpc_subnets=ec2.SubnetSelection(
            subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
        ),
        assign_public_ip=False,
        service_name=f"pantry-pirate-radio-{name}-{environment_name}",
        enable_execute_command=True,  # Enable ECS Exec for debugging
        security_groups=[security_group],
        circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True),
        **deployment_kwargs,
    )

    return service, security_group, task_definition.task_role
