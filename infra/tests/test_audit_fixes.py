"""CDK tests for infrastructure audit fixes (C4, M1).

C4: Reconciler deployment constrained to single instance during deployments
M1: Recorder visibility timeout increased to 300s
"""

import aws_cdk as cdk
import pytest
from aws_cdk import assertions

from stacks.compute_stack import ComputeStack
from stacks.queue_stack import QueueStack
from stacks.services_stack import ServicesStack


class TestC4ReconcilerDeploymentConstraint:
    """C4: Reconciler must not run concurrent instances during deployment."""

    @pytest.fixture
    def app(self):
        return cdk.App()

    @pytest.fixture
    def template(self, app):
        compute = ComputeStack(app, "C4Compute", environment_name="dev")
        stack = ServicesStack(
            app,
            "C4Services",
            environment_name="dev",
            vpc=compute.vpc,
            cluster=compute.cluster,
        )
        return assertions.Template.from_stack(stack)

    def test_reconciler_has_max_healthy_percent_100(self, template):
        """Reconciler service should have MaximumPercent=100 to prevent concurrent instances."""
        template.has_resource_properties(
            "AWS::ECS::Service",
            {
                "ServiceName": assertions.Match.string_like_regexp(".*reconciler.*"),
                "DeploymentConfiguration": assertions.Match.object_like(
                    {
                        "MaximumPercent": 100,
                        "MinimumHealthyPercent": 0,
                    }
                ),
            },
        )

    def test_all_services_have_circuit_breaker(self, template):
        """All Fargate services should have deployment circuit breaker with rollback."""
        # There are 3 services: validator, reconciler, recorder
        services = template.find_resources(
            "AWS::ECS::Service",
        )
        for _logical_id, resource in services.items():
            props = resource.get("Properties", {})
            deployment_config = props.get("DeploymentConfiguration", {})
            circuit_breaker = deployment_config.get("DeploymentCircuitBreaker", {})
            assert (
                circuit_breaker.get("Enable") is True
            ), f"Service {_logical_id} missing circuit breaker"
            assert (
                circuit_breaker.get("Rollback") is True
            ), f"Service {_logical_id} missing circuit breaker rollback"


class TestM1RecorderVisibilityTimeout:
    """M1: Recorder queue visibility timeout should be 300s."""

    @pytest.fixture
    def app(self):
        return cdk.App()

    @pytest.fixture
    def template(self, app):
        stack = QueueStack(app, "M1Queues", environment_name="dev")
        return assertions.Template.from_stack(stack)

    def test_recorder_queue_has_300s_visibility(self, template):
        """Recorder queue should have 300s visibility timeout (increased from 120s)."""
        template.has_resource_properties(
            "AWS::SQS::Queue",
            {
                "QueueName": assertions.Match.string_like_regexp(
                    ".*recorder.*dev\\.fifo"
                ),
                "VisibilityTimeout": 300,
            },
        )

    def test_reconciler_queue_still_300s(self, template):
        """Reconciler queue should still have 300s visibility (unchanged)."""
        template.has_resource_properties(
            "AWS::SQS::Queue",
            {
                "QueueName": assertions.Match.string_like_regexp(
                    ".*reconciler.*dev\\.fifo"
                ),
                "VisibilityTimeout": 300,
            },
        )

    def test_llm_queue_still_600s(self, template):
        """LLM queue should still have 600s visibility (unchanged)."""
        template.has_resource_properties(
            "AWS::SQS::Queue",
            {
                "QueueName": assertions.Match.string_like_regexp(
                    "pantry-pirate-radio-llm-dev\\.fifo"
                ),
                "VisibilityTimeout": 600,
            },
        )


class TestC2BatcherDlqPermissions:
    """C2: Batcher Lambda should have permission to send to staging DLQ."""

    @pytest.fixture
    def app(self):
        return cdk.App()

    @pytest.fixture
    def template(self, app):
        from stacks.batch_stack import BatchInferenceStack
        from stacks.storage_stack import StorageStack

        compute = ComputeStack(app, "C2Compute", environment_name="dev")
        queue_stack = QueueStack(app, "C2Queues", environment_name="dev")
        storage = StorageStack(app, "C2Storage", environment_name="dev")
        batch = BatchInferenceStack(
            app,
            "C2Batch",
            environment_name="dev",
            llm_queue=queue_stack.llm_queue,
            validator_queue=queue_stack.validator_queue,
            reconciler_queue=queue_stack.reconciler_queue,
            recorder_queue=queue_stack.recorder_queue,
            jobs_table=storage.jobs_table,
            content_bucket=storage.content_bucket,
            vpc=compute.vpc,
        )
        return assertions.Template.from_stack(batch)

    def test_batcher_lambda_has_staging_dlq_url_env(self, template):
        """Batcher Lambda should have STAGING_DLQ_URL environment variable."""
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {
                "Environment": assertions.Match.object_like(
                    {
                        "Variables": assertions.Match.object_like(
                            {
                                "STAGING_DLQ_URL": assertions.Match.any_value(),
                            }
                        )
                    }
                )
            },
        )
