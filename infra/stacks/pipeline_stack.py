"""Pipeline Stack for Pantry Pirate Radio.

Creates Step Functions state machine for scraper orchestration
with EventBridge schedules for automated daily scraper runs
and publisher (SQLite export to S3) tasks.
"""

import json

from aws_cdk import Duration, Stack
from aws_cdk import aws_ec2 as ec2
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
    with configurable concurrency (default: unlimited).

    Attributes:
        state_machine: Step Functions state machine
        schedule_rule: EventBridge schedule rule
    """

    # List of scrapers to run - can be customized per environment
    DEFAULT_SCRAPERS = [
        "vivery_api",
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
        max_concurrency: int = 0,
        scrapers: list[str] | None = None,
        publisher_task_family: str | None = None,
        publisher_task_role_arn: str | None = None,
        publisher_execution_role_arn: str | None = None,
        publisher_schedule_enabled: bool = False,
        staging_queue_url: str | None = None,
        batcher_lambda_arn: str | None = None,
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
            schedule_enabled: Whether to enable the daily scraper schedule
            max_concurrency: Maximum concurrent scraper tasks
            scrapers: List of scraper names to run (defaults to DEFAULT_SCRAPERS)
            publisher_task_family: Publisher task definition family name for SQLite export
            publisher_task_role_arn: IAM role ARN for the publisher task (cross-stack reference)
            publisher_execution_role_arn: IAM execution role ARN for the publisher task
                definition. Required so EventBridge can iam:PassRole on both task and
                execution roles when starting the scheduled ECS task.
            publisher_schedule_enabled: Whether to enable the daily publisher schedule
            staging_queue_url: SQS staging queue URL (overrides SQS_QUEUE_URL in scraper containers)
            batcher_lambda_arn: Batcher Lambda ARN (adds BatchOrForward step after scrapers)
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
            raise ValueError(
                "Either scraper_task_family or scraper_task_definition must be provided"
            )

        # Create state machine
        self.state_machine = self._create_state_machine(
            cluster=cluster,
            task_family=task_family,
            container_name=container_name,
            max_concurrency=max_concurrency,
            staging_queue_url=staging_queue_url,
            batcher_lambda_arn=batcher_lambda_arn,
        )

        # Create EventBridge schedule rule for scrapers
        self.schedule_rule = self._create_schedule_rule(enabled=schedule_enabled)

        # Create EventBridge schedule rule for publisher (SQLite export to S3)
        self.publisher_schedule_rule: events.Rule | None = None
        if publisher_task_family:
            self.publisher_schedule_rule = self._create_publisher_schedule_rule(
                cluster=cluster,
                publisher_task_family=publisher_task_family,
                publisher_task_role_arn=publisher_task_role_arn,
                publisher_execution_role_arn=publisher_execution_role_arn,
                enabled=publisher_schedule_enabled,
            )

    def _create_state_machine(
        self,
        cluster: ecs.ICluster,
        task_family: str,
        container_name: str,
        max_concurrency: int,
        staging_queue_url: str | None = None,
        batcher_lambda_arn: str | None = None,
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
            staging_queue_url: Optional staging queue URL for batch inference
            batcher_lambda_arn: Optional batcher Lambda ARN for batch inference

        Returns:
            Step Functions state machine
        """
        # Build subnet list from cluster's private subnets
        subnet_ids = [s.subnet_id for s in cluster.vpc.private_subnets]

        # Build container environment overrides
        container_env = [
            {
                "Name": "SERVICE_TYPE",
                "Value": "scraper",
            },
            {
                "Name": "SCRAPER_NAME",
                "Value.$": "$.scraper_name",
            },
        ]

        # Override SQS_QUEUE_URL to staging queue when batch inference is enabled
        if staging_queue_url:
            container_env.append(
                {
                    "Name": "SQS_QUEUE_URL",
                    "Value": staging_queue_url,
                }
            )

        # Determine what RunAllScrapers transitions to
        after_scrapers = "BatchOrForward" if batcher_lambda_arn else "PipelineSummary"

        # Build the state machine definition as JSON
        # This avoids CDK's EcsRunTask construct which requires concrete
        # TaskDefinition and ContainerDefinition objects (incompatible
        # with imported/cross-stack task definitions)
        definition = {
            "Comment": f"Scraper pipeline for {self.environment_name}",
            "TimeoutSeconds": 43200,  # 12 hours — vivery paginates 117 regions
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
                                                "Environment": container_env,
                                            }
                                        ]
                                    },
                                },
                                "ResultSelector": {
                                    "exitCode.$": "$.Containers[0].ExitCode",
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
                                "Parameters": {
                                    "scraper_name.$": "$.scraper_name",
                                    "execution_id.$": "$.execution_id",
                                    "errorInfo": {
                                        "Error.$": "$.errorInfo.Error",
                                    },
                                    "taskResult": {"status": "FAILED"},
                                },
                                "End": True,
                            },
                            "TaskComplete": {
                                "Type": "Pass",
                                "Parameters": {
                                    "scraper_name.$": "$.scraper_name",
                                    "execution_id.$": "$.execution_id",
                                    "taskResult.$": "$.taskResult",
                                },
                                "End": True,
                            },
                        },
                    },
                    "Next": after_scrapers,
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

        # Add BatchOrForward loop when batcher Lambda is configured.
        # The batcher drains as many messages as it can within its time
        # budget and returns queue_empty: true/false. Step Functions loops
        # until the staging queue is fully drained.
        if batcher_lambda_arn:
            definition["States"]["BatchOrForward"] = {
                "Type": "Task",
                "Resource": "arn:aws:states:::lambda:invoke",
                "Parameters": {
                    "FunctionName": batcher_lambda_arn,
                    "Payload": {
                        "execution_id.$": "$$.Execution.Id",
                        "scrapers.$": "$.results",
                    },
                },
                "ResultSelector": {
                    "queue_empty.$": "$.Payload.queue_empty",
                    "mode.$": "$.Payload.mode",
                    "record_count.$": "$.Payload.record_count",
                },
                "ResultPath": "$.batchResult",
                "Next": "CheckQueueDrained",
                "Retry": [
                    {
                        "ErrorEquals": [
                            "Lambda.ServiceException",
                            "Lambda.TooManyRequestsException",
                            "Lambda.AWSLambdaException",
                        ],
                        "IntervalSeconds": 30,
                        "MaxAttempts": 3,
                        "BackoffRate": 2.0,
                    }
                ],
                "Catch": [
                    {
                        "ErrorEquals": ["States.ALL"],
                        "ResultPath": "$.batchError",
                        "Next": "PipelineSummary",
                    }
                ],
            }
            definition["States"]["CheckQueueDrained"] = {
                "Type": "Choice",
                "Choices": [
                    {
                        "Variable": "$.batchResult.queue_empty",
                        "BooleanEquals": True,
                        "Next": "PipelineSummary",
                    }
                ],
                "Default": "BatchOrForward",
            }

        # Create state machine with JSON definition
        state_machine = sfn.StateMachine(
            self,
            "ScraperPipeline",
            state_machine_name=f"pantry-pirate-scraper-pipeline-{self.environment_name}",
            definition_body=sfn.DefinitionBody.from_string(json.dumps(definition)),
            timeout=Duration.hours(4),
            tracing_enabled=True,
        )

        # Grant permissions for ECS task management
        # Scope to task definitions in this account/region with our naming prefix
        task_def_arn = (
            f"arn:aws:ecs:{Stack.of(self).region}:{Stack.of(self).account}"
            f":task-definition/pantry-pirate-radio-*"
        )
        task_arn = (
            f"arn:aws:ecs:{Stack.of(self).region}:{Stack.of(self).account}" f":task/*"
        )
        state_machine.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ecs:RunTask"],
                resources=[task_def_arn],
            )
        )
        state_machine.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ecs:StopTask", "ecs:DescribeTasks"],
                resources=[task_arn],
            )
        )
        state_machine.add_to_role_policy(
            iam.PolicyStatement(
                actions=["iam:PassRole"],
                resources=[
                    f"arn:aws:iam::{Stack.of(self).account}:role/pantry-pirate-radio-*",
                    f"arn:aws:iam::{Stack.of(self).account}:role/ServicesStack-{self.environment_name}-*",
                ],
            )
        )
        # Required for .sync integration (waits for task completion)
        state_machine_arn = (
            f"arn:aws:events:{Stack.of(self).region}:{Stack.of(self).account}"
            f":rule/StepFunctionsGetEventsForECSTaskRule"
        )
        state_machine.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "events:PutTargets",
                    "events:PutRule",
                    "events:DescribeRule",
                ],
                resources=[state_machine_arn],
            )
        )

        # Grant Lambda invoke if batcher is configured
        if batcher_lambda_arn:
            state_machine.add_to_role_policy(
                iam.PolicyStatement(
                    actions=["lambda:InvokeFunction"],
                    resources=[batcher_lambda_arn],
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
            description=f"Weekly scraper pipeline — Mondays 2 AM UTC",
            schedule=events.Schedule.cron(
                minute="0",
                hour="2",  # 2 AM UTC
                week_day="MON",
            ),
            enabled=enabled,
        )

        # Add state machine as target with default scraper list
        rule.add_target(
            targets.SfnStateMachine(
                self.state_machine,
                input=events.RuleTargetInput.from_object({"scrapers": self._scrapers}),
            )
        )

        return rule

    def _create_publisher_schedule_rule(
        self,
        cluster: ecs.ICluster,
        publisher_task_family: str,
        publisher_task_role_arn: str | None,
        publisher_execution_role_arn: str | None,
        enabled: bool,
    ) -> events.Rule:
        """Create EventBridge rule for daily publisher (SQLite export) schedule.

        Runs daily at midnight UTC.

        Args:
            cluster: ECS cluster for running publisher task
            publisher_task_family: Publisher task definition family name
            publisher_task_role_arn: IAM role ARN for the publisher task
            enabled: Whether the schedule is enabled

        Returns:
            EventBridge rule
        """
        rule = events.Rule(
            self,
            "DailyPublisherSchedule",
            rule_name=f"pantry-pirate-publisher-schedule-{self.environment_name}",
            description=f"Daily SQLite export schedule for {self.environment_name}",
            schedule=events.Schedule.cron(
                minute="0",
                hour="0",  # Midnight UTC
            ),
            enabled=enabled,
        )

        # Import the publisher task role by ARN (cross-stack reference, no hardcoded name)
        if publisher_task_role_arn:
            imported_task_role = iam.Role.from_role_arn(
                self,
                "ImportedPublisherTaskRole",
                role_arn=publisher_task_role_arn,
            )
        else:
            imported_task_role = iam.Role.from_role_name(
                self,
                "ImportedPublisherTaskRole",
                role_name=f"pantry-pirate-publisher-task-role-{self.environment_name}",
            )

        # Import the execution role so CDK grants iam:PassRole on it to the events
        # target role. Without this, EventBridge's RunTask call is denied because the
        # events role can't PassRole the auto-created execution role. Root cause of
        # the publisher schedule being broken.
        imported_execution_role = (
            iam.Role.from_role_arn(
                self,
                "ImportedPublisherExecutionRole",
                role_arn=publisher_execution_role_arn,
            )
            if publisher_execution_role_arn
            else None
        )

        imported_task_def = (
            ecs.FargateTaskDefinition.from_fargate_task_definition_attributes(
                self,
                "ImportedPublisherTask",
                task_definition_arn=(
                    f"arn:aws:ecs:{Stack.of(self).region}:{Stack.of(self).account}"
                    f":task-definition/{publisher_task_family}"
                ),
                network_mode=ecs.NetworkMode.AWS_VPC,
                task_role=imported_task_role,
                execution_role=imported_execution_role,
            )
        )

        rule.add_target(
            targets.EcsTask(
                cluster=cluster,
                task_definition=imported_task_def,
                subnet_selection=ec2.SubnetSelection(
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
                ),
            )
        )

        return rule
