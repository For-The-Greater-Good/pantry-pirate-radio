"""Tests for APIStack CDK stack."""

import aws_cdk as cdk
import pytest
from aws_cdk import assertions
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecs as ecs

from stacks.api_stack import APIStack
from stacks.ecr_stack import ECRStack


class TestAPIStackResources:
    """Tests for APIStack resource creation."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def vpc_stack(self, app):
        """Create a VPC stack for testing."""
        stack = cdk.Stack(app, "VPCStack", env=cdk.Environment(
            account="123456789012", region="us-east-1"
        ))
        vpc = ec2.Vpc(stack, "VPC", max_azs=2)
        return stack, vpc

    @pytest.fixture
    def cluster(self, vpc_stack):
        """Create ECS cluster for testing."""
        stack, vpc = vpc_stack
        return ecs.Cluster(stack, "Cluster", vpc=vpc)

    @pytest.fixture
    def api_stack(self, app, vpc_stack, cluster):
        """Create API stack for testing."""
        stack, vpc = vpc_stack
        return APIStack(
            app,
            "TestAPIStack",
            vpc=vpc,
            cluster=cluster,
            environment_name="dev",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )

    @pytest.fixture
    def template(self, api_stack):
        """Get CloudFormation template from stack."""
        return assertions.Template.from_stack(api_stack)

    def test_creates_alb(self, template):
        """APIStack should create Application Load Balancer."""
        template.resource_count_is("AWS::ElasticLoadBalancingV2::LoadBalancer", 1)

    def test_creates_target_group(self, template):
        """APIStack should create target group."""
        template.resource_count_is("AWS::ElasticLoadBalancingV2::TargetGroup", 1)

    def test_creates_listener(self, template):
        """APIStack should create ALB listener."""
        template.resource_count_is("AWS::ElasticLoadBalancingV2::Listener", 1)

    def test_creates_fargate_service(self, template):
        """APIStack should create Fargate service."""
        template.resource_count_is("AWS::ECS::Service", 1)

    def test_creates_task_definition(self, template):
        """APIStack should create task definition."""
        template.resource_count_is("AWS::ECS::TaskDefinition", 1)

    def test_creates_log_group(self, template):
        """APIStack should create CloudWatch log group."""
        template.resource_count_is("AWS::Logs::LogGroup", 1)

    def test_alb_is_public(self, template):
        """ALB should be internet-facing."""
        template.has_resource_properties(
            "AWS::ElasticLoadBalancingV2::LoadBalancer",
            {"Scheme": "internet-facing"},
        )

    def test_target_group_has_health_check(self, template):
        """Target group should have health check configured."""
        template.has_resource_properties(
            "AWS::ElasticLoadBalancingV2::TargetGroup",
            {
                "HealthCheckPath": "/health",
                "HealthyThresholdCount": 2,
                "UnhealthyThresholdCount": 3,
            },
        )


class TestAPIStackTaskDefinition:
    """Tests for API task definition configuration."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def vpc_stack(self, app):
        """Create a VPC stack for testing."""
        stack = cdk.Stack(app, "VPCStack2", env=cdk.Environment(
            account="123456789012", region="us-east-1"
        ))
        vpc = ec2.Vpc(stack, "VPC", max_azs=2)
        return stack, vpc

    @pytest.fixture
    def cluster(self, vpc_stack):
        """Create ECS cluster for testing."""
        stack, vpc = vpc_stack
        return ecs.Cluster(stack, "Cluster", vpc=vpc)

    def test_task_def_has_custom_cpu(self, app, vpc_stack, cluster):
        """Task definition should have configured CPU."""
        stack, vpc = vpc_stack
        api_stack = APIStack(
            app,
            "CustomCPUStack",
            vpc=vpc,
            cluster=cluster,
            environment_name="dev",
            api_cpu=1024,
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        template = assertions.Template.from_stack(api_stack)

        template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            {"Cpu": "1024"},
        )

    def test_task_def_has_custom_memory(self, app, vpc_stack, cluster):
        """Task definition should have configured memory."""
        stack, vpc = vpc_stack
        api_stack = APIStack(
            app,
            "CustomMemoryStack",
            vpc=vpc,
            cluster=cluster,
            environment_name="dev",
            api_memory_mib=2048,
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        template = assertions.Template.from_stack(api_stack)

        template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            {"Memory": "2048"},
        )

    def test_container_exposes_port_8000(self, app, vpc_stack, cluster):
        """Container should expose port 8000."""
        stack, vpc = vpc_stack
        api_stack = APIStack(
            app,
            "PortStack",
            vpc=vpc,
            cluster=cluster,
            environment_name="dev",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        template = assertions.Template.from_stack(api_stack)

        template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            {
                "ContainerDefinitions": assertions.Match.array_with(
                    [
                        assertions.Match.object_like(
                            {
                                "PortMappings": assertions.Match.array_with(
                                    [
                                        assertions.Match.object_like(
                                            {"ContainerPort": 8000}
                                        )
                                    ]
                                )
                            }
                        )
                    ]
                )
            },
        )


