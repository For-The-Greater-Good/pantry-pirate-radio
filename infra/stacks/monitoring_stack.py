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
        cluster_name: str | None = None,
        queue_name: str | None = None,
        jobs_table_name: str | None = None,
        alert_email: str | None = None,
        **kwargs,
    ) -> None:
        """Initialize MonitoringStack.

        Args:
            scope: CDK scope
            construct_id: Unique identifier for this construct
            environment_name: Environment name (dev, staging, prod)
            api_service_name: Name of API ECS service
            worker_service_name: Name of worker ECS service
            cluster_name: Name of ECS cluster
            queue_name: Name of SQS queue
            jobs_table_name: Name of DynamoDB jobs table
            alert_email: Email address for alerts (optional)
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        self.environment_name = environment_name
        self.api_service_name = api_service_name or f"pantry-pirate-radio-api-{environment_name}"
        self.worker_service_name = worker_service_name or f"pantry-pirate-radio-worker-{environment_name}"
        self.cluster_name = cluster_name or f"pantry-pirate-radio-{environment_name}"
        self.queue_name = queue_name or f"pantry-pirate-radio-llm-{environment_name}.fifo"
        self.jobs_table_name = jobs_table_name or f"pantry-pirate-radio-jobs-{environment_name}"

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
            self._create_api_cpu_widget(),
            self._create_api_memory_widget(),
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
            self._create_worker_cpu_widget(),
            self._create_worker_memory_widget(),
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

        return dashboard

    def _create_api_cpu_widget(self) -> cloudwatch.GraphWidget:
        """Create API CPU utilization widget."""
        return cloudwatch.GraphWidget(
            title="API CPU Utilization",
            width=6,
            height=6,
            left=[
                cloudwatch.Metric(
                    namespace="AWS/ECS",
                    metric_name="CPUUtilization",
                    dimensions_map={
                        "ClusterName": self.cluster_name,
                        "ServiceName": self.api_service_name,
                    },
                    statistic="Average",
                    period=Duration.minutes(1),
                )
            ],
        )

    def _create_api_memory_widget(self) -> cloudwatch.GraphWidget:
        """Create API memory utilization widget."""
        return cloudwatch.GraphWidget(
            title="API Memory Utilization",
            width=6,
            height=6,
            left=[
                cloudwatch.Metric(
                    namespace="AWS/ECS",
                    metric_name="MemoryUtilization",
                    dimensions_map={
                        "ClusterName": self.cluster_name,
                        "ServiceName": self.api_service_name,
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

    def _create_worker_cpu_widget(self) -> cloudwatch.GraphWidget:
        """Create worker CPU utilization widget."""
        return cloudwatch.GraphWidget(
            title="Worker CPU Utilization",
            width=6,
            height=6,
            left=[
                cloudwatch.Metric(
                    namespace="AWS/ECS",
                    metric_name="CPUUtilization",
                    dimensions_map={
                        "ClusterName": self.cluster_name,
                        "ServiceName": self.worker_service_name,
                    },
                    statistic="Average",
                    period=Duration.minutes(1),
                )
            ],
        )

    def _create_worker_memory_widget(self) -> cloudwatch.GraphWidget:
        """Create worker memory utilization widget."""
        return cloudwatch.GraphWidget(
            title="Worker Memory Utilization",
            width=6,
            height=6,
            left=[
                cloudwatch.Metric(
                    namespace="AWS/ECS",
                    metric_name="MemoryUtilization",
                    dimensions_map={
                        "ClusterName": self.cluster_name,
                        "ServiceName": self.worker_service_name,
                    },
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
