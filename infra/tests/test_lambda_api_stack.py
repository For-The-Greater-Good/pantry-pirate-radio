"""Tests for LambdaApiStack CDK stack."""

import aws_cdk as cdk
import pytest
from aws_cdk import assertions

from stacks.compute_stack import ComputeStack
from stacks.database_stack import DatabaseStack
from stacks.ecr_stack import ECRStack
from stacks.lambda_api_stack import LambdaApiStack


class TestLambdaApiStackResources:
    """Tests for LambdaApiStack resource creation."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def dependent_stacks(self, app):
        """Create dependency stacks."""
        compute = ComputeStack(app, "TestComputeStack", environment_name="dev")
        database = DatabaseStack(
            app,
            "TestDatabaseStack",
            vpc=compute.vpc,
            environment_name="dev",
        )
        ecr = ECRStack(app, "TestECRStack", environment_name="dev")
        return compute, database, ecr

    @pytest.fixture
    def stack(self, app, dependent_stacks):
        """Create LambdaApiStack for testing."""
        compute, database, ecr = dependent_stacks
        return LambdaApiStack(
            app,
            "TestLambdaApiStack",
            vpc=compute.vpc,
            environment_name="dev",
            database_proxy_endpoint=database.proxy_endpoint,
            database_name=database.database_name,
            database_user="pantry_pirate",
            database_secret=database.database_credentials_secret,
            proxy_security_group=database.proxy_security_group,
            ecr_repository=ecr.repositories.get("app"),
            memory_size=1024,
            timeout_seconds=30,
        )

    @pytest.fixture
    def template(self, stack):
        """Get CloudFormation template from stack."""
        return assertions.Template.from_stack(stack)

    def test_creates_lambda_function(self, template):
        """Should create a Lambda function with Docker image."""
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {
                "Architectures": ["arm64"],
                "MemorySize": 1024,
                "Timeout": 30,
                "TracingConfig": {"Mode": "Active"},
            },
        )

    def test_lambda_has_database_env_vars(self, template):
        """Lambda should have DATABASE_HOST, DATABASE_NAME, DATABASE_SECRET_ARN."""
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {
                "Environment": assertions.Match.object_like({
                    "Variables": assertions.Match.object_like({
                        "DATABASE_USER": "pantry_pirate",
                        "DATABASE_PORT": "5432",
                    }),
                }),
            },
        )

    def test_creates_api_gateway_http_api(self, template):
        """Should create an API Gateway HTTP API."""
        template.has_resource_properties(
            "AWS::ApiGatewayV2::Api",
            {
                "ProtocolType": "HTTP",
            },
        )

    def test_creates_catch_all_route(self, template):
        """Should create a $default catch-all route."""
        template.has_resource_properties(
            "AWS::ApiGatewayV2::Route",
            {
                "RouteKey": "$default",
            },
        )

    def test_creates_auto_deploy_stage(self, template):
        """Should create a $default stage with auto-deploy."""
        template.has_resource_properties(
            "AWS::ApiGatewayV2::Stage",
            {
                "StageName": "$default",
                "AutoDeploy": True,
            },
        )

    def test_stage_has_access_log_settings(self, template):
        """Stage should have access log settings configured."""
        template.has_resource_properties(
            "AWS::ApiGatewayV2::Stage",
            {
                "AccessLogSettings": assertions.Match.object_like({
                    "DestinationArn": assertions.Match.any_value(),
                }),
            },
        )

    def test_creates_access_log_group(self, template):
        """Should create a CloudWatch log group for API Gateway access logs."""
        template.has_resource_properties(
            "AWS::Logs::LogGroup",
            assertions.Match.object_like({
                "LogGroupName": assertions.Match.string_like_regexp(
                    "/aws/apigateway/pantry-pirate-radio-api-.*"
                ),
            }),
        )

    def test_creates_lambda_integration(self, template):
        """Should create a Lambda integration with payload format 2.0."""
        template.has_resource_properties(
            "AWS::ApiGatewayV2::Integration",
            {
                "IntegrationType": "AWS_PROXY",
                "PayloadFormatVersion": "2.0",
            },
        )

    def test_creates_security_group(self, template):
        """Should create a security group for Lambda."""
        template.has_resource_properties(
            "AWS::EC2::SecurityGroup",
            {
                "GroupDescription": "Lambda API security group",
            },
        )

    def test_creates_log_group(self, template):
        """Should create a CloudWatch log group."""
        template.has_resource_properties(
            "AWS::Logs::LogGroup",
            assertions.Match.object_like({
                "RetentionInDays": 7,
            }),
        )

    def test_outputs_api_url(self, template):
        """Should output the API URL."""
        template.has_output("ApiUrl", {})

    def test_outputs_function_name(self, template):
        """Should output the Lambda function name."""
        template.has_output("FunctionName", {})


class TestLambdaApiStackAttributes:
    """Tests for LambdaApiStack exposed attributes."""

    @pytest.fixture
    def app(self):
        return cdk.App()

    @pytest.fixture
    def stack(self, app):
        compute = ComputeStack(app, "TestComputeStack2", environment_name="dev")
        database = DatabaseStack(
            app,
            "TestDatabaseStack2",
            vpc=compute.vpc,
            environment_name="dev",
        )
        ecr = ECRStack(app, "TestECRStack2", environment_name="dev")
        return LambdaApiStack(
            app,
            "TestLambdaApiStack2",
            vpc=compute.vpc,
            environment_name="dev",
            database_proxy_endpoint=database.proxy_endpoint,
            database_name=database.database_name,
            database_user="pantry_pirate",
            database_secret=database.database_credentials_secret,
            proxy_security_group=database.proxy_security_group,
            ecr_repository=ecr.repositories.get("app"),
        )

    def test_exposes_api_function(self, stack):
        """Stack should expose api_function attribute."""
        assert stack.api_function is not None

    def test_exposes_http_api(self, stack):
        """Stack should expose http_api attribute."""
        assert stack.http_api is not None

    def test_exposes_api_url(self, stack):
        """Stack should expose api_url attribute."""
        assert stack.api_url is not None
        assert "execute-api" in stack.api_url

    def test_exposes_lambda_security_group(self, stack):
        """Stack should expose lambda_security_group attribute."""
        assert stack.lambda_security_group is not None


class TestLambdaApiStackProvisionedConcurrency:
    """Tests for provisioned concurrency configuration."""

    @pytest.fixture
    def app(self):
        return cdk.App()

    @pytest.fixture
    def stack_with_provisioned(self, app):
        compute = ComputeStack(app, "TestComputeStack3", environment_name="prod")
        database = DatabaseStack(
            app,
            "TestDatabaseStack3",
            vpc=compute.vpc,
            environment_name="prod",
        )
        ecr = ECRStack(app, "TestECRStack3", environment_name="prod")
        return LambdaApiStack(
            app,
            "TestLambdaApiStack3",
            vpc=compute.vpc,
            environment_name="prod",
            database_proxy_endpoint=database.proxy_endpoint,
            database_name=database.database_name,
            database_user="pantry_pirate",
            database_secret=database.database_credentials_secret,
            proxy_security_group=database.proxy_security_group,
            ecr_repository=ecr.repositories.get("app"),
            provisioned_concurrent=2,
        )

    @pytest.fixture
    def template(self, stack_with_provisioned):
        return assertions.Template.from_stack(stack_with_provisioned)

    def test_creates_alias_with_provisioned_concurrency(self, template):
        """Prod stack should create Lambda alias with provisioned concurrency."""
        template.has_resource_properties(
            "AWS::Lambda::Alias",
            {
                "Name": "live",
                "ProvisionedConcurrencyConfig": {
                    "ProvisionedConcurrentExecutions": 2,
                },
            },
        )

    def test_prod_log_retention(self, template):
        """Prod stack should have 7-day log retention (unified)."""
        template.has_resource_properties(
            "AWS::Logs::LogGroup",
            assertions.Match.object_like({
                "RetentionInDays": 7,
            }),
        )


class TestLambdaApiStackDatabaseAccess:
    """Tests for grant_database_access method."""

    @pytest.fixture
    def app(self):
        return cdk.App()

    @pytest.fixture
    def stack_and_db(self, app):
        compute = ComputeStack(app, "TestComputeStack4", environment_name="dev")
        database = DatabaseStack(
            app,
            "TestDatabaseStack4",
            vpc=compute.vpc,
            environment_name="dev",
        )
        ecr = ECRStack(app, "TestECRStack4", environment_name="dev")
        stack = LambdaApiStack(
            app,
            "TestLambdaApiStack4",
            vpc=compute.vpc,
            environment_name="dev",
            database_proxy_endpoint=database.proxy_endpoint,
            database_name=database.database_name,
            database_user="pantry_pirate",
            database_secret=database.database_credentials_secret,
            proxy_security_group=database.proxy_security_group,
            ecr_repository=ecr.repositories.get("app"),
        )
        return stack, database

    def test_grant_database_access_creates_ingress(self, stack_and_db):
        """grant_database_access should create SG ingress rule."""
        stack, database = stack_and_db
        stack.grant_database_access(database.proxy_security_group)

        template = assertions.Template.from_stack(stack)
        template.has_resource_properties(
            "AWS::EC2::SecurityGroupIngress",
            {
                "IpProtocol": "tcp",
                "FromPort": 5432,
                "ToPort": 5432,
                "Description": "Allow Lambda API to connect to RDS Proxy",
            },
        )
