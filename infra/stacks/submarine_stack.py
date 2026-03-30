"""Submarine Step Functions orchestration stack.

Creates a Step Functions state machine that runs the submarine scanner
(crawl food bank websites for missing data), waits for crawlers to
finish processing, then triggers the batcher Lambda for batch LLM
extraction. Can be scheduled weekly or triggered on-demand via
``./bouy submarine --aws``.

Resources:
    - Step Functions state machine with ECS:runTask + Lambda integration
    - Inline check-queue Lambda (checks SQS queue depth)
    - EventBridge rule for weekly scheduling (disabled by default in dev)
    - IAM roles for Step Functions execution, ECS task launching, Lambda invoke

Attributes:
    state_machine: Step Functions state machine
    schedule_rule: EventBridge schedule rule
    check_queue_lambda: Lambda that checks SQS queue depth
"""

import json

from aws_cdk import Duration, RemovalPolicy, Stack
from aws_cdk import aws_events as events
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_logs as logs
from aws_cdk import aws_stepfunctions as sfn
from constructs import Construct

# Inline Python code for the check-queue Lambda.
# Returns {"is_empty": true} when the queue has 0 visible + 0 in-flight messages.
CHECK_QUEUE_CODE = """
import boto3
import os

sqs = boto3.client("sqs")

def handler(event, context):
    queue_url = event["queue_url"]
    resp = sqs.get_queue_attributes(
        QueueUrl=queue_url,
        AttributeNames=[
            "ApproximateNumberOfMessages",
            "ApproximateNumberOfMessagesNotVisible",
        ],
    )
    attrs = resp["Attributes"]
    visible = int(attrs.get("ApproximateNumberOfMessages", "0"))
    in_flight = int(attrs.get("ApproximateNumberOfMessagesNotVisible", "0"))
    return {"is_empty": (visible + in_flight) == 0, "visible": visible, "in_flight": in_flight}
"""


