"""Tests for PipelineStack CDK stack."""

import aws_cdk as cdk
import pytest
from aws_cdk import assertions

from stacks.pipeline_stack import PipelineStack
from stacks.compute_stack import ComputeStack
from stacks.services_stack import ServicesStack


class TestPipelineStackResources:
    """Tests for PipelineStack resource creation."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def dev_stack(self, app):
        """Create dev environment stack with dependencies."""
        compute_stack = ComputeStack(app, "TestComputeStack", environment_name="dev")
        services_stack = ServicesStack(
            app,
            "TestServicesStack",
            environment_name="dev",
            vpc=compute_stack.vpc,
            cluster=compute_stack.cluster,
        )
        return PipelineStack(
            app,
            "TestPipelineStack",
            environment_name="dev",
            cluster=compute_stack.cluster,
            scraper_task_definition=services_stack.scraper_task_definition,
        )

    @pytest.fixture
    def dev_template(self, dev_stack):
        """Get CloudFormation template from dev stack."""
        return assertions.Template.from_stack(dev_stack)

    def test_creates_state_machine(self, dev_template):
        """PipelineStack should create Step Functions state machine."""
        dev_template.resource_count_is("AWS::StepFunctions::StateMachine", 1)

    def test_creates_eventbridge_rule(self, dev_template):
        """PipelineStack should create EventBridge schedule rule."""
        dev_template.resource_count_is("AWS::Events::Rule", 1)

    def test_state_machine_has_name(self, dev_template):
        """State machine should have proper name."""
        dev_template.has_resource_properties(
            "AWS::StepFunctions::StateMachine",
            {
                "StateMachineName": assertions.Match.string_like_regexp(
                    "pantry-pirate-scraper-pipeline.*"
                )
            },
        )

    def test_eventbridge_rule_is_disabled_by_default(self, dev_template):
        """EventBridge schedule should be disabled by default."""
        dev_template.has_resource_properties(
            "AWS::Events::Rule",
            {"State": "DISABLED"},
        )


class TestPipelineStackEnvironments:
    """Tests for environment-specific configuration."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    def test_prod_rule_enabled(self, app):
        """Prod environment should have schedule enabled."""
        compute_stack = ComputeStack(app, "ComputeStack1", environment_name="prod")
        services_stack = ServicesStack(
            app,
            "ServicesStack1",
            environment_name="prod",
            vpc=compute_stack.vpc,
            cluster=compute_stack.cluster,
        )
        stack = PipelineStack(
            app,
            "ProdStack",
            environment_name="prod",
            cluster=compute_stack.cluster,
            scraper_task_definition=services_stack.scraper_task_definition,
            schedule_enabled=True,
        )
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::Events::Rule",
            {"State": "ENABLED"},
        )


class TestPipelineStackAttributes:
    """Tests for stack attributes and outputs."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def stack(self, app):
        """Create stack for testing."""
        compute_stack = ComputeStack(app, "ComputeStack", environment_name="dev")
        services_stack = ServicesStack(
            app,
            "ServicesStack",
            environment_name="dev",
            vpc=compute_stack.vpc,
            cluster=compute_stack.cluster,
        )
        return PipelineStack(
            app,
            "AttrTestStack",
            environment_name="dev",
            cluster=compute_stack.cluster,
            scraper_task_definition=services_stack.scraper_task_definition,
        )

    def test_exposes_state_machine(self, stack):
        """Stack should expose state_machine attribute."""
        assert stack.state_machine is not None

    def test_exposes_schedule_rule(self, stack):
        """Stack should expose schedule_rule attribute."""
        assert stack.schedule_rule is not None

    def test_environment_name_stored(self, stack):
        """Stack should store environment name."""
        assert stack.environment_name == "dev"
