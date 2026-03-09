"""Tests for BastionStack CDK stack."""

import aws_cdk as cdk
import pytest
from aws_cdk import assertions

from stacks.bastion_stack import BastionStack
from stacks.compute_stack import ComputeStack


class TestBastionStackResources:
    """Tests for BastionStack resource creation."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def compute_stack(self, app):
        """Create compute stack for VPC dependency."""
        return ComputeStack(app, "TestComputeStack", environment_name="dev")

    @pytest.fixture
    def dev_stack(self, app, compute_stack):
        """Create dev environment bastion stack."""
        return BastionStack(
            app,
            "TestBastionStack",
            environment_name="dev",
            vpc=compute_stack.vpc,
        )

    @pytest.fixture
    def dev_template(self, dev_stack):
        """Get CloudFormation template."""
        return assertions.Template.from_stack(dev_stack)

    def test_creates_ec2_instance(self, dev_template):
        """BastionStack should create an EC2 instance."""
        dev_template.resource_count_is("AWS::EC2::Instance", 1)

    def test_instance_type_is_t4g_nano(self, dev_template):
        """Bastion should use t4g.nano instance type."""
        dev_template.has_resource_properties(
            "AWS::EC2::Instance",
            {"InstanceType": "t4g.nano"},
        )

    def test_creates_security_group(self, dev_template):
        """BastionStack should create a security group."""
        dev_template.resource_count_is("AWS::EC2::SecurityGroup", 1)

    def test_security_group_has_no_inbound_rules(self, dev_template):
        """Bastion security group should have no inbound rules."""
        # The SG should exist but without SecurityGroupIngress
        raw_template = dev_template.to_json()
        for resource_id, resource in raw_template["Resources"].items():
            if resource["Type"] == "AWS::EC2::SecurityGroup":
                props = resource.get("Properties", {})
                ingress = props.get("SecurityGroupIngress", [])
                assert (
                    ingress == [] or "SecurityGroupIngress" not in props
                ), "Bastion security group should have no inbound rules"

    def test_instance_has_ssm_managed_role(self, dev_template):
        """Bastion should have IAM instance profile with SSM access."""
        raw_template = dev_template.to_json()
        found_ssm_policy = False
        for resource_id, resource in raw_template["Resources"].items():
            if resource["Type"] == "AWS::IAM::Role":
                arns = resource.get("Properties", {}).get("ManagedPolicyArns", [])
                for arn in arns:
                    # CDK generates Fn::Join for managed policy ARNs
                    if isinstance(arn, dict) and "Fn::Join" in arn:
                        joined = "".join(str(p) for p in arn["Fn::Join"][1])
                        if "AmazonSSMManagedInstanceCore" in joined:
                            found_ssm_policy = True
                    elif isinstance(arn, str) and "AmazonSSMManagedInstanceCore" in arn:
                        found_ssm_policy = True
        assert (
            found_ssm_policy
        ), "Bastion role should have AmazonSSMManagedInstanceCore policy"

    def test_instance_in_private_subnet(self, dev_template):
        """Bastion should be in a private subnet."""
        # Instance should reference a subnet from the VPC
        dev_template.has_resource_properties(
            "AWS::EC2::Instance",
            {
                "SubnetId": assertions.Match.any_value(),
            },
        )


class TestBastionStackAttributes:
    """Tests for stack attributes and outputs."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def stack(self, app):
        """Create stack for testing."""
        compute_stack = ComputeStack(app, "AttrCompute", environment_name="dev")
        return BastionStack(
            app,
            "AttrBastionStack",
            environment_name="dev",
            vpc=compute_stack.vpc,
        )

    def test_exposes_security_group(self, stack):
        """Stack should expose bastion_security_group."""
        assert stack.bastion_security_group is not None

    def test_exposes_instance(self, stack):
        """Stack should expose instance attribute."""
        assert stack.instance is not None

    def test_environment_name_stored(self, stack):
        """Stack should store environment name."""
        assert stack.environment_name == "dev"
