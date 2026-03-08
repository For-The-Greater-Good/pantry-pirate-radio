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
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.environment_name = environment_name
        env = environment_name

        # ECS service names
        self.worker_service_name = worker_service_name or f"pantry-pirate-radio-worker-{env}"
        self.validator_service_name = validator_service_name or f"pantry-pirate-radio-validator-{env}"
        self.reconciler_service_name = reconciler_service_name or f"pantry-pirate-radio-reconciler-{env}"
        self.recorder_service_name = recorder_service_name or f"pantry-pirate-radio-recorder-{env}"
        self.cluster_name = cluster_name or f"pantry-pirate-radio-{env}"

        # Queue names
        self.queue_name = queue_name or f"pantry-pirate-radio-llm-{env}.fifo"
        self.validator_queue_name = validator_queue_name or f"pantry-pirate-radio-validator-{env}.fifo"
        self.reconciler_queue_name = reconciler_queue_name or f"pantry-pirate-radio-reconciler-{env}.fifo"
        self.recorder_queue_name = recorder_queue_name or f"pantry-pirate-radio-recorder-{env}.fifo"
        self.staging_queue_name = staging_queue_name or f"pantry-pirate-radio-staging-{env}.fifo"

        # DynamoDB tables
        self.jobs_table_name = jobs_table_name or f"pantry-pirate-radio-jobs-{env}"
        self.content_index_table_name = content_index_table_name or f"pantry-pirate-radio-content-index-{env}"
        self.geocoding_cache_table_name = geocoding_cache_table_name or f"pantry-pirate-radio-geocoding-cache-{env}"

        # Lambda / API Gateway
        self.api_function_name = api_function_name or f"pantry-pirate-radio-api-{env}"
        self.api_gateway_id = api_gateway_id
        self.batcher_function_name = batcher_function_name
        self.result_processor_function_name = result_processor_function_name

        # Aurora
        self.aurora_cluster_id = aurora_cluster_id or f"pantry-pirate-radio-{env}"

        # Step Functions
        self.state_machine_name = state_machine_name or f"pantry-pirate-scraper-pipeline-{env}"

        # Bedrock
        self.bedrock_model_id = bedrock_model_id or "us.anthropic.claude-haiku-4-5-20251001-v1:0"

        # S3 buckets
        self.content_bucket_name = content_bucket_name or f"pantry-pirate-radio-content-{env}"
        self.batch_bucket_name = batch_bucket_name or f"pantry-pirate-radio-batch-{env}"
        self.exports_bucket_name = exports_bucket_name or f"pantry-pirate-radio-exports-{env}"

        # Amazon Location Service
        self.place_index_name = place_index_name or f"pantry-pirate-radio-geocoding-{env}"

        self.alerts_topic = self._create_alerts_topic(alert_email)
        self.dashboard = self._create_dashboard()
        self._create_alarms()

    # --- Generic helpers ---

    def _m(
        self, ns: str, name: str, dims: dict, stat: str = "Sum", period: Duration = Duration.minutes(5),
    ) -> cloudwatch.Metric:
        return cloudwatch.Metric(
            namespace=ns, metric_name=name, dimensions_map=dims, statistic=stat, period=period,
        )

    def _graph(
        self,
        title: str,
        left: list,
        right: list | None = None,
        width: int = 6,
    ) -> cloudwatch.GraphWidget:
        kw: dict = {"title": title, "width": width, "height": 6, "left": left}
        if right:
            kw["right"] = right
        return cloudwatch.GraphWidget(**kw)

    def _section(self, title: str) -> cloudwatch.TextWidget:
        return cloudwatch.TextWidget(markdown=f"# {title}", width=24, height=1)

    def _alarm(
        self,
        cid: str,
        name: str,
        metric: cloudwatch.Metric,
        threshold: float,
        periods: int,
        op: cloudwatch.ComparisonOperator,
        description: str,
        datapoints_to_alarm: int | None = None,
        treat_missing_data: cloudwatch.TreatMissingData | None = None,
    ) -> cloudwatch.Alarm:
        kw: dict = {
            "alarm_name": name, "alarm_description": description,
            "metric": metric, "threshold": threshold,
            "evaluation_periods": periods, "comparison_operator": op,
        }
        if datapoints_to_alarm is not None:
            kw["datapoints_to_alarm"] = datapoints_to_alarm
        if treat_missing_data is not None:
            kw["treat_missing_data"] = treat_missing_data
        alarm = cloudwatch.Alarm(self, cid, **kw)
        alarm.add_alarm_action(cw_actions.SnsAction(self.alerts_topic))
        return alarm

    # --- Alerts topic ---

    def _create_alerts_topic(self, alert_email: str | None) -> sns.Topic:
        topic = sns.Topic(
            self, "AlertsTopic",
            topic_name=f"pantry-pirate-radio-alerts-{self.environment_name}",
            display_name=f"Pantry Pirate Radio Alerts ({self.environment_name})",
        )
        if alert_email:
            topic.add_subscription(sns.subscriptions.EmailSubscription(alert_email))
        return topic

    # --- Dashboard ---

    def _create_dashboard(self) -> cloudwatch.Dashboard:
        db = cloudwatch.Dashboard(
            self, "OperationalDashboard",
            dashboard_name=f"PantryPirateRadio-{self.environment_name}",
        )

        self._add_lambda_api_section(db)
        self._add_worker_section(db)
        self._add_sqs_queues_section(db)
        self._add_pipeline_section(db)
        self._add_aurora_section(db)
        self._add_dynamodb_section(db)
        self._add_bedrock_section(db)
        if self.batcher_function_name:
            self._add_batch_inference_section(db)
        self._add_geocoding_section(db)
        self._add_autoscaling_section(db)
        self._add_s3_section(db)

        return db

    # --- Section 1: Lambda API ---

    def _add_lambda_api_section(self, db: cloudwatch.Dashboard) -> None:
        fn_dims = {"FunctionName": self.api_function_name}
        ns = "AWS/Lambda"
        p1 = Duration.minutes(1)

        invocations = self._m(ns, "Invocations", fn_dims, "Sum", p1)
        duration_avg = self._m(ns, "Duration", fn_dims, "Average", p1)
        duration_p99 = self._m(ns, "Duration", fn_dims, "p99", p1)
        errors = self._m(ns, "Errors", fn_dims, "Sum", p1)
        throttles = self._m(ns, "Throttles", fn_dims, "Sum", p1)
        cold_starts = self._m(ns, "ConcurrentExecutions", fn_dims, "Maximum", p1)

        left_errors: list = [errors, throttles]
        if self.api_gateway_id:
            gw_dims = {"ApiId": self.api_gateway_id}
            gw = "AWS/ApiGateway"
            left_errors.append(self._m(gw, "4xx", gw_dims, "Sum", p1))
            left_errors.append(self._m(gw, "5xx", gw_dims, "Sum", p1))

        db.add_widgets(self._section("Lambda API"))
        db.add_widgets(
            self._graph("API Invocations", [invocations]),
            self._graph("API Duration", [duration_avg, duration_p99]),
            self._graph("API Errors & Throttles", left_errors),
            self._graph("API Cold Starts", [cold_starts]),
        )

    # --- Section 2: ECS Services ---

    def _add_worker_section(self, db: cloudwatch.Dashboard) -> None:
        p1 = Duration.minutes(1)
        ns = "AWS/ECS"
        services = {
            "Worker": self.worker_service_name,
            "Validator": self.validator_service_name,
            "Reconciler": self.reconciler_service_name,
            "Recorder": self.recorder_service_name,
        }

        cpu_metrics = [
            self._m(ns, "CPUUtilization", {"ClusterName": self.cluster_name, "ServiceName": svc}, "Average", p1)
            for svc in services.values()
        ]
        mem_metrics = [
            self._m(ns, "MemoryUtilization", {"ClusterName": self.cluster_name, "ServiceName": svc}, "Average", p1)
            for svc in services.values()
        ]

        db.add_widgets(self._section("ECS Services"))
        db.add_widgets(
            self._graph("Service CPU %", cpu_metrics, width=12),
            self._graph("Service Memory %", mem_metrics, width=12),
        )

    # --- Section 3: SQS Queues ---

    def _add_sqs_queues_section(self, db: cloudwatch.Dashboard) -> None:
        p1 = Duration.minutes(1)
        ns = "AWS/SQS"

        queues = [
            ("LLM", self.queue_name),
            ("Staging", self.staging_queue_name),
            ("Validator", self.validator_queue_name),
            ("Reconciler", self.reconciler_queue_name),
            ("Recorder", self.recorder_queue_name),
        ]

        db.add_widgets(self._section("SQS Queues"))

        # Per-queue depth graphs: visible + not-visible, DLQ on right axis
        queue_widgets = []
        for label, qname in queues:
            dlq_name = qname.replace(".fifo", "-dlq.fifo")
            queue_widgets.append(self._graph(
                f"{label}",
                left=[
                    self._m(ns, "ApproximateNumberOfMessagesVisible", {"QueueName": qname}, "Sum", p1),
                    self._m(ns, "ApproximateNumberOfMessagesNotVisible", {"QueueName": qname}, "Sum", p1),
                ],
                right=[
                    self._m(ns, "ApproximateNumberOfMessagesVisible", {"QueueName": dlq_name}, "Sum", p1),
                ],
            ))

        # Queue ages (all on one graph)
        queue_widgets.append(self._graph(
            "Oldest Message Age",
            left=[
                self._m(ns, "ApproximateAgeOfOldestMessage", {"QueueName": qname}, "Maximum", p1)
                for _, qname in queues
            ],
        ))

        db.add_widgets(*queue_widgets)

    # --- Section 4: Pipeline Overview ---

    def _add_pipeline_section(self, db: cloudwatch.Dashboard) -> None:
        queues = [
            self.queue_name, self.staging_queue_name,
            self.validator_queue_name, self.reconciler_queue_name, self.recorder_queue_name,
        ]
        dlqs = [q.replace(".fifo", "-dlq.fifo") for q in queues]

        queue_depths = [
            self._m("AWS/SQS", "ApproximateNumberOfMessagesVisible", {"QueueName": q}, "Sum")
            for q in queues
        ]
        dlq_depths = [
            self._m("AWS/SQS", "ApproximateNumberOfMessagesVisible", {"QueueName": d}, "Sum")
            for d in dlqs
        ]

        sm_arn = f"arn:aws:states:{self.region}:{self.account}:stateMachine:{self.state_machine_name}"
        sm_dims = {"StateMachineArn": sm_arn}

        db.add_widgets(self._section("Pipeline Overview"))
        db.add_widgets(
            self._graph("All Queue Depths", queue_depths),
            self._graph("Dead Letter Queues", dlq_depths),
            self._graph("Step Functions Executions", [
                self._m("AWS/States", "ExecutionsStarted", sm_dims),
                self._m("AWS/States", "ExecutionsSucceeded", sm_dims),
                self._m("AWS/States", "ExecutionsFailed", sm_dims),
            ]),
            self._graph("Step Functions Duration", [
                self._m("AWS/States", "ExecutionTime", sm_dims, "Average"),
                self._m("AWS/States", "ExecutionTime", sm_dims, "p99"),
            ]),
        )

    # --- Section 4: Aurora Database ---

    def _add_aurora_section(self, db: cloudwatch.Dashboard) -> None:
        dims = {"DBClusterIdentifier": self.aurora_cluster_id}
        ns = "AWS/RDS"

        db.add_widgets(self._section("Aurora Database"))
        db.add_widgets(
            self._graph("Aurora ACU", [self._m(ns, "ServerlessDatabaseCapacity", dims, "Average")]),
            self._graph("DB Connections", [self._m(ns, "DatabaseConnections", dims, "Average")]),
            self._graph("DB Throughput", [
                self._m(ns, "CommitThroughput", dims), self._m(ns, "SelectThroughput", dims),
            ]),
            self._graph("DB Storage", [self._m(ns, "VolumeBytesUsed", dims, "Average")]),
        )

    # --- Section 5: DynamoDB Tables ---

    def _add_dynamodb_section(self, db: cloudwatch.Dashboard) -> None:
        tables = [self.jobs_table_name, self.content_index_table_name, self.geocoding_cache_table_name]
        ns = "AWS/DynamoDB"

        def multi(metric_name: str, stat: str = "Sum") -> list:
            return [self._m(ns, metric_name, {"TableName": t}, stat) for t in tables]

        db.add_widgets(self._section("DynamoDB Tables"))
        db.add_widgets(
            self._graph("DynamoDB Reads", multi("ConsumedReadCapacityUnits")),
            self._graph("DynamoDB Writes", multi("ConsumedWriteCapacityUnits")),
            self._graph("DynamoDB Throttles", multi("ThrottledRequests")),
            self._graph("DynamoDB Errors", multi("SystemErrors")),
        )

    # --- Section 6: Bedrock LLM ---

    def _add_bedrock_section(self, db: cloudwatch.Dashboard) -> None:
        dims = {"ModelId": self.bedrock_model_id}
        ns = "AWS/Bedrock"

        input_tokens = self._m(ns, "InputTokenCount", dims)
        output_tokens = self._m(ns, "OutputTokenCount", dims)
        cost = cloudwatch.MathExpression(
            expression="(input * 0.80 / 1000000) + (output * 4.00 / 1000000)",
            using_metrics={"input": input_tokens, "output": output_tokens},
            label="Estimated Cost ($)", period=Duration.minutes(5),
        )

        db.add_widgets(self._section("Bedrock LLM"))
        db.add_widgets(
            self._graph("Bedrock Invocations & Latency", [
                self._m(ns, "Invocations", dims), self._m(ns, "InvocationLatency", dims, "Average"),
                self._m(ns, "InvocationLatency", dims, "p99"),
            ]),
            self._graph("Bedrock Tokens & Cost", [input_tokens, output_tokens], [cost]),
            self._graph("Bedrock Errors & Throttles", [
                self._m(ns, "InvocationClientErrors", dims),
                self._m(ns, "InvocationServerErrors", dims),
                self._m(ns, "InvocationThrottles", dims),
            ]),
        )

    # --- Section 7: Batch Inference (conditional) ---

    def _add_batch_inference_section(self, db: cloudwatch.Dashboard) -> None:
        ns = "AWS/Lambda"
        b_dims = {"FunctionName": self.batcher_function_name}
        r_dims = {"FunctionName": self.result_processor_function_name}

        db.add_widgets(self._section("Batch Inference Lambdas"))
        db.add_widgets(
            self._graph("Batcher Invocations", [
                self._m(ns, "Invocations", b_dims), self._m(ns, "Errors", b_dims),
            ]),
            self._graph("Batcher Duration", [
                self._m(ns, "Duration", b_dims, "Average"), self._m(ns, "Duration", b_dims, "p99"),
            ]),
            self._graph("Result Processor Invocations", [
                self._m(ns, "Invocations", r_dims), self._m(ns, "Errors", r_dims),
            ]),
            self._graph("Result Processor Duration", [
                self._m(ns, "Duration", r_dims, "Average"), self._m(ns, "Duration", r_dims, "p99"),
            ]),
        )

    # --- Section 8: Geocoding (Amazon Location Service) ---

    def _add_geocoding_section(self, db: cloudwatch.Dashboard) -> None:
        dims = {"IndexName": self.place_index_name}
        ns = "AWS/Location"
        p5 = Duration.minutes(5)

        db.add_widgets(self._section("Geocoding (Amazon Location Service)"))
        db.add_widgets(
            self._graph("Geocoding Requests", [self._m(ns, "CallCount", dims, "Sum", p5)]),
            self._graph("Geocoding Latency", [
                self._m(ns, "CallLatency", dims, "Average", p5),
                self._m(ns, "CallLatency", dims, "p99", p5),
            ]),
            self._graph("Geocoding Errors", [
                self._m(ns, "ClientErrorCount", dims, "Sum", p5),
                self._m(ns, "ServerErrorCount", dims, "Sum", p5),
            ]),
        )

    # --- Section 9: Auto-Scaling ---

    def _add_autoscaling_section(self, db: cloudwatch.Dashboard) -> None:
        db.add_widgets(self._section("Auto-Scaling"))
        db.add_widgets(
            self._scaling_widget("Worker Scaling", self.worker_service_name, self.queue_name),
            self._scaling_widget("Validator Scaling", self.validator_service_name, self.validator_queue_name),
            self._scaling_widget("Reconciler Scaling", self.reconciler_service_name, self.reconciler_queue_name),
            self._scaling_widget("Recorder Scaling", self.recorder_service_name, self.recorder_queue_name),
        )

    def _scaling_widget(self, title: str, service_name: str, queue_name: str) -> cloudwatch.GraphWidget:
        dims = {"ClusterName": self.cluster_name, "ServiceName": service_name}
        p1 = Duration.minutes(1)
        return self._graph(
            title,
            left=[
                self._m("AWS/ECS", "DesiredCount", dims, "Average", p1),
                self._m("AWS/ECS", "RunningCount", dims, "Average", p1),
            ],
            right=[self._m("AWS/SQS", "ApproximateNumberOfMessagesVisible", {"QueueName": queue_name}, "Sum", p1)],
        )

    # --- Section 9: S3 Storage ---

    def _add_s3_section(self, db: cloudwatch.Dashboard) -> None:
        ns = "AWS/S3"
        day = Duration.days(1)

        def bucket_metrics(bucket_name: str) -> list:
            return [
                self._m(ns, "NumberOfObjects", {"BucketName": bucket_name, "StorageType": "AllStorageTypes"}, "Average", day),
                self._m(ns, "BucketSizeBytes", {"BucketName": bucket_name, "StorageType": "StandardStorage"}, "Average", day),
            ]

        db.add_widgets(self._section("S3 Storage"))
        db.add_widgets(
            self._graph("Content Bucket", bucket_metrics(self.content_bucket_name)),
            self._graph("Batch Bucket", bucket_metrics(self.batch_bucket_name)),
            self._graph("Exports Bucket", bucket_metrics(self.exports_bucket_name)),
        )

    # --- Alarms ---

    def _create_alarms(self) -> None:
        env = self.environment_name
        GT = cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD
        GTE = cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD
        NB = cloudwatch.TreatMissingData.NOT_BREACHING
        ppr = "pantry-pirate-radio"
        sqs_visible = "ApproximateNumberOfMessagesVisible"
        api_dims = {"FunctionName": self.api_function_name}

        # 1-2. API Lambda errors & throttles
        self._alarm("APILambdaErrorsAlarm", f"{ppr}-api-lambda-errors-{env}",
                     self._m("AWS/Lambda", "Errors", api_dims), 5, 2, GTE,
                     "API Lambda function errors are elevated")
        self._alarm("APILambdaThrottleAlarm", f"{ppr}-api-lambda-throttle-{env}",
                     self._m("AWS/Lambda", "Throttles", api_dims), 1, 2, GTE,
                     "API Lambda function is being throttled")

        # 3. LLM queue depth
        self._alarm("QueueDepthAlarm", f"{ppr}-queue-depth-{env}",
                     self._m("AWS/SQS", sqs_visible, {"QueueName": self.queue_name}, "Average"),
                     100, 3, GT, "SQS queue depth is high - jobs are backing up")

        # 4-5. DLQ alarms (LLM + staging)
        for cid, label, qname in [
            ("DLQAlarm", "dlq", self.queue_name),
            ("StagingDLQAlarm", "staging-dlq", self.staging_queue_name),
            ("ValidatorDLQAlarm", "validator-dlq", self.validator_queue_name),
            ("ReconcilerDLQAlarm", "reconciler-dlq", self.reconciler_queue_name),
            ("RecorderDLQAlarm", "recorder-dlq", self.recorder_queue_name),
        ]:
            dlq = qname.replace(".fifo", "-dlq.fifo")
            self._alarm(cid, f"{ppr}-{label}-{env}",
                         self._m("AWS/SQS", sqs_visible, {"QueueName": dlq}),
                         1, 1, GTE, f"Messages in {label.replace('-', ' ')}")

        # Result processor DLQ (standard, not FIFO)
        self._alarm("ResultProcessorDLQAlarm", f"{ppr}-result-processor-dlq-{env}",
                     self._m("AWS/SQS", sqs_visible, {"QueueName": f"{ppr}-result-processor-dlq-{env}"}),
                     1, 1, GTE, "Messages in result processor dead-letter queue")

        # 6. DynamoDB throttle (jobs table)
        self._alarm("DynamoDBThrottleAlarm", f"{ppr}-dynamodb-throttle-{env}",
                     self._m("AWS/DynamoDB", "ThrottledRequests", {"TableName": self.jobs_table_name}),
                     1, 1, GTE, "DynamoDB requests are being throttled")

        # 7. Bedrock throttle
        self._alarm("BedrockThrottleAlarm", f"{ppr}-bedrock-throttle-{env}",
                     self._m("AWS/Bedrock", "InvocationThrottles", {"ModelId": self.bedrock_model_id}),
                     5, 2, GT, "Bedrock LLM invocations are being throttled")

        # 8. Aurora ACU high — 75% of max
        acu_threshold = 1.5 if env == "dev" else 14
        self._alarm("AuroraACUAlarm", f"{ppr}-aurora-acu-high-{env}",
                     self._m("AWS/RDS", "ServerlessDatabaseCapacity",
                             {"DBClusterIdentifier": self.aurora_cluster_id}, "Average"),
                     acu_threshold, 3, GT, f"Aurora ACU usage above {acu_threshold} (75% of max)")

        # 9. Pipeline failure
        sm_arn = f"arn:aws:states:{self.region}:{self.account}:stateMachine:{self.state_machine_name}"
        self._alarm("PipelineFailureAlarm", f"{ppr}-pipeline-failure-{env}",
                     self._m("AWS/States", "ExecutionsFailed", {"StateMachineArn": sm_arn}),
                     1, 1, GTE, "Step Functions pipeline execution failed")

        # 14. Amazon Location Service errors
        self._alarm("LocationServiceErrorAlarm", f"{ppr}-location-service-errors-{env}",
                     self._m("AWS/Location", "ClientErrorCount", {"IndexName": self.place_index_name}),
                     10, 2, GTE, "Amazon Location Service geocoding errors are elevated")

        # H1-H8: Fargate CPU/Memory (ECS/ContainerInsights)
        for label, svc in [("Worker", self.worker_service_name),
                           ("Validator", self.validator_service_name),
                           ("Reconciler", self.reconciler_service_name),
                           ("Recorder", self.recorder_service_name)]:
            dims = {"ClusterName": self.cluster_name, "ServiceName": svc}
            slug = label.lower()
            for suffix, metric in [("cpu-high", "CpuUtilized"), ("memory-high", "MemoryUtilized")]:
                kind = "CPU" if "cpu" in suffix else "memory"
                self._alarm(f"{label}{kind.title()}Alarm", f"ppr-{env}-{slug}-{suffix}",
                             self._m("ECS/ContainerInsights", metric, dims, "Average"),
                             80, 5, GTE, f"{label} Fargate {kind} utilization above 80%",
                             datapoints_to_alarm=3, treat_missing_data=NB)

        # H9-H12: Lambda Error/Throttle (conditional)
        for fn_name, cid_prefix, label in [
            (self.batcher_function_name, "BatcherLambda", "batcher-lambda"),
            (self.result_processor_function_name, "ResultProcessorLambda", "result-processor-lambda"),
        ]:
            if not fn_name:
                continue
            fn_dims = {"FunctionName": fn_name}
            self._alarm(f"{cid_prefix}ErrorsAlarm", f"ppr-{env}-{label}-errors",
                         self._m("AWS/Lambda", "Errors", fn_dims), 5, 1, GTE,
                         f"{cid_prefix.replace('Lambda', ' Lambda')} errors are elevated")
            self._alarm(f"{cid_prefix}ThrottleAlarm", f"ppr-{env}-{label}-throttle",
                         self._m("AWS/Lambda", "Throttles", fn_dims), 1, 1, GTE,
                         f"{cid_prefix.replace('Lambda', ' Lambda')} is being throttled")

        # H13-H16: DynamoDB Throttle/Error (content_index + geocoding_cache)
        for label, slug, tbl in [("ContentIndex", "content-index", self.content_index_table_name),
                                  ("GeocodingCache", "geocoding-cache", self.geocoding_cache_table_name)]:
            t_dims = {"TableName": tbl}
            self._alarm(f"{label}ThrottleAlarm", f"ppr-{env}-{slug}-throttle",
                         self._m("AWS/DynamoDB", "ThrottledRequests", t_dims),
                         1, 1, GTE, f"DynamoDB {label} table requests are being throttled")
            self._alarm(f"{label}SystemErrorAlarm", f"ppr-{env}-{slug}-system-errors",
                         self._m("AWS/DynamoDB", "SystemErrors", t_dims),
                         1, 1, GTE, f"DynamoDB {label} table has system errors")

        # H17-H20: Queue depth (validator, reconciler, recorder, staging)
        for label, qname in [("Validator", self.validator_queue_name),
                              ("Reconciler", self.reconciler_queue_name),
                              ("Recorder", self.recorder_queue_name),
                              ("Staging", self.staging_queue_name)]:
            self._alarm(f"{label}QueueDepthAlarm", f"ppr-{env}-{label.lower()}-queue-depth",
                         self._m("AWS/SQS", sqs_visible, {"QueueName": qname}, "Average"),
                         100, 3, GT, f"{label} queue depth is high - jobs are backing up")
