"""Lambda API Stack for Pantry Pirate Radio.

Deploys the HSDS API as a Lambda function behind API Gateway HTTP API.
Public endpoints are read-only.
Zero idle compute cost — pays only per request.
"""

import aws_cdk as cdk
from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack
from aws_cdk import aws_apigatewayv2 as apigwv2
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_logs as logs
from aws_cdk import aws_secretsmanager as secretsmanager

from constructs import Construct


class LambdaApiStack(Stack):
    """Serverless API infrastructure for Pantry Pirate Radio.

    Creates:
    - Lambda function (Docker image, ARM64) for FastAPI
    - API Gateway HTTP API with catch-all proxy route
    - Security group for Lambda → RDS Proxy access
    - CloudWatch log group

    Attributes:
        api_function: Lambda function running the API
        http_api: API Gateway HTTP API
        api_url: Public URL of the API
        lambda_security_group: Security group for Lambda function
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.IVpc,
        environment_name: str = "dev",
        database_proxy_endpoint: str,
        database_name: str,
        database_user: str,
        database_secret: secretsmanager.ISecret,
        proxy_security_group: ec2.ISecurityGroup,
        ecr_repository: ecr.IRepository | None = None,
        tightbeam_api_keys_secret: secretsmanager.ISecret | None = None,
        memory_size: int = 1024,
        timeout_seconds: int = 30,
        provisioned_concurrent: int | None = None,
        **kwargs,
    ) -> None:
        """Initialize LambdaApiStack.

        Args:
            scope: CDK scope
            construct_id: Unique identifier
            vpc: VPC for Lambda placement
            environment_name: Environment name (dev, staging, prod)
            database_proxy_endpoint: RDS Proxy endpoint hostname
            database_name: Database name
            database_user: Database user
            database_secret: Secrets Manager secret for DB credentials
            proxy_security_group: RDS Proxy security group (for ingress rules)
            ecr_repository: ECR repository for the API Lambda image
            tightbeam_api_keys_secret: (Deprecated) Retained for CloudFormation export
                compatibility only. Remove after staged CF cleanup.
            memory_size: Lambda memory in MB
            timeout_seconds: Lambda timeout in seconds
            provisioned_concurrent: Provisioned concurrency (None = on-demand only)
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        self.environment_name = environment_name

        # Security group for Lambda → RDS Proxy
        self.lambda_security_group = ec2.SecurityGroup(
            self,
            "LambdaSG",
            vpc=vpc,
            description="Lambda API security group",
            allow_all_outbound=True,
        )

        # Log group
        log_group = logs.LogGroup(
            self,
            "ApiLambdaLogs",
            log_group_name=f"/aws/lambda/pantry-pirate-radio-api-{environment_name}",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Lambda function
        self.api_function = _lambda.DockerImageFunction(
            self,
            "ApiFunction",
            function_name=f"pantry-pirate-radio-api-{environment_name}",
            code=(
                _lambda.DockerImageCode.from_ecr(
                    repository=ecr_repository,
                    tag_or_digest="latest",
                )
                if ecr_repository
                else _lambda.DockerImageCode.from_image_asset(
                    directory=".",
                    file="docker/images/api-lambda/Dockerfile",
                )
            ),
            architecture=_lambda.Architecture.ARM_64,
            memory_size=memory_size,
            timeout=Duration.seconds(timeout_seconds),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            security_groups=[self.lambda_security_group],
            log_group=log_group,
            tracing=_lambda.Tracing.ACTIVE,
            environment={
                "DATABASE_HOST": database_proxy_endpoint,
                "DATABASE_NAME": database_name,
                "DATABASE_USER": database_user,
                "DATABASE_PORT": "5432",
                "DATABASE_SECRET_ARN": database_secret.secret_arn,
                "ENVIRONMENT": environment_name,
            },
        )

        # Service-level tag for cost attribution
        cdk.Tags.of(self.api_function).add("Service", "api")

        # Grant Secrets Manager read access
        database_secret.grant_read(self.api_function)

        # Provisioned concurrency (prod only, for warm starts)
        if provisioned_concurrent:
            version = self.api_function.current_version
            _lambda.Alias(
                self,
                "ApiLiveAlias",
                alias_name="live",
                version=version,
                provisioned_concurrent_executions=provisioned_concurrent,
            )

        # API Gateway HTTP API
        self.http_api = apigwv2.CfnApi(
            self,
            "HttpApi",
            name=f"pantry-pirate-radio-api-{environment_name}",
            protocol_type="HTTP",
            cors_configuration=apigwv2.CfnApi.CorsProperty(
                allow_methods=["GET", "HEAD", "OPTIONS"],
                allow_origins=["*"],
                allow_headers=["Content-Type", "X-Request-ID", "X-Api-Key"],
                expose_headers=["X-Request-ID"],
                max_age=600,
            ),
        )

        # Lambda integration
        integration = apigwv2.CfnIntegration(
            self,
            "LambdaIntegration",
            api_id=self.http_api.ref,
            integration_type="AWS_PROXY",
            integration_uri=self.api_function.function_arn,
            payload_format_version="2.0",
        )

        # Catch-all route
        apigwv2.CfnRoute(
            self,
            "DefaultRoute",
            api_id=self.http_api.ref,
            route_key="$default",
            target=f"integrations/{integration.ref}",
        )

        # Access log group for API Gateway
        access_log_group = logs.LogGroup(
            self,
            "ApiGwAccessLogs",
            log_group_name=f"/aws/apigateway/pantry-pirate-radio-api-{environment_name}",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Auto-deploy stage with access logging
        stage = apigwv2.CfnStage(
            self,
            "DefaultStage",
            api_id=self.http_api.ref,
            stage_name="$default",
            auto_deploy=True,
            access_log_settings=apigwv2.CfnStage.AccessLogSettingsProperty(
                destination_arn=access_log_group.log_group_arn,
                format='{"requestId":"$context.requestId","ip":"$context.identity.sourceIp","method":"$context.httpMethod","path":"$context.path","status":"$context.status","latency":"$context.responseLatency","error":"$context.error.message"}',
            ),
        )

        # NOTE: WAFv2 does NOT support API Gateway HTTP APIs (v2).
        # It only supports REST APIs (v1), ALBs, CloudFront, AppSync, etc.
        # Rate limiting is handled by API Gateway's built-in throttling instead.
        # To add WAF protection, put CloudFront in front of the HTTP API.

        # Grant API Gateway permission to invoke Lambda
        self.api_function.add_permission(
            "ApiGwInvoke",
            principal=iam.ServicePrincipal("apigateway.amazonaws.com"),
            source_arn=f"arn:aws:execute-api:{self.region}:{self.account}:{self.http_api.ref}/*",
        )

        # Outputs
        self.api_url = (
            f"https://{self.http_api.ref}.execute-api.{self.region}.amazonaws.com"
        )

        CfnOutput(
            self,
            "ApiUrl",
            value=self.api_url,
            description="API Gateway URL",
        )

        CfnOutput(
            self,
            "FunctionName",
            value=self.api_function.function_name,
            description="Lambda function name",
        )

    def grant_database_access(self, proxy_security_group: ec2.ISecurityGroup) -> None:
        """Allow Lambda to connect to RDS Proxy.

        Uses L1 CfnSecurityGroupIngress to avoid circular cross-stack references.

        Args:
            proxy_security_group: RDS Proxy security group
        """
        ec2.CfnSecurityGroupIngress(
            self,
            "LambdaApiToProxyIngress",
            group_id=proxy_security_group.security_group_id,
            source_security_group_id=self.lambda_security_group.security_group_id,
            ip_protocol="tcp",
            from_port=5432,
            to_port=5432,
            description="Allow Lambda API to connect to RDS Proxy",
        )
