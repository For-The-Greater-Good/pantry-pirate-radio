"""Tests for Submarine Step Functions stack."""

import aws_cdk as cdk
import pytest
from aws_cdk import assertions

from stacks.submarine_stack import SubmarineStack


class TestSubmarineStackResources:
    """Tests for submarine stack resource creation."""

    @pytest.fixture
    def app(self):
        return cdk.App()

    @pytest.fixture
    def stack(self, app):
        return SubmarineStack(
            app,
            "TestSubmarineStack",
            environment_name="dev",
            cluster_arn="arn:aws:ecs:us-east-1:123456789012:cluster/test",
            subnet_ids=["subnet-abc123"],
            scanner_task_family="pantry-pirate-radio-app-dev",
            scanner_container_name="AppContainer",
            submarine_queue_url="https://sqs.us-east-1.amazonaws.com/123/submarine.fifo",
        )

    @pytest.fixture
    def template(self, stack):
        return assertions.Template.from_stack(stack)

    def test_creates_state_machine(self, template):
        """Stack creates a Step Functions state machine."""
        template.resource_count_is("AWS::StepFunctions::StateMachine", 1)

    def test_creates_eventbridge_rule(self, template):
        """Stack creates an EventBridge schedule rule."""
        template.resource_count_is("AWS::Events::Rule", 1)

    def test_schedule_disabled_in_dev(self, template):
        """EventBridge rule is disabled in dev."""
        template.has_resource_properties(
            "AWS::Events::Rule",
            {"State": "DISABLED"},
        )

    def test_creates_iam_role(self, template):
        """Stack creates IAM role for state machine."""
        template.has_resource_properties(
            "AWS::IAM::Role",
            {
                "AssumeRolePolicyDocument": assertions.Match.object_like(
                    {
                        "Statement": assertions.Match.array_with(
                            [
                                assertions.Match.object_like(
                                    {
                                        "Action": "sts:AssumeRole",
                                        "Principal": {
                                            "Service": "states.amazonaws.com"
                                        },
                                    }
                                )
                            ]
                        )
                    }
                )
            },
        )


class TestSubmarineStackProd:
    """Tests for production environment settings."""

    @pytest.fixture
    def app(self):
        return cdk.App()

    @pytest.fixture
    def stack(self, app):
        return SubmarineStack(
            app,
            "TestSubmarineProdStack",
            environment_name="prod",
            cluster_arn="arn:aws:ecs:us-east-1:123456789012:cluster/prod",
            subnet_ids=["subnet-abc123"],
            scanner_task_family="pantry-pirate-radio-app-prod",
            scanner_container_name="AppContainer",
            submarine_queue_url="https://sqs.us-east-1.amazonaws.com/123/submarine.fifo",
            schedule_enabled=True,
        )

    @pytest.fixture
    def template(self, stack):
        return assertions.Template.from_stack(stack)

    def test_schedule_enabled_in_prod(self, template):
        """EventBridge rule is enabled in prod."""
        template.has_resource_properties(
            "AWS::Events::Rule",
            {"State": "ENABLED"},
        )


class TestSubmarineStackAttributes:
    """Tests for stack attribute availability."""

    @pytest.fixture
    def app(self):
        return cdk.App()

    @pytest.fixture
    def stack(self, app):
        return SubmarineStack(
            app,
            "TestSubmarineAttrStack",
            environment_name="dev",
            cluster_arn="arn:aws:ecs:us-east-1:123456789012:cluster/test",
            subnet_ids=["subnet-abc123"],
            scanner_task_family="pantry-pirate-radio-app-dev",
            scanner_container_name="AppContainer",
            submarine_queue_url="https://sqs.us-east-1.amazonaws.com/123/submarine.fifo",
        )

    def test_has_state_machine(self, stack):
        """Stack exposes state_machine attribute."""
        assert stack.state_machine is not None

    def test_has_schedule_rule(self, stack):
        """Stack exposes schedule_rule attribute."""
        assert stack.schedule_rule is not None
