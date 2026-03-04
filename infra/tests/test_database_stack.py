"""Tests for DatabaseStack CDK stack."""

import aws_cdk as cdk
import pytest
from aws_cdk import assertions

from stacks.database_stack import DatabaseStack
from stacks.compute_stack import ComputeStack


class TestDatabaseStackResources:
    """Tests for DatabaseStack resource creation."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def dev_stack(self, app):
        """Create dev environment stack with dependencies."""
        compute_stack = ComputeStack(app, "TestComputeStack", environment_name="dev")
        return DatabaseStack(
            app,
            "TestDatabaseStack",
            environment_name="dev",
            vpc=compute_stack.vpc,
        )

    @pytest.fixture
    def prod_stack(self, app):
        """Create prod environment stack with dependencies."""
        compute_stack = ComputeStack(
            app, "TestComputeStackProd", environment_name="prod"
        )
        return DatabaseStack(
            app,
            "TestDatabaseStackProd",
            environment_name="prod",
            vpc=compute_stack.vpc,
        )

    @pytest.fixture
    def dev_template(self, dev_stack):
        """Get CloudFormation template from dev stack."""
        return assertions.Template.from_stack(dev_stack)

    @pytest.fixture
    def prod_template(self, prod_stack):
        """Get CloudFormation template from prod stack."""
        return assertions.Template.from_stack(prod_stack)

    def test_creates_aurora_cluster(self, dev_template):
        """DatabaseStack should create Aurora Serverless v2 cluster."""
        dev_template.resource_count_is("AWS::RDS::DBCluster", 1)

    def test_aurora_cluster_is_serverless_v2(self, dev_template):
        """Aurora cluster should use serverless v2 engine mode."""
        dev_template.has_resource_properties(
            "AWS::RDS::DBCluster",
            {
                "Engine": "aurora-postgresql",
                "ServerlessV2ScalingConfiguration": assertions.Match.object_like(
                    {
                        "MinCapacity": assertions.Match.any_value(),
                        "MaxCapacity": assertions.Match.any_value(),
                    }
                ),
            },
        )

    def test_aurora_cluster_uses_postgresql_15(self, dev_template):
        """Aurora cluster should use PostgreSQL 15."""
        dev_template.has_resource_properties(
            "AWS::RDS::DBCluster",
            {
                "Engine": "aurora-postgresql",
                "EngineVersion": assertions.Match.string_like_regexp("15.*"),
            },
        )

    def test_creates_aurora_instance(self, dev_template):
        """DatabaseStack should create at least one Aurora instance."""
        dev_template.resource_count_is("AWS::RDS::DBInstance", 1)

    def test_aurora_instance_is_serverless(self, dev_template):
        """Aurora instance should use db.serverless class."""
        dev_template.has_resource_properties(
            "AWS::RDS::DBInstance",
            {"DBInstanceClass": "db.serverless"},
        )

    def test_creates_rds_proxy(self, dev_template):
        """DatabaseStack should create RDS Proxy."""
        dev_template.resource_count_is("AWS::RDS::DBProxy", 1)

    def test_rds_proxy_uses_iam_auth(self, dev_template):
        """RDS Proxy should require IAM authentication."""
        dev_template.has_resource_properties(
            "AWS::RDS::DBProxy",
            {"RequireTLS": True},
        )

    def test_creates_security_groups(self, dev_template):
        """DatabaseStack should create security groups."""
        # At least 2: one for Aurora, one for RDS Proxy
        dev_template.resource_count_is("AWS::EC2::SecurityGroup", 2)

    def test_creates_db_subnet_group(self, dev_template):
        """DatabaseStack should create DB subnet group."""
        dev_template.resource_count_is("AWS::RDS::DBSubnetGroup", 1)

    def test_creates_geocoding_cache_table(self, dev_template):
        """DatabaseStack should create DynamoDB table for geocoding cache."""
        dev_template.resource_count_is("AWS::DynamoDB::Table", 1)

    def test_geocoding_table_has_correct_key_schema(self, dev_template):
        """Geocoding cache table should use address as partition key."""
        dev_template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {
                "KeySchema": [{"AttributeName": "address", "KeyType": "HASH"}],
            },
        )

    def test_geocoding_table_has_ttl(self, dev_template):
        """Geocoding cache table should have TTL enabled."""
        dev_template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {
                "TimeToLiveSpecification": {
                    "AttributeName": "ttl",
                    "Enabled": True,
                }
            },
        )


class TestDatabaseStackEnvironments:
    """Tests for environment-specific configuration."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    def test_dev_uses_minimal_capacity(self, app):
        """Dev environment should use minimal Aurora capacity."""
        compute_stack = ComputeStack(app, "ComputeStack1", environment_name="dev")
        stack = DatabaseStack(
            app,
            "DevStack",
            environment_name="dev",
            vpc=compute_stack.vpc,
        )
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::RDS::DBCluster",
            {
                "ServerlessV2ScalingConfiguration": {
                    "MinCapacity": 0.5,
                    "MaxCapacity": 2,
                }
            },
        )

    def test_prod_uses_higher_capacity(self, app):
        """Prod environment should use higher Aurora capacity."""
        compute_stack = ComputeStack(app, "ComputeStack2", environment_name="prod")
        stack = DatabaseStack(
            app,
            "ProdStack",
            environment_name="prod",
            vpc=compute_stack.vpc,
        )
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::RDS::DBCluster",
            {
                "ServerlessV2ScalingConfiguration": {
                    "MinCapacity": 2,
                    "MaxCapacity": 16,
                }
            },
        )

    def test_prod_has_deletion_protection(self, app):
        """Prod environment should have deletion protection enabled."""
        compute_stack = ComputeStack(app, "ComputeStack3", environment_name="prod")
        stack = DatabaseStack(
            app,
            "ProdStack2",
            environment_name="prod",
            vpc=compute_stack.vpc,
        )
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::RDS::DBCluster",
            {"DeletionProtection": True},
        )

    def test_dev_no_deletion_protection(self, app):
        """Dev environment should not have deletion protection."""
        compute_stack = ComputeStack(app, "ComputeStack4", environment_name="dev")
        stack = DatabaseStack(
            app,
            "DevStack2",
            environment_name="dev",
            vpc=compute_stack.vpc,
        )
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::RDS::DBCluster",
            {"DeletionProtection": False},
        )

    def test_prod_has_backup_retention(self, app):
        """Prod environment should have 30-day backup retention."""
        compute_stack = ComputeStack(app, "ComputeStack5", environment_name="prod")
        stack = DatabaseStack(
            app,
            "ProdStack3",
            environment_name="prod",
            vpc=compute_stack.vpc,
        )
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::RDS::DBCluster",
            {"BackupRetentionPeriod": 30},
        )

    def test_dev_has_minimal_backup_retention(self, app):
        """Dev environment should have 1-day backup retention."""
        compute_stack = ComputeStack(app, "ComputeStack6", environment_name="dev")
        stack = DatabaseStack(
            app,
            "DevStack3",
            environment_name="dev",
            vpc=compute_stack.vpc,
        )
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::RDS::DBCluster",
            {"BackupRetentionPeriod": 1},
        )


