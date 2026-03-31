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
from aws_cdk import aws_apigatewayv2 as apigwv2
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
        http_api_id: str,
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

        # api.{domain} → API Gateway custom domain
        # Creates a custom domain on API Gateway with our ACM cert,
        # maps it to the HTTP API, then points DNS at it.
        api_domain_name = f"api.{domain_name}"
        custom_domain = apigwv2.CfnDomainName(
            self, "ApiCustomDomain",
            domain_name=api_domain_name,
            domain_name_configurations=[
                apigwv2.CfnDomainName.DomainNameConfigurationProperty(
                    certificate_arn=self.certificate.certificate_arn,
                    endpoint_type="REGIONAL",
                    security_policy="TLS_1_2",
                )
            ],
        )

        # Map the custom domain to the HTTP API ($default stage)
        apigwv2.CfnApiMapping(
            self, "ApiMapping",
            api_id=http_api_id,
            domain_name=api_domain_name,
            stage="$default",
        ).add_dependency(custom_domain)

        # Point DNS at the API Gateway custom domain's target
        route53.CnameRecord(
            self, "ApiRecord",
            zone=zone,
            record_name="api",
            domain_name=custom_domain.attr_regional_domain_name,
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
