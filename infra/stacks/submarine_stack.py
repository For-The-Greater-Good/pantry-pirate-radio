"""Submarine Step Functions orchestration stack.

Creates a Step Functions state machine that runs the submarine scanner
(crawl food bank websites for missing data). Can be scheduled weekly
or triggered on-demand via `./bouy submarine --aws`.

Resources:
    - Step Functions state machine with ECS:runTask integration
    - EventBridge rule for weekly scheduling (disabled by default in dev)
    - IAM roles for Step Functions execution and ECS task launching

Attributes:
    state_machine: Step Functions state machine
    schedule_rule: EventBridge schedule rule
"""

import json

from aws_cdk import Stack
from aws_cdk import aws_events as events
from aws_cdk import aws_iam as iam
from aws_cdk import aws_stepfunctions as sfn
from constructs import Construct


class SubmarineStack(Stack):
    """Submarine orchestration via Step Functions.

    Runs the submarine scanner as an ECS Fargate task using the
    submarine scanner task definition (which has DB access and the
    submarine ECR image).
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
        schedule_enabled: bool = False,
        schedule_expression: str = "rate(7 days)",
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.environment_name = environment_name

        # Container env overrides for the scanner task.
        # The task definition already has DB and queue env vars from
        # get_submarine_environment(). We override SERVICE_TYPE to bypass
        # the docker-entrypoint.sh routing and run the command directly.
        container_env = [
            {"Name": "SERVICE_TYPE", "Value": "exec"},
            {"Name": "PYTHONUNBUFFERED", "Value": "1"},
        ]

        # State machine definition (ASL JSON)
        # Uses ecs:runTask.sync to run scanner as a Fargate task.
        # TODO: Wire up input passthrough so state machine input
        # {"limit": 5, "scraper_id": "food_oasis_la"} is forwarded
        # as SUBMARINE_LIMIT / SUBMARINE_SCRAPER_FILTER env vars
        # to __main__.py via Step Functions JsonPath overrides.
        scan_command = ["python", "-m", "app.submarine", "scan"]
        definition = {
            "Comment": f"Submarine enrichment pipeline for {environment_name}",
            "StartAt": "RunSubmarineScan",
            "States": {
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
                    "Next": "ScanComplete",
                },
                "ScanComplete": {
                    "Type": "Succeed",
                },
                "ScanFailed": {
                    "Type": "Fail",
                    "Cause": "Submarine scan task failed",
                    "Error": "SubmarineScanFailed",
                },
            },
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
