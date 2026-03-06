"""Pipeline Stack for Pantry Pirate Radio.

Creates Step Functions state machine for scraper orchestration
with EventBridge schedule for automated daily runs.
"""

import json

from aws_cdk import Duration, Stack
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_stepfunctions as sfn
from constructs import Construct


class PipelineStack(Stack):
    """Scraper pipeline orchestration for Pantry Pirate Radio.

    Creates:
    - Step Functions state machine for running scrapers
    - EventBridge rule for daily scheduling (disabled by default in dev)

    The state machine uses a Map state to run scrapers in parallel
    with configurable concurrency (default: 10).

    Attributes:
        state_machine: Step Functions state machine
        schedule_rule: EventBridge schedule rule
    """

    # List of scrapers to run - can be customized per environment
    DEFAULT_SCRAPERS = [
        "vivery_api",
        "feeding_america",
        # Add more scrapers as they're created
    ]

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        environment_name: str = "dev",
        cluster: ecs.ICluster,
        scraper_task_definition: ecs.FargateTaskDefinition | None = None,
        scraper_task_family: str | None = None,
        scraper_container_name: str = "ScraperContainer",
        schedule_enabled: bool = False,
        max_concurrency: int = 10,
        scrapers: list[str] | None = None,
        **kwargs,
    ) -> None:
        """Initialize PipelineStack.

        Args:
            scope: CDK scope
            construct_id: Unique identifier for this construct
            environment_name: Environment name (dev, staging, prod)
            cluster: ECS cluster for running scraper tasks
            scraper_task_definition: Task definition for scraper tasks (deprecated, use scraper_task_family)
            scraper_task_family: Task definition family name (avoids cross-stack export on ARN)
            scraper_container_name: Container name in the task definition
            schedule_enabled: Whether to enable the daily schedule
            max_concurrency: Maximum concurrent scraper tasks
            scrapers: List of scraper names to run (defaults to DEFAULT_SCRAPERS)
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        self.environment_name = environment_name
        self._scrapers = scrapers or self.DEFAULT_SCRAPERS

        # Resolve task family name: prefer string (no cross-stack export) over object reference
        if scraper_task_family:
            task_family = scraper_task_family
            container_name = scraper_container_name
        elif scraper_task_definition:
            task_family = scraper_task_definition.family
            container_name = (
                scraper_task_definition.default_container.container_name
                if scraper_task_definition.default_container
                else scraper_container_name
            )
        else:
            raise ValueError("Either scraper_task_family or scraper_task_definition must be provided")

        # Create state machine
        self.state_machine = self._create_state_machine(
            cluster=cluster,
            task_family=task_family,
            container_name=container_name,
            max_concurrency=max_concurrency,
        )

        # Create EventBridge schedule rule
        self.schedule_rule = self._create_schedule_rule(
            enabled=schedule_enabled
        )

    def _create_state_machine(
        self,
        cluster: ecs.ICluster,
        task_family: str,
        container_name: str,
        max_concurrency: int,
    ) -> sfn.StateMachine:
        """Create Step Functions state machine for scraper orchestration.

        Uses a raw JSON definition to avoid CDK cross-stack export issues.
        The task definition is referenced by family name (a stable string)
        rather than by ARN (which changes on every task definition revision).

        Args:
            cluster: ECS cluster for tasks
            task_family: Task definition family name
            container_name: Name of the container in the task definition
            max_concurrency: Maximum concurrent tasks

        Returns:
            Step Functions state machine
        """
        # Build subnet list from cluster's private subnets
        subnet_ids = [s.subnet_id for s in cluster.vpc.private_subnets]

        # Build the state machine definition as JSON
        # This avoids CDK's EcsRunTask construct which requires concrete
        # TaskDefinition and ContainerDefinition objects (incompatible
        # with imported/cross-stack task definitions)
        definition = {
            "Comment": f"Scraper pipeline for {self.environment_name}",
            "StartAt": "RunAllScrapers",
            "States": {
                "RunAllScrapers": {
                    "Type": "Map",
                    "ItemsPath": "$.scrapers",
                    "ItemSelector": {
                        "scraper_name.$": "$$.Map.Item.Value",
                        "execution_id.$": "$$.Execution.Id",
                    },
                    "MaxConcurrency": max_concurrency,
                    "ResultPath": "$.results",
                    "ItemProcessor": {
                        "ProcessorConfig": {"Mode": "INLINE"},
                        "StartAt": "RunScraperTask",
                        "States": {
                            "RunScraperTask": {
                                "Type": "Task",
                                "Resource": "arn:aws:states:::ecs:runTask.sync",
                                "Parameters": {
                                    "Cluster": cluster.cluster_arn,
                                    "TaskDefinition": task_family,
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
                                                "Name": container_name,
                                                "Environment": [
                                                    {
                                                        "Name": "SERVICE_TYPE",
                                                        "Value": "scraper",
                                                    },
                                                    {
                                                        "Name": "SCRAPER_NAME",
                                                        "Value.$": "$.scraper_name",
                                                    },
                                                ],
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
                                        "IntervalSeconds": 60,
                                        "MaxAttempts": 2,
                                        "BackoffRate": 2.0,
                                    }
                                ],
                                "Catch": [
                                    {
                                        "ErrorEquals": ["States.ALL"],
                                        "ResultPath": "$.errorInfo",
                                        "Next": "RecordFailure",
                                    }
                                ],
                                "Next": "TaskComplete",
                            },
                            "RecordFailure": {
                                "Type": "Pass",
                                "Result": {"status": "FAILED"},
                                "ResultPath": "$.taskResult",
                                "End": True,
                            },
                            "TaskComplete": {
                                "Type": "Succeed",
                            },
                        },
                    },
                    "Next": "PipelineSummary",
                },
                "PipelineSummary": {
                    "Type": "Pass",
                    "Parameters": {
                        "execution_id.$": "$$.Execution.Id",
                        "results.$": "$.results",
                    },
                    "End": True,
                },
            },
        }

        # Create state machine with JSON definition
        state_machine = sfn.StateMachine(
            self,
            "ScraperPipeline",
            state_machine_name=f"pantry-pirate-scraper-pipeline-{self.environment_name}",
            definition_body=sfn.DefinitionBody.from_string(
                json.dumps(definition)
            ),
            timeout=Duration.hours(4),
        )

        # Grant permissions for ECS task management
        state_machine.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ecs:RunTask", "ecs:StopTask", "ecs:DescribeTasks"],
                resources=["*"],
            )
        )
        state_machine.add_to_role_policy(
            iam.PolicyStatement(
                actions=["iam:PassRole"],
                resources=["*"],
            )
        )
        # Required for .sync integration (waits for task completion)
        state_machine.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "events:PutTargets",
                    "events:PutRule",
                    "events:DescribeRule",
                ],
                resources=["*"],
            )
        )

        return state_machine

    def _create_schedule_rule(self, enabled: bool) -> events.Rule:
        """Create EventBridge rule for daily scraper schedule.

        Runs daily at 2 AM UTC by default.

        Args:
            enabled: Whether the schedule is enabled

        Returns:
            EventBridge rule
        """
        # Create the schedule rule
        rule = events.Rule(
            self,
            "DailyScraperSchedule",
            rule_name=f"pantry-pirate-scraper-schedule-{self.environment_name}",
            description=f"Daily scraper pipeline schedule for {self.environment_name}",
            schedule=events.Schedule.cron(
                minute="0",
                hour="2",  # 2 AM UTC
            ),
            enabled=enabled,
        )

        # Add state machine as target with default scraper list
        rule.add_target(
            targets.SfnStateMachine(
                self.state_machine,
                input=events.RuleTargetInput.from_object(
                    {"scrapers": self._scrapers}
                ),
            )
        )

        return rule
