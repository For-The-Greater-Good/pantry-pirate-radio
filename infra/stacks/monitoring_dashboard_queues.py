"""SQS queue and pipeline dashboard sections for Pantry Pirate Radio.

Extracted from ``monitoring_dashboard.py`` to keep files under the 600-line
limit.  Also houses the shared ``derive_dlq_name`` helper used by both
dashboard and alarm modules.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

from aws_cdk import Duration
from aws_cdk import aws_cloudwatch as cloudwatch

from stacks.monitoring_dashboard import graph, metric, section

if TYPE_CHECKING:
    from stacks.monitoring_stack import MonitoringStack


def derive_dlq_name(queue_name: str, env: str) -> str:
    """Derive DLQ name from main queue name.

    QueueStack creates DLQs as ``...-{name}-dlq-{env}.fifo``
    (e.g. ``pantry-pirate-radio-llm-dlq-dev.fifo``), so we insert
    ``-dlq`` before the environment suffix.

    BatchStack's staging DLQ uses ``...-staging-{env}-dlq.fifo``
    (e.g. ``pantry-pirate-radio-staging-dev-dlq.fifo``), so we
    append ``-dlq`` before ``.fifo`` for that queue.
    """
    # Exact BatchStack staging queue name (not submarine-staging)
    batch_staging_name = f"pantry-pirate-radio-staging-{env}.fifo"
    env_suffix = f"-{env}.fifo"

    # Staging queue (BatchStack): DLQ is ``...-staging-{env}-dlq.fifo``
    if queue_name == batch_staging_name:
        return queue_name.replace(".fifo", "-dlq.fifo")

    # QueueStack queues: DLQ is ``...-{name}-dlq-{env}.fifo``
    if queue_name.endswith(env_suffix):
        base = queue_name[: -len(env_suffix)]
        return f"{base}-dlq-{env}.fifo"

    # Fallback — naming convention not recognised
    warnings.warn(
        f"Queue name '{queue_name}' does not match any known naming convention "
        f"(expected ...-staging-{env}.fifo or ...-{{name}}-{env}.fifo). "
        f"DLQ name derivation may be incorrect.",
        stacklevel=2,
    )
    return queue_name.replace(".fifo", "-dlq.fifo")


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
        ("Submarine", stack.submarine_queue_name),
        ("Sub Staging", stack.submarine_staging_queue_name),
        ("Sub Extraction", stack.submarine_extraction_queue_name),
    ]

    db.add_widgets(section("SQS Queues"))

    # Per-queue depth graphs: visible + not-visible, DLQ on right axis.
    # SQS queue-depth metrics are gauges (point-in-time), not counters —
    # use Maximum to see peak depth within each period.
    queue_widgets = []
    for label, qname in queues:
        dlq_name = derive_dlq_name(qname, stack.environment_name)
        queue_widgets.append(
            graph(
                f"{label}",
                left=[
                    metric(
                        ns,
                        "ApproximateNumberOfMessagesVisible",
                        {"QueueName": qname},
                        "Maximum",
                        p1,
                    ),
                    metric(
                        ns,
                        "ApproximateNumberOfMessagesNotVisible",
                        {"QueueName": qname},
                        "Maximum",
                        p1,
                    ),
                ],
                right=[
                    metric(
                        ns,
                        "ApproximateNumberOfMessagesVisible",
                        {"QueueName": dlq_name},
                        "Maximum",
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
    p1 = Duration.minutes(1)
    env = stack.environment_name
    queues = [
        stack.queue_name,
        stack.staging_queue_name,
        stack.validator_queue_name,
        stack.reconciler_queue_name,
        stack.recorder_queue_name,
        stack.submarine_queue_name,
        stack.submarine_staging_queue_name,
        stack.submarine_extraction_queue_name,
    ]
    dlqs = [derive_dlq_name(q, env) for q in queues]

    queue_depths = [
        metric(
            "AWS/SQS",
            "ApproximateNumberOfMessagesVisible",
            {"QueueName": q},
            "Maximum",
            p1,
        )
        for q in queues
    ]
    dlq_depths = [
        metric(
            "AWS/SQS",
            "ApproximateNumberOfMessagesVisible",
            {"QueueName": d},
            "Maximum",
            p1,
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
