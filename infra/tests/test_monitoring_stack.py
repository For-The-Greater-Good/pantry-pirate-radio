"""Tests for MonitoringStack CDK stack."""

import aws_cdk as cdk
import pytest
from aws_cdk import assertions

from stacks.monitoring_stack import MonitoringStack


class TestMonitoringStackResources:
    """Tests for MonitoringStack resource creation."""

    @pytest.fixture
    def app(self):
        return cdk.App()

    @pytest.fixture
    def stack(self, app):
        return MonitoringStack(app, "TestMonitoringStack", environment_name="dev")

    @pytest.fixture
    def template(self, stack):
        return assertions.Template.from_stack(stack)

    def test_creates_sns_topic(self, template):
        template.resource_count_is("AWS::SNS::Topic", 1)

    def test_creates_dashboard(self, template):
        template.resource_count_is("AWS::CloudWatch::Dashboard", 1)

    def test_creates_alarms(self, template):
        # 30 alarms without conditional Lambdas:
        # 14 original + 8 Fargate CPU/Memory + 4 DynamoDB table + 4 queue depth
        template.resource_count_is("AWS::CloudWatch::Alarm", 30)

    def test_sns_topic_has_name(self, template):
        template.has_resource_properties(
            "AWS::SNS::Topic",
            {"TopicName": "pantry-pirate-radio-alerts-dev"},
        )

    def test_dashboard_has_name(self, template):
        template.has_resource_properties(
            "AWS::CloudWatch::Dashboard",
            {"DashboardName": "PantryPirateRadio-dev"},
        )