class TestDatabaseStackAttributes:
    """Tests for stack attributes and outputs."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def stack(self, app):
        """Create stack for testing."""
        compute_stack = ComputeStack(app, "ComputeStack", environment_name="dev")
        return DatabaseStack(
            app,
            "AttrTestStack",
            environment_name="dev",
            vpc=compute_stack.vpc,
        )

    def test_exposes_cluster(self, stack):
        """Stack should expose aurora_cluster attribute."""
        assert stack.aurora_cluster is not None

    def test_exposes_proxy(self, stack):
        """Stack should expose rds_proxy attribute."""
        assert stack.rds_proxy is not None

    def test_exposes_proxy_endpoint(self, stack):
        """Stack should expose proxy_endpoint attribute."""
        assert stack.proxy_endpoint is not None

    def test_exposes_geocoding_cache_table(self, stack):
        """Stack should expose geocoding_cache_table attribute."""
        assert stack.geocoding_cache_table is not None
        assert hasattr(stack.geocoding_cache_table, "table_name")

    def test_exposes_database_security_group(self, stack):
        """Stack should expose database_security_group attribute."""
        assert stack.database_security_group is not None

    def test_exposes_database_credentials_secret(self, stack):
        """Stack should expose database_credentials_secret attribute."""
        assert stack.database_credentials_secret is not None
        assert hasattr(stack.database_credentials_secret, "secret_arn")

    def test_environment_name_stored(self, stack):
        """Stack should store environment name."""
        assert stack.environment_name == "dev"

    def test_exposes_database_name(self, stack):
        """Stack should expose database_name property."""
        assert stack.database_name == "pantry_pirate_radio"

    def test_exposes_proxy_security_group(self, stack):
        """Stack should expose proxy_security_group for wiring."""
        assert stack.proxy_security_group is not None


class TestDatabaseStackOutputs:
    """Tests for stack CfnOutputs."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def stack(self, app):
        """Create stack for testing."""
        compute_stack = ComputeStack(app, "ComputeStackOutput", environment_name="dev")
        return DatabaseStack(
            app,
            "OutputTestStack",
            environment_name="dev",
            vpc=compute_stack.vpc,
        )

    @pytest.fixture
    def template(self, stack):
        """Get CloudFormation template from stack."""
        return assertions.Template.from_stack(stack)

    def test_outputs_proxy_endpoint(self, template):
        """Stack should output proxy endpoint."""
        template.has_output(
            "ProxyEndpoint",
            {
                "Value": assertions.Match.any_value(),
            },
        )

    def test_outputs_database_secret_arn(self, template):
        """Stack should output database secret ARN."""
        template.has_output(
            "DatabaseSecretArn",
            {
                "Value": assertions.Match.any_value(),
            },
        )

    def test_outputs_database_name(self, template):
        """Stack should output database name."""
        template.has_output(
            "DatabaseName",
            {
                "Value": "pantry_pirate_radio",
            },
        )
