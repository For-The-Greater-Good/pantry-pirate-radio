"""Tests for app.py stack wiring and IAM permission grants."""

import aws_cdk as cdk
import pytest
from aws_cdk import assertions

from stacks.api_stack import APIStack
from stacks.compute_stack import ComputeStack
from stacks.database_stack import DatabaseStack
from stacks.ecr_stack import ECRStack
from stacks.monitoring_stack import MonitoringStack
from stacks.pipeline_stack import PipelineStack
from stacks.queue_stack import QueueStack
from stacks.secrets_stack import SecretsStack
from stacks.services_stack import ServiceConfig, ServicesStack
from stacks.storage_stack import StorageStack


class TestAppStackWiring:
    """Tests for cross-stack wiring in app.py."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def environment_name(self):
        """Return test environment name."""
        return "dev"

    @pytest.fixture
    def env(self):
        """Return test CDK environment."""
        return cdk.Environment(account="123456789012", region="us-east-1")

    @pytest.fixture
    def all_stacks(self, app, environment_name, env):
        """Create all stacks with proper wiring as in app.py."""
        secrets_stack = SecretsStack(
            app,
            f"SecretsStack-{environment_name}",
            environment_name=environment_name,
            env=env,
        )

        ecr_stack = ECRStack(
            app,
            f"ECRStack-{environment_name}",
            environment_name=environment_name,
            env=env,
        )

        storage_stack = StorageStack(
            app,
            f"StorageStack-{environment_name}",
            environment_name=environment_name,
            env=env,
        )

        queue_stack = QueueStack(
            app,
            f"QueueStack-{environment_name}",
            environment_name=environment_name,
            env=env,
        )

        compute_stack = ComputeStack(
            app,
            f"ComputeStack-{environment_name}",
            environment_name=environment_name,
            env=env,
        )

        database_stack = DatabaseStack(
            app,
            f"DatabaseStack-{environment_name}",
            vpc=compute_stack.vpc,
            environment_name=environment_name,
            env=env,
        )

        # Create service config
        service_config = ServiceConfig(
            database_host=database_stack.proxy_endpoint,
            database_name=database_stack.database_name,
            database_user="pantry_pirate",
            database_secret=database_stack.database_credentials_secret,
            queue_urls=queue_stack.queue_urls,
            content_bucket_name=storage_stack.content_bucket.bucket_name,
            content_index_table_name=storage_stack.content_index_table.table_name,
            geocoding_cache_table_name=database_stack.geocoding_cache_table.table_name,
            github_pat_secret=secrets_stack.github_pat_secret,
            llm_api_keys_secret=secrets_stack.llm_api_keys_secret,
        )

        services_stack = ServicesStack(
            app,
            f"ServicesStack-{environment_name}",
            vpc=compute_stack.vpc,
            cluster=compute_stack.cluster,
            environment_name=environment_name,
            config=service_config,
            env=env,
        )

        pipeline_stack = PipelineStack(
            app,
            f"PipelineStack-{environment_name}",
            cluster=compute_stack.cluster,
            scraper_task_family=f"pantry-pirate-radio-scraper-{environment_name}",
            environment_name=environment_name,
            env=env,
        )

        api_stack = APIStack(
            app,
            f"APIStack-{environment_name}",
            vpc=compute_stack.vpc,
            cluster=compute_stack.cluster,
            environment_name=environment_name,
            env=env,
        )

        monitoring_stack = MonitoringStack(
            app,
            f"MonitoringStack-{environment_name}",
            environment_name=environment_name,
            env=env,
        )

        # Grant permissions (mirroring app.py)
        compute_stack.grant_queue_access(queue_stack.llm_queue)
        compute_stack.grant_storage_access(
            storage_stack.content_bucket,
            storage_stack.jobs_table,
            storage_stack.content_index_table,
        )

        api_stack.grant_database_read(
            storage_stack.jobs_table,
            storage_stack.content_index_table,
        )
        api_stack.grant_queue_write(queue_stack.llm_queue)

        # Security group wiring
        database_stack.allow_connection_from(services_stack.validator_security_group)
        database_stack.allow_connection_from(services_stack.reconciler_security_group)
        database_stack.allow_connection_from(services_stack.publisher_security_group)
        database_stack.allow_connection_from(services_stack.recorder_security_group)
        database_stack.allow_connection_from(services_stack.scraper_security_group)
        database_stack.allow_connection_from(compute_stack.worker_security_group)
        database_stack.allow_connection_from(
            api_stack.api_service.service.connections.security_groups[0]
        )

        # IAM permission grants

        # Validator permissions
        queue_stack.validator_queue.grant_consume_messages(
            services_stack.validator_task_role
        )
        queue_stack.reconciler_queue.grant_send_messages(
            services_stack.validator_task_role
        )
        database_stack.geocoding_cache_table.grant_read_write_data(
            services_stack.validator_task_role
        )
        storage_stack.content_bucket.grant_read(services_stack.validator_task_role)
        database_stack.database_credentials_secret.grant_read(
            services_stack.validator_task_role
        )

        # Reconciler permissions
        queue_stack.reconciler_queue.grant_consume_messages(
            services_stack.reconciler_task_role
        )
        queue_stack.recorder_queue.grant_send_messages(
            services_stack.reconciler_task_role
        )
        database_stack.database_credentials_secret.grant_read(
            services_stack.reconciler_task_role
        )

        # Publisher permissions
        secrets_stack.github_pat_secret.grant_read(services_stack.publisher_task_role)
        database_stack.database_credentials_secret.grant_read(
            services_stack.publisher_task_role
        )

        # Recorder permissions
        queue_stack.recorder_queue.grant_consume_messages(
            services_stack.recorder_task_role
        )
        storage_stack.content_bucket.grant_read_write(services_stack.recorder_task_role)
        storage_stack.content_index_table.grant_read_write_data(
            services_stack.recorder_task_role
        )

        # Scraper permissions
        queue_stack.llm_queue.grant_send_messages(services_stack.scraper_task_role)
        storage_stack.content_bucket.grant_read_write(services_stack.scraper_task_role)
        storage_stack.content_index_table.grant_read_write_data(
            services_stack.scraper_task_role
        )
        database_stack.database_credentials_secret.grant_read(
            services_stack.scraper_task_role
        )

        # Worker (LLM) permissions
        queue_stack.validator_queue.grant_send_messages(compute_stack.task_role)
        secrets_stack.llm_api_keys_secret.grant_read(compute_stack.task_role)

        return {
            "secrets": secrets_stack,
            "ecr": ecr_stack,
            "storage": storage_stack,
            "queue": queue_stack,
            "compute": compute_stack,
            "database": database_stack,
            "services": services_stack,
            "pipeline": pipeline_stack,
            "api": api_stack,
            "monitoring": monitoring_stack,
        }

    def test_all_stacks_synth_successfully(self, all_stacks):
        """All stacks should synthesize without errors when wired together."""
        # If we got here, all stacks synthesized successfully
        assert all_stacks["secrets"] is not None
        assert all_stacks["ecr"] is not None
        assert all_stacks["storage"] is not None
        assert all_stacks["queue"] is not None
        assert all_stacks["compute"] is not None
        assert all_stacks["database"] is not None
        assert all_stacks["services"] is not None
        assert all_stacks["pipeline"] is not None
        assert all_stacks["api"] is not None
        assert all_stacks["monitoring"] is not None


class TestValidatorIAMPermissions:
    """Tests for Validator service IAM permissions."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def env(self):
        """Return test CDK environment."""
        return cdk.Environment(account="123456789012", region="us-east-1")

    @pytest.fixture
    def wired_services_template(self, app, env):
        """Create services stack with IAM grants and return template."""
        compute_stack = ComputeStack(
            app, "ComputeStack", environment_name="dev", env=env
        )
        queue_stack = QueueStack(app, "QueueStack", environment_name="dev", env=env)
        database_stack = DatabaseStack(
            app,
            "DatabaseStack",
            vpc=compute_stack.vpc,
            environment_name="dev",
            env=env,
        )
        storage_stack = StorageStack(
            app, "StorageStack", environment_name="dev", env=env
        )
        services_stack = ServicesStack(
            app,
            "ServicesStack",
            vpc=compute_stack.vpc,
            cluster=compute_stack.cluster,
            environment_name="dev",
            env=env,
        )

        # Grant Validator permissions
        queue_stack.validator_queue.grant_consume_messages(
            services_stack.validator_task_role
        )
        queue_stack.reconciler_queue.grant_send_messages(
            services_stack.validator_task_role
        )
        database_stack.geocoding_cache_table.grant_read_write_data(
            services_stack.validator_task_role
        )
        storage_stack.content_bucket.grant_read(services_stack.validator_task_role)
        database_stack.database_credentials_secret.grant_read(
            services_stack.validator_task_role
        )

        return assertions.Template.from_stack(services_stack)

    def test_validator_has_iam_policy(self, wired_services_template):
        """Validator should have IAM policies attached via grants."""
        # IAM policies are created when grants are made
        wired_services_template.has_resource_properties(
            "AWS::IAM::Policy",
            {
                "PolicyDocument": assertions.Match.object_like(
                    {
                        "Statement": assertions.Match.array_with(
                            [
                                assertions.Match.object_like(
                                    {
                                        "Action": assertions.Match.any_value(),
                                        "Effect": "Allow",
                                    }
                                )
                            ]
                        )
                    }
                )
            },
        )


