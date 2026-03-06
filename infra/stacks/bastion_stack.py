"""Bastion Stack for Pantry Pirate Radio.

Creates a minimal EC2 instance for SSM Session Manager port forwarding
to Aurora (via RDS Proxy). Used for Metabase and ad-hoc database access.
No SSH keys required — access is via AWS SSM only.
"""

from aws_cdk import RemovalPolicy, Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam
from constructs import Construct


class BastionStack(Stack):
    """Bastion host for SSM port forwarding to Aurora.

    Creates:
    - t4g.nano EC2 instance (~$3/month) in a private subnet
    - IAM instance profile with SSM Managed Instance Core policy
    - Security group with no inbound rules (SSM uses outbound HTTPS)

    Usage:
        aws ssm start-session --target <instance-id> \\
          --document-name AWS-StartPortForwardingSessionToRemoteHost \\
          --parameters '{"host":["<proxy-endpoint>"],"portNumber":["5432"],"localPortNumber":["5432"]}'

    Attributes:
        instance: EC2 instance
        bastion_security_group: Security group for the bastion
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        environment_name: str = "dev",
        vpc: ec2.IVpc,
        **kwargs,
    ) -> None:
        """Initialize BastionStack.

        Args:
            scope: CDK scope
            construct_id: Unique identifier for this construct
            environment_name: Environment name (dev, staging, prod)
            vpc: VPC to place the bastion in
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        self.environment_name = environment_name

        # Security group with no inbound rules
        self.bastion_security_group = ec2.SecurityGroup(
            self,
            "BastionSecurityGroup",
            vpc=vpc,
            description=f"Bastion for SSM port forwarding - {environment_name}",
            allow_all_outbound=True,
        )

        # IAM role with SSM access
        role = iam.Role(
            self,
            "BastionRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMManagedInstanceCore"
                ),
            ],
        )

        # t4g.nano instance — Amazon Linux 2023, SSM pre-installed
        self.instance = ec2.Instance(
            self,
            "BastionInstance",
            instance_type=ec2.InstanceType("t4g.nano"),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(
                cpu_type=ec2.AmazonLinuxCpuType.ARM_64,
            ),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
            ),
            security_group=self.bastion_security_group,
            role=role,
        )
