"""Submarine Stack — Step Functions orchestration for web crawling enrichment.

Creates a standalone state machine that triggers submarine scans
(crawl food bank websites for missing data). Can be scheduled weekly
or triggered manually via ./bouy submarine --aws.

Accepts parameters for filtering by scraper and limiting job count.
"""

import json

from aws_cdk import Duration, Stack
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_stepfunctions as sfn
from constructs import Construct


class SubmarineStack(Stack):
    """Submarine orchestration for Pantry Pirate Radio.

    Creates:
    - Step Functions state machine that runs the submarine scanner as an ECS task
    - EventBridge rule for weekly scheduling (disabled by default in dev)

    The state machine runs a single ECS task with the scanner command,
    accepting optional scraper_id and limit parameters.

    Input format:
        {"scraper_id": "optional_scraper_name", "limit": 50}

    Attributes:
        state_machine: Step Functions state machine
        schedule_rule: EventBridge schedule rule
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
        scanner_container_name: str = "AppContainer",
        submarine_queue_url: str = "",
        schedule_enabled: bool = False,
        schedule_expression: str = "rate(7 days)",
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.environment_name = environment_name

        # Build the scanner command with optional parameters
        # The container runs: python -m app.submarine scan [--scraper X] [--limit N]
        # Parameters are injected via ContainerOverrides from Step Functions input
        base_cmd = ["python", "-m", "app.submarine", "scan"]

        # Build container environment
        container_env = [
            {"Name": "SUBMARINE_QUEUE_URL", "Value": submarine_queue_url},
        ]

        # State machine definition (ASL JSON)
        # Uses ecs:runTask.sync to run scanner as a Fargate task
        definition = {
            "Comment": f"Submarine enrichment pipeline for {environment_name}",
            "StartAt": "BuildScanCommand",
            "States": {
                "BuildScanCommand": {
                    "Type": "Pass",
                    "Parameters": {
                        "command.$": "States.Array('python', '-m', 'app.submarine', 'scan')",
                        "scraper_id.$": "$.scraper_id",
                        "limit.$": "$.limit",
                    },
                    "ResultPath": "$.config",
                    "Next": "RunSubmarineScan",
                },
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
                                "AssignPublicIp": "DISABLED",
                            }
                        },
                        "Overrides": {
                            "ContainerOverrides": [
                                {
                                    "Name": scanner_container_name,
                                    "Command.$": "$.config.command",
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
            description="Role for Submarine Step Functions state machine",
        )

        # Grant ECS RunTask
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["ecs:RunTask"],
                resources=["*"],
                conditions={
                    "ArnLike": {
                        "ecs:cluster": cluster_arn,
                    }
                },
            )
        )

        # Grant PassRole for task execution and task roles
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["iam:PassRole"],
                resources=["*"],
                conditions={
                    "StringLike": {
                        "iam:PassedToService": "ecs-tasks.amazonaws.com",
                    }
                },
            )
        )

        # Grant StopTask and DescribeTasks for .sync integration
        role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "ecs:StopTask",
                    "ecs:DescribeTasks",
                    "events:PutTargets",
                    "events:PutRule",
                    "events:DescribeRule",
                ],
                resources=["*"],
            )
        )

        # Create the state machine
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
                    input=json.dumps({"scraper_id": None, "limit": None}),
                )
            ],
        )
