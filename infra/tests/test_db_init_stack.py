"""Tests for DbInitStack CDK stack."""

import aws_cdk as cdk
import pytest
from aws_cdk import assertions

from stacks.compute_stack import ComputeStack
from stacks.database_stack import DatabaseStack
from stacks.db_init_stack import DbInitStack
from stacks.secrets_stack import SecretsStack


class TestDbInitStackResources:
    """Tests for DbInitStack resource creation."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def compute_stack(self, app):
        """Create compute stack for dependencies."""
        return ComputeStack(app, "TestCompute", environment_name="dev")

    @pytest.fixture
    def database_stack(self, app, compute_stack):
        """Create database stack for dependencies."""
        return DatabaseStack(
            app,
            "TestDatabase",
            environment_name="dev",
            vpc=compute_stack.vpc,
        )

    @pytest.fixture
    def secrets_stack(self, app):
        """Create secrets stack for dependencies."""
        return SecretsStack(app, "TestSecrets", environment_name="dev")

    @pytest.fixture
    def stack(self, app, compute_stack, database_stack, secrets_stack):
        """Create stack for testing."""
        return DbInitStack(
            app,
            "TestDbInitStack",
            environment_name="dev",
            vpc=compute_stack.vpc,
            cluster=compute_stack.cluster,
            database_proxy_endpoint=database_stack.proxy_endpoint,
            database_secret=database_stack.database_credentials_secret,
            github_pat_secret=secrets_stack.github_pat_secret,
            proxy_security_group=database_stack.proxy_security_group,
        )

    @pytest.fixture
    def template(self, stack):
        """Get CloudFormation template from stack."""
        return assertions.Template.from_stack(stack)

    def test_creates_ssm_parameter(self, template):
        """DbInitStack should create SSM parameter for tracking init state."""
        template.resource_count_is("AWS::SSM::Parameter", 1)

    def test_ssm_parameter_initial_value_false(self, template):
        """SSM parameter should have initial value of 'false'."""
        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {
                "Value": "false",
                "Type": "String",
            },
        )

    def test_ssm_parameter_has_correct_name(self, template):
        """SSM parameter should have correct naming pattern."""
        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {
                "Name": "/pantry-pirate-radio/dev/db-initialized",
            },
        )

    def test_creates_check_db_lambda(self, template):
        """DbInitStack should create Lambda function to check database state."""
        # Lambda functions: check-db, trigger, plus custom resource provider framework
        template.resource_count_is("AWS::Lambda::Function", 4)

    def test_check_db_lambda_has_ssm_environment(self, template):
        """Check-db Lambda should have SSM parameter name in environment."""
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {
                "Environment": assertions.Match.object_like(
                    {
                        "Variables": assertions.Match.object_like(
                            {
                                "SSM_PARAMETER_NAME": assertions.Match.any_value(),
                            }
                        ),
                    }
                ),
            },
        )

    def test_creates_init_task_definition(self, template):
        """DbInitStack should create ECS task definition for db-init."""
        template.resource_count_is("AWS::ECS::TaskDefinition", 1)

    def test_init_task_has_4gb_memory(self, template):
        """Init task should have 4GB memory."""
        template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            {
                "Cpu": "1024",
                "Memory": "4096",
            },
        )

    def test_init_task_has_db_secrets(self, template):
        """Init task should have database secrets configured."""
        template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            {
                "ContainerDefinitions": assertions.Match.array_with(
                    [
                        assertions.Match.object_like(
                            {
                                "Secrets": assertions.Match.array_with(
                                    [
                                        assertions.Match.object_like(
                                            {
                                                "Name": "PGPASSWORD",
                                            }
                                        ),
                                    ]
                                ),
                            }
                        ),
                    ]
                ),
            },
        )

    def test_creates_state_machine(self, template):
        """DbInitStack should create Step Functions state machine."""
        template.resource_count_is("AWS::StepFunctions::StateMachine", 1)

    def test_state_machine_has_correct_name(self, template):
        """State machine should have correct naming pattern."""
        template.has_resource_properties(
            "AWS::StepFunctions::StateMachine",
            {
                "StateMachineName": "pantry-pirate-radio-db-init-dev",
            },
        )

    def test_creates_custom_resource(self, template):
        """DbInitStack should create custom resource for init trigger."""
        template.resource_count_is("AWS::CloudFormation::CustomResource", 1)

    def test_creates_log_groups(self, template):
        """DbInitStack should create log groups."""
        template.resource_count_is("AWS::Logs::LogGroup", 1)

    def test_creates_security_groups(self, template):
        """DbInitStack should create security groups for Lambda and ECS."""
        # Check-db Lambda SG + Init task SG
        template.resource_count_is("AWS::EC2::SecurityGroup", 2)


class TestDbInitStackEnvironments:
    """Tests for environment-specific DbInit configuration."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def compute_stack_dev(self, app):
        """Create dev compute stack."""
        return ComputeStack(app, "DevCompute", environment_name="dev")

    @pytest.fixture
    def database_stack_dev(self, app, compute_stack_dev):
        """Create dev database stack."""
        return DatabaseStack(
            app,
            "DevDatabase",
            environment_name="dev",
            vpc=compute_stack_dev.vpc,
        )

    @pytest.fixture
    def secrets_stack_dev(self, app):
        """Create dev secrets stack."""
        return SecretsStack(app, "DevSecrets", environment_name="dev")

    @pytest.fixture
    def compute_stack_prod(self, app):
        """Create prod compute stack."""
        return ComputeStack(app, "ProdCompute", environment_name="prod")

    @pytest.fixture
    def database_stack_prod(self, app, compute_stack_prod):
        """Create prod database stack."""
        return DatabaseStack(
            app,
            "ProdDatabase",
            environment_name="prod",
            vpc=compute_stack_prod.vpc,
        )

    @pytest.fixture
    def secrets_stack_prod(self, app):
        """Create prod secrets stack."""
        return SecretsStack(app, "ProdSecrets", environment_name="prod")

    def test_dev_log_retention(
        self, app, compute_stack_dev, database_stack_dev, secrets_stack_dev
    ):
        """Dev environment should have 7-day log retention."""
        stack = DbInitStack(
            app,
            "DevDbInit",
            environment_name="dev",
            vpc=compute_stack_dev.vpc,
            cluster=compute_stack_dev.cluster,
            database_proxy_endpoint=database_stack_dev.proxy_endpoint,
            database_secret=database_stack_dev.database_credentials_secret,
            github_pat_secret=secrets_stack_dev.github_pat_secret,
            proxy_security_group=database_stack_dev.proxy_security_group,
        )
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::Logs::LogGroup",
            {"RetentionInDays": 7},
        )

    def test_prod_log_retention(
        self, app, compute_stack_prod, database_stack_prod, secrets_stack_prod
    ):
        """Prod environment should have 30-day log retention."""
        stack = DbInitStack(
            app,
            "ProdDbInit",
            environment_name="prod",
            vpc=compute_stack_prod.vpc,
            cluster=compute_stack_prod.cluster,
            database_proxy_endpoint=database_stack_prod.proxy_endpoint,
            database_secret=database_stack_prod.database_credentials_secret,
            github_pat_secret=secrets_stack_prod.github_pat_secret,
            proxy_security_group=database_stack_prod.proxy_security_group,
        )
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::Logs::LogGroup",
            {"RetentionInDays": 30},
        )


