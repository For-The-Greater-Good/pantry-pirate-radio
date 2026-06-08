"""Federation archive tiering + retention-prune stack (P1 PR-D, Tasks 9-10).

The AWS realization of the federation log retention prune (the Docker twin is
``./bouy federation prune``). It provisions:

* a **dedicated, never-expiring** S3 archive bucket (§6.2g: "never destroy" — NO
  lifecycle expiry, versioned, public access blocked, retained in prod) that the
  prune writes each over-SLA leaf's exact signed bytes to BEFORE trimming the live
  Postgres window, so checkpoints + consistency proofs stay valid forever;
* an EventBridge-scheduled **prune Lambda** (VPC + RDS Proxy + Secrets Manager DB
  password, reusing the batch-lambda image with the
  ``app.federation.prune_lambda.handler`` cmd), enabled ONLY in prod;
* the Lambda's CloudWatch Errors alarm lives in ``MonitoringStack`` (Principle XIV),
  wired by threading ``prune_lambda.function_name`` through ``app.py``.
"""

from __future__ import annotations

from aws_cdk import Duration, RemovalPolicy, Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from constructs import Construct


class FederationStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        environment_name: str,
        vpc: ec2.IVpc,
        database_proxy_endpoint: str | None = None,
        database_secret=None,
        proxy_security_group: ec2.ISecurityGroup | None = None,
        ecr_repository=None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.environment_name = environment_name
        self._vpc = vpc
        self.ecr_repository = ecr_repository

        self.archive_bucket = self._create_archive_bucket()
        self.prune_security_group = ec2.SecurityGroup(
            self,
            "FederationPruneSG",
            vpc=vpc,
            description="Federation prune Lambda - DB access via RDS Proxy",
        )
        self.prune_lambda = self._create_prune_lambda(
            database_proxy_endpoint=database_proxy_endpoint,
            database_secret=database_secret,
        )
        self.archive_bucket.grant_read_write(self.prune_lambda)
        if database_secret is not None:
            database_secret.grant_read(self.prune_lambda)

        # Daily prune, AFTER the midnight publisher; enabled only in prod (dev/test
        # prune on demand via `./bouy federation prune`).
        rule = events.Rule(
            self,
            "FederationPruneSchedule",
            rule_name=f"pantry-pirate-radio-federation-prune-{environment_name}",
            description="Daily federation log archive/prune",
            schedule=events.Schedule.cron(minute="0", hour="3"),
            enabled=environment_name == "prod",
        )
        rule.add_target(targets.LambdaFunction(self.prune_lambda))

    def _create_archive_bucket(self) -> s3.Bucket:
        """The never-destroyed leaf archive (§6.2g): NO lifecycle expiry, versioned."""
        return s3.Bucket(
            self,
            "FederationArchiveBucket",
            bucket_name=f"pantry-pirate-radio-federation-archive-{self.environment_name}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            versioned=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=(
                RemovalPolicy.RETAIN
                if self.environment_name == "prod"
                else RemovalPolicy.DESTROY
            ),
            auto_delete_objects=self.environment_name != "prod",
            # No lifecycle_rules — archived leaves are retained forever.
        )

    def _docker_image_code(self, cmd: list[str]) -> _lambda.DockerImageCode:
        if self.ecr_repository:
            return _lambda.DockerImageCode.from_ecr(
                repository=self.ecr_repository, tag_or_digest="latest", cmd=cmd
            )
        return _lambda.DockerImageCode.from_image_asset(
            directory="..",
            file=".docker/images/batch-lambda/Dockerfile",
            cmd=cmd,
        )

    def _create_prune_lambda(
        self, *, database_proxy_endpoint: str | None, database_secret
    ) -> _lambda.DockerImageFunction:
        env: dict[str, str] = {
            "FEDERATION_ENABLED": "true",
            "FEDERATION_ARCHIVE_BACKEND": "s3",
            "FEDERATION_ARCHIVE_S3_BUCKET": self.archive_bucket.bucket_name,
        }
        if database_proxy_endpoint:
            env["DATABASE_HOST"] = database_proxy_endpoint
            env["DATABASE_NAME"] = "pantry_pirate_radio"
            env["DATABASE_USER"] = "pantry_pirate"
        if database_secret is not None:
            env["DATABASE_SECRET_ARN"] = database_secret.secret_arn

        log_group = logs.LogGroup(
            self,
            "FederationPruneLogGroup",
            log_group_name=f"/aws/lambda/pantry-pirate-radio-federation-prune-{self.environment_name}",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )
        return _lambda.DockerImageFunction(
            self,
            "FederationPruneLambda",
            function_name=f"pantry-pirate-radio-federation-prune-{self.environment_name}",
            code=self._docker_image_code(cmd=["app.federation.prune_lambda.handler"]),
            timeout=Duration.seconds(300),
            memory_size=512,
            tracing=_lambda.Tracing.ACTIVE,
            environment=env,
            log_group=log_group,
            vpc=self._vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            security_groups=[self.prune_security_group],
        )
