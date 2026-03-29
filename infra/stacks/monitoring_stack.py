"""Monitoring Stack for Pantry Pirate Radio.

Creates CloudWatch dashboards, alarms, and SNS topics for
operational monitoring and alerting.

Dashboard sections are implemented in monitoring_dashboard.py.
Alarm definitions are implemented in monitoring_alarms.py.
"""

from aws_cdk import Stack
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_logs as logs
from aws_cdk import aws_sns as sns
from constructs import Construct

from stacks.monitoring_alarms import create_alarms
from stacks.monitoring_dashboard import build_dashboard


class MonitoringStack(Stack):
    """Monitoring infrastructure for Pantry Pirate Radio.

    Creates:
    - SNS topic for alerts
    - CloudWatch dashboard for operational visibility
    - CloudWatch alarms for critical metrics

    Attributes:
        alerts_topic: SNS topic for alert notifications
        dashboard: CloudWatch dashboard
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        environment_name: str = "dev",
        worker_service_name: str | None = None,
        validator_service_name: str | None = None,
        reconciler_service_name: str | None = None,
        recorder_service_name: str | None = None,
        submarine_service_name: str | None = None,
        cluster_name: str | None = None,
        queue_name: str | None = None,
        validator_queue_name: str | None = None,
        reconciler_queue_name: str | None = None,
        recorder_queue_name: str | None = None,
        submarine_queue_name: str | None = None,
        submarine_staging_queue_name: str | None = None,
        submarine_extraction_queue_name: str | None = None,
        jobs_table_name: str | None = None,
        bedrock_model_id: str | None = None,
        alert_email: str | None = None,
        aurora_cluster_id: str | None = None,
        api_function_name: str | None = None,
        api_gateway_id: str | None = None,
        batcher_function_name: str | None = None,
        result_processor_function_name: str | None = None,
        staging_queue_name: str | None = None,
        content_index_table_name: str | None = None,
        geocoding_cache_table_name: str | None = None,
        state_machine_name: str | None = None,
        content_bucket_name: str | None = None,
        batch_bucket_name: str | None = None,
        exports_bucket_name: str | None = None,
        place_index_name: str | None = None,
        rds_proxy_name: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.environment_name = environment_name
        env = environment_name

        # ECS service names
        self.worker_service_name = (
            worker_service_name or f"pantry-pirate-radio-worker-{env}"
        )
        self.validator_service_name = (
            validator_service_name or f"pantry-pirate-radio-validator-{env}"
        )
        self.reconciler_service_name = (
            reconciler_service_name or f"pantry-pirate-radio-reconciler-{env}"
        )
        self.recorder_service_name = (
            recorder_service_name or f"pantry-pirate-radio-recorder-{env}"
        )
        self.submarine_service_name = (
            submarine_service_name or f"pantry-pirate-radio-submarine-{env}"
        )
        self.cluster_name = cluster_name or f"pantry-pirate-radio-{env}"

        # Queue names
        self.queue_name = queue_name or f"pantry-pirate-radio-llm-{env}.fifo"
        self.validator_queue_name = (
            validator_queue_name or f"pantry-pirate-radio-validator-{env}.fifo"
        )
        self.reconciler_queue_name = (
            reconciler_queue_name or f"pantry-pirate-radio-reconciler-{env}.fifo"
        )
        self.recorder_queue_name = (
            recorder_queue_name or f"pantry-pirate-radio-recorder-{env}.fifo"
        )
        self.submarine_queue_name = (
            submarine_queue_name or f"pantry-pirate-radio-submarine-{env}.fifo"
        )
        self.submarine_staging_queue_name = (
            submarine_staging_queue_name
            or f"pantry-pirate-radio-submarine-staging-{env}.fifo"
        )
        self.submarine_extraction_queue_name = (
            submarine_extraction_queue_name
            or f"pantry-pirate-radio-submarine-extraction-{env}.fifo"
        )
        self.staging_queue_name = (
            staging_queue_name or f"pantry-pirate-radio-staging-{env}.fifo"
        )

        # DynamoDB tables
        self.jobs_table_name = jobs_table_name or f"pantry-pirate-radio-jobs-{env}"
        self.content_index_table_name = (
            content_index_table_name or f"pantry-pirate-radio-content-index-{env}"
        )
        self.geocoding_cache_table_name = (
            geocoding_cache_table_name or f"pantry-pirate-radio-geocoding-cache-{env}"
        )

        # Lambda / API Gateway
        self.api_function_name = api_function_name or f"pantry-pirate-radio-api-{env}"
        self.api_gateway_id = api_gateway_id
        self.batcher_function_name = batcher_function_name
        self.result_processor_function_name = result_processor_function_name

        # Aurora
        self.aurora_cluster_id = aurora_cluster_id or f"pantry-pirate-radio-{env}"

        # RDS Proxy
        self.rds_proxy_name = rds_proxy_name or f"pantry-pirate-radio-proxy-{env}"

        # Step Functions
        self.state_machine_name = (
            state_machine_name or f"pantry-pirate-scraper-pipeline-{env}"
        )

        # Bedrock
        self.bedrock_model_id = (
            bedrock_model_id or "us.anthropic.claude-haiku-4-5-20251001-v1:0"
        )

        # S3 buckets
        self.content_bucket_name = (
            content_bucket_name or f"pantry-pirate-radio-content-{env}"
        )
        self.batch_bucket_name = batch_bucket_name or f"pantry-pirate-radio-batch-{env}"
        self.exports_bucket_name = (
            exports_bucket_name or f"pantry-pirate-radio-exports-{env}"
        )

        # Amazon Location Service
        self.place_index_name = (
            place_index_name or f"pantry-pirate-radio-geocoding-{env}"
        )

        # Submarine log-based metrics
        self._create_submarine_metric_filters(env)

        # Create SNS topic, dashboard, and alarms via extracted modules
        self.alerts_topic = self._create_alerts_topic(alert_email)
        self.dashboard = build_dashboard(self)
        create_alarms(self)

    def _create_submarine_metric_filters(self, env: str) -> None:
        """Create CloudWatch metric filters on submarine log events.

        Extracts operational metrics from structured log events emitted by
        the submarine worker, enabling dashboard graphs without code changes.
        """
        ns = "PantryPirateRadio/Submarine"
        log_group = logs.LogGroup.from_log_group_name(
            self,
            "SubmarineLogGroup",
            f"/ecs/pantry-pirate-radio/submarine-{env}",
        )

        filters = {
            "JobsStarted": "submarine_job_started",
            "JobsCompleted": "submarine_job_completed",
            "JobsNoData": "submarine_job_no_useful_data",
            "ContentNotFoodRelated": "submarine_content_not_food_related",
            "CrawlErrors": "submarine_crawl_error",
            "ExtractionErrors": "submarine_extraction_failed",
        }
        for metric_name, pattern in filters.items():
            logs.MetricFilter(
                self,
                f"Submarine{metric_name}Filter",
                log_group=log_group,
                filter_pattern=logs.FilterPattern.literal(pattern),
                metric_namespace=ns,
                metric_name=metric_name,
                metric_value="1",
                default_value=0,
            )

    def _create_alerts_topic(self, alert_email: str | None) -> sns.Topic:
        topic = sns.Topic(
            self,
            "AlertsTopic",
            topic_name=f"pantry-pirate-radio-alerts-{self.environment_name}",
            display_name=f"Pantry Pirate Radio Alerts ({self.environment_name})",
        )
        if alert_email:
            topic.add_subscription(sns.subscriptions.EmailSubscription(alert_email))
        return topic