class TestMonitoringStackAlarms:
    """Tests for alarm configuration."""

    @pytest.fixture
    def app(self):
        return cdk.App()

    @pytest.fixture
    def stack(self, app):
        return MonitoringStack(app, "AlarmStack", environment_name="dev")

    @pytest.fixture
    def template(self, stack):
        return assertions.Template.from_stack(stack)

    def test_api_lambda_errors_alarm_exists(self, template):
        template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            {
                "AlarmName": "pantry-pirate-radio-api-lambda-errors-dev",
                "MetricName": "Errors",
                "Namespace": "AWS/Lambda",
            },
        )

    def test_api_lambda_throttle_alarm_exists(self, template):
        template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            {
                "AlarmName": "pantry-pirate-radio-api-lambda-throttle-dev",
                "MetricName": "Throttles",
                "Namespace": "AWS/Lambda",
            },
        )

    def test_queue_depth_alarm_exists(self, template):
        template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            {
                "AlarmName": "pantry-pirate-radio-queue-depth-dev",
                "MetricName": "ApproximateNumberOfMessagesVisible",
                "Namespace": "AWS/SQS",
            },
        )

    def test_dlq_alarm_exists(self, template):
        template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            {"AlarmName": "pantry-pirate-radio-dlq-dev"},
        )

    def test_staging_dlq_alarm_exists(self, template):
        template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            {"AlarmName": "pantry-pirate-radio-staging-dlq-dev"},
        )

    def test_dynamodb_throttle_alarm_exists(self, template):
        template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            {
                "AlarmName": "pantry-pirate-radio-dynamodb-throttle-dev",
                "MetricName": "ThrottledRequests",
                "Namespace": "AWS/DynamoDB",
            },
        )

    def test_bedrock_throttle_alarm_exists(self, template):
        template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            {
                "AlarmName": "pantry-pirate-radio-bedrock-throttle-dev",
                "MetricName": "InvocationThrottles",
                "Namespace": "AWS/Bedrock",
            },
        )

    def test_aurora_acu_alarm_exists(self, template):
        template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            {
                "AlarmName": "pantry-pirate-radio-aurora-acu-high-dev",
                "MetricName": "ServerlessDatabaseCapacity",
                "Namespace": "AWS/RDS",
            },
        )

    def test_aurora_acu_dev_threshold(self, template):
        template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            {
                "AlarmName": "pantry-pirate-radio-aurora-acu-high-dev",
                "Threshold": 1.5,
            },
        )

    def test_aurora_acu_prod_threshold(self):
        app = cdk.App()
        stack = MonitoringStack(app, "ProdACUStack", environment_name="prod")
        template = assertions.Template.from_stack(stack)
        template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            {
                "AlarmName": "pantry-pirate-radio-aurora-acu-high-prod",
                "Threshold": 1.5,
            },
        )

    def test_pipeline_failure_alarm_exists(self, template):
        template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            {
                "AlarmName": "pantry-pirate-radio-pipeline-failure-dev",
                "MetricName": "ExecutionsFailed",
                "Namespace": "AWS/States",
            },
        )

    def test_validator_dlq_alarm_exists(self, template):
        template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            {
                "AlarmName": "pantry-pirate-radio-validator-dlq-dev",
                "MetricName": "ApproximateNumberOfMessagesVisible",
                "Namespace": "AWS/SQS",
            },
        )

    def test_reconciler_dlq_alarm_exists(self, template):
        template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            {
                "AlarmName": "pantry-pirate-radio-reconciler-dlq-dev",
                "MetricName": "ApproximateNumberOfMessagesVisible",
                "Namespace": "AWS/SQS",
            },
        )

    def test_recorder_dlq_alarm_exists(self, template):
        template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            {
                "AlarmName": "pantry-pirate-radio-recorder-dlq-dev",
                "MetricName": "ApproximateNumberOfMessagesVisible",
                "Namespace": "AWS/SQS",
            },
        )

    def test_result_processor_dlq_alarm_exists(self, template):
        template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            {
                "AlarmName": "pantry-pirate-radio-result-processor-dlq-dev",
                "MetricName": "ApproximateNumberOfMessagesVisible",
                "Namespace": "AWS/SQS",
            },
        )

    def test_location_service_error_alarm_exists(self, template):
        template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            {
                "AlarmName": "pantry-pirate-radio-location-service-errors-dev",
                "MetricName": "ErrorCount",
                "Namespace": "AWS/Location",
            },
        )

    # --- H1-H8: Fargate CPU/Memory alarms ---

    @pytest.mark.parametrize(
        "service", ["worker", "validator", "reconciler", "recorder"]
    )
    def test_fargate_cpu_alarm_exists(self, template, service):
        template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            {
                "AlarmName": f"ppr-dev-{service}-cpu-high",
                "MetricName": "CpuUtilized",
                "Namespace": "ECS/ContainerInsights",
                "Threshold": 80,
                "EvaluationPeriods": 5,
                "DatapointsToAlarm": 3,
            },
        )

    @pytest.mark.parametrize(
        "service", ["worker", "validator", "reconciler", "recorder"]
    )
    def test_fargate_memory_alarm_exists(self, template, service):
        template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            {
                "AlarmName": f"ppr-dev-{service}-memory-high",
                "MetricName": "MemoryUtilized",
                "Namespace": "ECS/ContainerInsights",
                "Threshold": 80,
                "EvaluationPeriods": 5,
                "DatapointsToAlarm": 3,
            },
        )

    # --- H13-H16: DynamoDB Throttle/Error alarms ---

    @pytest.mark.parametrize("table_slug", ["content-index", "geocoding-cache"])
    def test_dynamodb_table_throttle_alarm_exists(self, template, table_slug):
        template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            {
                "AlarmName": f"ppr-dev-{table_slug}-throttle",
                "MetricName": "ThrottledRequests",
                "Namespace": "AWS/DynamoDB",
            },
        )

    @pytest.mark.parametrize("table_slug", ["content-index", "geocoding-cache"])
    def test_dynamodb_table_system_error_alarm_exists(self, template, table_slug):
        template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            {
                "AlarmName": f"ppr-dev-{table_slug}-system-errors",
                "MetricName": "SystemErrors",
                "Namespace": "AWS/DynamoDB",
            },
        )

    # --- H17-H20: Queue depth alarms ---

    @pytest.mark.parametrize(
        "queue_slug", ["validator", "reconciler", "recorder", "staging"]
    )
    def test_service_queue_depth_alarm_exists(self, template, queue_slug):
        template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            {
                "AlarmName": f"ppr-dev-{queue_slug}-queue-depth",
                "MetricName": "ApproximateNumberOfMessagesVisible",
                "Namespace": "AWS/SQS",
                "Threshold": 100,
                "EvaluationPeriods": 3,
            },
        )

    def test_alarms_have_actions(self, template):
        alarms = template.find_resources("AWS::CloudWatch::Alarm")
        for name, alarm in alarms.items():
            props = alarm.get("Properties", {})
            assert "AlarmActions" in props, f"Alarm {name} should have AlarmActions"


