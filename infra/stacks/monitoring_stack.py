"""Monitoring Stack for Pantry Pirate Radio.

Creates CloudWatch dashboards, alarms, and SNS topics for
operational monitoring and alerting.
"""

from aws_cdk import Duration, Stack
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_cloudwatch_actions as cw_actions
from aws_cdk import aws_sns as sns
from constructs import Construct


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
        api_service_name: str | None = None,
        worker_service_name: str | None = None,
        validator_service_name: str | None = None,
        reconciler_service_name: str | None = None,
        recorder_service_name: str | None = None,
        cluster_name: str | None = None,
        queue_name: str | None = None,
        validator_queue_name: str | None = None,
        reconciler_queue_name: str | None = None,
        recorder_queue_name: str | None = None,
        jobs_table_name: str | None = None,
        bedrock_model_id: str | None = None,
        alert_email: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.environment_name = environment_name
        self.api_service_name = api_service_name or f"pantry-pirate-radio-api-{environment_name}"
        self.worker_service_name = worker_service_name or f"pantry-pirate-radio-worker-{environment_name}"
        self.validator_service_name = validator_service_name or f"pantry-pirate-radio-validator-{environment_name}"
        self.reconciler_service_name = reconciler_service_name or f"pantry-pirate-radio-reconciler-{environment_name}"
        self.recorder_service_name = recorder_service_name or f"pantry-pirate-radio-recorder-{environment_name}"
        self.cluster_name = cluster_name or f"pantry-pirate-radio-{environment_name}"
        self.queue_name = queue_name or f"pantry-pirate-radio-llm-{environment_name}.fifo"
        self.validator_queue_name = validator_queue_name or f"pantry-pirate-radio-validator-{environment_name}.fifo"
        self.reconciler_queue_name = reconciler_queue_name or f"pantry-pirate-radio-reconciler-{environment_name}.fifo"
        self.recorder_queue_name = recorder_queue_name or f"pantry-pirate-radio-recorder-{environment_name}.fifo"
        self.jobs_table_name = jobs_table_name or f"pantry-pirate-radio-jobs-{environment_name}"
        self.bedrock_model_id = bedrock_model_id or "us.anthropic.claude-haiku-4-5-20251001-v1:0"

        # Create SNS topic for alerts
        self.alerts_topic = self._create_alerts_topic(alert_email)

        # Create CloudWatch dashboard
        self.dashboard = self._create_dashboard()

        # Create alarms
        self._create_alarms()

    def _create_alerts_topic(self, alert_email: str | None) -> sns.Topic:
        """Create SNS topic for alert notifications."""
        topic = sns.Topic(
            self,
            "AlertsTopic",
            topic_name=f"pantry-pirate-radio-alerts-{self.environment_name}",
            display_name=f"Pantry Pirate Radio Alerts ({self.environment_name})",
        )

        if alert_email:
            topic.add_subscription(
                sns.subscriptions.EmailSubscription(alert_email)
            )

        return topic

    def _create_dashboard(self) -> cloudwatch.Dashboard:
        """Create CloudWatch dashboard for operational visibility."""
        dashboard = cloudwatch.Dashboard(
            self,
            "OperationalDashboard",
            dashboard_name=f"PantryPirateRadio-{self.environment_name}",
        )

        # Add API metrics row
        dashboard.add_widgets(
            cloudwatch.TextWidget(
                markdown="# API Service Metrics",
                width=24,
                height=1,
            )
        )

        dashboard.add_widgets(
            self._create_ecs_metric_widget("API CPU Utilization", "CPUUtilization", self.api_service_name),
            self._create_ecs_metric_widget("API Memory Utilization", "MemoryUtilization", self.api_service_name),
            self._create_api_request_count_widget(),
            self._create_api_response_time_widget(),
        )

        # Add Worker metrics row
        dashboard.add_widgets(
            cloudwatch.TextWidget(
                markdown="# Worker Service Metrics",
                width=24,
                height=1,
            )
        )

        dashboard.add_widgets(
            self._create_ecs_metric_widget("Worker CPU Utilization", "CPUUtilization", self.worker_service_name),
            self._create_ecs_metric_widget("Worker Memory Utilization", "MemoryUtilization", self.worker_service_name),
            self._create_queue_depth_widget(),
            self._create_queue_age_widget(),
        )

        # Add DynamoDB metrics row
        dashboard.add_widgets(
            cloudwatch.TextWidget(
                markdown="# Database Metrics",
                width=24,
                height=1,
            )
        )

        dashboard.add_widgets(
            self._create_dynamodb_read_widget(),
            self._create_dynamodb_write_widget(),
            self._create_dynamodb_throttle_widget(),
            self._create_dynamodb_errors_widget(),
        )

        # Add Bedrock LLM metrics row
        dashboard.add_widgets(
            cloudwatch.TextWidget(
                markdown="# Bedrock LLM Metrics",
                width=24,
                height=1,
            )
        )

        dashboard.add_widgets(
            self._create_bedrock_invocations_widget(),
            self._create_bedrock_latency_widget(),
            self._create_bedrock_token_cost_widget(),
            self._create_bedrock_errors_widget(),
        )

        # Add Auto-Scaling metrics row
        dashboard.add_widgets(
            cloudwatch.TextWidget(
                markdown="# Auto-Scaling Metrics",
                width=24,
                height=1,
            )
        )

        dashboard.add_widgets(
            self._create_scaling_widget("Worker Scaling", self.worker_service_name, self.queue_name),
            self._create_scaling_widget("Validator Scaling", self.validator_service_name, self.validator_queue_name),
            self._create_scaling_widget("Reconciler Scaling", self.reconciler_service_name, self.reconciler_queue_name),
            self._create_scaling_widget("Recorder Scaling", self.recorder_service_name, self.recorder_queue_name),
        )

        return dashboard

    def _create_ecs_metric_widget(
        self, title: str, metric_name: str, service_name: str,
    ) -> cloudwatch.GraphWidget:
        """Create ECS metric widget for a given service."""
        return cloudwatch.GraphWidget(
            title=title,
            width=6,
            height=6,
            left=[
                cloudwatch.Metric(
                    namespace="AWS/ECS",
                    metric_name=metric_name,
                    dimensions_map={
                        "ClusterName": self.cluster_name,
                        "ServiceName": service_name,
                    },
                    statistic="Average",
                    period=Duration.minutes(1),
                )
            ],
        )

    def _create_api_request_count_widget(self) -> cloudwatch.GraphWidget:
        """Create API request count widget."""
        return cloudwatch.GraphWidget(
            title="API Request Count",
            width=6,
            height=6,
            left=[
                cloudwatch.Metric(
                    namespace="AWS/ApplicationELB",
                    metric_name="RequestCount",
                    statistic="Sum",
                    period=Duration.minutes(1),
                )
            ],
        )

    def _create_api_response_time_widget(self) -> cloudwatch.GraphWidget:
        """Create API response time widget."""
        return cloudwatch.GraphWidget(
            title="API Response Time",
            width=6,
            height=6,
            left=[
                cloudwatch.Metric(
                    namespace="AWS/ApplicationELB",
                    metric_name="TargetResponseTime",
                    statistic="Average",
                    period=Duration.minutes(1),
                )
            ],
        )

    def _create_queue_depth_widget(self) -> cloudwatch.GraphWidget:
        """Create SQS queue depth widget."""
        return cloudwatch.GraphWidget(
            title="Queue Depth",
            width=6,
            height=6,
            left=[
                cloudwatch.Metric(
                    namespace="AWS/SQS",
                    metric_name="ApproximateNumberOfMessagesVisible",
                    dimensions_map={"QueueName": self.queue_name},
                    statistic="Average",
                    period=Duration.minutes(1),
                ),
                cloudwatch.Metric(
                    namespace="AWS/SQS",
                    metric_name="ApproximateNumberOfMessagesNotVisible",
                    dimensions_map={"QueueName": self.queue_name},
                    statistic="Average",
                    period=Duration.minutes(1),
                ),
            ],
        )

    def _create_queue_age_widget(self) -> cloudwatch.GraphWidget:
        """Create SQS oldest message age widget."""
        return cloudwatch.GraphWidget(
            title="Oldest Message Age",
            width=6,
            height=6,
            left=[
                cloudwatch.Metric(
                    namespace="AWS/SQS",
                    metric_name="ApproximateAgeOfOldestMessage",
                    dimensions_map={"QueueName": self.queue_name},
                    statistic="Maximum",
                    period=Duration.minutes(1),
                )
            ],
        )

    def _create_dynamodb_read_widget(self) -> cloudwatch.GraphWidget:
        """Create DynamoDB read capacity widget."""
        return cloudwatch.GraphWidget(
            title="DynamoDB Read Units",
            width=6,
            height=6,
            left=[
                cloudwatch.Metric(
                    namespace="AWS/DynamoDB",
                    metric_name="ConsumedReadCapacityUnits",
                    dimensions_map={"TableName": self.jobs_table_name},
                    statistic="Sum",
                    period=Duration.minutes(1),
                )
            ],
        )

    def _create_dynamodb_write_widget(self) -> cloudwatch.GraphWidget:
        """Create DynamoDB write capacity widget."""
        return cloudwatch.GraphWidget(
            title="DynamoDB Write Units",
            width=6,
            height=6,
            left=[
                cloudwatch.Metric(
                    namespace="AWS/DynamoDB",
                    metric_name="ConsumedWriteCapacityUnits",
                    dimensions_map={"TableName": self.jobs_table_name},
                    statistic="Sum",
                    period=Duration.minutes(1),
                )
            ],
        )

    def _create_dynamodb_throttle_widget(self) -> cloudwatch.GraphWidget:
        """Create DynamoDB throttled requests widget."""
        return cloudwatch.GraphWidget(
            title="DynamoDB Throttles",
            width=6,
            height=6,
            left=[
                cloudwatch.Metric(
                    namespace="AWS/DynamoDB",
                    metric_name="ThrottledRequests",
                    dimensions_map={"TableName": self.jobs_table_name},
                    statistic="Sum",
                    period=Duration.minutes(1),
                )
            ],
        )

    def _create_dynamodb_errors_widget(self) -> cloudwatch.GraphWidget:
        """Create DynamoDB errors widget."""
        return cloudwatch.GraphWidget(
            title="DynamoDB Errors",
            width=6,
            height=6,
            left=[
                cloudwatch.Metric(
                    namespace="AWS/DynamoDB",
                    metric_name="SystemErrors",
                    dimensions_map={"TableName": self.jobs_table_name},
                    statistic="Sum",
                    period=Duration.minutes(1),
                )
            ],
        )

    def _create_bedrock_invocations_widget(self) -> cloudwatch.GraphWidget:
        """Create Bedrock invocation count widget."""
        return cloudwatch.GraphWidget(
            title="Bedrock Invocations",
            width=6,
            height=6,
            left=[
                cloudwatch.Metric(
                    namespace="AWS/Bedrock",
                    metric_name="Invocations",
                    dimensions_map={"ModelId": self.bedrock_model_id},
                    statistic="Sum",
                    period=Duration.minutes(5),
                )
            ],
        )

    def _create_bedrock_latency_widget(self) -> cloudwatch.GraphWidget:
        """Create Bedrock invocation latency widget."""
        return cloudwatch.GraphWidget(
            title="Bedrock Latency",
            width=6,
            height=6,
            left=[
                cloudwatch.Metric(
                    namespace="AWS/Bedrock",
                    metric_name="InvocationLatency",
                    dimensions_map={"ModelId": self.bedrock_model_id},
                    statistic="Average",
                    period=Duration.minutes(5),
                ),
                cloudwatch.Metric(
                    namespace="AWS/Bedrock",
                    metric_name="InvocationLatency",
                    dimensions_map={"ModelId": self.bedrock_model_id},
                    statistic="p99",
                    period=Duration.minutes(5),
                ),
            ],
        )

    def _create_bedrock_token_cost_widget(self) -> cloudwatch.GraphWidget:
        """Create Bedrock token count and estimated cost widget."""
        input_tokens = cloudwatch.Metric(
            namespace="AWS/Bedrock",
            metric_name="InputTokenCount",
            dimensions_map={"ModelId": self.bedrock_model_id},
            statistic="Sum",
            period=Duration.minutes(5),
        )
        output_tokens = cloudwatch.Metric(
            namespace="AWS/Bedrock",
            metric_name="OutputTokenCount",
            dimensions_map={"ModelId": self.bedrock_model_id},
            statistic="Sum",
            period=Duration.minutes(5),
        )
        estimated_cost = cloudwatch.MathExpression(
            expression="(input * 0.80 / 1000000) + (output * 4.00 / 1000000)",
            using_metrics={"input": input_tokens, "output": output_tokens},
            label="Estimated Cost ($)",
            period=Duration.minutes(5),
        )
        return cloudwatch.GraphWidget(
            title="Bedrock Tokens & Cost",
            width=6,
            height=6,
            left=[input_tokens, output_tokens],
            right=[estimated_cost],
        )

    def _create_bedrock_errors_widget(self) -> cloudwatch.GraphWidget:
        """Create Bedrock errors and throttles widget."""
        return cloudwatch.GraphWidget(
            title="Bedrock Errors",
            width=6,
            height=6,
            left=[
                cloudwatch.Metric(
                    namespace="AWS/Bedrock",
                    metric_name="InvocationClientErrors",
                    dimensions_map={"ModelId": self.bedrock_model_id},
                    statistic="Sum",
                    period=Duration.minutes(5),
                ),
                cloudwatch.Metric(
                    namespace="AWS/Bedrock",
                    metric_name="InvocationServerErrors",
                    dimensions_map={"ModelId": self.bedrock_model_id},
                    statistic="Sum",
                    period=Duration.minutes(5),
                ),
                cloudwatch.Metric(
                    namespace="AWS/Bedrock",
                    metric_name="InvocationThrottles",
                    dimensions_map={"ModelId": self.bedrock_model_id},
                    statistic="Sum",
                    period=Duration.minutes(5),
                ),
            ],
        )

    def _create_scaling_widget(
        self, title: str, service_name: str, queue_name: str,
    ) -> cloudwatch.GraphWidget:
        """Create auto-scaling widget showing task count vs queue depth."""
        dims = {"ClusterName": self.cluster_name, "ServiceName": service_name}
        return cloudwatch.GraphWidget(
            title=title,
            width=6,
            height=6,
            left=[
                cloudwatch.Metric(
                    namespace="AWS/ECS",
                    metric_name="DesiredCount",
                    dimensions_map=dims,
                    statistic="Average",
                    period=Duration.minutes(1),
                ),
                cloudwatch.Metric(
                    namespace="AWS/ECS",
                    metric_name="RunningCount",
                    dimensions_map=dims,
                    statistic="Average",
                    period=Duration.minutes(1),
                ),
            ],
            right=[
                cloudwatch.Metric(
                    namespace="AWS/SQS",
                    metric_name="ApproximateNumberOfMessagesVisible",
                    dimensions_map={"QueueName": queue_name},
                    statistic="Sum",
                    period=Duration.minutes(1),
                ),
            ],
        )

    def _create_alarms(self) -> None:
        """Create CloudWatch alarms for critical metrics."""
        # API high CPU alarm
        api_cpu_alarm = cloudwatch.Alarm(
            self,
            "APICPUAlarm",
            alarm_name=f"pantry-pirate-radio-api-cpu-{self.environment_name}",
            alarm_description="API CPU utilization is high",
            metric=cloudwatch.Metric(
                namespace="AWS/ECS",
                metric_name="CPUUtilization",
                dimensions_map={
                    "ClusterName": self.cluster_name,
                    "ServiceName": self.api_service_name,
                },
                statistic="Average",
                period=Duration.minutes(5),
            ),
            threshold=80,
            evaluation_periods=3,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
        )
        api_cpu_alarm.add_alarm_action(cw_actions.SnsAction(self.alerts_topic))

        # Queue depth alarm (messages backing up)
        queue_depth_alarm = cloudwatch.Alarm(
            self,
            "QueueDepthAlarm",
            alarm_name=f"pantry-pirate-radio-queue-depth-{self.environment_name}",
            alarm_description="SQS queue depth is high - jobs are backing up",
            metric=cloudwatch.Metric(
                namespace="AWS/SQS",
                metric_name="ApproximateNumberOfMessagesVisible",
                dimensions_map={"QueueName": self.queue_name},
                statistic="Average",
                period=Duration.minutes(5),
            ),
            threshold=100,
            evaluation_periods=3,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
        )
        queue_depth_alarm.add_alarm_action(cw_actions.SnsAction(self.alerts_topic))

        # DLQ messages alarm (failed jobs)
        dlq_name = self.queue_name.replace(".fifo", "-dlq.fifo")
        dlq_alarm = cloudwatch.Alarm(
            self,
            "DLQAlarm",
            alarm_name=f"pantry-pirate-radio-dlq-{self.environment_name}",
            alarm_description="Messages in dead-letter queue - jobs are failing",
            metric=cloudwatch.Metric(
                namespace="AWS/SQS",
                metric_name="ApproximateNumberOfMessagesVisible",
                dimensions_map={"QueueName": dlq_name},
                statistic="Sum",
                period=Duration.minutes(5),
            ),
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
        )
        dlq_alarm.add_alarm_action(cw_actions.SnsAction(self.alerts_topic))

        # DynamoDB throttle alarm
        throttle_alarm = cloudwatch.Alarm(
            self,
            "DynamoDBThrottleAlarm",
            alarm_name=f"pantry-pirate-radio-dynamodb-throttle-{self.environment_name}",
            alarm_description="DynamoDB requests are being throttled",
            metric=cloudwatch.Metric(
                namespace="AWS/DynamoDB",
                metric_name="ThrottledRequests",
                dimensions_map={"TableName": self.jobs_table_name},
                statistic="Sum",
                period=Duration.minutes(5),
            ),
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
        )
        throttle_alarm.add_alarm_action(cw_actions.SnsAction(self.alerts_topic))

        # Bedrock throttle alarm
        bedrock_throttle_alarm = cloudwatch.Alarm(
            self,
            "BedrockThrottleAlarm",
            alarm_name=f"pantry-pirate-radio-bedrock-throttle-{self.environment_name}",
            alarm_description="Bedrock LLM invocations are being throttled",
            metric=cloudwatch.Metric(
                namespace="AWS/Bedrock",
                metric_name="InvocationThrottles",
                dimensions_map={"ModelId": self.bedrock_model_id},
                statistic="Sum",
                period=Duration.minutes(5),
            ),
            threshold=5,
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
        )
        bedrock_throttle_alarm.add_alarm_action(cw_actions.SnsAction(self.alerts_topic))
