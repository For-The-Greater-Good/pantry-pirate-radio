"""Tests for ServicesStack CDK stack - core service creation tests."""

import aws_cdk as cdk
import pytest
from aws_cdk import assertions

from stacks.ecr_stack import ECRStack
from stacks.services_stack import ServicesStack
from stacks.compute_stack import ComputeStack


class TestServicesStackResources:
    """Tests for ServicesStack resource creation."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def dev_stack(self, app):
        """Create dev environment stack with dependencies."""
        compute_stack = ComputeStack(app, "TestComputeStack", environment_name="dev")
        return ServicesStack(
            app,
            "TestServicesStack",
            environment_name="dev",
            vpc=compute_stack.vpc,
            cluster=compute_stack.cluster,
        )

    @pytest.fixture
    def dev_template(self, dev_stack):
        """Get CloudFormation template from dev stack."""
        return assertions.Template.from_stack(dev_stack)

    def test_creates_validator_service(self, dev_template):
        """ServicesStack should create Fargate services (validator, reconciler, recorder)."""
        # 3 services: validator, reconciler, recorder
        # Publisher is now a task definition, not a service
        dev_template.resource_count_is("AWS::ECS::Service", 3)

    def test_creates_task_definitions(self, dev_template):
        """ServicesStack should create task definitions for services and tasks."""
        # 3 services + 1 scraper task + 1 publisher task = 5
        dev_template.resource_count_is("AWS::ECS::TaskDefinition", 5)

    def test_creates_log_groups(self, dev_template):
        """ServicesStack should create log groups for each service and task."""
        # 3 services + 1 scraper + 1 publisher = 5
        dev_template.resource_count_is("AWS::Logs::LogGroup", 5)

    def test_validator_service_has_correct_cpu(self, dev_template):
        """Validator task definition should have correct CPU."""
        dev_template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            {
                "Cpu": "512",
                "Memory": "1024",
            },
        )

    def test_reconciler_has_max_count_one(self, dev_template):
        """Reconciler service should have max count of 1."""
        dev_template.has_resource_properties(
            "AWS::ECS::Service",
            {"DesiredCount": 1},
        )

    def test_scraper_task_definition_exists(self, dev_template):
        """Scraper task definition should exist for one-shot tasks."""
        # Scraper is a task, not a service
        dev_template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            {
                "Cpu": "512",
                "Memory": "1024",
                "RequiresCompatibilities": ["FARGATE"],
            },
        )


class TestServicesStackEnvironments:
    """Tests for environment-specific configuration."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    def test_dev_log_retention(self, app):
        """Dev environment should have shorter log retention."""
        compute_stack = ComputeStack(app, "ComputeStack1", environment_name="dev")
        stack = ServicesStack(
            app,
            "DevStack",
            environment_name="dev",
            vpc=compute_stack.vpc,
            cluster=compute_stack.cluster,
        )
        template = assertions.Template.from_stack(stack)

        # Dev should have 7-day retention
        template.has_resource_properties(
            "AWS::Logs::LogGroup",
            {"RetentionInDays": 7},
        )

    def test_prod_log_retention(self, app):
        """Prod environment should have 7-day log retention (unified)."""
        compute_stack = ComputeStack(app, "ComputeStack2", environment_name="prod")
        stack = ServicesStack(
            app,
            "ProdStack",
            environment_name="prod",
            vpc=compute_stack.vpc,
            cluster=compute_stack.cluster,
        )
        template = assertions.Template.from_stack(stack)

        # Prod uses same 7-day retention as dev (unified)
        template.has_resource_properties(
            "AWS::Logs::LogGroup",
            {"RetentionInDays": 7},
        )