class TestMonitoringStackConfiguration:
    """Tests for monitoring stack configuration options."""

    @pytest.fixture
    def app(self):
        return cdk.App()

    def test_custom_service_names(self, app):
        stack = MonitoringStack(
            app,
            "CustomNamesStack",
            environment_name="prod",
            worker_service_name="custom-worker",
            cluster_name="custom-cluster",
            queue_name="custom-queue.fifo",
            jobs_table_name="custom-jobs-table",
            bedrock_model_id="custom-model-id",
            api_function_name="custom-api-fn",
            aurora_cluster_id="custom-cluster-id",
            state_machine_name="custom-state-machine",
            content_bucket_name="custom-content-bucket",
        )

        assert stack.worker_service_name == "custom-worker"
        assert stack.cluster_name == "custom-cluster"
        assert stack.queue_name == "custom-queue.fifo"
        assert stack.jobs_table_name == "custom-jobs-table"
        assert stack.bedrock_model_id == "custom-model-id"
        assert stack.api_function_name == "custom-api-fn"
        assert stack.aurora_cluster_id == "custom-cluster-id"
        assert stack.state_machine_name == "custom-state-machine"
        assert stack.content_bucket_name == "custom-content-bucket"

    def test_default_parameter_values(self, app):
        stack = MonitoringStack(app, "DefaultsStack", environment_name="dev")

        assert stack.api_function_name == "pantry-pirate-radio-api-dev"
        assert stack.aurora_cluster_id == "pantry-pirate-radio-dev"
        assert stack.state_machine_name == "pantry-pirate-scraper-pipeline-dev"
        assert stack.staging_queue_name == "pantry-pirate-radio-staging-dev.fifo"
        assert stack.content_index_table_name == "pantry-pirate-radio-content-index-dev"
        assert (
            stack.geocoding_cache_table_name
            == "pantry-pirate-radio-geocoding-cache-dev"
        )
        assert stack.content_bucket_name == "pantry-pirate-radio-content-dev"
        assert stack.batch_bucket_name == "pantry-pirate-radio-batch-dev"
        assert stack.exports_bucket_name == "pantry-pirate-radio-exports-dev"
        assert stack.place_index_name == "pantry-pirate-radio-geocoding-dev"

    def test_prod_environment_name(self, app):
        stack = MonitoringStack(app, "ProdStack", environment_name="prod")
        template = assertions.Template.from_stack(stack)
        template.has_resource_properties(
            "AWS::SNS::Topic",
            {"TopicName": "pantry-pirate-radio-alerts-prod"},
        )

    def test_batch_inference_section_conditional(self, app):
        """Batch inference section only renders when batcher_function_name provided."""
        stack_without = MonitoringStack(
            app,
            "NoBatchStack",
            environment_name="dev",
        )
        stack_with = MonitoringStack(
            app,
            "WithBatchStack",
            environment_name="dev",
            batcher_function_name="my-batcher",
            result_processor_function_name="my-processor",
        )
        # Both should synth without error
        assertions.Template.from_stack(stack_without)
        assertions.Template.from_stack(stack_with)

    def test_lambda_alarms_conditional(self):
        """Lambda error/throttle alarms only created when function names provided."""
        app_without = cdk.App()
        stack_without = MonitoringStack(
            app_without, "NoLambdaAlarmStack", environment_name="dev"
        )
        tmpl_without = assertions.Template.from_stack(stack_without)
        tmpl_without.resource_count_is("AWS::CloudWatch::Alarm", 30)

        app_with = cdk.App()
        stack_with = MonitoringStack(
            app_with,
            "WithLambdaAlarmStack",
            environment_name="dev",
            batcher_function_name="my-batcher",
            result_processor_function_name="my-processor",
        )
        tmpl_with = assertions.Template.from_stack(stack_with)
        # 30 base + 4 Lambda alarms (2 per function)
        tmpl_with.resource_count_is("AWS::CloudWatch::Alarm", 34)

    def test_batcher_lambda_error_alarm(self, app):
        stack = MonitoringStack(
            app,
            "BatcherErrorStack",
            environment_name="dev",
            batcher_function_name="my-batcher",
            result_processor_function_name="my-processor",
        )
        template = assertions.Template.from_stack(stack)
        template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            {"AlarmName": "ppr-dev-batcher-lambda-errors", "Namespace": "AWS/Lambda"},
        )

    def test_result_processor_lambda_throttle_alarm(self, app):
        stack = MonitoringStack(
            app,
            "RPThrottleStack",
            environment_name="dev",
            batcher_function_name="my-batcher",
            result_processor_function_name="my-processor",
        )
        template = assertions.Template.from_stack(stack)
        template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            {
                "AlarmName": "ppr-dev-result-processor-lambda-throttle",
                "Namespace": "AWS/Lambda",
            },
        )


