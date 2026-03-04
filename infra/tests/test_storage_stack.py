"""Tests for StorageStack CDK stack."""

import aws_cdk as cdk
import pytest
from aws_cdk import assertions

from stacks.storage_stack import StorageStack


class TestStorageStackResources:
    """Tests for StorageStack resource creation."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def dev_stack(self, app):
        """Create dev environment stack."""
        return StorageStack(app, "TestStorageStack", environment_name="dev")

    @pytest.fixture
    def prod_stack(self, app):
        """Create prod environment stack."""
        return StorageStack(app, "TestStorageStackProd", environment_name="prod")

    @pytest.fixture
    def dev_template(self, dev_stack):
        """Get CloudFormation template from dev stack."""
        return assertions.Template.from_stack(dev_stack)

    @pytest.fixture
    def prod_template(self, prod_stack):
        """Get CloudFormation template from prod stack."""
        return assertions.Template.from_stack(prod_stack)

    def test_creates_s3_bucket(self, dev_template):
        """StorageStack should create S3 bucket for content store."""
        dev_template.resource_count_is("AWS::S3::Bucket", 1)

    def test_s3_bucket_has_encryption(self, dev_template):
        """S3 bucket should have server-side encryption enabled."""
        dev_template.has_resource_properties(
            "AWS::S3::Bucket",
            {
                "BucketEncryption": {
                    "ServerSideEncryptionConfiguration": [
                        {"ServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}
                    ]
                }
            },
        )

    def test_s3_bucket_has_versioning(self, dev_template):
        """S3 bucket should have versioning enabled."""
        dev_template.has_resource_properties(
            "AWS::S3::Bucket",
            {"VersioningConfiguration": {"Status": "Enabled"}},
        )

    def test_s3_bucket_blocks_public_access(self, dev_template):
        """S3 bucket should block all public access."""
        dev_template.has_resource_properties(
            "AWS::S3::Bucket",
            {
                "PublicAccessBlockConfiguration": {
                    "BlockPublicAcls": True,
                    "BlockPublicPolicy": True,
                    "IgnorePublicAcls": True,
                    "RestrictPublicBuckets": True,
                }
            },
        )

    def test_s3_bucket_has_lifecycle_rules(self, dev_template):
        """S3 bucket should have lifecycle rules for cost optimization."""
        dev_template.has_resource_properties(
            "AWS::S3::Bucket",
            {
                "LifecycleConfiguration": {
                    "Rules": assertions.Match.array_with(
                        [
                            assertions.Match.object_like(
                                {
                                    "Id": "TransitionOldVersions",
                                    "Status": "Enabled",
                                }
                            )
                        ]
                    )
                }
            },
        )

    def test_creates_jobs_dynamodb_table(self, dev_template):
        """StorageStack should create DynamoDB table for jobs."""
        dev_template.resource_count_is("AWS::DynamoDB::Table", 2)

    def test_jobs_table_has_correct_key_schema(self, dev_template):
        """Jobs table should use job_id as partition key."""
        dev_template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {
                "KeySchema": [{"AttributeName": "job_id", "KeyType": "HASH"}],
                "AttributeDefinitions": assertions.Match.array_with(
                    [{"AttributeName": "job_id", "AttributeType": "S"}]
                ),
            },
        )

    def test_jobs_table_has_pay_per_request_billing(self, dev_template):
        """Jobs table should use PAY_PER_REQUEST billing mode."""
        dev_template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {"BillingMode": "PAY_PER_REQUEST"},
        )

    def test_jobs_table_has_ttl(self, dev_template):
        """Jobs table should have TTL enabled."""
        dev_template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {
                "TimeToLiveSpecification": {
                    "AttributeName": "ttl",
                    "Enabled": True,
                }
            },
        )

    def test_jobs_table_has_status_gsi(self, dev_template):
        """Jobs table should have GSI for querying by status."""
        dev_template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {
                "GlobalSecondaryIndexes": assertions.Match.array_with(
                    [
                        assertions.Match.object_like(
                            {
                                "IndexName": "status-created_at-index",
                                "KeySchema": [
                                    {"AttributeName": "status", "KeyType": "HASH"},
                                    {"AttributeName": "created_at", "KeyType": "RANGE"},
                                ],
                            }
                        )
                    ]
                )
            },
        )

    def test_content_index_table_has_correct_key_schema(self, dev_template):
        """Content index table should use content_hash as partition key."""
        dev_template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {
                "KeySchema": [{"AttributeName": "content_hash", "KeyType": "HASH"}],
            },
        )


class TestStorageStackEnvironments:
    """Tests for environment-specific configuration."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    def test_dev_bucket_auto_delete(self, app):
        """Dev environment bucket should have auto-delete enabled."""
        stack = StorageStack(app, "DevStack", environment_name="dev")
        template = assertions.Template.from_stack(stack)

        # In dev, bucket should have UpdateReplacePolicy: Delete
        template.has_resource(
            "AWS::S3::Bucket",
            {
                "DeletionPolicy": "Delete",
                "UpdateReplacePolicy": "Delete",
            },
        )

    def test_prod_bucket_retained(self, app):
        """Prod environment bucket should be retained on deletion."""
        stack = StorageStack(app, "ProdStack", environment_name="prod")
        template = assertions.Template.from_stack(stack)

        # In prod, bucket should have DeletionPolicy: Retain
        template.has_resource(
            "AWS::S3::Bucket",
            {
                "DeletionPolicy": "Retain",
                "UpdateReplacePolicy": "Retain",
            },
        )

    def test_prod_tables_have_pitr(self, app):
        """Prod environment tables should have point-in-time recovery."""
        stack = StorageStack(app, "ProdStack2", environment_name="prod")
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {
                "PointInTimeRecoverySpecification": {"PointInTimeRecoveryEnabled": True}
            },
        )

    def test_dev_tables_no_pitr(self, app):
        """Dev environment tables should not have point-in-time recovery enabled."""
        stack = StorageStack(app, "DevStack2", environment_name="dev")
        template = assertions.Template.from_stack(stack)

        # Dev tables should have PITR specification but with enabled=False
        template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {
                "PointInTimeRecoverySpecification": {
                    "PointInTimeRecoveryEnabled": False
                }
            },
        )


class TestStorageStackAttributes:
    """Tests for stack attributes and outputs."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def stack(self, app):
        """Create stack for testing."""
        return StorageStack(app, "AttrTestStack", environment_name="dev")

    def test_exposes_content_bucket(self, stack):
        """Stack should expose content_bucket attribute."""
        assert stack.content_bucket is not None
        assert hasattr(stack.content_bucket, "bucket_name")

    def test_exposes_jobs_table(self, stack):
        """Stack should expose jobs_table attribute."""
        assert stack.jobs_table is not None
        assert hasattr(stack.jobs_table, "table_name")

    def test_exposes_content_index_table(self, stack):
        """Stack should expose content_index_table attribute."""
        assert stack.content_index_table is not None
        assert hasattr(stack.content_index_table, "table_name")

    def test_environment_name_stored(self, stack):
        """Stack should store environment name."""
        assert stack.environment_name == "dev"
