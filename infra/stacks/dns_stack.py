"""DNS Stack for Pantry Pirate Radio.

Creates Route 53 records and an ACM wildcard certificate for
services under the delegated subdomain (e.g. lighthouse.plentiful.org).

Records created:
  - api.{domain}              → API Gateway HTTP API
  - report-webhook.{domain}  → Helm webhook API Gateway
  - metabase.{domain}        → NLB for Metabase Cloud access
  - exports.{domain}         → CloudFront distribution fronting S3 exports bucket

Amplify (portal) manages its own custom domain outside this stack.

All configuration comes from environment variables:
  HOSTED_ZONE_ID  — Route 53 hosted zone ID
  DOMAIN_NAME     — Base domain (e.g. lighthouse.plentiful.org)
"""

from aws_cdk import CfnOutput, Duration, Stack
from aws_cdk import aws_apigatewayv2 as apigwv2
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_route53_targets as targets
from aws_cdk import aws_s3 as s3
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
        webhook_api_id: str | None = None,
        nlb: elbv2.INetworkLoadBalancer | None = None,
        exports_bucket: s3.IBucket | None = None,
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

        # report-webhook.{domain} → Typeform webhook API Gateway.
        # Originally Helm's, folded into ppr-lighthouse's admin
        # surface (AdminWebhook) in ppr-lighthouse PR #61. The
        # webhook_api_id import in infra/app.py still reads from
        # Helm's CloudFormation export until the cutover retires
        # that stack; app.py carries the TODO for the switch.
        if webhook_api_id:
            webhook_domain_name = f"report-webhook.{domain_name}"
            webhook_custom_domain = apigwv2.CfnDomainName(
                self, "WebhookCustomDomain",
                domain_name=webhook_domain_name,
                domain_name_configurations=[
                    apigwv2.CfnDomainName.DomainNameConfigurationProperty(
                        certificate_arn=self.certificate.certificate_arn,
                        endpoint_type="REGIONAL",
                        security_policy="TLS_1_2",
                    )
                ],
            )

            apigwv2.CfnApiMapping(
                self, "WebhookApiMapping",
                api_id=webhook_api_id,
                domain_name=webhook_domain_name,
                stage="$default",
            ).add_dependency(webhook_custom_domain)

            route53.CnameRecord(
                self, "WebhookRecord",
                zone=zone,
                record_name="report-webhook",
                domain_name=webhook_custom_domain.attr_regional_domain_name,
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

        # exports.{domain} → CloudFront distribution fronting the S3 exports bucket.
        # Direct S3 virtual-hosted addressing requires bucket name == hostname, and
        # S3's default certificate only covers *.s3.amazonaws.com, so a raw CNAME
        # breaks on both fronts. CloudFront + the wildcard ACM cert gives us HTTPS,
        # edge caching, and keeps the raw S3 URL working for anyone already using it.
        #
        # Uses HttpOrigin (not S3BucketOrigin) so we don't mutate the bucket's
        # resource policy from this stack — that would create a cross-stack
        # dependency cycle with StorageStack. The bucket already grants public
        # read on sqlite-exports/*, so CloudFront can fetch anonymously.
        if exports_bucket is not None:
            exports_distribution = cloudfront.Distribution(
                self, "ExportsDistribution",
                domain_names=[f"exports.{domain_name}"],
                certificate=self.certificate,
                price_class=cloudfront.PriceClass.PRICE_CLASS_100,
                comment=(
                    f"pantry-pirate-radio SQLite exports CDN ({environment_name})"
                ),
                default_behavior=cloudfront.BehaviorOptions(
                    origin=origins.HttpOrigin(
                        exports_bucket.bucket_regional_domain_name,
                        protocol_policy=(
                            cloudfront.OriginProtocolPolicy.HTTPS_ONLY
                        ),
                    ),
                    viewer_protocol_policy=(
                        cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS
                    ),
                    allowed_methods=cloudfront.AllowedMethods.ALLOW_GET_HEAD,
                    cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                    # SQLite is already a binary format; skip CF compression overhead.
                    compress=False,
                ),
            )

            route53.ARecord(
                self, "ExportsRecord",
                zone=zone,
                record_name="exports",
                target=route53.RecordTarget.from_alias(
                    targets.CloudFrontTarget(exports_distribution)
                ),
            )
            route53.AaaaRecord(
                self, "ExportsRecordAAAA",
                zone=zone,
                record_name="exports",
                target=route53.RecordTarget.from_alias(
                    targets.CloudFrontTarget(exports_distribution)
                ),
            )

            CfnOutput(
                self, "ExportsDistributionDomainName",
                value=exports_distribution.distribution_domain_name,
                description="CloudFront domain for exports.{domain}",
            )

        CfnOutput(
            self, "DomainName",
            value=domain_name,
            description="Base domain for all services",
        )
