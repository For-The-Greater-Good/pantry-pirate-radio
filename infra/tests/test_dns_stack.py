"""Tests for DnsStack CDK stack (Route 53 + CloudFront)."""

import aws_cdk as cdk
import pytest
from aws_cdk import assertions
from aws_cdk import aws_s3 as s3

from stacks.dns_stack import DnsStack


@pytest.fixture
def env():
    return cdk.Environment(account="123456789012", region="us-east-1")


@pytest.fixture
def exports_bucket(env):
    # Build the bucket in its own stack so the DnsStack can reference it
    # without owning the bucket resource.
    app = cdk.App()
    stack = cdk.Stack(app, "ExportsBucketStack", env=env)
    return app, stack, s3.Bucket(
        stack,
        "ExportsBucket",
        bucket_name="pantry-pirate-radio-exports-test",
    )


class TestExportsCloudFront:
    """Tests for the exports.{domain} CloudFront distribution."""

    def test_creates_cloudfront_distribution_for_exports(self, env, exports_bucket):
        app, _bucket_stack, bucket = exports_bucket
        dns = DnsStack(
            app,
            "DnsStackExportsCF",
            environment_name="dev",
            hosted_zone_id="Z0123456789ABCDEFGHIJ",
            domain_name="example.com",
            http_api_id="abc123",
            exports_bucket=bucket,
            env=env,
        )
        template = assertions.Template.from_stack(dns)

        # One distribution, aliased to exports.{domain}
        template.resource_count_is("AWS::CloudFront::Distribution", 1)
        template.has_resource_properties(
            "AWS::CloudFront::Distribution",
            {
                "DistributionConfig": {
                    "Aliases": ["exports.example.com"],
                },
            },
        )

    def test_creates_a_and_aaaa_alias_records_for_exports(self, env, exports_bucket):
        app, _bucket_stack, bucket = exports_bucket
        dns = DnsStack(
            app,
            "DnsStackExportsRecords",
            environment_name="dev",
            hosted_zone_id="Z0123456789ABCDEFGHIJ",
            domain_name="example.com",
            http_api_id="abc123",
            exports_bucket=bucket,
            env=env,
        )
        template = assertions.Template.from_stack(dns)

        # ALIAS to CloudFront is an A record (plus AAAA for IPv6)
        template.has_resource_properties(
            "AWS::Route53::RecordSet",
            {
                "Type": "A",
                "Name": "exports.example.com.",
            },
        )
        template.has_resource_properties(
            "AWS::Route53::RecordSet",
            {
                "Type": "AAAA",
                "Name": "exports.example.com.",
            },
        )

    def test_no_cloudfront_when_exports_bucket_missing(self, env):
        app = cdk.App()
        dns = DnsStack(
            app,
            "DnsStackNoExports",
            environment_name="dev",
            hosted_zone_id="Z0123456789ABCDEFGHIJ",
            domain_name="example.com",
            http_api_id="abc123",
            exports_bucket=None,
            env=env,
        )
        template = assertions.Template.from_stack(dns)

        template.resource_count_is("AWS::CloudFront::Distribution", 0)
        # No exports.* record either
        for record in template.find_resources("AWS::Route53::RecordSet").values():
            assert not record["Properties"]["Name"].startswith("exports.")