class TestAPIStackAutoScaling:
    """Tests for auto-scaling configuration."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def vpc_stack(self, app):
        """Create a VPC stack for testing."""
        stack = cdk.Stack(app, "VPCStack3", env=cdk.Environment(
            account="123456789012", region="us-east-1"
        ))
        vpc = ec2.Vpc(stack, "VPC", max_azs=2)
        return stack, vpc

    @pytest.fixture
    def cluster(self, vpc_stack):
        """Create ECS cluster for testing."""
        stack, vpc = vpc_stack
        return ecs.Cluster(stack, "Cluster", vpc=vpc)

    @pytest.fixture
    def api_stack(self, app, vpc_stack, cluster):
        """Create API stack for testing."""
        stack, vpc = vpc_stack
        return APIStack(
            app,
            "AutoScaleStack",
            vpc=vpc,
            cluster=cluster,
            environment_name="dev",
            min_capacity=2,
            max_capacity=20,
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )

    @pytest.fixture
    def template(self, api_stack):
        """Get CloudFormation template from stack."""
        return assertions.Template.from_stack(api_stack)

    def test_creates_scalable_target(self, template):
        """Stack should create auto-scaling target."""
        template.resource_count_is(
            "AWS::ApplicationAutoScaling::ScalableTarget", 1
        )

    def test_creates_scaling_policies(self, template):
        """Stack should create scaling policies."""
        # Should have CPU and request-based scaling policies
        template.resource_count_is(
            "AWS::ApplicationAutoScaling::ScalingPolicy", 2
        )

    def test_scalable_target_has_correct_capacity(self, template):
        """Scalable target should have correct min/max capacity."""
        template.has_resource_properties(
            "AWS::ApplicationAutoScaling::ScalableTarget",
            {
                "MinCapacity": 2,
                "MaxCapacity": 20,
            },
        )


class TestAPIStackAttributes:
    """Tests for APIStack attributes."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def vpc_stack(self, app):
        """Create a VPC stack for testing."""
        stack = cdk.Stack(app, "VPCStack4", env=cdk.Environment(
            account="123456789012", region="us-east-1"
        ))
        vpc = ec2.Vpc(stack, "VPC", max_azs=2)
        return stack, vpc

    @pytest.fixture
    def cluster(self, vpc_stack):
        """Create ECS cluster for testing."""
        stack, vpc = vpc_stack
        return ecs.Cluster(stack, "Cluster", vpc=vpc)

    @pytest.fixture
    def api_stack(self, app, vpc_stack, cluster):
        """Create API stack for testing."""
        stack, vpc = vpc_stack
        return APIStack(
            app,
            "AttrStack",
            vpc=vpc,
            cluster=cluster,
            environment_name="dev",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )

    def test_exposes_api_service(self, api_stack):
        """Stack should expose api_service attribute."""
        assert api_stack.api_service is not None

    def test_exposes_task_role(self, api_stack):
        """Stack should expose task_role attribute."""
        assert api_stack.task_role is not None

    def test_exposes_log_group(self, api_stack):
        """Stack should expose log_group attribute."""
        assert api_stack.log_group is not None

    def test_exposes_api_url(self, api_stack):
        """Stack should expose api_url attribute."""
        assert api_stack.api_url is not None
        assert "http" in api_stack.api_url

    def test_environment_name_stored(self, api_stack):
        """Stack should store environment name."""
        assert api_stack.environment_name == "dev"


class TestAPIStackWithECRRepository:
    """Tests for APIStack with ECR repository object."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def vpc_stack(self, app):
        """Create a VPC stack for testing."""
        stack = cdk.Stack(app, "VPCStack5", env=cdk.Environment(
            account="123456789012", region="us-east-1"
        ))
        vpc = ec2.Vpc(stack, "VPC", max_azs=2)
        return stack, vpc

    @pytest.fixture
    def cluster(self, vpc_stack):
        """Create ECS cluster for testing."""
        stack, vpc = vpc_stack
        return ecs.Cluster(stack, "Cluster", vpc=vpc)

    @pytest.fixture
    def ecr_stack(self, app):
        """Create ECR stack for repository objects."""
        return ECRStack(
            app, "ECRTestStack", environment_name="dev",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )

    def test_creates_with_ecr_repository(self, app, vpc_stack, cluster, ecr_stack):
        """APIStack should accept ECR repository object."""
        stack, vpc = vpc_stack
        api_stack = APIStack(
            app,
            "ECRAPIStack",
            vpc=vpc,
            cluster=cluster,
            environment_name="dev",
            ecr_repository=ecr_stack.repositories["app"],
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        assert api_stack.api_service is not None

    def test_ecr_repo_auto_grants_pull_permissions(self, app, vpc_stack, cluster, ecr_stack):
        """Using ECR repo object should auto-grant image pull permissions."""
        stack, vpc = vpc_stack
        api_stack = APIStack(
            app,
            "ECRPermAPIStack",
            vpc=vpc,
            cluster=cluster,
            environment_name="dev",
            ecr_repository=ecr_stack.repositories["app"],
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        template = assertions.Template.from_stack(api_stack)
        template.has_resource_properties(
            "AWS::IAM::Policy",
            {
                "PolicyDocument": assertions.Match.object_like({
                    "Statement": assertions.Match.array_with([
                        assertions.Match.object_like({
                            "Action": assertions.Match.array_with([
                                "ecr:BatchCheckLayerAvailability",
                            ]),
                            "Effect": "Allow",
                        })
                    ])
                })
            },
        )
