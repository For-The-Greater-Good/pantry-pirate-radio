"""CloudWatch alarms for Pantry Pirate Radio.

Extracted from MonitoringStack._create_alarms() to keep the monitoring
stack under the 600-line limit.  All alarms fire to the stack's SNS
alerts topic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aws_cdk import Duration
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_cloudwatch_actions as cw_actions

if TYPE_CHECKING:
    from stacks.monitoring_stack import MonitoringStack

# ── Comparison / missing-data shorthands ───────────────────────────
GT = cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD
GTE = cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD
NB = cloudwatch.TreatMissingData.NOT_BREACHING


# ── Helpers ────────────────────────────────────────────────────────


def metric(
    ns: str,
    name: str,
    dims: dict,
    stat: str = "Sum",
    period: Duration = Duration.minutes(5),
) -> cloudwatch.Metric:
    """Create a CloudWatch ``Metric`` — matches the dashboard helper signature."""
    return cloudwatch.Metric(
        namespace=ns,
        metric_name=name,
        dimensions_map=dims,
        statistic=stat,
        period=period,
    )


def alarm(
    stack: MonitoringStack,
    cid: str,
    name: str,
    m: cloudwatch.Metric,
    threshold: float,
    periods: int,
    op: cloudwatch.ComparisonOperator,
    description: str,
    *,
    datapoints_to_alarm: int | None = None,
    treat_missing_data: cloudwatch.TreatMissingData | None = None,
) -> cloudwatch.Alarm:
    """Create a CloudWatch alarm wired to the stack's SNS topic."""
    kw: dict = {
        "alarm_name": name,
        "alarm_description": description,
        "metric": m,
        "threshold": threshold,
        "evaluation_periods": periods,
        "comparison_operator": op,
    }
    if datapoints_to_alarm is not None:
        kw["datapoints_to_alarm"] = datapoints_to_alarm
    if treat_missing_data is not None:
        kw["treat_missing_data"] = treat_missing_data
    a = cloudwatch.Alarm(stack, cid, **kw)
    a.add_alarm_action(cw_actions.SnsAction(stack.alerts_topic))
    return a


def _derive_dlq_name(queue_name: str, env: str) -> str:
    """Derive DLQ name from main queue name.

    QueueStack creates DLQs as ``...-{name}-dlq-{env}.fifo``
    (e.g. ``pantry-pirate-radio-llm-dlq-dev.fifo``), so we insert
    ``-dlq`` before the environment suffix.

    BatchStack's staging DLQ uses ``...-staging-{env}-dlq.fifo``
    (e.g. ``pantry-pirate-radio-staging-dev-dlq.fifo``), so we
    append ``-dlq`` before ``.fifo`` for that queue.
    """
    staging_suffix = f"-staging-{env}.fifo"
    env_suffix = f"-{env}.fifo"

    # Staging queue (BatchStack): DLQ is ``...-staging-{env}-dlq.fifo``
    if queue_name.endswith(staging_suffix):
        return queue_name.replace(".fifo", "-dlq.fifo")

    # QueueStack queues: DLQ is ``...-{name}-dlq-{env}.fifo``
    if queue_name.endswith(env_suffix):
        base = queue_name[: -len(env_suffix)]
        return f"{base}-dlq-{env}.fifo"

    # Fallback
    return queue_name.replace(".fifo", "-dlq.fifo")


# ── Public entry point ─────────────────────────────────────────────


