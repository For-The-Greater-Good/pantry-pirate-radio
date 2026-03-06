"""Tests for MetabaseAccessStack CDK stack."""

import aws_cdk as cdk
import pytest
from aws_cdk import assertions

from stacks.compute_stack import ComputeStack
from stacks.metabase_access_stack import MetabaseAccessStack


class TestMetabaseAccessStackResources:
    """Tests for MetabaseAccessStack resource creation."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def compute_stack(self, app):
        """Create compute stack for VPC dependency."""
        return ComputeStack(
            app,
            "TestComputeStack",
            environment_name="dev",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )

    @pytest.fixture
    def stack(self, app, compute_stack):
        """Create MetabaseAccessStack for testing."""
        return MetabaseAccessStack(
            app,
            "TestMetabaseStack",
            vpc=compute_stack.vpc,
            proxy_endpoint="test-proxy.proxy-abc123.us-east-1.rds.amazonaws.com",
            environment_name="dev",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )

    @pytest.fixture
    def template(self, stack):
        """Get CloudFormation template from stack."""
        return assertions.Template.from_stack(stack)

    def test_creates_one_nlb(self, template):
        """MetabaseAccessStack should create 1 internet-facing NLB."""
        template.resource_count_is(
            "AWS::ElasticLoadBalancingV2::LoadBalancer", 1
        )

    def test_nlb_is_internet_facing(self, template):
        """NLB should be internet-facing for Metabase Cloud access."""
        template.has_resource_properties(
            "AWS::ElasticLoadBalancingV2::LoadBalancer",
            {
                "Scheme": "internet-facing",
                "Type": "network",
            },
        )

    def test_creates_tcp_listener_on_5432(self, template):
        """NLB should have a TCP listener on port 5432."""
        template.has_resource_properties(
            "AWS::ElasticLoadBalancingV2::Listener",
            {
                "Port": 5432,
                "Protocol": "TCP",
            },
        )

    def test_creates_ip_target_group(self, template):
        """Target group should use IP target type on port 5432."""
        template.has_resource_properties(
            "AWS::ElasticLoadBalancingV2::TargetGroup",
            {
                "TargetType": "ip",
                "Port": 5432,
                "Protocol": "TCP",
            },
        )

    def test_creates_lambda_functions(self, template):
        """Stack should create Lambda functions (IP sync + custom resource provider)."""
        template.resource_count_is("AWS::Lambda::Function", 2)

    def test_creates_eventbridge_rule(self, template):
        """Stack should create EventBridge rule for periodic IP sync."""
        template.has_resource_properties(
            "AWS::Events::Rule",
            {
                "ScheduleExpression": "rate(1 minute)",
                "State": "ENABLED",
            },
        )

    def test_creates_security_group(self, template):
        """Stack should create a security group for the NLB."""
        template.resource_count_is("AWS::EC2::SecurityGroup", 1)

    def test_security_group_allows_metabase_ips(self, template):
        """Security group should allow TCP 5432 from Metabase Cloud IPs."""
        template.has_resource_properties(
            "AWS::EC2::SecurityGroup",
            {
                "SecurityGroupIngress": assertions.Match.array_with(
                    [
                        assertions.Match.object_like(
                            {
                                "CidrIp": "18.207.81.126/32",
                                "FromPort": 5432,
                                "ToPort": 5432,
                                "IpProtocol": "tcp",
                            }
                        ),
                        assertions.Match.object_like(
                            {
                                "CidrIp": "3.211.20.157/32",
                                "FromPort": 5432,
                                "ToPort": 5432,
                                "IpProtocol": "tcp",
                            }
                        ),
                        assertions.Match.object_like(
                            {
                                "CidrIp": "50.17.234.169/32",
                                "FromPort": 5432,
                                "ToPort": 5432,
                                "IpProtocol": "tcp",
                            }
                        ),
                    ]
                )
            },
        )


class TestMetabaseAccessStackAttributes:
    """Tests for stack attributes and outputs."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def compute_stack(self, app):
        """Create compute stack for VPC dependency."""
        return ComputeStack(
            app,
            "AttrComputeStack",
            environment_name="dev",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )

    @pytest.fixture
    def stack(self, app, compute_stack):
        """Create MetabaseAccessStack for testing."""
        return MetabaseAccessStack(
            app,
            "AttrMetabaseStack",
            vpc=compute_stack.vpc,
            proxy_endpoint="test-proxy.proxy-abc123.us-east-1.rds.amazonaws.com",
            environment_name="dev",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )

    def test_exposes_nlb(self, stack):
        """Stack should expose nlb attribute."""
        assert stack.nlb is not None

    def test_exposes_nlb_dns_name(self, stack):
        """Stack should expose nlb_dns_name attribute."""
        assert stack.nlb_dns_name is not None

    def test_exposes_nlb_security_group(self, stack):
        """Stack should expose nlb_security_group for proxy SG wiring."""
        assert stack.nlb_security_group is not None

    def test_stores_environment_name(self, stack):
        """Stack should store environment name."""
        assert stack.environment_name == "dev"


class TestMetabaseAccessStackLambda:
    """Tests for Lambda function configuration."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def compute_stack(self, app):
        """Create compute stack for VPC dependency."""
        return ComputeStack(
            app,
            "LambdaComputeStack",
            environment_name="dev",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )

    @pytest.fixture
    def stack(self, app, compute_stack):
        """Create MetabaseAccessStack for testing."""
        return MetabaseAccessStack(
            app,
            "LambdaMetabaseStack",
            vpc=compute_stack.vpc,
            proxy_endpoint="test-proxy.proxy-abc123.us-east-1.rds.amazonaws.com",
            environment_name="dev",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )

    @pytest.fixture
    def template(self, stack):
        """Get CloudFormation template from stack."""
        return assertions.Template.from_stack(stack)

    def test_lambda_has_proxy_endpoint_env(self, template):
        """Lambda should have PROXY_ENDPOINT environment variable."""
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {
                "Environment": assertions.Match.object_like(
                    {
                        "Variables": assertions.Match.object_like(
                            {
                                "PROXY_ENDPOINT": "test-proxy.proxy-abc123.us-east-1.rds.amazonaws.com",
                            }
                        )
                    }
                )
            },
        )

    def test_lambda_has_target_group_arn_env(self, template):
        """Lambda should have TARGET_GROUP_ARN environment variable."""
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {
                "Environment": assertions.Match.object_like(
                    {
                        "Variables": assertions.Match.object_like(
                            {
                                "TARGET_GROUP_ARN": assertions.Match.any_value(),
                            }
                        )
                    }
                )
            },
        )

    def test_lambda_has_elbv2_permissions(self, template):
        """Lambda should have ELBv2 permissions for target management."""
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
                                                "elasticloadbalancing:RegisterTargets",
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

    def test_lambda_runtime_is_python(self, template):
        """Lambda should use Python 3.11 runtime."""
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {
                "Runtime": "python3.11",
            },
        )

    def test_lambda_not_in_vpc(self, template):
        """Lambda should NOT be in VPC (only needs DNS + ELBv2 API)."""
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {
                "VpcConfig": assertions.Match.absent(),
            },
        )