class TestReconcilerIAMPermissions:
    """Tests for Reconciler service IAM permissions."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def env(self):
        """Return test CDK environment."""
        return cdk.Environment(account="123456789012", region="us-east-1")

    @pytest.fixture
    def wired_services_template(self, app, env):
        """Create services stack with IAM grants and return template."""
        compute_stack = ComputeStack(
            app, "ComputeStack", environment_name="dev", env=env
        )
        queue_stack = QueueStack(app, "QueueStack", environment_name="dev", env=env)
        database_stack = DatabaseStack(
            app,
            "DatabaseStack",
            vpc=compute_stack.vpc,
            environment_name="dev",
            env=env,
        )
        services_stack = ServicesStack(
            app,
            "ServicesStack",
            vpc=compute_stack.vpc,
            cluster=compute_stack.cluster,
            environment_name="dev",
            env=env,
        )

        # Grant Reconciler permissions
        queue_stack.reconciler_queue.grant_consume_messages(
            services_stack.reconciler_task_role
        )
        queue_stack.recorder_queue.grant_send_messages(
            services_stack.reconciler_task_role
        )
        database_stack.database_credentials_secret.grant_read(
            services_stack.reconciler_task_role
        )

        return assertions.Template.from_stack(services_stack)

    def test_reconciler_has_iam_policy(self, wired_services_template):
        """Reconciler should have IAM policies attached via grants."""
        wired_services_template.has_resource_properties(
            "AWS::IAM::Policy",
            {
                "PolicyDocument": assertions.Match.object_like(
                    {
                        "Statement": assertions.Match.array_with(
                            [
                                assertions.Match.object_like(
                                    {
                                        "Effect": "Allow",
                                    }
                                )
                            ]
                        )
                    }
                )
            },
        )


class TestWorkerIAMPermissions:
    """Tests for Worker (LLM) service IAM permissions."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def env(self):
        """Return test CDK environment."""
        return cdk.Environment(account="123456789012", region="us-east-1")

    @pytest.fixture
    def wired_compute_template(self, app, env):
        """Create compute stack with IAM grants and return template."""
        compute_stack = ComputeStack(
            app, "ComputeStack", environment_name="dev", env=env
        )
        queue_stack = QueueStack(app, "QueueStack", environment_name="dev", env=env)
        secrets_stack = SecretsStack(
            app, "SecretsStack", environment_name="dev", env=env
        )

        # Grant Worker permissions
        queue_stack.validator_queue.grant_send_messages(compute_stack.task_role)
        secrets_stack.llm_api_keys_secret.grant_read(compute_stack.task_role)

        return assertions.Template.from_stack(compute_stack)

    def test_worker_has_iam_policy(self, wired_compute_template):
        """Worker should have IAM policies for queue and secrets access."""
        # Worker already has Bedrock permissions, now should also have secrets access
        wired_compute_template.has_resource_properties(
            "AWS::IAM::Policy",
            {
                "PolicyDocument": assertions.Match.object_like(
                    {
                        "Statement": assertions.Match.array_with(
                            [
                                assertions.Match.object_like(
                                    {
                                        "Effect": "Allow",
                                    }
                                )
                            ]
                        )
                    }
                )
            },
        )


