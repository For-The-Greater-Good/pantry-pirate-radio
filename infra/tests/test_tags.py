"""Tests for resource tagging across all CDK stacks."""

import aws_cdk as cdk
import pytest
from aws_cdk import assertions

from stacks.monitoring_stack import MonitoringStack
from stacks.storage_stack import StorageStack


class TestAppLevelTags:
    """Tests that app-level tags propagate to resources in stacks."""

    @pytest.fixture
    def app(self):
        app = cdk.App()
        cdk.Tags.of(app).add("Project", "pantry-pirate-radio")
        cdk.Tags.of(app).add("Environment", "dev")
        cdk.Tags.of(app).add("ManagedBy", "cdk")
        cdk.Tags.of(app).add("Owner", "for-the-greater-good")
        cdk.Tags.of(app).add("CostCenter", "pantry-pirate-radio-dev")
        return app

    @pytest.fixture
    def storage_stack(self, app):
        return StorageStack(app, "TaggedStorageStack", environment_name="dev")

    @pytest.fixture
    def storage_template(self, storage_stack):
        return assertions.Template.from_stack(storage_stack)

    def test_s3_bucket_has_project_tag(self, storage_template):
        storage_template.has_resource_properties(
            "AWS::S3::Bucket",
            {
                "Tags": assertions.Match.array_with(
                    [
                        assertions.Match.object_like(
                            {"Key": "Project", "Value": "pantry-pirate-radio"}
                        ),
                    ]
                )
            },
        )

    def test_s3_bucket_has_environment_tag(self, storage_template):
        storage_template.has_resource_properties(
            "AWS::S3::Bucket",
            {
                "Tags": assertions.Match.array_with(
                    [
                        assertions.Match.object_like(
                            {"Key": "Environment", "Value": "dev"}
                        ),
                    ]
                )
            },
        )

    def test_s3_bucket_has_managed_by_tag(self, storage_template):
        storage_template.has_resource_properties(
            "AWS::S3::Bucket",
            {
                "Tags": assertions.Match.array_with(
                    [
                        assertions.Match.object_like(
                            {"Key": "ManagedBy", "Value": "cdk"}
                        ),
                    ]
                )
            },
        )

    def test_s3_bucket_has_owner_tag(self, storage_template):
        storage_template.has_resource_properties(
            "AWS::S3::Bucket",
            {
                "Tags": assertions.Match.array_with(
                    [
                        assertions.Match.object_like(
                            {"Key": "Owner", "Value": "for-the-greater-good"}
                        ),
                    ]
                )
            },
        )

    def test_s3_bucket_has_cost_center_tag(self, storage_template):
        storage_template.has_resource_properties(
            "AWS::S3::Bucket",
            {
                "Tags": assertions.Match.array_with(
                    [
                        assertions.Match.object_like(
                            {"Key": "CostCenter", "Value": "pantry-pirate-radio-dev"}
                        ),
                    ]
                )
            },
        )

    def test_dynamodb_table_has_project_tag(self, storage_template):
        storage_template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {
                "Tags": assertions.Match.array_with(
                    [
                        assertions.Match.object_like(
                            {"Key": "Project", "Value": "pantry-pirate-radio"}
                        ),
                    ]
                )
            },
        )


class TestPerStackTags:
    """Tests that per-stack tags are applied correctly."""

    @pytest.fixture
    def app(self):
        return cdk.App()

    def test_stack_tag_applied(self, app):
        stack = StorageStack(app, "StackTagTest", environment_name="dev")
        cdk.Tags.of(stack).add("Stack", "StorageStack-dev")
        template = assertions.Template.from_stack(stack)
        template.has_resource_properties(
            "AWS::S3::Bucket",
            {
                "Tags": assertions.Match.array_with(
                    [
                        assertions.Match.object_like(
                            {"Key": "Stack", "Value": "StorageStack-dev"}
                        ),
                    ]
                )
            },
        )

    def test_monitoring_stack_tag_applied(self, app):
        stack = MonitoringStack(app, "MonStackTagTest", environment_name="dev")
        cdk.Tags.of(stack).add("Stack", "MonitoringStack-dev")
        template = assertions.Template.from_stack(stack)
        template.has_resource_properties(
            "AWS::SNS::Topic",
            {
                "Tags": assertions.Match.array_with(
                    [
                        assertions.Match.object_like(
                            {"Key": "Stack", "Value": "MonitoringStack-dev"}
                        ),
                    ]
                )
            },
        )


class TestProdEnvironmentTags:
    """Tests that tags use correct environment values for prod."""

    def test_prod_tags_use_prod_environment(self):
        app = cdk.App()
        cdk.Tags.of(app).add("Environment", "prod")
        cdk.Tags.of(app).add("CostCenter", "pantry-pirate-radio-prod")
        stack = StorageStack(app, "ProdTagTest", environment_name="prod")
        template = assertions.Template.from_stack(stack)
        # Check Environment tag on at least one S3 bucket
        template.has_resource_properties(
            "AWS::S3::Bucket",
            {
                "Tags": assertions.Match.array_with(
                    [
                        assertions.Match.object_like(
                            {"Key": "Environment", "Value": "prod"}
                        ),
                    ]
                )
            },
        )
        # Verify CostCenter tag separately (S3 buckets may have different tag sets)
        template.has_resource_properties(
            "AWS::S3::Bucket",
            {
                "Tags": assertions.Match.array_with(
                    [
                        assertions.Match.object_like(
                            {"Key": "CostCenter", "Value": "pantry-pirate-radio-prod"}
                        ),
                    ]
                )
            },
        )