class TestServicesStackAttributes:
    """Tests for stack attributes and outputs."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def stack(self, app):
        """Create stack for testing."""
        compute_stack = ComputeStack(app, "ComputeStack", environment_name="dev")
        return ServicesStack(
            app,
            "AttrTestStack",
            environment_name="dev",
            vpc=compute_stack.vpc,
            cluster=compute_stack.cluster,
        )

    def test_exposes_validator_service(self, stack):
        """Stack should expose validator_service attribute."""
        assert stack.validator_service is not None

    def test_exposes_reconciler_service(self, stack):
        """Stack should expose reconciler_service attribute."""
        assert stack.reconciler_service is not None

    def test_exposes_publisher_task_definition(self, stack):
        """Stack should expose publisher_task_definition attribute."""
        assert stack.publisher_task_definition is not None

    def test_exposes_recorder_service(self, stack):
        """Stack should expose recorder_service attribute."""
        assert stack.recorder_service is not None

    def test_exposes_scraper_task_definition(self, stack):
        """Stack should expose scraper_task_definition attribute."""
        assert stack.scraper_task_definition is not None

    def test_environment_name_stored(self, stack):
        """Stack should store environment name."""
        assert stack.environment_name == "dev"

    def test_exposes_validator_security_group(self, stack):
        """Stack should expose validator security group for wiring."""
        assert stack.validator_security_group is not None

    def test_exposes_reconciler_security_group(self, stack):
        """Stack should expose reconciler security group for wiring."""
        assert stack.reconciler_security_group is not None

    def test_exposes_publisher_security_group(self, stack):
        """Stack should expose publisher security group for wiring."""
        assert stack.publisher_security_group is not None

    def test_exposes_publisher_task_role(self, stack):
        """Stack should expose publisher task role for IAM grants."""
        assert stack.publisher_task_role is not None

    def test_exposes_recorder_security_group(self, stack):
        """Stack should expose recorder security group for wiring."""
        assert stack.recorder_security_group is not None

    def test_exposes_scraper_security_group(self, stack):
        """Stack should expose scraper security group for wiring."""
        assert stack.scraper_security_group is not None

    def test_exposes_validator_task_role(self, stack):
        """Stack should expose validator task role for IAM grants."""
        assert stack.validator_task_role is not None

    def test_exposes_reconciler_task_role(self, stack):
        """Stack should expose reconciler task role for IAM grants."""
        assert stack.reconciler_task_role is not None

    def test_exposes_recorder_task_role(self, stack):
        """Stack should expose recorder task role for IAM grants."""
        assert stack.recorder_task_role is not None

    def test_exposes_scraper_task_role(self, stack):
        """Stack should expose scraper task role for IAM grants."""
        assert stack.scraper_task_role is not None

    def test_stores_config(self, stack):
        """Stack should store the config object."""
        assert stack.config is not None


class TestServicesStackWithConfig:
    """Tests for ServicesStack with ServiceConfig."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def compute_stack(self, app):
        """Create compute stack for dependencies."""
        return ComputeStack(app, "TestCompute", environment_name="dev")

    def test_creates_with_empty_config(self, app, compute_stack):
        """Stack should work with default empty config."""
        from stacks.services_stack import ServiceConfig

        stack = ServicesStack(
            app,
            "EmptyConfigStack",
            environment_name="dev",
            vpc=compute_stack.vpc,
            cluster=compute_stack.cluster,
            config=ServiceConfig(),
        )
        assert stack.validator_service is not None

    def test_creates_with_partial_config(self, app, compute_stack):
        """Stack should work with partial config."""
        from stacks.services_stack import ServiceConfig

        config = ServiceConfig(
            database_host="test-host.rds.amazonaws.com",
            database_name="test_db",
        )
        stack = ServicesStack(
            app,
            "PartialConfigStack",
            environment_name="dev",
            vpc=compute_stack.vpc,
            cluster=compute_stack.cluster,
            config=config,
        )
        assert stack.validator_service is not None
        assert stack.config.database_host == "test-host.rds.amazonaws.com"

    def test_validator_container_has_queue_backend(self, app, compute_stack):
        """Validator container should have QUEUE_BACKEND env var."""
        from stacks.services_stack import ServiceConfig

        config = ServiceConfig()
        stack = ServicesStack(
            app,
            "EnvVarStack",
            environment_name="dev",
            vpc=compute_stack.vpc,
            cluster=compute_stack.cluster,
            config=config,
        )
        template = assertions.Template.from_stack(stack)

        # Verify validator task definition has expected environment variable
        template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            {
                "ContainerDefinitions": assertions.Match.array_with(
                    [
                        assertions.Match.object_like(
                            {
                                "Environment": assertions.Match.array_with(
                                    [
                                        assertions.Match.object_like(
                                            {
                                                "Name": "QUEUE_BACKEND",
                                                "Value": "sqs",
                                            }
                                        )
                                    ]
                                )
                            }
                        )
                    ]
                )
            },
        )

    def test_scraper_container_has_service_type(self, app, compute_stack):
        """Scraper container should have SERVICE_TYPE=scraper env var."""
        from stacks.services_stack import ServiceConfig

        config = ServiceConfig()
        stack = ServicesStack(
            app,
            "ScraperEnvStack",
            environment_name="dev",
            vpc=compute_stack.vpc,
            cluster=compute_stack.cluster,
            config=config,
        )
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            {
                "ContainerDefinitions": assertions.Match.array_with(
                    [
                        assertions.Match.object_like(
                            {
                                "Environment": assertions.Match.array_with(
                                    [
                                        assertions.Match.object_like(
                                            {
                                                "Name": "SERVICE_TYPE",
                                                "Value": "scraper",
                                            }
                                        )
                                    ]
                                )
                            }
                        )
                    ]
                )
            },
        )

    def test_validator_has_amazon_location_env_vars(self, app, compute_stack):
        """Validator container should have AMAZON_LOCATION_INDEX when configured."""
        from stacks.services_stack import ServiceConfig

        config = ServiceConfig(
            place_index_name="test-geocoding-index",
            place_index_arn="arn:aws:geo:us-east-1:123456:place-index/test",
        )
        stack = ServicesStack(
            app,
            "AmazonLocationStack",
            environment_name="dev",
            vpc=compute_stack.vpc,
            cluster=compute_stack.cluster,
            config=config,
        )
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            {
                "ContainerDefinitions": assertions.Match.array_with(
                    [
                        assertions.Match.object_like(
                            {
                                "Environment": assertions.Match.array_with(
                                    [
                                        assertions.Match.object_like(
                                            {
                                                "Name": "AMAZON_LOCATION_INDEX",
                                                "Value": "test-geocoding-index",
                                            }
                                        )
                                    ]
                                )
                            }
                        )
                    ]
                )
            },
        )

    def test_validator_geocoding_provider_overridden(self, app, compute_stack):
        """Validator should override GEOCODING_PROVIDER to amazon-location when Place Index is configured."""
        from stacks.services_stack import ServiceConfig

        config = ServiceConfig(
            place_index_name="test-geocoding-index",
            place_index_arn="arn:aws:geo:us-east-1:123456:place-index/test",
        )
        stack = ServicesStack(
            app,
            "GeoProviderStack",
            environment_name="dev",
            vpc=compute_stack.vpc,
            cluster=compute_stack.cluster,
            config=config,
        )
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            {
                "ContainerDefinitions": assertions.Match.array_with(
                    [
                        assertions.Match.object_like(
                            {
                                "Environment": assertions.Match.array_with(
                                    [
                                        assertions.Match.object_like(
                                            {
                                                "Name": "GEOCODING_PROVIDER",
                                                "Value": "amazon-location",
                                            }
                                        )
                                    ]
                                )
                            }
                        )
                    ]
                )
            },
        )

    def test_scraper_container_has_sqs_env_vars(self, app, compute_stack):
        """Scraper container should have SQS_QUEUE_URL and SQS_JOBS_TABLE when configured."""
        from stacks.services_stack import ServiceConfig

        config = ServiceConfig(
            queue_urls={
                "llm": "https://sqs.us-east-1.amazonaws.com/123456/llm-queue.fifo"
            },
            jobs_table_name="test-jobs-table",
        )
        stack = ServicesStack(
            app,
            "ScraperSQSStack",
            environment_name="dev",
            vpc=compute_stack.vpc,
            cluster=compute_stack.cluster,
            config=config,
        )
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            {
                "ContainerDefinitions": assertions.Match.array_with(
                    [
                        assertions.Match.object_like(
                            {
                                "Environment": assertions.Match.array_with(
                                    [
                                        assertions.Match.object_like(
                                            {
                                                "Name": "SQS_QUEUE_URL",
                                                "Value": "https://sqs.us-east-1.amazonaws.com/123456/llm-queue.fifo",
                                            }
                                        ),
                                    ]
                                )
                            }
                        )
                    ]
                )
            },
        )

        template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            {
                "ContainerDefinitions": assertions.Match.array_with(
                    [
                        assertions.Match.object_like(
                            {
                                "Environment": assertions.Match.array_with(
                                    [
                                        assertions.Match.object_like(
                                            {
                                                "Name": "SQS_JOBS_TABLE",
                                                "Value": "test-jobs-table",
                                            }
                                        ),
                                    ]
                                )
                            }
                        )
                    ]
                )
            },
        )