class TestDbInitStackAttributes:
    """Tests for DbInitStack attributes and outputs."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def compute_stack(self, app):
        """Create compute stack for dependencies."""
        return ComputeStack(app, "AttrCompute", environment_name="dev")

    @pytest.fixture
    def database_stack(self, app, compute_stack):
        """Create database stack for dependencies."""
        return DatabaseStack(
            app,
            "AttrDatabase",
            environment_name="dev",
            vpc=compute_stack.vpc,
        )

    @pytest.fixture
    def secrets_stack(self, app):
        """Create secrets stack for dependencies."""
        return SecretsStack(app, "AttrSecrets", environment_name="dev")

    @pytest.fixture
    def stack(self, app, compute_stack, database_stack, secrets_stack):
        """Create stack for testing."""
        return DbInitStack(
            app,
            "AttrTestStack",
            environment_name="dev",
            vpc=compute_stack.vpc,
            cluster=compute_stack.cluster,
            database_proxy_endpoint=database_stack.proxy_endpoint,
            database_secret=database_stack.database_credentials_secret,
            github_pat_secret=secrets_stack.github_pat_secret,
            proxy_security_group=database_stack.proxy_security_group,
        )

    def test_exposes_init_flag_parameter(self, stack):
        """Stack should expose init_flag SSM parameter."""
        assert stack.init_flag is not None
        assert hasattr(stack.init_flag, "parameter_name")

    def test_exposes_state_machine(self, stack):
        """Stack should expose state_machine."""
        assert stack.state_machine is not None
        assert hasattr(stack.state_machine, "state_machine_arn")

    def test_exposes_init_task_definition(self, stack):
        """Stack should expose init_task_definition."""
        assert stack.init_task_definition is not None

    def test_exposes_check_db_lambda(self, stack):
        """Stack should expose check_db_lambda."""
        assert stack.check_db_lambda is not None
        assert hasattr(stack.check_db_lambda, "function_arn")

    def test_environment_name_stored(self, stack):
        """Stack should store environment name."""
        assert stack.environment_name == "dev"

    def test_exposes_check_db_lambda_security_group(self, stack):
        """Stack should expose check_db_lambda_security_group for wiring."""
        assert stack.check_db_lambda_security_group is not None

    def test_exposes_init_task_security_group(self, stack):
        """Stack should expose init_task_security_group for wiring."""
        assert stack.init_task_security_group is not None


class TestDbInitStackSafety:
    """Critical safety tests for DbInitStack.

    These tests verify the safety mechanisms that prevent
    database re-initialization on stack updates.
    """

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def compute_stack(self, app):
        """Create compute stack for dependencies."""
        return ComputeStack(app, "SafetyCompute", environment_name="dev")

    @pytest.fixture
    def database_stack(self, app, compute_stack):
        """Create database stack for dependencies."""
        return DatabaseStack(
            app,
            "SafetyDatabase",
            environment_name="dev",
            vpc=compute_stack.vpc,
        )

    @pytest.fixture
    def secrets_stack(self, app):
        """Create secrets stack for dependencies."""
        return SecretsStack(app, "SafetySecrets", environment_name="dev")

    @pytest.fixture
    def stack(self, app, compute_stack, database_stack, secrets_stack):
        """Create stack for testing."""
        return DbInitStack(
            app,
            "SafetyTestStack",
            environment_name="dev",
            vpc=compute_stack.vpc,
            cluster=compute_stack.cluster,
            database_proxy_endpoint=database_stack.proxy_endpoint,
            database_secret=database_stack.database_credentials_secret,
            github_pat_secret=secrets_stack.github_pat_secret,
            proxy_security_group=database_stack.proxy_security_group,
        )

    @pytest.fixture
    def template(self, stack):
        """Get CloudFormation template from stack."""
        return assertions.Template.from_stack(stack)

    def test_custom_resource_exists(self, template):
        """Custom resource should exist for triggering init."""
        template.resource_count_is("AWS::CloudFormation::CustomResource", 1)

    def test_ssm_parameter_tracks_init_state(self, template):
        """SSM parameter should exist for tracking init state."""
        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {
                "Name": "/pantry-pirate-radio/dev/db-initialized",
                "Value": "false",
            },
        )