def create_alarms(stack: MonitoringStack) -> None:  # noqa: C901 — alarm catalogue
    """Create all CloudWatch alarms for *stack* and wire them to SNS."""
    env = stack.environment_name
    ppr = "pantry-pirate-radio"
    sqs_visible = "ApproximateNumberOfMessagesVisible"
    api_dims = {"FunctionName": stack.api_function_name}

    # ── 1-2. API Lambda errors & throttles ────────────────────────
    alarm(
        stack,
        "APILambdaErrorsAlarm",
        f"{ppr}-api-lambda-errors-{env}",
        metric("AWS/Lambda", "Errors", api_dims),
        5,
        2,
        GTE,
        "API Lambda function errors are elevated",
    )
    alarm(
        stack,
        "APILambdaThrottleAlarm",
        f"{ppr}-api-lambda-throttle-{env}",
        metric("AWS/Lambda", "Throttles", api_dims),
        1,
        2,
        GTE,
        "API Lambda function is being throttled",
    )

    # ── 3. LLM queue depth ────────────────────────────────────────
    alarm(
        stack,
        "QueueDepthAlarm",
        f"{ppr}-queue-depth-{env}",
        metric("AWS/SQS", sqs_visible, {"QueueName": stack.queue_name}, "Average"),
        100,
        3,
        GT,
        "SQS queue depth is high - jobs are backing up",
    )

    # ── 4-5. DLQ alarms (LLM + staging + validator + reconciler + recorder)
    for cid, label, qname in [
        ("DLQAlarm", "dlq", stack.queue_name),
        ("StagingDLQAlarm", "staging-dlq", stack.staging_queue_name),
        ("ValidatorDLQAlarm", "validator-dlq", stack.validator_queue_name),
        ("ReconcilerDLQAlarm", "reconciler-dlq", stack.reconciler_queue_name),
        ("RecorderDLQAlarm", "recorder-dlq", stack.recorder_queue_name),
    ]:
        dlq = _derive_dlq_name(qname, env)
        alarm(
            stack,
            cid,
            f"{ppr}-{label}-{env}",
            metric("AWS/SQS", sqs_visible, {"QueueName": dlq}),
            1,
            1,
            GTE,
            f"Messages in {label.replace('-', ' ')}",
        )

    # Result processor DLQ (standard, not FIFO)
    alarm(
        stack,
        "ResultProcessorDLQAlarm",
        f"{ppr}-result-processor-dlq-{env}",
        metric(
            "AWS/SQS",
            sqs_visible,
            {"QueueName": f"{ppr}-result-processor-dlq-{env}"},
        ),
        1,
        1,
        GTE,
        "Messages in result processor dead-letter queue",
    )

    # ── 6. DynamoDB throttle (jobs table) ─────────────────────────
    alarm(
        stack,
        "DynamoDBThrottleAlarm",
        f"{ppr}-dynamodb-throttle-{env}",
        metric(
            "AWS/DynamoDB",
            "ThrottledRequests",
            {"TableName": stack.jobs_table_name},
        ),
        1,
        1,
        GTE,
        "DynamoDB requests are being throttled",
    )

    # ── 7. Bedrock throttle ───────────────────────────────────────
    alarm(
        stack,
        "BedrockThrottleAlarm",
        f"{ppr}-bedrock-throttle-{env}",
        metric(
            "AWS/Bedrock",
            "InvocationThrottles",
            {"ModelId": stack.bedrock_model_id},
        ),
        5,
        2,
        GT,
        "Bedrock LLM invocations are being throttled",
    )

    # ── 8. Aurora ACU high — 75% of 2 ACU max ────────────────────
    acu_threshold = 1.5
    alarm(
        stack,
        "AuroraACUAlarm",
        f"{ppr}-aurora-acu-high-{env}",
        metric(
            "AWS/RDS",
            "ServerlessDatabaseCapacity",
            {"DBClusterIdentifier": stack.aurora_cluster_id},
            "Average",
        ),
        acu_threshold,
        3,
        GT,
        f"Aurora ACU usage above {acu_threshold} (75% of 2 ACU max)",
    )

    # ── 9. Pipeline failure ───────────────────────────────────────
    sm_arn = (
        f"arn:aws:states:{stack.region}:{stack.account}"
        f":stateMachine:{stack.state_machine_name}"
    )
    alarm(
        stack,
        "PipelineFailureAlarm",
        f"{ppr}-pipeline-failure-{env}",
        metric("AWS/States", "ExecutionsFailed", {"StateMachineArn": sm_arn}),
        1,
        1,
        GTE,
        "Step Functions pipeline execution failed",
    )

    # ── 14. Amazon Location Service errors ────────────────────────
    alarm(
        stack,
        "LocationServiceErrorAlarm",
        f"{ppr}-location-service-errors-{env}",
        metric(
            "AWS/Location",
            "ErrorCount",
            {
                "ResourceName": stack.place_index_name,
                "OperationName": "SearchPlaceIndexForText",
            },
        ),
        10,
        2,
        GTE,
        "Amazon Location Service geocoding errors are elevated",
    )

    # ── H1-H8: Fargate CPU/Memory (ECS/ContainerInsights) ────────
    for label, svc in [
        ("Worker", stack.worker_service_name),
        ("Validator", stack.validator_service_name),
        ("Reconciler", stack.reconciler_service_name),
        ("Recorder", stack.recorder_service_name),
    ]:
        dims = {"ClusterName": stack.cluster_name, "ServiceName": svc}
        slug = label.lower()
        for suffix, metric_name in [
            ("cpu-high", "CpuUtilized"),
            ("memory-high", "MemoryUtilized"),
        ]:
            kind = "CPU" if "cpu" in suffix else "memory"
            alarm(
                stack,
                f"{label}{kind.title()}Alarm",
                f"ppr-{env}-{slug}-{suffix}",
                metric("ECS/ContainerInsights", metric_name, dims, "Average"),
                80,
                5,
                GTE,
                f"{label} Fargate {kind} utilization above 80%",
                datapoints_to_alarm=3,
                treat_missing_data=NB,
            )

    # ── H9-H12: Lambda Error/Throttle (conditional) ──────────────
    for fn_name, cid_prefix, label in [
        (stack.batcher_function_name, "BatcherLambda", "batcher-lambda"),
        (
            stack.result_processor_function_name,
            "ResultProcessorLambda",
            "result-processor-lambda",
        ),
    ]:
        if not fn_name:
            continue
        fn_dims = {"FunctionName": fn_name}
        alarm(
            stack,
            f"{cid_prefix}ErrorsAlarm",
            f"ppr-{env}-{label}-errors",
            metric("AWS/Lambda", "Errors", fn_dims),
            5,
            1,
            GTE,
            f"{cid_prefix.replace('Lambda', ' Lambda')} errors are elevated",
        )
        alarm(
            stack,
            f"{cid_prefix}ThrottleAlarm",
            f"ppr-{env}-{label}-throttle",
            metric("AWS/Lambda", "Throttles", fn_dims),
            1,
            1,
            GTE,
            f"{cid_prefix.replace('Lambda', ' Lambda')} is being throttled",
        )

    # ── H13-H16: DynamoDB Throttle/Error (content_index + geocoding_cache)
    for label, slug, tbl in [
        ("ContentIndex", "content-index", stack.content_index_table_name),
        ("GeocodingCache", "geocoding-cache", stack.geocoding_cache_table_name),
    ]:
        t_dims = {"TableName": tbl}
        alarm(
            stack,
            f"{label}ThrottleAlarm",
            f"ppr-{env}-{slug}-throttle",
            metric("AWS/DynamoDB", "ThrottledRequests", t_dims),
            1,
            1,
            GTE,
            f"DynamoDB {label} table requests are being throttled",
        )
        alarm(
            stack,
            f"{label}SystemErrorAlarm",
            f"ppr-{env}-{slug}-system-errors",
            metric("AWS/DynamoDB", "SystemErrors", t_dims),
            1,
            1,
            GTE,
            f"DynamoDB {label} table has system errors",
        )

    # ── H17-H20: Queue depth (validator, reconciler, recorder, staging)
    for label, qname in [
        ("Validator", stack.validator_queue_name),
        ("Reconciler", stack.reconciler_queue_name),
        ("Recorder", stack.recorder_queue_name),
        ("Staging", stack.staging_queue_name),
    ]:
        alarm(
            stack,
            f"{label}QueueDepthAlarm",
            f"ppr-{env}-{label.lower()}-queue-depth",
            metric("AWS/SQS", sqs_visible, {"QueueName": qname}, "Average"),
            100,
            3,
            GT,
            f"{label} queue depth is high - jobs are backing up",
        )

    # ================================================================
    # NEW ALARMS
    # ================================================================

    # ── (a) API Gateway 5xx ───────────────────────────────────────
    if stack.api_gateway_id:
        gw_dims = {"ApiId": stack.api_gateway_id}
        alarm(
            stack,
            "ApiGateway5xxAlarm",
            f"ppr-{env}-api-gateway-5xx",
            metric("AWS/ApiGateway", "5xx", gw_dims),
            5,
            2,
            GTE,
            "API Gateway 5xx errors are elevated",
        )

        # ── (b) API Gateway 4xx ──────────────────────────────────
        alarm(
            stack,
            "ApiGateway4xxAlarm",
            f"ppr-{env}-api-gateway-4xx",
            metric("AWS/ApiGateway", "4xx", gw_dims),
            50,
            3,
            GTE,
            "API Gateway 4xx errors are elevated",
        )

    # ── (c) API Lambda error rate % (MathExpression) ─────────────
    errors_metric = cloudwatch.Metric(
        namespace="AWS/Lambda",
        metric_name="Errors",
        dimensions_map=api_dims,
        statistic="Sum",
        period=Duration.minutes(5),
    )
    invocations_metric = cloudwatch.Metric(
        namespace="AWS/Lambda",
        metric_name="Invocations",
        dimensions_map=api_dims,
        statistic="Sum",
        period=Duration.minutes(5),
    )
    error_rate = cloudwatch.MathExpression(
        expression="(errors / invocations) * 100",
        using_metrics={"errors": errors_metric, "invocations": invocations_metric},
        label="Error rate %",
        period=Duration.minutes(5),
    )
    error_rate_alarm = cloudwatch.Alarm(
        stack,
        "ApiLambdaErrorRateAlarm",
        alarm_name=f"ppr-{env}-api-lambda-error-rate",
        alarm_description="API Lambda error rate exceeds 5%",
        metric=error_rate,
        threshold=5,
        evaluation_periods=3,
        comparison_operator=GT,
        treat_missing_data=NB,
    )
    error_rate_alarm.add_alarm_action(cw_actions.SnsAction(stack.alerts_topic))

    # ── (d) Aurora connections high ──────────────────────────────
    alarm(
        stack,
        "AuroraConnectionsHighAlarm",
        f"ppr-{env}-aurora-connections-high",
        metric(
            "AWS/RDS",
            "DatabaseConnections",
            {"DBClusterIdentifier": stack.aurora_cluster_id},
            "Average",
        ),
        80,
        3,
        GT,
        "Aurora database connections are high",
    )

    # ── (e) RDS Proxy connections high ───────────────────────────
    alarm(
        stack,
        "RdsProxyConnectionsHighAlarm",
        f"ppr-{env}-rds-proxy-connections-high",
        metric(
            "AWS/RDS",
            "DatabaseConnections",
            {"ProxyName": stack.rds_proxy_name},
            "Average",
        ),
        50,
        3,
        GT,
        "RDS Proxy connections are high",
    )

    # ── (f-g) S3 content bucket 4xx / 5xx ────────────────────────
    _s3_error_alarms(
        stack,
        label="content",
        bucket_name=stack.content_bucket_name,
        env=env,
    )

    # ── (h-i) S3 exports bucket 4xx / 5xx ────────────────────────
    _s3_error_alarms(
        stack,
        label="exports",
        bucket_name=stack.exports_bucket_name,
        env=env,
    )


# ── Internal helpers for grouped alarm patterns ────────────────────


def _s3_error_alarms(
    stack: MonitoringStack,
    *,
    label: str,
    bucket_name: str,
    env: str,
) -> None:
    """Create 4xx and 5xx alarms for an S3 bucket."""
    dims = {"BucketName": bucket_name, "FilterId": "AllRequests"}

    alarm(
        stack,
        f"S3{label.title()}4xxAlarm",
        f"ppr-{env}-s3-{label}-4xx",
        metric("AWS/S3", "4xxErrors", dims),
        10,
        2,
        GTE,
        f"S3 {label} bucket 4xx errors are elevated",
        treat_missing_data=NB,
    )
    alarm(
        stack,
        f"S3{label.title()}5xxAlarm",
        f"ppr-{env}-s3-{label}-5xx",
        metric("AWS/S3", "5xxErrors", dims),
        1,
        1,
        GTE,
        f"S3 {label} bucket 5xx errors detected",
        treat_missing_data=NB,
    )
