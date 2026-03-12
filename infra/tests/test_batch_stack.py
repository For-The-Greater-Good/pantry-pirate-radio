"""Tests for BatchInferenceStack CDK stack."""

import json

import aws_cdk as cdk
import pytest
from aws_cdk import assertions

from stacks.batch_stack import BatchInferenceStack
from stacks.compute_stack import ComputeStack
from stacks.ecr_stack import ECRStack
from stacks.queue_stack import QueueStack
from stacks.storage_stack import StorageStack


class TestBatchInferenceStackResources:
    """Tests for BatchInferenceStack resource creation."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def dependent_stacks(self, app):
        """Create dependency stacks."""
        storage = StorageStack(app, "TestStorageStack", environment_name="dev")
        queues = QueueStack(app, "TestQueueStack", environment_name="dev")
        compute = ComputeStack(app, "TestComputeStack", environment_name="dev")
        ecr = ECRStack(app, "TestECRStack", environment_name="dev")
        return storage, queues, compute, ecr

    @pytest.fixture
    def stack(self, app, dependent_stacks):
        """Create BatchInferenceStack for testing."""
        storage, queues, compute, ecr = dependent_stacks
        return BatchInferenceStack(
            app,
            "TestBatchStack",
            environment_name="dev",
            content_bucket=storage.content_bucket,
            jobs_table=storage.jobs_table,
            llm_queue=queues.llm_queue,
            validator_queue=queues.validator_queue,
            reconciler_queue=queues.reconciler_queue,
            recorder_queue=queues.recorder_queue,
            vpc=compute.vpc,
            ecr_repository=ecr.repositories.get("batch-lambda"),
        )

    @pytest.fixture
    def template(self, stack):
        """Get CloudFormation template from stack."""
        return assertions.Template.from_stack(stack)

    def test_creates_staging_queue_and_dlq(self, template):
        """Should create staging FIFO queue, its DLQ, and result processor DLQ."""
        # 2 FIFO (staging + staging DLQ) + 1 standard (result processor DLQ)
        template.resource_count_is("AWS::SQS::Queue", 3)
        template.has_resource_properties(
            "AWS::SQS::Queue",
            {
                "FifoQueue": True,
                "ContentBasedDeduplication": True,
                "VisibilityTimeout": 300,
            },
        )

    def test_creates_batch_io_bucket(self, template):
        """Should create S3 bucket for batch I/O with lifecycle rules."""
        template.has_resource_properties(
            "AWS::S3::Bucket",
            {
                "LifecycleConfiguration": assertions.Match.object_like(
                    {
                        "Rules": assertions.Match.array_with(
                            [
                                assertions.Match.object_like(
                                    {
                                        "ExpirationInDays": 7,
                                        "Status": "Enabled",
                                    }
                                ),
                            ]
                        ),
                    }
                ),
            },
        )

    def test_creates_bedrock_service_role(self, template):
        """Should create IAM role for Bedrock batch with correct trust policy."""
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
                                        "Effect": "Allow",
                                        "Principal": {
                                            "Service": "bedrock.amazonaws.com",
                                        },
                                    }
                                ),
                            ]
                        ),
                    }
                ),
            },
        )

    def test_creates_batcher_lambda(self, template):
        """Should create Batcher Lambda with 4 GB ephemeral storage for streaming."""
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {
                "PackageType": "Image",
                "Timeout": 900,
                "MemorySize": 1024,
                "EphemeralStorage": {"Size": 4096},
            },
        )

    def test_creates_result_processor_lambda(self, template):
        """Should create Result Processor Lambda with 4 GB ephemeral storage for streaming."""
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {
                "PackageType": "Image",
                "Timeout": 900,
                "MemorySize": 1769,
                "EphemeralStorage": {"Size": 4096},
                "DeadLetterConfig": assertions.Match.any_value(),
            },
        )

    def test_creates_lambdas(self, template):
        """Should create 2 app Lambdas + CDK auto-delete Custom Resource Lambdas."""
        # Batcher: 4 GB ephemeral storage for streaming temp files
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {
                "PackageType": "Image",
                "Timeout": 900,
                "MemorySize": 1024,
                "EphemeralStorage": {"Size": 4096},
            },
        )
        # Result Processor: 4 GB ephemeral storage + DLQ config
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {
                "PackageType": "Image",
                "Timeout": 900,
                "MemorySize": 1769,
                "EphemeralStorage": {"Size": 4096},
                "DeadLetterConfig": assertions.Match.any_value(),
            },
        )

    def test_creates_eventbridge_rule(self, template):
        """Should create EventBridge rule for batch job state changes."""
        template.has_resource_properties(
            "AWS::Events::Rule",
            {
                "EventPattern": assertions.Match.object_like(
                    {
                        "source": ["aws.bedrock"],
                        "detail-type": ["Batch Inference Job State Change"],
                    }
                ),
            },
        )

    def test_service_role_no_overly_broad_permissions(self, template):
        """Service role should not have Resource: * on sensitive actions."""
        raw = template.to_json()
        for resource_id, resource in raw["Resources"].items():
            if resource["Type"] != "AWS::IAM::Policy":
                continue
            policy_doc = resource["Properties"].get("PolicyDocument", {})
            for statement in policy_doc.get("Statement", []):
                actions = statement.get("Action", [])
                if isinstance(actions, str):
                    actions = [actions]
                # bedrock:InvokeModel should NOT have Resource: *
                if "bedrock:InvokeModel" in actions:
                    resources = statement.get("Resource", [])
                    if isinstance(resources, str):
                        resources = [resources]
                    assert (
                        "*" not in resources
                    ), "bedrock:InvokeModel should not have Resource: *"


class TestBatchInferenceStackLogging:
    """Tests for Lambda log group configuration."""

    @pytest.fixture
    def app(self):
        return cdk.App()

    @pytest.fixture
    def template(self, app):
        storage = StorageStack(app, "LogStorageStack", environment_name="dev")
        queues = QueueStack(app, "LogQueueStack", environment_name="dev")
        compute = ComputeStack(app, "LogComputeStack", environment_name="dev")
        ecr = ECRStack(app, "LogECRStack", environment_name="dev")
        stack = BatchInferenceStack(
            app,
            "LogBatchStack",
            environment_name="dev",
            content_bucket=storage.content_bucket,
            jobs_table=storage.jobs_table,
            llm_queue=queues.llm_queue,
            validator_queue=queues.validator_queue,
            reconciler_queue=queues.reconciler_queue,
            recorder_queue=queues.recorder_queue,
            vpc=compute.vpc,
            ecr_repository=ecr.repositories.get("batch-lambda"),
        )
        return assertions.Template.from_stack(stack)

    def test_batcher_log_group_has_explicit_name(self, template):
        """Batcher Lambda log group should have an explicit name for discoverability."""
        template.has_resource_properties(
            "AWS::Logs::LogGroup",
            {
                "LogGroupName": "/aws/lambda/pantry-pirate-radio-batcher-dev",
                "RetentionInDays": 7,
            },
        )

    def test_result_processor_log_group_has_explicit_name(self, template):
        """Result Processor Lambda log group should have an explicit name."""
        template.has_resource_properties(
            "AWS::Logs::LogGroup",
            {
                "LogGroupName": "/aws/lambda/pantry-pirate-radio-result-processor-dev",
                "RetentionInDays": 7,
            },
        )


class TestBatchInferenceStackTracing:
    """Tests for X-Ray tracing on batch Lambdas."""

    @pytest.fixture
    def app(self):
        return cdk.App()

    @pytest.fixture
    def template(self, app):
        storage = StorageStack(app, "TracingStorageStack", environment_name="dev")
        queues = QueueStack(app, "TracingQueueStack", environment_name="dev")
        compute = ComputeStack(app, "TracingComputeStack", environment_name="dev")
        ecr = ECRStack(app, "TracingECRStack", environment_name="dev")
        stack = BatchInferenceStack(
            app,
            "TracingBatchStack",
            environment_name="dev",
            content_bucket=storage.content_bucket,
            jobs_table=storage.jobs_table,
            llm_queue=queues.llm_queue,
            validator_queue=queues.validator_queue,
            reconciler_queue=queues.reconciler_queue,
            recorder_queue=queues.recorder_queue,
            vpc=compute.vpc,
            ecr_repository=ecr.repositories.get("batch-lambda"),
        )
        return assertions.Template.from_stack(stack)

    def test_batcher_lambda_has_xray_tracing(self, template):
        """Batcher Lambda should have X-Ray tracing enabled."""
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {
                "PackageType": "Image",
                "Timeout": 900,
                "MemorySize": 1024,
                "EphemeralStorage": {"Size": 4096},
                "TracingConfig": {"Mode": "Active"},
            },
        )

    def test_result_processor_lambda_has_xray_tracing(self, template):
        """Result Processor Lambda should have X-Ray tracing enabled."""
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {
                "PackageType": "Image",
                "Timeout": 900,
                "MemorySize": 1769,
                "EphemeralStorage": {"Size": 4096},
                "TracingConfig": {"Mode": "Active"},
            },
        )


class TestBatchInferenceStackAttributes:
    """Tests for stack attributes."""

    @pytest.fixture
    def app(self):
        return cdk.App()

    @pytest.fixture
    def stack(self, app):
        storage = StorageStack(app, "AttrStorageStack", environment_name="dev")
        queues = QueueStack(app, "AttrQueueStack", environment_name="dev")
        compute = ComputeStack(app, "AttrComputeStack", environment_name="dev")
        ecr = ECRStack(app, "AttrECRStack", environment_name="dev")
        return BatchInferenceStack(
            app,
            "AttrBatchStack",
            environment_name="dev",
            content_bucket=storage.content_bucket,
            jobs_table=storage.jobs_table,
            llm_queue=queues.llm_queue,
            validator_queue=queues.validator_queue,
            reconciler_queue=queues.reconciler_queue,
            recorder_queue=queues.recorder_queue,
            vpc=compute.vpc,
            ecr_repository=ecr.repositories.get("batch-lambda"),
        )

    def test_exposes_staging_queue(self, stack):
        """Stack should expose staging queue."""
        assert stack.staging_queue is not None

    def test_exposes_batcher_lambda(self, stack):
        """Stack should expose batcher Lambda."""
        assert stack.batcher_lambda is not None

    def test_exposes_batch_bucket(self, stack):
        """Stack should expose batch I/O bucket."""
        assert stack.batch_bucket is not None

    def test_exposes_staging_queue_url(self, stack):
        """Stack should expose staging queue URL."""
        assert stack.staging_queue.queue_url is not None
