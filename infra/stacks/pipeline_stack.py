"""Pipeline Stack for Pantry Pirate Radio.

Creates Step Functions state machine for scraper orchestration
with EventBridge schedule for automated daily runs.
"""

from aws_cdk import Duration, Stack
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_stepfunctions as sfn
from aws_cdk import aws_stepfunctions_tasks as tasks
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
        scraper_task_definition: ecs.FargateTaskDefinition,
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
            scraper_task_definition: Task definition for scraper tasks
            schedule_enabled: Whether to enable the daily schedule
            max_concurrency: Maximum concurrent scraper tasks
            scrapers: List of scraper names to run (defaults to DEFAULT_SCRAPERS)
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        self.environment_name = environment_name
        self._scrapers = scrapers or self.DEFAULT_SCRAPERS

        # Create state machine
        self.state_machine = self._create_state_machine(
            cluster=cluster,
            task_definition=scraper_task_definition,
            max_concurrency=max_concurrency,
        )

        # Create EventBridge schedule rule
        self.schedule_rule = self._create_schedule_rule(
            enabled=schedule_enabled
        )

    def _create_state_machine(
        self,
        cluster: ecs.ICluster,
        task_definition: ecs.FargateTaskDefinition,
        max_concurrency: int,
    ) -> sfn.StateMachine:
        """Create Step Functions state machine for scraper orchestration.

        The state machine:
        1. Takes a list of scraper names as input
        2. Runs each scraper as a Fargate task in parallel
        3. Collects results and failures

        Args:
            cluster: ECS cluster for tasks
            task_definition: Scraper task definition
            max_concurrency: Maximum concurrent tasks

        Returns:
            Step Functions state machine
        """
        # Define the ECS RunTask action for a single scraper
        run_scraper_task = tasks.EcsRunTask(
            self,
            "RunScraperTask",
            integration_pattern=sfn.IntegrationPattern.RUN_JOB,
            cluster=cluster,
            task_definition=task_definition,
            launch_target=tasks.EcsFargateLaunchTarget(
                platform_version=ecs.FargatePlatformVersion.LATEST,
            ),
            container_overrides=[
                tasks.ContainerOverride(
                    container_definition=task_definition.default_container,
                    environment=[
                        tasks.TaskEnvironmentVariable(
                            name="SCRAPER_NAME",
                            value=sfn.JsonPath.string_at("$.scraper_name"),
                        ),
                    ],
                ),
            ],
            result_path="$.taskResult",
        )

        # Add retry configuration for transient failures
        run_scraper_task.add_retry(
            errors=["States.TaskFailed", "ECS.AmazonECSException"],
            interval=Duration.seconds(60),
            max_attempts=2,
            backoff_rate=2.0,
        )

        # Add catch for permanent failures - continue with other scrapers
        run_scraper_task.add_catch(
            handler=sfn.Pass(
                self,
                "RecordFailure",
                result=sfn.Result.from_object({"status": "FAILED"}),
                result_path="$.taskResult",
            ),
            errors=["States.ALL"],
            result_path="$.errorInfo",
        )

        # Create Map state to run scrapers in parallel
        map_state = sfn.Map(
            self,
            "RunAllScrapers",
            items_path="$.scrapers",
            parameters={
                "scraper_name.$": "$$.Map.Item.Value",
                "execution_id.$": "$$.Execution.Id",
            },
            max_concurrency=max_concurrency,
            result_path="$.results",
        )
        map_state.iterator(run_scraper_task)

        # Create pipeline summary step
        pipeline_summary = sfn.Pass(
            self,
            "PipelineSummary",
            parameters={
                "execution_id.$": "$$.Execution.Id",
                "results.$": "$.results",
                "scraper_count.$": "States.ArrayLength($.scrapers)",
            },
        )

        # Build the state machine definition
        definition = map_state.next(pipeline_summary)

        # Create the state machine
        state_machine = sfn.StateMachine(
            self,
            "ScraperPipeline",
            state_machine_name=f"pantry-pirate-scraper-pipeline-{self.environment_name}",
            definition=definition,
            timeout=Duration.hours(4),  # Max 4 hours for all scrapers
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
