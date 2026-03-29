"""Tests for ServicesStack CDK stack - auto-scaling and alarm tests."""

import aws_cdk as cdk
import pytest
from aws_cdk import assertions

from stacks.services_stack import ServicesStack
from stacks.compute_stack import ComputeStack
from stacks.queue_stack import QueueStack


class TestServicesStackAutoScaling:
    """Tests for SQS queue-depth-driven auto-scaling of pipeline services."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def compute_stack(self, app):
        """Create compute stack for dependencies."""
        return ComputeStack(app, "AutoScaleCompute", environment_name="dev")

    @pytest.fixture
    def queue_stack(self, app):
        """Create queue stack for SQS queues."""
        return QueueStack(app, "AutoScaleQueues", environment_name="dev")

    @pytest.fixture
    def stack_with_all_scaling(self, app, compute_stack, queue_stack):
        """Create services stack with all services auto-scaled."""
        stack = ServicesStack(
            app,
            "AllScalingStack",
            environment_name="dev",
            vpc=compute_stack.vpc,
            cluster=compute_stack.cluster,
        )
        stack.configure_auto_scaling(
            validator_queue=queue_stack.validator_queue,
            reconciler_queue=queue_stack.reconciler_queue,
            recorder_queue=queue_stack.recorder_queue,
        )
        return stack

    @pytest.fixture
    def template_with_all_scaling(self, stack_with_all_scaling):
        """Get CloudFormation template from stack with all scaling."""
        return assertions.Template.from_stack(stack_with_all_scaling)

    def test_creates_four_scalable_targets(self, template_with_all_scaling):
        """Auto-scaling should create 4 ScalableTargets (validator, reconciler, recorder, submarine)."""
        template_with_all_scaling.resource_count_is(
            "AWS::ApplicationAutoScaling::ScalableTarget", 4
        )

    def test_validator_max_capacity_is_four(self, template_with_all_scaling):
        """Validator ScalableTarget should have max capacity of 4."""
        template_with_all_scaling.has_resource_properties(
            "AWS::ApplicationAutoScaling::ScalableTarget",
            {
                "MaxCapacity": 4,
                "MinCapacity": 0,
                "ScalableDimension": "ecs:service:DesiredCount",
            },
        )

    def test_reconciler_max_capacity_is_one(self, template_with_all_scaling):
        """Reconciler ScalableTarget should have max capacity of 1."""
        template_with_all_scaling.has_resource_properties(
            "AWS::ApplicationAutoScaling::ScalableTarget",
            {
                "MaxCapacity": 1,
                "MinCapacity": 0,
                "ScalableDimension": "ecs:service:DesiredCount",
            },
        )

    def test_creates_six_scaling_policies(self, template_with_all_scaling):
        """Auto-scaling should create 6 scaling policies (2 per service)."""
        template_with_all_scaling.resource_count_is(
            "AWS::ApplicationAutoScaling::ScalingPolicy", 6
        )

    def test_partial_config_only_validator(self, app, queue_stack):
        """Passing only validator_queue should create scaling for validator only."""
        compute = ComputeStack(app, "PartialCompute", environment_name="dev")
        stack = ServicesStack(
            app,
            "PartialScaleStack",
            environment_name="dev",
            vpc=compute.vpc,
            cluster=compute.cluster,
        )
        stack.configure_auto_scaling(validator_queue=queue_stack.validator_queue)
        template = assertions.Template.from_stack(stack)
        template.resource_count_is("AWS::ApplicationAutoScaling::ScalableTarget", 1)
        template.resource_count_is("AWS::ApplicationAutoScaling::ScalingPolicy", 2)

    def test_without_configure_no_scaling_resources(self, app):
        """Without configure_auto_scaling(), no scaling resources should exist."""
        compute = ComputeStack(app, "NoScaleCompute", environment_name="dev")
        stack = ServicesStack(
            app,
            "NoScaleServicesStack",
            environment_name="dev",
            vpc=compute.vpc,
            cluster=compute.cluster,
        )
        template = assertions.Template.from_stack(stack)
        template.resource_count_is("AWS::ApplicationAutoScaling::ScalableTarget", 0)
        template.resource_count_is("AWS::ApplicationAutoScaling::ScalingPolicy", 0)
