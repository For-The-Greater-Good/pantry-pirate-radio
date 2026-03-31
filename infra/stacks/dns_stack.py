"""DNS Stack for Pantry Pirate Radio.

Creates Route 53 records and an ACM wildcard certificate for
services under the delegated subdomain (e.g. lighthouse.plentiful.org).

Records created:
  - api.{domain}       → API Gateway HTTP API
  - metabase.{domain}  → NLB for Metabase Cloud access
  - exports.{domain}   → S3 exports bucket (website redirect)

Amplify (portal) manages its own custom domain outside this stack.

All configuration comes from environment variables:
  HOSTED_ZONE_ID  — Route 53 hosted zone ID
  DOMAIN_NAME     — Base domain (e.g. lighthouse.plentiful.org)
"""

from aws_cdk import CfnOutput, Duration, Stack
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_route53_targets as targets
from aws_cdk import aws_elasticloadbalancingv2 as elbv2


class DnsStack(Stack):
    """Route 53 records + ACM wildcard cert for the delegated subdomain."""

    def __init__(
        self,
        scope,
        construct_id: str,
        *,
        environment_name: str,
        hosted_zone_id: str,
        domain_name: str,
        api_gateway_domain: str,
        nlb: elbv2.INetworkLoadBalancer | None = None,
        exports_bucket_name: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.environment_name = environment_name

        # Import the hosted zone (created outside CDK)
        zone = route53.HostedZone.from_hosted_zone_attributes(
            self, "HostedZone",
            hosted_zone_id=hosted_zone_id,
            zone_name=domain_name,
        )

        # Wildcard ACM certificate with DNS validation
        self.certificate = acm.Certificate(
            self, "WildcardCert",
            domain_name=f"*.{domain_name}",
            subject_alternative_names=[domain_name],
            validation=acm.CertificateValidation.from_dns(zone),
        )

        CfnOutput(self, "CertificateArn", value=self.certificate.certificate_arn)

        # api.{domain} → API Gateway
        # API Gateway execute-api domains are regional, use CNAME
        route53.CnameRecord(
            self, "ApiRecord",
            zone=zone,
            record_name="api",
            domain_name=api_gateway_domain,
            ttl=Duration.minutes(5),
        )

        # metabase.{domain} → NLB
        if nlb:
            route53.ARecord(
                self, "MetabaseRecord",
                zone=zone,
                record_name="metabase",
                target=route53.RecordTarget.from_alias(
                    targets.LoadBalancerTarget(nlb)
                ),
            )

        # exports.{domain} → S3 bucket website
        # S3 website hosting requires bucket name to match the domain,
        # which ours doesn't. Use a CNAME to the S3 website endpoint instead.
        if exports_bucket_name:
            route53.CnameRecord(
                self, "ExportsRecord",
                zone=zone,
                record_name="exports",
                domain_name=f"{exports_bucket_name}.s3.amazonaws.com",
                ttl=Duration.minutes(5),
            )

        CfnOutput(
            self, "DomainName",
            value=domain_name,
            description="Base domain for all services",
        )
