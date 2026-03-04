"""Tests for MonitoringStack CDK stack."""

import aws_cdk as cdk
import pytest
from aws_cdk import assertions

from stacks.monitoring_stack import MonitoringStack


class TestMonitoringStackResources:
    """Tests for MonitoringStack resource creation."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def stack(self, app):
        """Create stack for testing."""
        return MonitoringStack(
            app,
            "TestMonitoringStack",
            environment_name="dev",
        )

    @pytest.fixture
    def template(self, stack):
        """Get CloudFormation template from stack."""
        return assertions.Template.from_stack(stack)

    def test_creates_sns_topic(self, template):
        """MonitoringStack should create SNS topic for alerts."""
        template.resource_count_is("AWS::SNS::Topic", 1)

    def test_creates_dashboard(self, template):
        """MonitoringStack should create CloudWatch dashboard."""
        template.resource_count_is("AWS::CloudWatch::Dashboard", 1)

    def test_creates_alarms(self, template):
        """MonitoringStack should create CloudWatch alarms."""
        # Should create 4 alarms: API CPU, Queue Depth, DLQ, DynamoDB Throttle
        template.resource_count_is("AWS::CloudWatch::Alarm", 4)

    def test_sns_topic_has_name(self, template):
        """SNS topic should have configured name."""
        template.has_resource_properties(
            "AWS::SNS::Topic",
            {
                "TopicName": "pantry-pirate-radio-alerts-dev",
            },
        )

    def test_dashboard_has_name(self, template):
        """Dashboard should have configured name."""
        template.has_resource_properties(
            "AWS::CloudWatch::Dashboard",
            {
                "DashboardName": "PantryPirateRadio-dev",
            },
        )


class TestMonitoringStackAlarms:
    """Tests for alarm configuration."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def stack(self, app):
        """Create stack for testing."""
        return MonitoringStack(
            app,
            "AlarmStack",
            environment_name="dev",
        )

    @pytest.fixture
    def template(self, stack):
        """Get CloudFormation template from stack."""
        return assertions.Template.from_stack(stack)

    def test_api_cpu_alarm_exists(self, template):
        """Should create API CPU alarm."""
        template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            {
                "AlarmName": "pantry-pirate-radio-api-cpu-dev",
                "MetricName": "CPUUtilization",
                "Namespace": "AWS/ECS",
            },
        )

    def test_queue_depth_alarm_exists(self, template):
        """Should create queue depth alarm."""
        template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            {
                "AlarmName": "pantry-pirate-radio-queue-depth-dev",
                "MetricName": "ApproximateNumberOfMessagesVisible",
                "Namespace": "AWS/SQS",
            },
        )

    def test_dlq_alarm_exists(self, template):
        """Should create DLQ alarm."""
        template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            {
                "AlarmName": "pantry-pirate-radio-dlq-dev",
            },
        )

    def test_dynamodb_throttle_alarm_exists(self, template):
        """Should create DynamoDB throttle alarm."""
        template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            {
                "AlarmName": "pantry-pirate-radio-dynamodb-throttle-dev",
                "MetricName": "ThrottledRequests",
                "Namespace": "AWS/DynamoDB",
            },
        )

    def test_alarms_have_actions(self, template):
        """All alarms should have SNS action configured."""
        # Get all alarm resources
        alarms = template.find_resources("AWS::CloudWatch::Alarm")
        for _name, alarm in alarms.items():
            props = alarm.get("Properties", {})
            assert "AlarmActions" in props, f"Alarm {_name} should have AlarmActions"


class TestMonitoringStackConfiguration:
    """Tests for monitoring stack configuration options."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    def test_custom_service_names(self, app):
        """Stack should accept custom service names."""
        stack = MonitoringStack(
            app,
            "CustomNamesStack",
            environment_name="prod",
            api_service_name="custom-api",
            worker_service_name="custom-worker",
            cluster_name="custom-cluster",
            queue_name="custom-queue.fifo",
            jobs_table_name="custom-jobs-table",
        )

        assert stack.api_service_name == "custom-api"
        assert stack.worker_service_name == "custom-worker"
        assert stack.cluster_name == "custom-cluster"
        assert stack.queue_name == "custom-queue.fifo"
        assert stack.jobs_table_name == "custom-jobs-table"

    def test_prod_environment_name(self, app):
        """Stack should work with prod environment."""
        stack = MonitoringStack(
            app,
            "ProdStack",
            environment_name="prod",
        )
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::SNS::Topic",
            {
                "TopicName": "pantry-pirate-radio-alerts-prod",
            },
        )


class TestMonitoringStackAttributes:
    """Tests for MonitoringStack attributes."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def stack(self, app):
        """Create stack for testing."""
        return MonitoringStack(
            app,
            "AttrStack",
            environment_name="dev",
        )

    def test_exposes_alerts_topic(self, stack):
        """Stack should expose alerts_topic attribute."""
        assert stack.alerts_topic is not None
        assert hasattr(stack.alerts_topic, "topic_arn")

    def test_exposes_dashboard(self, stack):
        """Stack should expose dashboard attribute."""
        assert stack.dashboard is not None

    def test_environment_name_stored(self, stack):
        """Stack should store environment name."""
        assert stack.environment_name == "dev"
