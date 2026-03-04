"""Tests for ComputeStack CDK stack."""

import aws_cdk as cdk
import pytest
from aws_cdk import assertions

from stacks.compute_stack import ComputeStack


class TestComputeStackResources:
    """Tests for ComputeStack resource creation."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def stack(self, app):
        """Create stack for testing."""
        return ComputeStack(
            app,
            "TestComputeStack",
            environment_name="dev",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )

    @pytest.fixture
    def template(self, stack):
        """Get CloudFormation template from stack."""
        return assertions.Template.from_stack(stack)

    def test_creates_vpc(self, template):
        """ComputeStack should create VPC."""
        template.resource_count_is("AWS::EC2::VPC", 1)

    def test_creates_ecs_cluster(self, template):
        """ComputeStack should create ECS cluster."""
        template.resource_count_is("AWS::ECS::Cluster", 1)

    def test_creates_fargate_service(self, template):
        """ComputeStack should create Fargate service."""
        template.resource_count_is("AWS::ECS::Service", 1)

    def test_creates_task_definition(self, template):
        """ComputeStack should create task definition."""
        template.resource_count_is("AWS::ECS::TaskDefinition", 1)

    def test_creates_log_group(self, template):
        """ComputeStack should create CloudWatch log group."""
        template.resource_count_is("AWS::Logs::LogGroup", 1)

    def test_vpc_has_subnets(self, template):
        """VPC should have public and private subnets."""
        # Should have at least 4 subnets (2 AZs x 2 types)
        template.resource_count_is("AWS::EC2::Subnet", 4)

    def test_ecs_cluster_has_container_insights(self, template):
        """ECS cluster should have Container Insights enabled."""
        template.has_resource_properties(
            "AWS::ECS::Cluster",
            {
                "ClusterSettings": assertions.Match.array_with(
                    [
                        assertions.Match.object_like(
                            {"Name": "containerInsights", "Value": "enabled"}
                        )
                    ]
                )
            },
        )


class TestComputeStackTaskDefinition:
    """Tests for task definition configuration."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def stack(self, app):
        """Create stack for testing."""
        return ComputeStack(
            app,
            "TaskDefStack",
            environment_name="dev",
            worker_cpu=2048,
            worker_memory_mib=4096,
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )

    @pytest.fixture
    def template(self, stack):
        """Get CloudFormation template from stack."""
        return assertions.Template.from_stack(stack)

    def test_task_def_has_cpu(self, template):
        """Task definition should have configured CPU."""
        template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            {
                "Cpu": "2048",
            },
        )

    def test_task_def_has_memory(self, template):
        """Task definition should have configured memory."""
        template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            {
                "Memory": "4096",
            },
        )

    def test_task_def_is_fargate(self, template):
        """Task definition should use Fargate."""
        template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            {
                "RequiresCompatibilities": ["FARGATE"],
            },
        )


class TestComputeStackIAM:
    """Tests for IAM role configuration."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def stack(self, app):
        """Create stack for testing."""
        return ComputeStack(
            app,
            "IAMStack",
            environment_name="dev",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )

    @pytest.fixture
    def template(self, stack):
        """Get CloudFormation template from stack."""
        return assertions.Template.from_stack(stack)

    def test_creates_execution_role(self, template):
        """Stack should create task execution role."""
        template.has_resource_properties(
            "AWS::IAM::Role",
            {
                "AssumeRolePolicyDocument": assertions.Match.object_like(
                    {
                        "Statement": assertions.Match.array_with(
                            [
                                assertions.Match.object_like(
                                    {
                                        "Principal": {
                                            "Service": "ecs-tasks.amazonaws.com"
                                        },
                                    }
                                )
                            ]
                        )
                    }
                )
            },
        )

    def test_task_role_has_bedrock_permissions(self, template):
        """Task role should have Bedrock invoke permissions."""
        template.has_resource_properties(
            "AWS::IAM::Policy",
            {
                "PolicyDocument": assertions.Match.object_like(
                    {
                        "Statement": assertions.Match.array_with(
                            [
                                assertions.Match.object_like(
                                    {
                                        "Action": assertions.Match.array_with(
                                            ["bedrock:InvokeModel"]
                                        ),
                                        "Effect": "Allow",
                                    }
                                )
                            ]
                        )
                    }
                )
            },
        )


class TestComputeStackAttributes:
    """Tests for ComputeStack attributes."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def stack(self, app):
        """Create stack for testing."""
        return ComputeStack(
            app,
            "AttrStack",
            environment_name="dev",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )

    def test_exposes_vpc(self, stack):
        """Stack should expose vpc attribute."""
        assert stack.vpc is not None

    def test_exposes_cluster(self, stack):
        """Stack should expose cluster attribute."""
        assert stack.cluster is not None

    def test_exposes_worker_service(self, stack):
        """Stack should expose worker_service attribute."""
        assert stack.worker_service is not None

    def test_exposes_task_role(self, stack):
        """Stack should expose task_role attribute."""
        assert stack.task_role is not None

    def test_environment_name_stored(self, stack):
        """Stack should store environment name."""
        assert stack.environment_name == "dev"

    def test_exposes_worker_security_group(self, stack):
        """Stack should expose worker_security_group for database wiring."""
        assert stack.worker_security_group is not None


class TestComputeStackEnvironments:
    """Tests for environment-specific configuration."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    def test_dev_uses_single_nat_gateway(self, app):
        """Dev environment should use 1 NAT gateway for cost savings."""
        stack = ComputeStack(
            app,
            "DevStack",
            environment_name="dev",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        template = assertions.Template.from_stack(stack)

        # Dev should have 1 NAT gateway
        template.resource_count_is("AWS::EC2::NatGateway", 1)

    def test_prod_uses_multiple_nat_gateways(self, app):
        """Prod environment should use multiple NAT gateways for HA."""
        stack = ComputeStack(
            app,
            "ProdStack",
            environment_name="prod",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        template = assertions.Template.from_stack(stack)

        # Prod should have 2 NAT gateways (one per AZ)
        template.resource_count_is("AWS::EC2::NatGateway", 2)
