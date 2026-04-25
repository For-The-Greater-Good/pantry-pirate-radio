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
    return (
        app,
        stack,
        s3.Bucket(
            stack,
            "ExportsBucket",
            bucket_name="pantry-pirate-radio-exports-test",
        ),
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

    def test_publishes_cloudfront_distribution_id_to_ssm(self, env, exports_bucket):
        """DnsStack writes the distribution ID to SSM so the publisher
        task in ServicesStack can read it without a CDK cross-stack cycle."""
        app, _bucket_stack, bucket = exports_bucket
        dns = DnsStack(
            app,
            "DnsStackSsmParam",
            environment_name="dev",
            hosted_zone_id="Z0123456789ABCDEFGHIJ",
            domain_name="example.com",
            http_api_id="abc123",
            exports_bucket=bucket,
            env=env,
        )
        template = assertions.Template.from_stack(dns)

        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {
                "Name": (
                    "/pantry-pirate-radio/dev" "/exports-cloudfront-distribution-id"
                ),
                "Type": "String",
            },
        )

    def test_no_ssm_param_without_cloudfront_distribution(self, env):
        """SSM parameter is only written when the CloudFront distribution
        is actually created (i.e. when exports_bucket was provided)."""
        app = cdk.App()
        dns = DnsStack(
            app,
            "DnsStackNoSsmParam",
            environment_name="dev",
            hosted_zone_id="Z0123456789ABCDEFGHIJ",
            domain_name="example.com",
            http_api_id="abc123",
            exports_bucket=None,
            env=env,
        )
        template = assertions.Template.from_stack(dns)
        template.resource_count_is("AWS::SSM::Parameter", 0)


class TestTwilioDomainVerification:
    """Tests for the `_twilio.<domain>` TXT record that proves DNS
    ownership of the subdomain to Twilio's organization-domain
    verification flow."""

    def test_creates_twilio_verification_txt_record(self, env):
        app = cdk.App()
        dns = DnsStack(
            app,
            "DnsStackTwilioTxt",
            environment_name="dev",
            hosted_zone_id="Z0123456789ABCDEFGHIJ",
            domain_name="example.com",
            http_api_id="abc123",
            env=env,
        )
        template = assertions.Template.from_stack(dns)

        # CDK quotes TXT values per RFC 1035; the record value is the
        # verification token Twilio displays in its UI.
        template.has_resource_properties(
            "AWS::Route53::RecordSet",
            {
                "Type": "TXT",
                "Name": "_twilio.example.com.",
                "ResourceRecords": [
                    '"twilio-domain-verification=3549c54fc8e07957c0457e0640eeee95"',
                ],
            },
        )
