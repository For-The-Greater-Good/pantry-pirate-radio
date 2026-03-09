"""Tests for ComputeStack CDK stack."""

import aws_cdk as cdk
import pytest
from aws_cdk import assertions

from stacks.compute_stack import ComputeStack
from stacks.ecr_stack import ECRStack
from stacks.queue_stack import QueueStack


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

    def test_dev_uses_nat_instance(self, app):
        """Dev environment should use a NAT Instance (t4g.nano) for cost savings."""
        stack = ComputeStack(
            app,
            "DevStack",
            environment_name="dev",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        template = assertions.Template.from_stack(stack)

        # Dev should have 0 managed NAT Gateways (uses NAT Instance instead)
        template.resource_count_is("AWS::EC2::NatGateway", 0)
        # NAT Instance is an EC2 instance
        template.has_resource_properties(
            "AWS::EC2::Instance",
            {"InstanceType": "t4g.nano"},
        )

    def test_prod_uses_nat_instance(self, app):
        """Prod environment should also use NAT Instance (same as dev)."""
        stack = ComputeStack(
            app,
            "ProdStack",
            environment_name="prod",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        template = assertions.Template.from_stack(stack)

        # Prod should have 0 managed NAT Gateways (uses NAT Instance like dev)
        template.resource_count_is("AWS::EC2::NatGateway", 0)
        template.has_resource_properties(
            "AWS::EC2::Instance",
            {"InstanceType": "t4g.nano"},
        )


class TestComputeStackVPCEndpoints:
    """Tests for VPC endpoint configuration."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def stack(self, app):
        """Create stack for testing."""
        return ComputeStack(
            app,
            "EndpointStack",
            environment_name="dev",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )

    @pytest.fixture
    def template(self, stack):
        """Get CloudFormation template from stack."""
        return assertions.Template.from_stack(stack)

    def test_creates_vpc_endpoints(self, template):
        """Should create 5 VPC endpoints (2 gateway + 3 interface)."""
        template.resource_count_is("AWS::EC2::VPCEndpoint", 5)

    def test_creates_gateway_endpoints(self, template):
        """Should create S3 and DynamoDB gateway endpoints (free)."""
        raw = template.to_json()
        endpoints = [
            r
            for r in raw["Resources"].values()
            if r["Type"] == "AWS::EC2::VPCEndpoint"
            and r["Properties"].get("VpcEndpointType") == "Gateway"
        ]
        assert len(endpoints) == 2

    def test_creates_interface_endpoints(self, template):
        """Should create ECR API, ECR DKR, and CloudWatch Logs interface endpoints."""
        raw = template.to_json()
        endpoints = [
            r
            for r in raw["Resources"].values()
            if r["Type"] == "AWS::EC2::VPCEndpoint"
            and r["Properties"].get("VpcEndpointType") == "Interface"
        ]
        assert len(endpoints) == 3

    def test_interface_endpoints_have_private_dns(self, template):
        """Interface endpoints should have private DNS enabled."""
        raw = template.to_json()
        endpoints = [
            r
            for r in raw["Resources"].values()
            if r["Type"] == "AWS::EC2::VPCEndpoint"
            and r["Properties"].get("VpcEndpointType") == "Interface"
        ]
        for ep in endpoints:
            assert ep["Properties"].get("PrivateDnsEnabled") is True


class TestComputeStackWithECRRepository:
    """Tests for ComputeStack with ECR repository object."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def ecr_stack(self, app):
        """Create ECR stack for repository objects."""
        return ECRStack(
            app,
            "ECRTestStack",
            environment_name="dev",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )

    def test_creates_with_ecr_repository(self, app, ecr_stack):
        """ComputeStack should accept ECR repository object."""
        stack = ComputeStack(
            app,
            "ECRComputeStack",
            environment_name="dev",
            ecr_repository=ecr_stack.repositories["worker"],
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        assert stack.worker_service is not None

    def test_ecr_repo_auto_grants_pull_permissions(self, app, ecr_stack):
        """Using ECR repo object should auto-grant image pull permissions."""
        stack = ComputeStack(
            app,
            "ECRPermComputeStack",
            environment_name="dev",
            ecr_repository=ecr_stack.repositories["worker"],
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        template = assertions.Template.from_stack(stack)
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
                                            [
                                                "ecr:BatchCheckLayerAvailability",
                                            ]
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


class TestComputeStackAutoScaling:
    """Tests for SQS queue-depth-driven auto-scaling."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def queue_stack(self, app):
        """Create queue stack for SQS queues."""
        return QueueStack(
            app,
            "AutoScaleQueueStack",
            environment_name="dev",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )

    @pytest.fixture
    def stack_with_scaling(self, app, queue_stack):
        """Create compute stack with auto-scaling configured."""
        stack = ComputeStack(
            app,
            "AutoScaleComputeStack",
            environment_name="dev",
            max_capacity=20,
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.configure_auto_scaling(queue_stack.llm_queue)
        return stack

    @pytest.fixture
    def template_with_scaling(self, stack_with_scaling):
        """Get CloudFormation template from stack with scaling."""
        return assertions.Template.from_stack(stack_with_scaling)

    def test_creates_scalable_target(self, template_with_scaling):
        """Auto-scaling should create a ScalableTarget with min=0, max=20."""
        template_with_scaling.has_resource_properties(
            "AWS::ApplicationAutoScaling::ScalableTarget",
            {
                "MinCapacity": 0,
                "MaxCapacity": 20,
                "ScalableDimension": "ecs:service:DesiredCount",
                "ServiceNamespace": "ecs",
            },
        )

    def test_creates_scaling_policies(self, template_with_scaling):
        """Auto-scaling should create step scaling policies (upper + lower)."""
        template_with_scaling.resource_count_is(
            "AWS::ApplicationAutoScaling::ScalingPolicy", 2
        )

    def test_creates_cloudwatch_alarms(self, template_with_scaling):
        """Auto-scaling should create CloudWatch alarms for scaling triggers."""
        template_with_scaling.resource_count_is("AWS::CloudWatch::Alarm", 2)

    def test_without_configure_no_scaling_resources(self, app):
        """Without configure_auto_scaling(), no scaling resources should exist."""
        stack = ComputeStack(
            app,
            "NoScaleStack",
            environment_name="dev",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        template = assertions.Template.from_stack(stack)
        template.resource_count_is("AWS::ApplicationAutoScaling::ScalableTarget", 0)
        template.resource_count_is("AWS::ApplicationAutoScaling::ScalingPolicy", 0)

    def test_scaling_uses_step_policy(self, template_with_scaling):
        """Scaling policy should use StepScaling type."""
        template_with_scaling.has_resource_properties(
            "AWS::ApplicationAutoScaling::ScalingPolicy",
            {
                "PolicyType": "StepScaling",
            },
        )

    def test_scaling_alarms_treat_missing_data_as_not_breaching(
        self, template_with_scaling
    ):
        """Alarms should treat missing data as notBreaching for reliable scale-from-zero."""
        raw = template_with_scaling.to_json()
        alarms = [
            r
            for r in raw["Resources"].values()
            if r["Type"] == "AWS::CloudWatch::Alarm"
        ]
        assert len(alarms) == 2
        for alarm in alarms:
            assert alarm["Properties"]["TreatMissingData"] == "notBreaching", (
                "Scaling alarms must use TreatMissingData=notBreaching "
                "to avoid INSUFFICIENT_DATA during idle periods"
            )

    def test_scaling_policy_has_metric_aggregation_type(self, template_with_scaling):
        """Step scaling policies should have explicit MetricAggregationType."""
        template_with_scaling.has_resource_properties(
            "AWS::ApplicationAutoScaling::ScalingPolicy",
            {
                "PolicyType": "StepScaling",
                "StepScalingPolicyConfiguration": assertions.Match.object_like(
                    {
                        "MetricAggregationType": "Average",
                    }
                ),
            },
        )
