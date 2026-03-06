"""Tests for PipelineStack CDK stack."""

import json

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
        return PipelineStack(
            app,
            "TestPipelineStack",
            environment_name="dev",
            cluster=compute_stack.cluster,
            scraper_task_family="pantry-pirate-radio-scraper-dev",
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

    def test_container_overrides_include_service_type(self, dev_stack):
        """Container overrides should set SERVICE_TYPE=scraper."""
        template = assertions.Template.from_stack(dev_stack)
        raw_template = template.to_json()
        # Find the state machine and parse its definition string
        for resource_id, resource in raw_template["Resources"].items():
            if resource["Type"] == "AWS::StepFunctions::StateMachine":
                def_string = resource["Properties"]["DefinitionString"]
                # May be plain string or Fn::Join
                if isinstance(def_string, str):
                    definition = json.loads(def_string)
                else:
                    parts = def_string["Fn::Join"]
                    definition = json.loads("".join(str(p) for p in parts[1]))

                # Navigate to container overrides
                run_task = definition["States"]["RunAllScrapers"]["ItemProcessor"]["States"]["RunScraperTask"]
                overrides = run_task["Parameters"]["Overrides"]["ContainerOverrides"][0]
                env_vars = {e["Name"]: e.get("Value", e.get("Value.$")) for e in overrides["Environment"]}

                assert env_vars.get("SERVICE_TYPE") == "scraper", (
                    "SERVICE_TYPE should be 'scraper'"
                )
                assert env_vars.get("SCRAPER_NAME") == "$.scraper_name", (
                    "SCRAPER_NAME should reference input path"
                )
                break
        else:
            pytest.fail("No StateMachine resource found")

    def test_backward_compat_with_task_definition_object(self, app):
        """PipelineStack should still work with scraper_task_definition object."""
        compute_stack = ComputeStack(app, "CompatCompute", environment_name="dev")
        services_stack = ServicesStack(
            app,
            "CompatServices",
            environment_name="dev",
            vpc=compute_stack.vpc,
            cluster=compute_stack.cluster,
        )
        stack = PipelineStack(
            app,
            "CompatPipeline",
            environment_name="dev",
            cluster=compute_stack.cluster,
            scraper_task_definition=services_stack.scraper_task_definition,
        )
        assert stack.state_machine is not None


class TestPublisherSchedule:
    """Tests for the publisher EventBridge schedule."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    def test_creates_publisher_schedule_rule(self, app):
        """PipelineStack should create publisher EventBridge rule when configured."""
        compute_stack = ComputeStack(app, "PubSchedCompute", environment_name="dev")
        stack = PipelineStack(
            app,
            "PubSchedPipeline",
            environment_name="dev",
            cluster=compute_stack.cluster,
            scraper_task_family="pantry-pirate-radio-scraper-dev",
            publisher_task_family="pantry-pirate-radio-publisher-dev",
            publisher_schedule_enabled=True,
        )
        template = assertions.Template.from_stack(stack)

        # Should have 2 EventBridge rules: scraper schedule + publisher schedule
        template.resource_count_is("AWS::Events::Rule", 2)

    def test_publisher_schedule_disabled_by_default(self, app):
        """Publisher schedule should be disabled by default."""
        compute_stack = ComputeStack(app, "PubDefCompute", environment_name="dev")
        stack = PipelineStack(
            app,
            "PubDefPipeline",
            environment_name="dev",
            cluster=compute_stack.cluster,
            scraper_task_family="pantry-pirate-radio-scraper-dev",
        )
        template = assertions.Template.from_stack(stack)

        # Only the scraper schedule should exist
        template.resource_count_is("AWS::Events::Rule", 1)

    def test_publisher_schedule_runs_at_4am_utc(self, app):
        """Publisher schedule should run daily at 4 AM UTC."""
        compute_stack = ComputeStack(app, "Pub4AMCompute", environment_name="dev")
        stack = PipelineStack(
            app,
            "Pub4AMPipeline",
            environment_name="dev",
            cluster=compute_stack.cluster,
            scraper_task_family="pantry-pirate-radio-scraper-dev",
            publisher_task_family="pantry-pirate-radio-publisher-dev",
            publisher_schedule_enabled=True,
        )
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::Events::Rule",
            {
                "ScheduleExpression": "cron(0 4 * * ? *)",
                "State": "ENABLED",
            },
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
        stack = PipelineStack(
            app,
            "ProdStack",
            environment_name="prod",
            cluster=compute_stack.cluster,
            scraper_task_family="pantry-pirate-radio-scraper-prod",
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
        return PipelineStack(
            app,
            "AttrTestStack",
            environment_name="dev",
            cluster=compute_stack.cluster,
            scraper_task_family="pantry-pirate-radio-scraper-dev",
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