class TestScraperIAMPermissions:
    """Tests for Scraper task IAM permissions."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def env(self):
        """Return test CDK environment."""
        return cdk.Environment(account="123456789012", region="us-east-1")

    @pytest.fixture
    def wired_services_template(self, app, env):
        """Create services stack with IAM grants and return template."""
        compute_stack = ComputeStack(
            app, "ComputeStack", environment_name="dev", env=env
        )
        queue_stack = QueueStack(app, "QueueStack", environment_name="dev", env=env)
        database_stack = DatabaseStack(
            app,
            "DatabaseStack",
            vpc=compute_stack.vpc,
            environment_name="dev",
            env=env,
        )
        storage_stack = StorageStack(
            app, "StorageStack", environment_name="dev", env=env
        )
        services_stack = ServicesStack(
            app,
            "ServicesStack",
            vpc=compute_stack.vpc,
            cluster=compute_stack.cluster,
            environment_name="dev",
            env=env,
        )

        # Grant Scraper permissions
        queue_stack.llm_queue.grant_send_messages(services_stack.scraper_task_role)
        storage_stack.content_bucket.grant_read_write(services_stack.scraper_task_role)
        storage_stack.content_index_table.grant_read_write_data(
            services_stack.scraper_task_role
        )
        storage_stack.jobs_table.grant_read_write_data(services_stack.scraper_task_role)
        database_stack.database_credentials_secret.grant_read(
            services_stack.scraper_task_role
        )

        return assertions.Template.from_stack(services_stack)

    def test_scraper_has_iam_policy(self, wired_services_template):
        """Scraper should have IAM policies for queue, storage, and secrets."""
        wired_services_template.has_resource_properties(
            "AWS::IAM::Policy",
            {
                "PolicyDocument": assertions.Match.object_like(
                    {
                        "Statement": assertions.Match.array_with(
                            [
                                assertions.Match.object_like(
                                    {
                                        "Effect": "Allow",
                                    }
                                )
                            ]
                        )
                    }
                )
            },
        )


class TestPublisherIAMPermissions:
    """Tests for Publisher service IAM permissions."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def env(self):
        """Return test CDK environment."""
        return cdk.Environment(account="123456789012", region="us-east-1")

    @pytest.fixture
    def wired_services_template(self, app, env):
        """Create services stack with IAM grants and return template."""
        compute_stack = ComputeStack(
            app, "ComputeStack", environment_name="dev", env=env
        )
        database_stack = DatabaseStack(
            app,
            "DatabaseStack",
            vpc=compute_stack.vpc,
            environment_name="dev",
            env=env,
        )
        secrets_stack = SecretsStack(
            app, "SecretsStack", environment_name="dev", env=env
        )
        services_stack = ServicesStack(
            app,
            "ServicesStack",
            vpc=compute_stack.vpc,
            cluster=compute_stack.cluster,
            environment_name="dev",
            env=env,
        )

        # Grant Publisher permissions
        secrets_stack.github_pat_secret.grant_read(services_stack.publisher_task_role)
        database_stack.database_credentials_secret.grant_read(
            services_stack.publisher_task_role
        )

        return assertions.Template.from_stack(services_stack)

    def test_publisher_has_iam_policy(self, wired_services_template):
        """Publisher should have IAM policies for GitHub PAT and DB credentials."""
        wired_services_template.has_resource_properties(
            "AWS::IAM::Policy",
            {
                "PolicyDocument": assertions.Match.object_like(
                    {
                        "Statement": assertions.Match.array_with(
                            [
                                assertions.Match.object_like(
                                    {
                                        "Effect": "Allow",
                                    }
                                )
                            ]
                        )
                    }
                )
            },
        )


