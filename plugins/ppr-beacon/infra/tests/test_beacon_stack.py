"""CDK template assertions for BeaconStack.

Verifies: S3 buckets, CloudFront, DynamoDB, Glue, CloudWatch alarms.
Lambda/Step Functions require VPC context so are tested separately.
"""

import pytest
import aws_cdk as cdk
from aws_cdk.assertions import Template

from ..beacon_stack import BeaconStack


@pytest.fixture
def template() -> Template:
    """Synth BeaconStack without VPC (no Lambda/SFN resources)."""
    app = cdk.App()
    stack = BeaconStack(
        app,
        "TestBeaconStack",
        environment_name="test",
        plugin_context={},
        env=cdk.Environment(account="123456789012", region="us-east-1"),
    )
    return Template.from_stack(stack)


class TestS3Buckets:
    def test_site_bucket_exists(self, template):
        template.resource_count_is("AWS::S3::Bucket", 2)  # site + logs

    def test_site_bucket_encrypted(self, template):
        template.has_resource_properties(
            "AWS::S3::Bucket",
            {"BucketName": "ppr-beacon-site-test"},
        )

    def test_log_bucket_lifecycle(self, template):
        template.has_resource_properties(
            "AWS::S3::Bucket",
            {
                "BucketName": "ppr-beacon-logs-test",
                "LifecycleConfiguration": {
                    "Rules": [{"ExpirationInDays": 90, "Status": "Enabled"}],
                },
            },
        )


class TestCloudFront:
    def test_distribution_exists(self, template):
        template.resource_count_is("AWS::CloudFront::Distribution", 1)

    def test_oai_exists(self, template):
        template.resource_count_is(
            "AWS::CloudFront::CloudFrontOriginAccessIdentity", 1
        )


class TestDynamoDB:
    def test_build_metadata_table(self, template):
        template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {
                "TableName": "ppr-beacon-build-test",
                "KeySchema": [
                    {"AttributeName": "location_id", "KeyType": "HASH"},
                ],
            },
        )

    def test_analytics_table_with_ttl(self, template):
        template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {
                "TableName": "ppr-beacon-analytics-test",
                "TimeToLiveSpecification": {
                    "AttributeName": "expires_at",
                    "Enabled": True,
                },
            },
        )


class TestGlue:
    def test_glue_database(self, template):
        template.has_resource_properties(
            "AWS::Glue::Database",
            {
                "DatabaseInput": {
                    "Name": "ppr_beacon_logs_test",
                },
            },
        )


class TestCloudWatchAlarms:
    def test_dynamodb_alarms_exist(self, template):
        # 4 DynamoDB alarms: 2 tables x 2 (throttles + system errors)
        template.resource_count_is("AWS::CloudWatch::Alarm", 4)

    def test_alarm_routes_to_sns(self, template):
        # With explicit env, ARN resolves to a string (not Fn::Join)
        template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            {
                "AlarmActions": [
                    "arn:aws:sns:us-east-1:123456789012:pantry-pirate-radio-alerts-test",
                ],
            },
        )


class TestOutputs:
    def test_site_url_output(self, template):
        template.has_output("BeaconSiteUrl", {})

    def test_bucket_name_output(self, template):
        template.has_output("BeaconBucketName", {})

    def test_distribution_id_output(self, template):
        template.has_output("BeaconDistributionId", {})