class SubmarineStack(Stack):
    """Submarine orchestration via Step Functions.

    Runs the submarine scanner as an ECS Fargate task, waits for
    crawlers to drain the submarine queue, then invokes the batcher
    Lambda for batch LLM extraction of crawled content.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        environment_name: str = "dev",
        cluster_arn: str,
        subnet_ids: list[str],
        scanner_task_family: str,
        scanner_container_name: str = "SubmarineScannerContainer",
        scanner_security_group_id: str = "",
        submarine_queue_url: str = "",
        batcher_lambda_arn: str = "",
        schedule_enabled: bool = False,
        schedule_expression: str = "rate(7 days)",
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.environment_name = environment_name

        # Create the check-queue Lambda (inline, tiny — just checks SQS depth)
        self.check_queue_lambda = self._create_check_queue_lambda(submarine_queue_url)

        # Container env overrides for the scanner task.
        # The task definition already has DB and queue env vars from
        # get_submarine_environment(). We override SERVICE_TYPE to bypass
        # the docker-entrypoint.sh routing and run the command directly.
        container_env = [
            {"Name": "SERVICE_TYPE", "Value": "exec"},
            {"Name": "PYTHONUNBUFFERED", "Value": "1"},
        ]

        # State machine definition (ASL JSON)
        # Uses ecs:runTask.sync to run scanner as a Fargate task,
        # then waits for crawlers to drain the submarine queue,
        # then invokes the batcher Lambda for batch extraction.
        scan_command = ["python", "-m", "app.submarine", "scan"]

        states: dict = {
            "RunSubmarineScan": {
                "Type": "Task",
                "Resource": "arn:aws:states:::ecs:runTask.sync",
                "Parameters": {
                    "Cluster": cluster_arn,
                    "TaskDefinition": scanner_task_family,
                    "LaunchType": "FARGATE",
                    "NetworkConfiguration": {
                        "AwsvpcConfiguration": {
                            "Subnets": subnet_ids,
                            "SecurityGroups": (
                                [scanner_security_group_id]
                                if scanner_security_group_id
                                else []
                            ),
                            "AssignPublicIp": "DISABLED",
                        }
                    },
                    "Overrides": {
                        "ContainerOverrides": [
                            {
                                "Name": scanner_container_name,
                                "Command": scan_command,
                                "Environment": container_env,
                            }
                        ]
                    },
                },
                "ResultPath": "$.taskResult",
                "Retry": [
                    {
                        "ErrorEquals": [
                            "States.TaskFailed",
                            "ECS.AmazonECSException",
                        ],
                        "IntervalSeconds": 120,
                        "MaxAttempts": 2,
                        "BackoffRate": 2.0,
                    }
                ],
                "Catch": [
                    {
                        "ErrorEquals": ["States.ALL"],
                        "ResultPath": "$.error",
                        "Next": "ScanFailed",
                    }
                ],
                "Next": "WaitForCrawlSoak",
            },
            "WaitForCrawlSoak": {
                "Type": "Wait",
                "Seconds": 1800,
                "Comment": "Wait 30 min for crawlers to process initial batch",
                "Next": "CheckCrawlersDone",
            },
            "CheckCrawlersDone": {
                "Type": "Task",
                "Resource": "arn:aws:states:::lambda:invoke",
                "Parameters": {
                    "FunctionName": self.check_queue_lambda.function_arn,
                    "Payload": {
                        "queue_url": submarine_queue_url,
                    },
                },
                "ResultSelector": {
                    "is_empty.$": "$.Payload.is_empty",
                },
                "ResultPath": "$.queueCheck",
                "Next": "IsCrawlComplete",
            },
            "IsCrawlComplete": {
                "Type": "Choice",
                "Choices": [
                    {
                        "Variable": "$.queueCheck.is_empty",
                        "BooleanEquals": True,
                        "Next": "RunBatcher",
                    }
                ],
                "Default": "WaitMoreForCrawlers",
            },
            "WaitMoreForCrawlers": {
                "Type": "Wait",
                "Seconds": 300,
                "Next": "CheckCrawlersDone",
            },
            "ScanComplete": {
                "Type": "Succeed",
            },
            "ScanFailed": {
                "Type": "Fail",
                "Cause": "Submarine scan task failed",
                "Error": "SubmarineScanFailed",
            },
        }

        # Add batcher step if batcher Lambda ARN is provided
        if batcher_lambda_arn:
            states["RunBatcher"] = {
                "Type": "Task",
                "Resource": "arn:aws:states:::lambda:invoke",
                "Parameters": {
                    "FunctionName": batcher_lambda_arn,
                    "Payload": {
                        "source": "submarine",
                        "execution_id.$": "$$.Execution.Id",
                    },
                },
                "ResultPath": "$.batchResult",
                "Next": "ScanComplete",
                "Retry": [
                    {
                        "ErrorEquals": [
                            "Lambda.ServiceException",
                            "Lambda.AWSLambdaException",
                        ],
                        "IntervalSeconds": 60,
                        "MaxAttempts": 2,
                        "BackoffRate": 2,
                    }
                ],
                "Catch": [
                    {
                        "ErrorEquals": ["States.ALL"],
                        "Next": "BatchFailed",
                    }
                ],
            }
            states["BatchFailed"] = {
                "Type": "Fail",
                "Cause": "Submarine batcher failed",
                "Error": "SubmarineBatchFailed",
            }
        else:
            # No batcher — go straight to ScanComplete after crawl drains
            states["IsCrawlComplete"]["Choices"][0]["Next"] = "ScanComplete"

        definition = {
            "Comment": f"Submarine enrichment pipeline for {environment_name}",
            "StartAt": "RunSubmarineScan",
            "States": states,
        }

        # IAM role for the state machine
        role = iam.Role(
            self,
            "SubmarineStateMachineRole",
            assumed_by=iam.ServicePrincipal("states.amazonaws.com"),
        )

        # Allow running ECS tasks
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["ecs:RunTask", "ecs:StopTask", "ecs:DescribeTasks"],
                resources=["*"],
                conditions={
                    "ArnEquals": {"ecs:cluster": cluster_arn},
                },
            )
        )

        # Allow passing the task role
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["iam:PassRole"],
                resources=["*"],
                conditions={
                    "StringLike": {
                        "iam:PassedToService": "ecs-tasks.amazonaws.com"
                    },
                },
            )
        )

        # Allow EventBridge sync (.sync integration needs events access)
        role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "events:PutTargets",
                    "events:PutRule",
                    "events:DescribeRule",
                ],
                resources=[
                    f"arn:aws:events:{Stack.of(self).region}:{Stack.of(self).account}:rule/StepFunctionsGetEventsForECSTaskRule",
                ],
            )
        )

        # Allow invoking the check-queue Lambda
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["lambda:InvokeFunction"],
                resources=[self.check_queue_lambda.function_arn],
            )
        )

        # Allow invoking the batcher Lambda (if provided)
        if batcher_lambda_arn:
            role.add_to_policy(
                iam.PolicyStatement(
                    actions=["lambda:InvokeFunction"],
                    resources=[batcher_lambda_arn],
                )
            )

        # State machine
        self.state_machine = sfn.CfnStateMachine(
            self,
            "SubmarineStateMachine",
            state_machine_name=f"pantry-pirate-radio-submarine-{environment_name}",
            definition_string=json.dumps(definition),
            role_arn=role.role_arn,
            state_machine_type="STANDARD",
        )

        # EventBridge schedule (weekly, disabled by default in dev)
        self.schedule_rule = events.CfnRule(
            self,
            "SubmarineScheduleRule",
            name=f"pantry-pirate-radio-submarine-schedule-{environment_name}",
            description="Weekly submarine enrichment scan",
            schedule_expression=schedule_expression,
            state="ENABLED" if schedule_enabled else "DISABLED",
            targets=[
                events.CfnRule.TargetProperty(
                    arn=self.state_machine.attr_arn,
                    id="SubmarineStateMachine",
                    role_arn=role.role_arn,
                    input=json.dumps({}),
                )
            ],
        )

    def _create_check_queue_lambda(
        self, submarine_queue_url: str
    ) -> _lambda.Function:
        """Create inline Lambda that checks SQS queue depth.

        Returns ``{"is_empty": true}`` when the queue has 0 visible
        and 0 in-flight messages.
        """
        log_group = logs.LogGroup(
            self,
            "CheckQueueLambdaLogs",
            log_group_name=(
                f"/aws/lambda/pantry-pirate-radio-submarine-check-queue-"
                f"{self.environment_name}"
            ),
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=(
                RemovalPolicy.RETAIN
                if self.environment_name == "prod"
                else RemovalPolicy.DESTROY
            ),
        )

        fn = _lambda.Function(
            self,
            "CheckQueueLambda",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=_lambda.Code.from_inline(CHECK_QUEUE_CODE),
            timeout=Duration.seconds(30),
            memory_size=128,
            log_group=log_group,
            environment={
                "DEFAULT_QUEUE_URL": submarine_queue_url,
            },
        )

        # Grant SQS GetQueueAttributes permission
        fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["sqs:GetQueueAttributes"],
                resources=["*"],
            )
        )

        return fn
