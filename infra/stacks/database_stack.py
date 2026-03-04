"""Database Stack for Pantry Pirate Radio.

Creates Aurora Serverless v2 PostgreSQL with RDS Proxy for the reconciler
and other services that need PostgreSQL access.
"""

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_rds as rds
from aws_cdk import aws_secretsmanager as secretsmanager
from constructs import Construct


class DatabaseStack(Stack):
    """Database infrastructure for Pantry Pirate Radio.

    Creates:
    - Database credentials secret (auto-generated)
    - Aurora Serverless v2 PostgreSQL 15 cluster
    - RDS Proxy with IAM authentication for connection pooling
    - Security groups for database access
    - DynamoDB table for geocoding cache

    Attributes:
        database_credentials_secret: Secret containing DB username/password
        aurora_cluster: Aurora Serverless v2 cluster
        rds_proxy: RDS Proxy for connection pooling
        proxy_endpoint: RDS Proxy endpoint URL
        database_security_group: Security group for database access
        geocoding_cache_table: DynamoDB table for geocoding cache
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
        """Initialize DatabaseStack.

        Args:
            scope: CDK scope
            construct_id: Unique identifier for this construct
            environment_name: Environment name (dev, staging, prod)
            vpc: VPC for database placement
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        self.environment_name = environment_name

        # Environment-specific configuration
        is_prod = environment_name == "prod"
        removal_policy = RemovalPolicy.RETAIN if is_prod else RemovalPolicy.DESTROY

        # Create database credentials secret (owned by this stack)
        self.database_credentials_secret = self._create_database_credentials_secret(
            removal_policy
        )

        # Create security groups
        self.database_security_group = self._create_database_security_group(vpc)
        self._proxy_security_group = self._create_proxy_security_group(vpc)

        # Create DB subnet group
        db_subnet_group = self._create_db_subnet_group(vpc)

        # Create Aurora cluster
        self.aurora_cluster = self._create_aurora_cluster(
            vpc=vpc,
            security_group=self.database_security_group,
            subnet_group=db_subnet_group,
            is_prod=is_prod,
        )

        # Create RDS Proxy
        self.rds_proxy = self._create_rds_proxy(
            vpc=vpc,
            security_group=self._proxy_security_group,
        )

        # Proxy endpoint for services to use
        self.proxy_endpoint = self.rds_proxy.endpoint

        # Create geocoding cache table
        self.geocoding_cache_table = self._create_geocoding_cache_table()

        # Allow proxy to connect to database
        self.database_security_group.add_ingress_rule(
            peer=self._proxy_security_group,
            connection=ec2.Port.tcp(5432),
            description="Allow RDS Proxy to connect to Aurora",
        )

        # Expose proxy security group for cross-stack wiring
        self.proxy_security_group = self._proxy_security_group

        # Add CfnOutputs for cross-stack references
        CfnOutput(
            self,
            "ProxyEndpoint",
            value=self.rds_proxy.endpoint,
            description="RDS Proxy endpoint for database connections",
        )
        CfnOutput(
            self,
            "DatabaseSecretArn",
            value=self.database_credentials_secret.secret_arn,
            description="ARN of the database credentials secret",
        )
        CfnOutput(
            self,
            "DatabaseName",
            value=self.database_name,
            description="Name of the database",
        )

    def _create_database_credentials_secret(
        self, removal_policy: RemovalPolicy
    ) -> secretsmanager.Secret:
        """Create secret for Aurora PostgreSQL database credentials.

        Password is auto-generated with secure defaults.
        Can be rotated using Secrets Manager rotation.

        Returns:
            Secrets Manager secret with DB credentials
        """
        secret = secretsmanager.Secret(
            self,
            "DatabaseCredentialsSecret",
            secret_name=f"pantry-pirate-radio/database-credentials-{self.environment_name}",
            description=f"Aurora PostgreSQL database credentials for {self.environment_name}",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"username": "pantry_pirate"}',
                generate_string_key="password",
                exclude_characters='"@/\\',
                password_length=32,
            ),
            removal_policy=removal_policy,
        )

        return secret

    def _create_database_security_group(self, vpc: ec2.IVpc) -> ec2.SecurityGroup:
        """Create security group for Aurora database.

        Returns:
            Security group for Aurora cluster
        """
        sg = ec2.SecurityGroup(
            self,
            "DatabaseSecurityGroup",
            vpc=vpc,
            description=f"Security group for Aurora PostgreSQL - {self.environment_name}",
            allow_all_outbound=False,
        )

        return sg

    def _create_proxy_security_group(self, vpc: ec2.IVpc) -> ec2.SecurityGroup:
        """Create security group for RDS Proxy.

        Returns:
            Security group for RDS Proxy
        """
        sg = ec2.SecurityGroup(
            self,
            "ProxySecurityGroup",
            vpc=vpc,
            description=f"Security group for RDS Proxy - {self.environment_name}",
            allow_all_outbound=True,
        )

        return sg

    def _create_db_subnet_group(self, vpc: ec2.IVpc) -> rds.SubnetGroup:
        """Create DB subnet group for Aurora.

        Returns:
            DB subnet group using private subnets
        """
        return rds.SubnetGroup(
            self,
            "DatabaseSubnetGroup",
            description=f"Subnet group for Aurora PostgreSQL - {self.environment_name}",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
        )

    def _create_aurora_cluster(
        self,
        vpc: ec2.IVpc,
        security_group: ec2.ISecurityGroup,
        subnet_group: rds.SubnetGroup,
        is_prod: bool,
    ) -> rds.DatabaseCluster:
        """Create Aurora Serverless v2 PostgreSQL cluster.

        Args:
            vpc: VPC for cluster placement
            security_group: Security group for cluster
            subnet_group: DB subnet group
            is_prod: Whether this is production environment

        Returns:
            Aurora Serverless v2 cluster
        """
        # Environment-specific settings
        min_capacity = 2 if is_prod else 0.5
        max_capacity = 16 if is_prod else 2
        backup_retention = Duration.days(30) if is_prod else Duration.days(1)
        deletion_protection = is_prod
        removal_policy = RemovalPolicy.RETAIN if is_prod else RemovalPolicy.DESTROY

        cluster = rds.DatabaseCluster(
            self,
            "AuroraCluster",
            cluster_identifier=f"pantry-pirate-radio-{self.environment_name}",
            engine=rds.DatabaseClusterEngine.aurora_postgres(
                version=rds.AuroraPostgresEngineVersion.VER_15_4
            ),
            credentials=rds.Credentials.from_secret(self.database_credentials_secret),
            writer=rds.ClusterInstance.serverless_v2(
                "WriterInstance",
                auto_minor_version_upgrade=True,
            ),
            serverless_v2_min_capacity=min_capacity,
            serverless_v2_max_capacity=max_capacity,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            subnet_group=subnet_group,
            security_groups=[security_group],
            default_database_name="pantry_pirate_radio",
            backup=rds.BackupProps(retention=backup_retention),
            deletion_protection=deletion_protection,
            removal_policy=removal_policy,
            storage_encrypted=True,
        )

        return cluster

    def _create_rds_proxy(
        self,
        vpc: ec2.IVpc,
        security_group: ec2.ISecurityGroup,
    ) -> rds.DatabaseProxy:
        """Create RDS Proxy for connection pooling.

        RDS Proxy provides:
        - Connection pooling for efficient database connections
        - Automatic failover for high availability
        - IAM authentication support

        Args:
            vpc: VPC for proxy placement
            security_group: Security group for proxy

        Returns:
            RDS Proxy
        """
        proxy = rds.DatabaseProxy(
            self,
            "RDSProxy",
            db_proxy_name=f"pantry-pirate-radio-proxy-{self.environment_name}",
            proxy_target=rds.ProxyTarget.from_cluster(self.aurora_cluster),
            secrets=[self.database_credentials_secret],
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            security_groups=[security_group],
            require_tls=True,
            idle_client_timeout=Duration.minutes(30),
            max_connections_percent=100,
            max_idle_connections_percent=50,
        )

        return proxy

    def _create_geocoding_cache_table(self) -> dynamodb.Table:
        """Create DynamoDB table for geocoding cache.

        Schema:
        - address (PK): Normalized address string
        - latitude: Latitude coordinate
        - longitude: Longitude coordinate
        - provider: Geocoding provider used
        - cached_at: When the result was cached
        - ttl: Expiration timestamp for cache entry

        Returns:
            DynamoDB table for geocoding cache
        """
        removal_policy = (
            RemovalPolicy.RETAIN
            if self.environment_name == "prod"
            else RemovalPolicy.DESTROY
        )

        table = dynamodb.Table(
            self,
            "GeocodingCacheTable",
            table_name=f"pantry-pirate-radio-geocoding-cache-{self.environment_name}",
            partition_key=dynamodb.Attribute(
                name="address",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=removal_policy,
            time_to_live_attribute="ttl",
        )

        return table

    def allow_connection_from(self, security_group: ec2.ISecurityGroup) -> None:
        """Allow a security group to connect to the RDS Proxy.

        This is a helper method for other stacks to grant database access
        to their Fargate services.

        Args:
            security_group: Security group to grant access
        """
        self._proxy_security_group.add_ingress_rule(
            peer=security_group,
            connection=ec2.Port.tcp(5432),
            description="Allow connection to RDS Proxy",
        )

    @property
    def database_name(self) -> str:
        """Return the database name for connection strings."""
        return "pantry_pirate_radio"
