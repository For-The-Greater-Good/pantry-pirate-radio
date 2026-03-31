"""Dashboard section builders for the MonitoringStack.

Each ``add_*_section()`` function appends a group of widgets to the
CloudWatch dashboard.  The module-level helpers (``metric``, ``graph``,
``section``, ``scaling_widget``) mirror the former private methods of
``MonitoringStack`` but operate on a stack instance passed as the first
parameter.

SQS queue and pipeline sections live in ``monitoring_dashboard_queues``
to keep this file under 600 lines.

``build_dashboard(stack)`` is the top-level orchestrator that creates the
``cloudwatch.Dashboard`` and calls every section builder in order.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aws_cdk import Duration
from aws_cdk import aws_cloudwatch as cloudwatch

if TYPE_CHECKING:
    from stacks.monitoring_stack import MonitoringStack

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
    concurrency = metric(ns, "ConcurrentExecutions", fn_dims, "Maximum", p1)

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
        graph("API Concurrent Executions", [concurrency]),
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
        "Submarine": stack.submarine_service_name,
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
    """Section 6 -- RDS Proxy metrics.

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
    """Section 7 -- DynamoDB Tables."""
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
    """Section 8 -- Bedrock LLM."""
    dims = {"ModelId": stack.bedrock_model_id}
    ns = "AWS/Bedrock"

    input_tokens = metric(ns, "InputTokenCount", dims)
    output_tokens = metric(ns, "OutputTokenCount", dims)
    # Pricing for Claude Haiku 4.5 on-demand ($0.80/MTok input, $4.00/MTok output).
    # Update rates if bedrock_model_id changes to a different model.
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
    """Section 9 -- Batch Inference Lambdas (conditional)."""
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
    """Section 10 -- Geocoding (Amazon Location Service)."""
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
    """Section 11 -- Auto-Scaling."""
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
        scaling_widget(
            stack,
            "Submarine Scaling",
            stack.submarine_service_name,
            stack.submarine_queue_name,
        ),
    )


def add_submarine_section(
    stack: MonitoringStack, db: cloudwatch.Dashboard
) -> None:
    """Section -- Submarine Enrichment performance from log-based metrics."""
    ns = "PantryPirateRadio/Submarine"
    p5 = Duration.minutes(5)
    dims: dict = {}  # Metric filters don't use dimensions

    started = metric(ns, "JobsStarted", dims, "Sum", p5)
    completed = metric(ns, "JobsCompleted", dims, "Sum", p5)
    no_data = metric(ns, "JobsNoData", dims, "Sum", p5)

    db.add_widgets(section("Submarine Enrichment"))
    db.add_widgets(
        graph(
            "Submarine Jobs",
            [started, completed, no_data],
        ),
        graph(
            "Submarine Success Rate",
            [
                cloudwatch.MathExpression(
                    expression=(
                        "IF(started > 0, 100 * completed / started, 0)"
                    ),
                    using_metrics={"started": started, "completed": completed},
                    label="Success %",
                    period=p5,
                ),
            ],
        ),
        graph(
            "Submarine Errors",
            [
                metric(ns, "CrawlErrors", dims, "Sum", p5),
                metric(ns, "ExtractionErrors", dims, "Sum", p5),
            ],
        ),
        graph(
            "Content Relevance Rejections",
            [metric(ns, "ContentNotFoodRelated", dims, "Sum", p5)],
        ),
    )


def _add_service_section(
    stack: MonitoringStack,
    db: cloudwatch.Dashboard,
    title: str,
    service_name: str,
    queue_name: str,
    env: str,
) -> None:
    """Add a per-service dashboard section with queue + ECS metrics."""
    p1 = Duration.minutes(1)
    sqs_ns = "AWS/SQS"
    ecs_ns = "AWS/ECS"
    ecs_dims = {"ClusterName": stack.cluster_name, "ServiceName": service_name}
    from stacks.monitoring_dashboard_queues import derive_dlq_name

    dlq_name = derive_dlq_name(queue_name, env)

    db.add_widgets(section(title))
    db.add_widgets(
        graph(
            f"{title} Queue",
            left=[
                metric(sqs_ns, "ApproximateNumberOfMessagesVisible",
                       {"QueueName": queue_name}, "Sum", p1),
                metric(sqs_ns, "ApproximateNumberOfMessagesNotVisible",
                       {"QueueName": queue_name}, "Sum", p1),
            ],
            right=[
                metric(sqs_ns, "ApproximateNumberOfMessagesVisible",
                       {"QueueName": dlq_name}, "Sum", p1),
            ],
        ),
        graph(
            f"{title} Tasks vs Queue",
            left=[
                metric(ecs_ns, "DesiredCount", ecs_dims, "Average", p1),
                metric(ecs_ns, "RunningCount", ecs_dims, "Average", p1),
            ],
            right=[
                metric(sqs_ns, "ApproximateNumberOfMessagesVisible",
                       {"QueueName": queue_name}, "Sum", p1),
            ],
        ),
        graph(
            f"{title} CPU %",
            [metric(ecs_ns, "CPUUtilization", ecs_dims, "Average", p1)],
        ),
        graph(
            f"{title} Memory %",
            [metric(ecs_ns, "MemoryUtilization", ecs_dims, "Average", p1)],
        ),
    )


def add_service_sections(
    stack: MonitoringStack, db: cloudwatch.Dashboard
) -> None:
    """Per-service operational sections for Validator, Reconciler, Recorder."""
    env = stack.environment_name
    services = [
        ("Validator", stack.validator_service_name, stack.validator_queue_name),
        ("Reconciler", stack.reconciler_service_name, stack.reconciler_queue_name),
        ("Recorder", stack.recorder_service_name, stack.recorder_queue_name),
    ]
    for title, svc_name, q_name in services:
        _add_service_section(stack, db, title, svc_name, q_name, env)


def add_s3_section(
    stack: MonitoringStack, db: cloudwatch.Dashboard
) -> None:
    """Section 12 -- S3 Storage."""
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
    from stacks.monitoring_dashboard_queues import (
        add_pipeline_section,
        add_sqs_queues_section,
    )

    db = cloudwatch.Dashboard(
        stack,
        "OperationalDashboard",
        dashboard_name=f"PantryPirateRadio-{stack.environment_name}",
    )

    add_lambda_api_section(stack, db)
    add_worker_section(stack, db)
    add_service_sections(stack, db)
    add_sqs_queues_section(stack, db)
    add_pipeline_section(stack, db)
    add_aurora_section(stack, db)
    add_rds_proxy_section(stack, db)
    add_dynamodb_section(stack, db)
    add_bedrock_section(stack, db)
    if stack.batcher_function_name and stack.result_processor_function_name:
        add_batch_inference_section(stack, db)
    add_geocoding_section(stack, db)
    add_submarine_section(stack, db)
    add_autoscaling_section(stack, db)
    add_s3_section(stack, db)

    return db