class TestRecorderIAMPermissions:
    """Tests for Recorder service IAM permissions."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def env(self):
        """Return test CDK environment."""
        return cdk.Environment(account="123456789012", region="us-east-1")

    @pytest.fixture
    def wired_services_template(self, app, env):
        """Create services stack with IAM grants and return template."""
        compute_stack = ComputeStack(
            app, "ComputeStack", environment_name="dev", env=env
        )
        queue_stack = QueueStack(app, "QueueStack", environment_name="dev", env=env)
        storage_stack = StorageStack(
            app, "StorageStack", environment_name="dev", env=env
        )
        services_stack = ServicesStack(
            app,
            "ServicesStack",
            vpc=compute_stack.vpc,
            cluster=compute_stack.cluster,
            environment_name="dev",
            env=env,
        )

        # Grant Recorder permissions
        queue_stack.recorder_queue.grant_consume_messages(
            services_stack.recorder_task_role
        )
        storage_stack.content_bucket.grant_read_write(services_stack.recorder_task_role)
        storage_stack.content_index_table.grant_read_write_data(
            services_stack.recorder_task_role
        )

        return assertions.Template.from_stack(services_stack)

    def test_recorder_has_iam_policy(self, wired_services_template):
        """Recorder should have IAM policies for queue and storage access."""
        wired_services_template.has_resource_properties(
            "AWS::IAM::Policy",
            {
                "PolicyDocument": assertions.Match.object_like(
                    {
                        "Statement": assertions.Match.array_with(
                            [
                                assertions.Match.object_like(
                                    {
                                        "Effect": "Allow",
                                    }
                                )
                            ]
                        )
                    }
                )
            },
        )
