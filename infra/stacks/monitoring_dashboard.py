"""Dashboard section builders for the MonitoringStack.

Each ``add_*_section()`` function appends a group of widgets to the
CloudWatch dashboard.  The module-level helpers (``metric``, ``graph``,
``section``, ``derive_dlq_name``, ``scaling_widget``) mirror the former
private methods of ``MonitoringStack`` but operate on a stack instance
passed as the first parameter.

``build_dashboard(stack)`` is the top-level orchestrator that creates the
``cloudwatch.Dashboard`` and calls every section builder in order.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aws_cdk import Duration
from aws_cdk import aws_cloudwatch as cloudwatch

if TYPE_CHECKING:
    from infra.stacks.monitoring_stack import MonitoringStack

# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def metric(
    ns: str,
    name: str,
    dims: dict,
    stat: str = "Sum",
    period: Duration = Duration.minutes(5),
) -> cloudwatch.Metric:
    """Create a CloudWatch ``Metric``."""
    return cloudwatch.Metric(
        namespace=ns,
        metric_name=name,
        dimensions_map=dims,
        statistic=stat,
        period=period,
    )


def graph(
    title: str,
    left: list,
    right: list | None = None,
    width: int = 6,
) -> cloudwatch.GraphWidget:
    """Create a CloudWatch ``GraphWidget``."""
    kw: dict = {"title": title, "width": width, "height": 6, "left": left}
    if right:
        kw["right"] = right
    return cloudwatch.GraphWidget(**kw)


def section(title: str) -> cloudwatch.TextWidget:
    """Create a section-header ``TextWidget``."""
    return cloudwatch.TextWidget(markdown=f"# {title}", width=24, height=1)


def derive_dlq_name(stack: MonitoringStack, queue_name: str) -> str:
    """Derive the DLQ name from a main queue name.

    QueueStack creates DLQs as ``...-{name}-dlq-{env}.fifo``
    (e.g. ``pantry-pirate-radio-llm-dlq-dev.fifo``), so we insert
    ``-dlq`` before the environment suffix.

    BatchStack's staging DLQ uses ``...-staging-{env}-dlq.fifo``
    (e.g. ``pantry-pirate-radio-staging-dev-dlq.fifo``), so we
    append ``-dlq`` before ``.fifo`` for that queue.
    """
    env = stack.environment_name
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


def scaling_widget(
    stack: MonitoringStack,
    title: str,
    service_name: str,
    queue_name: str,
) -> cloudwatch.GraphWidget:
    """Create an auto-scaling graph for an ECS service backed by an SQS queue."""
    dims = {"ClusterName": stack.cluster_name, "ServiceName": service_name}
    p1 = Duration.minutes(1)
    return graph(
        title,
        left=[
            metric("AWS/ECS", "DesiredCount", dims, "Average", p1),
            metric("AWS/ECS", "RunningCount", dims, "Average", p1),
        ],
        right=[
            metric(
                "AWS/SQS",
                "ApproximateNumberOfMessagesVisible",
                {"QueueName": queue_name},
                "Sum",
                p1,
            )
        ],
    )


# ---------------------------------------------------------------------------
# Dashboard section builders
# ---------------------------------------------------------------------------


def add_lambda_api_section(
    stack: MonitoringStack, db: cloudwatch.Dashboard
) -> None:
    """Section 1 -- Lambda API."""
    fn_dims = {"FunctionName": stack.api_function_name}
    ns = "AWS/Lambda"
    p1 = Duration.minutes(1)

    invocations = metric(ns, "Invocations", fn_dims, "Sum", p1)
    duration_avg = metric(ns, "Duration", fn_dims, "Average", p1)
    duration_p99 = metric(ns, "Duration", fn_dims, "p99", p1)
    errors = metric(ns, "Errors", fn_dims, "Sum", p1)
    throttles = metric(ns, "Throttles", fn_dims, "Sum", p1)
    cold_starts = metric(ns, "ConcurrentExecutions", fn_dims, "Maximum", p1)

    left_errors: list = [errors, throttles]
    if stack.api_gateway_id:
        gw_dims = {"ApiId": stack.api_gateway_id}
        gw = "AWS/ApiGateway"
        left_errors.append(metric(gw, "4xx", gw_dims, "Sum", p1))
        left_errors.append(metric(gw, "5xx", gw_dims, "Sum", p1))

    db.add_widgets(section("Lambda API"))
    db.add_widgets(
        graph("API Invocations", [invocations]),
        graph("API Duration", [duration_avg, duration_p99]),
        graph("API Errors & Throttles", left_errors),
        graph("API Cold Starts", [cold_starts]),
    )


def add_worker_section(
    stack: MonitoringStack, db: cloudwatch.Dashboard
) -> None:
    """Section 2 -- ECS Services."""
    p1 = Duration.minutes(1)
    ns = "AWS/ECS"
    services = {
        "Worker": stack.worker_service_name,
        "Validator": stack.validator_service_name,
        "Reconciler": stack.reconciler_service_name,
        "Recorder": stack.recorder_service_name,
    }

    cpu_metrics = [
        metric(
            ns,
            "CPUUtilization",
            {"ClusterName": stack.cluster_name, "ServiceName": svc},
            "Average",
            p1,
        )
        for svc in services.values()
    ]
    mem_metrics = [
        metric(
            ns,
            "MemoryUtilization",
            {"ClusterName": stack.cluster_name, "ServiceName": svc},
            "Average",
            p1,
        )
        for svc in services.values()
    ]

    db.add_widgets(section("ECS Services"))
    db.add_widgets(
        graph("Service CPU %", cpu_metrics, width=12),
        graph("Service Memory %", mem_metrics, width=12),
    )


def add_sqs_queues_section(
    stack: MonitoringStack, db: cloudwatch.Dashboard
) -> None:
    """Section 3 -- SQS Queues."""
    p1 = Duration.minutes(1)
    ns = "AWS/SQS"

    queues = [
        ("LLM", stack.queue_name),
        ("Staging", stack.staging_queue_name),
        ("Validator", stack.validator_queue_name),
        ("Reconciler", stack.reconciler_queue_name),
        ("Recorder", stack.recorder_queue_name),
    ]

    db.add_widgets(section("SQS Queues"))

    # Per-queue depth graphs: visible + not-visible, DLQ on right axis
    queue_widgets = []
    for label, qname in queues:
        dlq_name = derive_dlq_name(stack, qname)
        queue_widgets.append(
            graph(
                f"{label}",
                left=[
                    metric(
                        ns,
                        "ApproximateNumberOfMessagesVisible",
                        {"QueueName": qname},
                        "Sum",
                        p1,
                    ),
                    metric(
                        ns,
                        "ApproximateNumberOfMessagesNotVisible",
                        {"QueueName": qname},
                        "Sum",
                        p1,
                    ),
                ],
                right=[
                    metric(
                        ns,
                        "ApproximateNumberOfMessagesVisible",
                        {"QueueName": dlq_name},
                        "Sum",
                        p1,
                    ),
                ],
            )
        )

    # Queue ages (all on one graph)
    queue_widgets.append(
        graph(
            "Oldest Message Age",
            left=[
                metric(
                    ns,
                    "ApproximateAgeOfOldestMessage",
                    {"QueueName": qname},
                    "Maximum",
                    p1,
                )
                for _, qname in queues
            ],
        )
    )

    db.add_widgets(*queue_widgets)


def add_pipeline_section(
    stack: MonitoringStack, db: cloudwatch.Dashboard
) -> None:
    """Section 4 -- Pipeline Overview."""
    queues = [
        stack.queue_name,
        stack.staging_queue_name,
        stack.validator_queue_name,
        stack.reconciler_queue_name,
        stack.recorder_queue_name,
    ]
    dlqs = [derive_dlq_name(stack, q) for q in queues]

    queue_depths = [
        metric(
            "AWS/SQS",
            "ApproximateNumberOfMessagesVisible",
            {"QueueName": q},
            "Sum",
        )
        for q in queues
    ]
    dlq_depths = [
        metric(
            "AWS/SQS",
            "ApproximateNumberOfMessagesVisible",
            {"QueueName": d},
            "Sum",
        )
        for d in dlqs
    ]

    sm_arn = (
        f"arn:aws:states:{stack.region}:{stack.account}"
        f":stateMachine:{stack.state_machine_name}"
    )
    sm_dims = {"StateMachineArn": sm_arn}

    db.add_widgets(section("Pipeline Overview"))
    db.add_widgets(
        graph("All Queue Depths", queue_depths),
        graph("Dead Letter Queues", dlq_depths),
        graph(
            "Step Functions Executions",
            [
                metric("AWS/States", "ExecutionsStarted", sm_dims),
                metric("AWS/States", "ExecutionsSucceeded", sm_dims),
                metric("AWS/States", "ExecutionsFailed", sm_dims),
            ],
        ),
        graph(
            "Step Functions Duration",
            [
                metric("AWS/States", "ExecutionTime", sm_dims, "Average"),
                metric("AWS/States", "ExecutionTime", sm_dims, "p99"),
            ],
        ),
    )


def add_aurora_section(
    stack: MonitoringStack, db: cloudwatch.Dashboard
) -> None:
    """Section 5 -- Aurora Database."""
    dims = {"DBClusterIdentifier": stack.aurora_cluster_id}
    ns = "AWS/RDS"

    db.add_widgets(section("Aurora Database"))
    db.add_widgets(
        graph(
            "Aurora ACU",
            [metric(ns, "ServerlessDatabaseCapacity", dims, "Average")],
        ),
        graph(
            "DB Connections",
            [metric(ns, "DatabaseConnections", dims, "Average")],
        ),
        graph(
            "DB Throughput",
            [
                metric(ns, "CommitThroughput", dims),
                metric(ns, "SelectThroughput", dims),
            ],
        ),
        graph(
            "DB Storage",
            [metric(ns, "VolumeBytesUsed", dims, "Average")],
        ),
    )


def add_rds_proxy_section(
    stack: MonitoringStack, db: cloudwatch.Dashboard
) -> None:
    """Section -- RDS Proxy metrics.

    Graphs for client connections, query latency, database connections,
    and query response latency sourced from the ``AWS/RDS`` namespace
    with ``ProxyName`` dimensions.
    """
    dims = {"ProxyName": stack.rds_proxy_name}
    ns = "AWS/RDS"
    p1 = Duration.minutes(1)

    db.add_widgets(section("RDS Proxy"))
    db.add_widgets(
        graph(
            "Client Connections",
            [metric(ns, "ClientConnections", dims, "Sum", p1)],
        ),
        graph(
            "Query Latency",
            [
                metric(ns, "QueryDatabaseResponseLatency", dims, "Average", p1),
                metric(ns, "QueryDatabaseResponseLatency", dims, "p99", p1),
            ],
        ),
        graph(
            "DB Connections",
            [
                metric(ns, "DatabaseConnections", dims, "Sum", p1),
                metric(
                    ns,
                    "DatabaseConnectionsCurrentlyInTransaction",
                    dims,
                    "Sum",
                    p1,
                ),
            ],
        ),
        graph(
            "Query Response Latency",
            [metric(ns, "QueryDatabaseResponseLatency", dims, "Maximum", p1)],
        ),
    )


def add_dynamodb_section(
    stack: MonitoringStack, db: cloudwatch.Dashboard
) -> None:
    """Section 6 -- DynamoDB Tables."""
    tables = [
        stack.jobs_table_name,
        stack.content_index_table_name,
        stack.geocoding_cache_table_name,
    ]
    ns = "AWS/DynamoDB"

    def multi(metric_name: str, stat: str = "Sum") -> list:
        return [metric(ns, metric_name, {"TableName": t}, stat) for t in tables]

    db.add_widgets(section("DynamoDB Tables"))
    db.add_widgets(
        graph("DynamoDB Reads", multi("ConsumedReadCapacityUnits")),
        graph("DynamoDB Writes", multi("ConsumedWriteCapacityUnits")),
        graph("DynamoDB Throttles", multi("ThrottledRequests")),
        graph("DynamoDB Errors", multi("SystemErrors")),
    )


def add_bedrock_section(
    stack: MonitoringStack, db: cloudwatch.Dashboard
) -> None:
    """Section 7 -- Bedrock LLM."""
    dims = {"ModelId": stack.bedrock_model_id}
    ns = "AWS/Bedrock"

    input_tokens = metric(ns, "InputTokenCount", dims)
    output_tokens = metric(ns, "OutputTokenCount", dims)
    cost = cloudwatch.MathExpression(
        expression="(input * 0.80 / 1000000) + (output * 4.00 / 1000000)",
        using_metrics={"input": input_tokens, "output": output_tokens},
        label="Estimated Cost ($)",
        period=Duration.minutes(5),
    )

    db.add_widgets(section("Bedrock LLM"))
    db.add_widgets(
        graph(
            "Bedrock Invocations & Latency",
            [
                metric(ns, "Invocations", dims),
                metric(ns, "InvocationLatency", dims, "Average"),
                metric(ns, "InvocationLatency", dims, "p99"),
            ],
        ),
        graph("Bedrock Tokens & Cost", [input_tokens, output_tokens], [cost]),
        graph(
            "Bedrock Errors & Throttles",
            [
                metric(ns, "InvocationClientErrors", dims),
                metric(ns, "InvocationServerErrors", dims),
                metric(ns, "InvocationThrottles", dims),
            ],
        ),
    )


def add_batch_inference_section(
    stack: MonitoringStack, db: cloudwatch.Dashboard
) -> None:
    """Section 8 -- Batch Inference Lambdas (conditional)."""
    ns = "AWS/Lambda"
    b_dims = {"FunctionName": stack.batcher_function_name}
    r_dims = {"FunctionName": stack.result_processor_function_name}

    db.add_widgets(section("Batch Inference Lambdas"))
    db.add_widgets(
        graph(
            "Batcher Invocations",
            [
                metric(ns, "Invocations", b_dims),
                metric(ns, "Errors", b_dims),
            ],
        ),
        graph(
            "Batcher Duration",
            [
                metric(ns, "Duration", b_dims, "Average"),
                metric(ns, "Duration", b_dims, "p99"),
            ],
        ),
        graph(
            "Result Processor Invocations",
            [
                metric(ns, "Invocations", r_dims),
                metric(ns, "Errors", r_dims),
            ],
        ),
        graph(
            "Result Processor Duration",
            [
                metric(ns, "Duration", r_dims, "Average"),
                metric(ns, "Duration", r_dims, "p99"),
            ],
        ),
    )


def add_geocoding_section(
    stack: MonitoringStack, db: cloudwatch.Dashboard
) -> None:
    """Section 9 -- Geocoding (Amazon Location Service)."""
    ns = "AWS/Location"
    p5 = Duration.minutes(5)
    fwd = {
        "ResourceName": stack.place_index_name,
        "OperationName": "SearchPlaceIndexForText",
    }
    rev = {
        "ResourceName": stack.place_index_name,
        "OperationName": "SearchPlaceIndexForPosition",
    }

    db.add_widgets(section("Geocoding (Amazon Location Service)"))
    db.add_widgets(
        graph(
            "Geocoding Requests",
            [
                metric(ns, "CallCount", fwd, "Sum", p5),
                metric(ns, "CallCount", rev, "Sum", p5),
            ],
        ),
        graph(
            "Geocoding Latency",
            [
                metric(ns, "CallLatency", fwd, "Average", p5),
                metric(ns, "CallLatency", fwd, "p99", p5),
                metric(ns, "CallLatency", rev, "Average", p5),
            ],
        ),
        graph(
            "Geocoding Errors",
            [
                metric(ns, "ErrorCount", fwd, "Sum", p5),
                metric(ns, "ErrorCount", rev, "Sum", p5),
            ],
        ),
    )


def add_autoscaling_section(
    stack: MonitoringStack, db: cloudwatch.Dashboard
) -> None:
    """Section 10 -- Auto-Scaling."""
    db.add_widgets(section("Auto-Scaling"))
    db.add_widgets(
        scaling_widget(stack, "Worker Scaling", stack.worker_service_name, stack.queue_name),
        scaling_widget(
            stack,
            "Validator Scaling",
            stack.validator_service_name,
            stack.validator_queue_name,
        ),
        scaling_widget(
            stack,
            "Reconciler Scaling",
            stack.reconciler_service_name,
            stack.reconciler_queue_name,
        ),
        scaling_widget(
            stack,
            "Recorder Scaling",
            stack.recorder_service_name,
            stack.recorder_queue_name,
        ),
    )


def add_s3_section(
    stack: MonitoringStack, db: cloudwatch.Dashboard
) -> None:
    """Section 11 -- S3 Storage."""
    ns = "AWS/S3"
    day = Duration.days(1)

    def bucket_metrics(bucket_name: str) -> list:
        return [
            metric(
                ns,
                "NumberOfObjects",
                {"BucketName": bucket_name, "StorageType": "AllStorageTypes"},
                "Average",
                day,
            ),
            metric(
                ns,
                "BucketSizeBytes",
                {"BucketName": bucket_name, "StorageType": "StandardStorage"},
                "Average",
                day,
            ),
        ]

    db.add_widgets(section("S3 Storage"))
    db.add_widgets(
        graph("Content Bucket", bucket_metrics(stack.content_bucket_name)),
        graph("Batch Bucket", bucket_metrics(stack.batch_bucket_name)),
        graph("Exports Bucket", bucket_metrics(stack.exports_bucket_name)),
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def build_dashboard(stack: MonitoringStack) -> cloudwatch.Dashboard:
    """Create the operational CloudWatch dashboard with all sections.

    Returns the ``cloudwatch.Dashboard`` instance so the caller can store
    it as ``stack.dashboard``.
    """
    db = cloudwatch.Dashboard(
        stack,
        "OperationalDashboard",
        dashboard_name=f"PantryPirateRadio-{stack.environment_name}",
    )

    add_lambda_api_section(stack, db)
    add_worker_section(stack, db)
    add_sqs_queues_section(stack, db)
    add_pipeline_section(stack, db)
    add_aurora_section(stack, db)
    add_rds_proxy_section(stack, db)
    add_dynamodb_section(stack, db)
    add_bedrock_section(stack, db)
    if stack.batcher_function_name:
        add_batch_inference_section(stack, db)
    add_geocoding_section(stack, db)
    add_autoscaling_section(stack, db)
    add_s3_section(stack, db)

    return db
