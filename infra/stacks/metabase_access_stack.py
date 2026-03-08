"""Metabase Access Stack for Pantry Pirate Radio.

Creates a Network Load Balancer in public subnets to expose the RDS Proxy
to Metabase Cloud. A Lambda function runs every minute to resolve the proxy's
DNS to IPs and sync the NLB target group (RDS Proxy has dynamic private IPs).

Access is restricted to Metabase Cloud's published static IPs via security group.
"""

import textwrap

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_logs as logs
from constructs import Construct

# Metabase Cloud static IPs for us-east-1
# Source: https://www.metabase.com/docs/latest/cloud/ip-addresses-to-whitelist
METABASE_CLOUD_IPS_US_EAST_1 = [
    "18.207.81.126",
    "3.211.20.157",
    "50.17.234.169",
]


class MetabaseAccessStack(Stack):
    """NLB + Lambda stack for Metabase Cloud access to Aurora via RDS Proxy.

    Creates:
    - Security group allowing TCP 5432 from Metabase Cloud IPs
    - Internet-facing Network Load Balancer in public subnets
    - IP-based target group pointing at RDS Proxy IPs
    - TCP listener on port 5432
    - Lambda function to resolve proxy DNS and sync target IPs
    - EventBridge rule triggering Lambda every minute (seeds IPs within 60s)

    Attributes:
        nlb: Network Load Balancer construct
        nlb_dns_name: CfnOutput with NLB DNS name
        nlb_security_group: Security group for proxy SG ingress wiring
        environment_name: Environment name
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.IVpc,
        proxy_endpoint: str,
        environment_name: str = "dev",
        metabase_cloud_ips: list[str] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.environment_name = environment_name

        if metabase_cloud_ips is None:
            metabase_cloud_ips = METABASE_CLOUD_IPS_US_EAST_1

        # Security group: inbound TCP 5432 from each Metabase Cloud IP
        self.nlb_security_group = ec2.SecurityGroup(
            self,
            "NlbSecurityGroup",
            vpc=vpc,
            description=f"NLB for Metabase Cloud access - {environment_name}",
            allow_all_outbound=True,
        )
        for ip in metabase_cloud_ips:
            self.nlb_security_group.add_ingress_rule(
                peer=ec2.Peer.ipv4(f"{ip}/32"),
                connection=ec2.Port.tcp(5432),
                description=f"Metabase Cloud IP {ip}",
            )

        # Network Load Balancer — internet-facing, public subnets
        self.nlb = elbv2.NetworkLoadBalancer(
            self,
            "MetabaseNlb",
            vpc=vpc,
            internet_facing=True,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PUBLIC,
            ),
            security_groups=[self.nlb_security_group],
            load_balancer_name=f"metabase-nlb-{environment_name}",
        )

        # Target group — IP type, TCP 5432
        target_group = elbv2.NetworkTargetGroup(
            self,
            "ProxyTargetGroup",
            vpc=vpc,
            port=5432,
            protocol=elbv2.Protocol.TCP,
            target_type=elbv2.TargetType.IP,
            health_check=elbv2.HealthCheck(
                protocol=elbv2.Protocol.TCP,
                port="5432",
            ),
            target_group_name=f"metabase-proxy-{environment_name}",
        )

        # TCP listener on port 5432
        self.nlb.add_listener(
            "TcpListener",
            port=5432,
            protocol=elbv2.Protocol.TCP,
            default_target_groups=[target_group],
        )

        # Lambda function to resolve proxy DNS and sync target IPs
        ip_sync_code = textwrap.dedent("""\
            import json
            import os
            import socket

            import boto3

            elbv2_client = boto3.client("elbv2")

            def handler(event, context):
                endpoint = os.environ["PROXY_ENDPOINT"]
                tg_arn = os.environ["TARGET_GROUP_ARN"]

                # Resolve current proxy IPs
                current_ips = set()
                for info in socket.getaddrinfo(endpoint, 5432, socket.AF_INET):
                    current_ips.add(info[4][0])

                # Get registered IPs
                resp = elbv2_client.describe_target_health(TargetGroupArn=tg_arn)
                registered_ips = {
                    t["Target"]["Id"]
                    for t in resp["TargetHealthDescriptions"]
                }

                # Register new, deregister stale
                to_add = current_ips - registered_ips
                to_remove = registered_ips - current_ips

                if to_add:
                    elbv2_client.register_targets(
                        TargetGroupArn=tg_arn,
                        Targets=[{"Id": ip, "Port": 5432} for ip in to_add],
                    )
                if to_remove:
                    elbv2_client.deregister_targets(
                        TargetGroupArn=tg_arn,
                        Targets=[{"Id": ip, "Port": 5432} for ip in to_remove],
                    )

                return {
                    "statusCode": 200,
                    "body": json.dumps({
                        "current": sorted(current_ips),
                        "added": sorted(to_add),
                        "removed": sorted(to_remove),
                    }),
                }
        """)

        ip_sync_log_group = logs.LogGroup(
            self,
            "IpSyncLogs",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )

        ip_sync_fn = _lambda.Function(
            self,
            "IpSyncFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="index.handler",
            code=_lambda.Code.from_inline(ip_sync_code),
            timeout=Duration.seconds(30),
            environment={
                "PROXY_ENDPOINT": proxy_endpoint,
                "TARGET_GROUP_ARN": target_group.target_group_arn,
            },
            function_name=f"metabase-ip-sync-{environment_name}",
            log_group=ip_sync_log_group,
        )

        # IAM: allow Lambda to manage target group
        # Register/Deregister support resource-level permissions
        ip_sync_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "elasticloadbalancing:RegisterTargets",
                    "elasticloadbalancing:DeregisterTargets",
                ],
                resources=[target_group.target_group_arn],
            )
        )
        # DescribeTargetHealth requires resource "*" per IAM docs
        ip_sync_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["elasticloadbalancing:DescribeTargetHealth"],
                resources=["*"],
            )
        )

        # EventBridge rule — every 1 minute (seeds targets within 60s of deploy)
        events.Rule(
            self,
            "IpSyncSchedule",
            schedule=events.Schedule.rate(Duration.minutes(1)),
            targets=[targets.LambdaFunction(ip_sync_fn)],
        )

        # Output NLB DNS name for Metabase Cloud configuration
        self.nlb_dns_name = CfnOutput(
            self,
            "NlbDnsName",
            value=self.nlb.load_balancer_dns_name,
            description="NLB DNS name for Metabase Cloud DB host",
        )