class TestPublisherTaskDefinition:
    """Tests for publisher as a one-shot task definition (not a service)."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def compute_stack(self, app):
        """Create compute stack for dependencies."""
        return ComputeStack(app, "PubTestCompute", environment_name="dev")

    def test_publisher_is_task_not_service(self, app, compute_stack):
        """Publisher should be a task definition, not a Fargate service."""
        from stacks.services_stack import ServiceConfig

        stack = ServicesStack(
            app,
            "PubTaskStack",
            environment_name="dev",
            vpc=compute_stack.vpc,
            cluster=compute_stack.cluster,
            config=ServiceConfig(),
        )
        # publisher_task_definition should exist, publisher_service should not
        assert stack.publisher_task_definition is not None
        assert not hasattr(stack, "publisher_service")

    def test_publisher_container_runs_exporter(self, app, compute_stack):
        """Publisher container should run the exporter module."""
        from stacks.services_stack import ServiceConfig

        config = ServiceConfig(exports_bucket_name="my-exports-bucket")
        stack = ServicesStack(
            app,
            "PubCmdStack",
            environment_name="dev",
            vpc=compute_stack.vpc,
            cluster=compute_stack.cluster,
            config=config,
        )
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            {
                "ContainerDefinitions": assertions.Match.array_with(
                    [
                        assertions.Match.object_like(
                            {
                                "Command": assertions.Match.array_with(
                                    [
                                        "python",
                                        "-m",
                                        "app.datasette.exporter",
                                    ]
                                ),
                            }
                        )
                    ]
                )
            },
        )

    def test_publisher_has_exports_bucket_env(self, app, compute_stack):
        """Publisher container should have EXPORT_S3_BUCKET env var."""
        from stacks.services_stack import ServiceConfig

        config = ServiceConfig(exports_bucket_name="my-exports-bucket")
        stack = ServicesStack(
            app,
            "PubEnvStack",
            environment_name="dev",
            vpc=compute_stack.vpc,
            cluster=compute_stack.cluster,
            config=config,
        )
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            {
                "ContainerDefinitions": assertions.Match.array_with(
                    [
                        assertions.Match.object_like(
                            {
                                "Environment": assertions.Match.array_with(
                                    [
                                        assertions.Match.object_like(
                                            {
                                                "Name": "EXPORT_S3_BUCKET",
                                                "Value": "my-exports-bucket",
                                            }
                                        )
                                    ]
                                )
                            }
                        )
                    ]
                )
            },
        )

    def test_publisher_has_database_env_vars(self, app, compute_stack):
        """Publisher container should have DATABASE_HOST env var when configured."""
        from stacks.services_stack import ServiceConfig

        config = ServiceConfig(database_host="my-proxy.rds.amazonaws.com")
        stack = ServicesStack(
            app,
            "PubDbStack",
            environment_name="dev",
            vpc=compute_stack.vpc,
            cluster=compute_stack.cluster,
            config=config,
        )
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            {
                "ContainerDefinitions": assertions.Match.array_with(
                    [
                        assertions.Match.object_like(
                            {
                                "Environment": assertions.Match.array_with(
                                    [
                                        assertions.Match.object_like(
                                            {
                                                "Name": "DATABASE_HOST",
                                                "Value": "my-proxy.rds.amazonaws.com",
                                            }
                                        )
                                    ]
                                )
                            }
                        )
                    ]
                )
            },
        )


class TestServicesStackWithECRRepositories:
    """Tests for ServicesStack with ECR repository objects."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def compute_stack(self, app):
        """Create compute stack for dependencies."""
        return ComputeStack(app, "ECRTestCompute", environment_name="dev")

    @pytest.fixture
    def ecr_stack(self, app):
        """Create ECR stack for repository objects."""
        return ECRStack(app, "ECRTestECR", environment_name="dev")

    def test_creates_with_ecr_repositories(self, app, compute_stack, ecr_stack):
        """Stack should accept ECR repository objects."""
        stack = ServicesStack(
            app,
            "ECRRepoStack",
            environment_name="dev",
            vpc=compute_stack.vpc,
            cluster=compute_stack.cluster,
            ecr_repositories=ecr_stack.repositories,
        )
        assert stack.validator_service is not None
        assert stack.scraper_task_definition is not None

    def test_ecr_repos_auto_grant_pull_permissions(self, app, compute_stack, ecr_stack):
        """Using ECR repo objects should auto-grant image pull permissions."""
        stack = ServicesStack(
            app,
            "ECRPermStack",
            environment_name="dev",
            vpc=compute_stack.vpc,
            cluster=compute_stack.cluster,
            ecr_repositories=ecr_stack.repositories,
        )
        template = assertions.Template.from_stack(stack)
        # ECR repositories auto-grant pull permissions via IAM policy
        template.has_resource_properties(
            "AWS::IAM::Policy",
            {
                "PolicyDocument": assertions.Match.object_like(
                    {
                        "Statement": assertions.Match.array_with(
                            [
                                assertions.Match.object_like(
                                    {
                                        "Action": assertions.Match.array_with(
                                            [
                                                "ecr:BatchCheckLayerAvailability",
                                            ]
                                        ),
                                        "Effect": "Allow",
                                    }
                                )
                            ]
                        )
                    }
                )
            },
        )
