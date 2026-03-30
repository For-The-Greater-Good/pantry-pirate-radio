"""CDK Stack for ppr-beacon: static mini-site hosting + build pipeline.

S3 + CloudFront for static HTML, Lambda for build orchestration,
Step Functions for workflow, EventBridge for scheduling, DynamoDB for
build metadata and analytics, Athena for CloudFront log analysis.
"""

from __future__ import annotations

from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
)
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_cloudwatch_actions as cw_actions
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_glue as glue
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subs
from aws_cdk import aws_stepfunctions as sfn
from aws_cdk import aws_stepfunctions_tasks as sfn_tasks
from constructs import Construct


class BeaconStack(Stack):
    """Static mini-site hosting with automated build pipeline.

    Requires plugin_context with:
        vpc: ec2.IVpc
        proxy_endpoint: str (RDS Proxy hostname)
        proxy_security_group: ec2.ISecurityGroup
        database_credentials_secret: secretsmanager.ISecret
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        environment_name: str = "dev",
        plugin_context: dict | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.environment_name = environment_name
        ctx = plugin_context or {}
        env = environment_name

        vpc = ctx.get("vpc")
        proxy_endpoint = ctx.get("proxy_endpoint", "")
        db_secret = ctx.get("database_credentials_secret")

        # --- Alarm topic (Principle XIV Plugin Exception) ---
        alarm_topic = sns.Topic.from_topic_arn(
            self,
            "AlertsTopic",
            topic_arn=f"arn:aws:sns:{self.region}:{self.account}"
            f":pantry-pirate-radio-alerts-{env}",
        )

        # ── S3: Static Site Bucket ──────────────────────────────────
        site_bucket = s3.Bucket(
            self,
            "BeaconSiteBucket",
            bucket_name=f"ppr-beacon-site-{env}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            removal_policy=RemovalPolicy.RETAIN,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        )

        # ── S3: CloudFront Access Logs ──────────────────────────────
        log_bucket = s3.Bucket(
            self,
            "BeaconLogBucket",
            bucket_name=f"ppr-beacon-logs-{env}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            removal_policy=RemovalPolicy.DESTROY,
            lifecycle_rules=[
                s3.LifecycleRule(expiration=Duration.days(90)),
            ],
        )

        # ── CloudFront Distribution ─────────────────────────────────
        oai = cloudfront.OriginAccessIdentity(
            self,
            "BeaconOAI",
            comment=f"ppr-beacon OAI {env}",
        )
        site_bucket.grant_read(oai)

        distribution = cloudfront.Distribution(
            self,
            "BeaconDistribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3Origin(
                    site_bucket,
                    origin_access_identity=oai,
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                compress=True,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
            ),
            default_root_object="index.html",
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=404,
                    response_page_path="/404.html",
                    ttl=Duration.seconds(60),
                ),
            ],
            enable_logging=True,
            log_bucket=log_bucket,
            log_file_prefix="cf-logs/",
        )

        # ── DynamoDB: Build Metadata ────────────────────────────────
        build_table = dynamodb.Table(
            self,
            "BeaconBuildMetadata",
            table_name=f"ppr-beacon-build-{env}",
            partition_key=dynamodb.Attribute(
                name="location_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ── DynamoDB: Analytics Events ──────────────────────────────
        analytics_table = dynamodb.Table(
            self,
            "BeaconAnalyticsEvents",
            table_name=f"ppr-beacon-analytics-{env}",
            partition_key=dynamodb.Attribute(
                name="page_path", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            time_to_live_attribute="expires_at",
        )

        # ── Glue: Athena-queryable log schema ───────────────────────
        glue_db = glue.CfnDatabase(
            self,
            "BeaconLogGlueDB",
            catalog_id=self.account,
            database_input=glue.CfnDatabase.DatabaseInputProperty(
                name=f"ppr_beacon_logs_{env}",
                description="CloudFront access logs for ppr-beacon",
            ),
        )

        # ── Build Lambda (VPC for RDS Proxy access) ─────────────────
        if vpc:
            self.lambda_sg = ec2.SecurityGroup(
                self,
                "BeaconBuildSG",
                vpc=vpc,
                description="Beacon build Lambda security group",
                allow_all_outbound=True,
            )

            build_log_group = logs.LogGroup(
                self,
                "BeaconBuildLogs",
                log_group_name=f"/aws/lambda/ppr-beacon-build-{env}",
                retention=logs.RetentionDays.TWO_WEEKS,
                removal_policy=RemovalPolicy.DESTROY,
            )

            build_function = _lambda.DockerImageFunction(
                self,
                "BeaconBuildFunction",
                function_name=f"ppr-beacon-build-{env}",
                code=_lambda.DockerImageCode.from_image_asset(
                    str(__file__).rsplit("/infra/", 1)[0],
                    file=".docker/Dockerfile",
                ),
                timeout=Duration.minutes(15),
                memory_size=1024,
                vpc=vpc,
                vpc_subnets=ec2.SubnetSelection(
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                ),
                security_groups=[self.lambda_sg],
                log_group=build_log_group,
                environment={
                    "DATABASE_SECRET_ARN": (
                        db_secret.secret_arn if db_secret else ""
                    ),
                    "DATABASE_PROXY_ENDPOINT": proxy_endpoint,
                    "BEACON_S3_BUCKET": site_bucket.bucket_name,
                    "BEACON_CLOUDFRONT_DIST_ID": distribution.distribution_id,
                    "BEACON_BASE_URL": f"https://providers.plentiful.org",
                    "ENVIRONMENT": env,
                },
            )

            if db_secret:
                db_secret.grant_read(build_function)
            site_bucket.grant_read_write(build_function)

            # CloudFront invalidation permission
            build_function.add_to_role_policy(
                iam.PolicyStatement(
                    actions=["cloudfront:CreateInvalidation"],
                    resources=[
                        f"arn:aws:cloudfront::{self.account}"
                        f":distribution/{distribution.distribution_id}"
                    ],
                )
            )

            # DynamoDB access for build metadata
            build_table.grant_read_write_data(build_function)

            # ── Step Functions Workflow ──────────────────────────────
            build_task = sfn_tasks.LambdaInvoke(
                self,
                "RunBuild",
                lambda_function=build_function,
                result_path="$.buildResult",
            )

            state_machine = sfn.StateMachine(
                self,
                "BeaconBuildStateMachine",
                state_machine_name=f"ppr-beacon-build-{env}",
                definition_body=sfn.DefinitionBody.from_chainable(build_task),
                timeout=Duration.minutes(30),
            )

            # ── EventBridge: Daily rebuild (prod only) ──────────────
            is_prod = env == "prod"
            events.Rule(
                self,
                "BeaconDailyBuild",
                rule_name=f"ppr-beacon-daily-build-{env}",
                schedule=events.Schedule.cron(
                    hour="4", minute="0",
                ),
                targets=[targets.SfnStateMachine(state_machine)],
                enabled=is_prod,
            )

            # ── SNS Subscription: verification events trigger rebuild
            lighthouse_topic_arn = (
                f"arn:aws:sns:{self.region}:{self.account}"
                f":ppr-lighthouse-events-{env}"
            )
            lighthouse_topic = sns.Topic.from_topic_arn(
                self, "LighthouseEventsTopic", lighthouse_topic_arn
            )
            lighthouse_topic.add_subscription(
                subs.LambdaSubscription(build_function)
            )

            # ── CloudWatch Alarms (Principle XIV) ───────────────────
            # Build Lambda
            cloudwatch.Alarm(
                self,
                "BeaconBuildErrors",
                alarm_name=f"ppr-beacon-build-errors-{env}",
                metric=build_function.metric_errors(),
                threshold=5,
                evaluation_periods=2,
                treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
            ).add_alarm_action(cw_actions.SnsAction(alarm_topic))

            cloudwatch.Alarm(
                self,
                "BeaconBuildThrottles",
                alarm_name=f"ppr-beacon-build-throttles-{env}",
                metric=build_function.metric_throttles(),
                threshold=1,
                evaluation_periods=2,
                treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
            ).add_alarm_action(cw_actions.SnsAction(alarm_topic))

            # Step Functions
            cloudwatch.Alarm(
                self,
                "BeaconSfnFailed",
                alarm_name=f"ppr-beacon-sfn-failed-{env}",
                metric=state_machine.metric_failed(),
                threshold=1,
                evaluation_periods=1,
                treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
            ).add_alarm_action(cw_actions.SnsAction(alarm_topic))

        # ── DynamoDB Alarms (always, even without VPC) ──────────────
        for table, name in [
            (build_table, "build"),
            (analytics_table, "analytics"),
        ]:
            cloudwatch.Alarm(
                self,
                f"Beacon{name.title()}Throttles",
                alarm_name=f"ppr-beacon-{name}-throttles-{env}",
                metric=table.metric_throttled_requests_for_operation(
                    "PutItem"
                ),
                threshold=1,
                evaluation_periods=1,
                treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
            ).add_alarm_action(cw_actions.SnsAction(alarm_topic))

            cloudwatch.Alarm(
                self,
                f"Beacon{name.title()}SystemErrors",
                alarm_name=f"ppr-beacon-{name}-syserr-{env}",
                metric=cloudwatch.Metric(
                    namespace="AWS/DynamoDB",
                    metric_name="SystemErrors",
                    dimensions_map={"TableName": table.table_name},
                    statistic="Sum",
                    period=Duration.minutes(5),
                ),
                threshold=1,
                evaluation_periods=1,
                treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
            ).add_alarm_action(cw_actions.SnsAction(alarm_topic))

        # ── Outputs ─────────────────────────────────────────────────
        CfnOutput(
            self,
            "BeaconSiteUrl",
            value=f"https://{distribution.distribution_domain_name}",
        )
        CfnOutput(
            self,
            "BeaconBucketName",
            value=site_bucket.bucket_name,
        )
        CfnOutput(
            self,
            "BeaconDistributionId",
            value=distribution.distribution_id,
        )
