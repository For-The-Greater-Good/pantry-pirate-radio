"""Tests for QueueStack CDK stack."""

import aws_cdk as cdk
import pytest
from aws_cdk import assertions

from stacks.queue_stack import QueueStack


class TestQueueStackResources:
    """Tests for QueueStack resource creation."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def stack(self, app):
        """Create stack for testing."""
        return QueueStack(app, "TestQueueStack", environment_name="dev")

    @pytest.fixture
    def template(self, stack):
        """Get CloudFormation template from stack."""
        return assertions.Template.from_stack(stack)

    def test_creates_fourteen_sqs_queues(self, template):
        """QueueStack should create 7 queues + 7 DLQs."""
        # LLM, Validator, Reconciler, Recorder, Submarine, Submarine-Staging, Submarine-Extraction + their DLQs
        template.resource_count_is("AWS::SQS::Queue", 14)

    def test_main_queue_is_fifo(self, template):
        """Main queue should be a FIFO queue."""
        template.has_resource_properties(
            "AWS::SQS::Queue",
            {
                "FifoQueue": True,
                "ContentBasedDeduplication": True,
            },
        )

    def test_main_queue_has_visibility_timeout(self, template):
        """Main queue should have configured visibility timeout."""
        template.has_resource_properties(
            "AWS::SQS::Queue",
            {
                "VisibilityTimeout": 600,  # Default 10 minutes
            },
        )

    def test_main_queue_has_dlq_configured(self, template):
        """Main queue should have dead-letter queue configured."""
        template.has_resource_properties(
            "AWS::SQS::Queue",
            {
                "RedrivePolicy": assertions.Match.object_like(
                    {
                        "maxReceiveCount": 3,
                    }
                ),
            },
        )

    def test_dlq_has_retention_period(self, template):
        """DLQ should have 14 day retention period."""
        # 14 days = 1209600 seconds
        template.has_resource_properties(
            "AWS::SQS::Queue",
            {
                "MessageRetentionPeriod": 1209600,
            },
        )


class TestQueueStackConfiguration:
    """Tests for QueueStack configuration options."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    def test_custom_max_receive_count(self, app):
        """Stack should accept custom max receive count."""
        stack = QueueStack(
            app,
            "CustomMaxReceiveStack",
            environment_name="dev",
            max_receive_count=5,
        )
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::SQS::Queue",
            {
                "RedrivePolicy": assertions.Match.object_like(
                    {
                        "maxReceiveCount": 5,
                    }
                ),
            },
        )


class TestQueueStackAttributes:
    """Tests for QueueStack attributes."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def stack(self, app):
        """Create stack for testing."""
        return QueueStack(app, "AttrTestStack", environment_name="dev")

    def test_exposes_llm_queue(self, stack):
        """Stack should expose llm_queue attribute."""
        assert stack.llm_queue is not None
        assert hasattr(stack.llm_queue, "queue_name")

    def test_exposes_dlq(self, stack):
        """Stack should expose dlq attribute."""
        assert stack.dlq is not None
        assert hasattr(stack.dlq, "queue_name")

    def test_exposes_validator_queue(self, stack):
        """Stack should expose validator_queue attribute."""
        assert stack.validator_queue is not None
        assert hasattr(stack.validator_queue, "queue_name")

    def test_exposes_validator_dlq(self, stack):
        """Stack should expose validator_dlq attribute."""
        assert stack.validator_dlq is not None
        assert hasattr(stack.validator_dlq, "queue_name")

    def test_exposes_reconciler_queue(self, stack):
        """Stack should expose reconciler_queue attribute."""
        assert stack.reconciler_queue is not None
        assert hasattr(stack.reconciler_queue, "queue_name")

    def test_exposes_reconciler_dlq(self, stack):
        """Stack should expose reconciler_dlq attribute."""
        assert stack.reconciler_dlq is not None
        assert hasattr(stack.reconciler_dlq, "queue_name")

    def test_exposes_recorder_queue(self, stack):
        """Stack should expose recorder_queue attribute."""
        assert stack.recorder_queue is not None
        assert hasattr(stack.recorder_queue, "queue_name")

    def test_exposes_recorder_dlq(self, stack):
        """Stack should expose recorder_dlq attribute."""
        assert stack.recorder_dlq is not None
        assert hasattr(stack.recorder_dlq, "queue_name")

    def test_environment_name_stored(self, stack):
        """Stack should store environment name."""
        assert stack.environment_name == "dev"

    def test_queue_urls_property_has_all_queues(self, stack):
        """queue_urls property should contain all queue URLs."""
        urls = stack.queue_urls
        assert "llm" in urls
        assert "validator" in urls
        assert "reconciler" in urls
        assert "recorder" in urls
        assert "submarine" in urls
        assert "submarine-staging" in urls
        assert "submarine-extraction" in urls
        assert len(urls) == 7

    def test_queue_urls_are_not_empty(self, stack):
        """queue_urls should contain actual queue URL values."""
        urls = stack.queue_urls
        # Token values won't be actual URLs but should exist
        assert urls["llm"] is not None
        assert urls["validator"] is not None
        assert urls["reconciler"] is not None
        assert urls["recorder"] is not None
        assert urls["submarine"] is not None