class TestMonitoringStackBedrock:
    """Tests for Bedrock LLM metrics configuration."""

    @pytest.fixture
    def app(self):
        return cdk.App()

    def test_default_bedrock_model_id(self, app):
        stack = MonitoringStack(app, "DefaultBedrockStack", environment_name="dev")
        assert stack.bedrock_model_id == "us.anthropic.claude-haiku-4-5-20251001-v1:0"

    def test_custom_bedrock_model_id(self, app):
        stack = MonitoringStack(
            app,
            "CustomBedrockStack",
            environment_name="dev",
            bedrock_model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
        )
        assert stack.bedrock_model_id == "us.anthropic.claude-sonnet-4-20250514-v1:0"

    def test_bedrock_throttle_alarm_has_action(self, app):
        stack = MonitoringStack(app, "BedrockAlarmStack", environment_name="dev")
        template = assertions.Template.from_stack(stack)
        template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            {
                "AlarmName": "pantry-pirate-radio-bedrock-throttle-dev",
                "AlarmActions": assertions.Match.any_value(),
            },
        )


class TestMonitoringStackAutoScaling:
    """Tests for auto-scaling metrics configuration."""

    @pytest.fixture
    def app(self):
        return cdk.App()

    @pytest.fixture
    def stack(self, app):
        return MonitoringStack(app, "ScalingStack", environment_name="dev")

    def test_default_scaling_service_names(self, stack):
        assert stack.validator_service_name == "pantry-pirate-radio-validator-dev"
        assert stack.reconciler_service_name == "pantry-pirate-radio-reconciler-dev"
        assert stack.recorder_service_name == "pantry-pirate-radio-recorder-dev"

    def test_default_scaling_queue_names(self, stack):
        assert stack.validator_queue_name == "pantry-pirate-radio-validator-dev.fifo"
        assert stack.reconciler_queue_name == "pantry-pirate-radio-reconciler-dev.fifo"
        assert stack.recorder_queue_name == "pantry-pirate-radio-recorder-dev.fifo"

    def test_custom_scaling_service_names(self, app):
        stack = MonitoringStack(
            app,
            "CustomScalingStack",
            environment_name="dev",
            validator_service_name="custom-validator",
            reconciler_service_name="custom-reconciler",
            recorder_service_name="custom-recorder",
            validator_queue_name="custom-validator.fifo",
            reconciler_queue_name="custom-reconciler.fifo",
            recorder_queue_name="custom-recorder.fifo",
        )
        assert stack.validator_service_name == "custom-validator"
        assert stack.reconciler_service_name == "custom-reconciler"
        assert stack.recorder_service_name == "custom-recorder"
        assert stack.validator_queue_name == "custom-validator.fifo"
        assert stack.reconciler_queue_name == "custom-reconciler.fifo"
        assert stack.recorder_queue_name == "custom-recorder.fifo"


class TestMonitoringStackAttributes:
    """Tests for MonitoringStack attributes."""

    @pytest.fixture
    def app(self):
        return cdk.App()

    @pytest.fixture
    def stack(self, app):
        return MonitoringStack(app, "AttrStack", environment_name="dev")

    def test_exposes_alerts_topic(self, stack):
        assert stack.alerts_topic is not None
        assert hasattr(stack.alerts_topic, "topic_arn")

    def test_exposes_dashboard(self, stack):
        assert stack.dashboard is not None

    def test_environment_name_stored(self, stack):
        assert stack.environment_name == "dev"
