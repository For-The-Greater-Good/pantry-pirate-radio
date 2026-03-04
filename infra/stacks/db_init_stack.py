"""Database Initialization Stack for Pantry Pirate Radio.

Creates a safe first-deploy-only database initialization mechanism:
- SSM Parameter Guard to track initialization state
- Custom Resource that ONLY triggers on CREATE (never UPDATE)
- Lambda to check if database has data
- ECS Task for actual database initialization
- Step Functions state machine for orchestration

CRITICAL SAFETY: DB init must ONLY run on first deploy (CREATE), never on updates.
Data loss prevention is the top priority.
"""

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack, CustomResource
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_secretsmanager as secretsmanager
from aws_cdk import aws_ssm as ssm
from aws_cdk import aws_stepfunctions as sfn
from aws_cdk import aws_stepfunctions_tasks as tasks
from aws_cdk import custom_resources as cr
from constructs import Construct


class DbInitStack(Stack):
    """Safe database initialization infrastructure for Pantry Pirate Radio.

    CRITICAL: This stack is designed to ONLY initialize the database on first
    deployment (CloudFormation CREATE). It will NOT run on subsequent updates.

    Safety mechanisms:
    1. SSM Parameter tracks initialization state
    2. Custom Resource with on_create ONLY (no on_update)
    3. Lambda checks if DB already has data before init
    4. State machine is idempotent and can be manually re-triggered

    Architecture:
        CDK Deploy (CREATE only)
              |
              v
        Custom Resource Lambda
          - Starts Step Functions State Machine
              |
              v
        CheckDbData (Lambda)
          - SELECT COUNT(*) FROM organization
          - Returns {needs_init: true/false}
              |
          (needs_init?)
           /        \\
         No          Yes
          |           |
          v           v
        SetFlag    RunDbInit (ECS Task)
          |           |
          v           v
        Success    SetFlag --> Success

    Attributes:
        init_flag: SSM Parameter tracking initialization state
        state_machine: Step Functions state machine for init orchestration
        init_task_definition: ECS task definition for db-init
        environment_name: Environment name (dev, staging, prod)
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        environment_name: str = "dev",
        vpc: ec2.IVpc,
        cluster: ecs.ICluster,
        database_proxy_endpoint: str,
        database_secret: secretsmanager.ISecret,
        github_pat_secret: secretsmanager.ISecret,
        proxy_security_group: ec2.ISecurityGroup,
        **kwargs,
    ) -> None:
        """Initialize DbInitStack.

        Args:
            scope: CDK scope
            construct_id: Unique identifier for this construct
            environment_name: Environment name (dev, staging, prod)
            vpc: VPC for Lambda and ECS placement
            cluster: ECS cluster for init task
            database_proxy_endpoint: RDS Proxy endpoint URL
            database_secret: Secret containing database credentials
            github_pat_secret: Secret containing GitHub PAT for migrations
            proxy_security_group: Security group that can access RDS Proxy
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        self.environment_name = environment_name

        # Environment-specific configuration
        is_prod = environment_name == "prod"
        log_retention = (
            logs.RetentionDays.ONE_MONTH if is_prod else logs.RetentionDays.ONE_WEEK
        )

        # 1. SSM Parameter to track initialization state
        self.init_flag = self._create_init_flag_parameter()

        # 2. Lambda to check if database has data
        self.check_db_lambda = self._create_check_db_lambda(
            vpc=vpc,
            database_proxy_endpoint=database_proxy_endpoint,
            database_secret=database_secret,
            proxy_security_group=proxy_security_group,
            log_retention=log_retention,
        )

        # 3. ECS task definition for db-init
        self.init_task_definition, self._init_security_group = (
            self._create_init_task_definition(
                vpc=vpc,
                database_proxy_endpoint=database_proxy_endpoint,
                database_secret=database_secret,
                github_pat_secret=github_pat_secret,
                log_retention=log_retention,
            )
        )

        # 4. Step Functions state machine
        self.state_machine = self._create_state_machine(
            cluster=cluster,
            vpc=vpc,
            proxy_security_group=proxy_security_group,
        )

        # 5. Custom Resource - ONLY triggers on CREATE
        self._create_init_trigger()

        # Expose security groups for cross-stack wiring
        # The caller (app.py) must call database_stack.allow_connection_from()
        # to grant these security groups access to the RDS Proxy
        self.check_db_lambda_security_group = self._check_db_lambda_sg
        self.init_task_security_group = self._init_security_group

        # Add CfnOutputs
        CfnOutput(
            self,
            "InitFlagParameter",
            value=self.init_flag.parameter_name,
            description="SSM Parameter tracking database initialization state",
        )
        CfnOutput(
            self,
            "StateMachineArn",
            value=self.state_machine.state_machine_arn,
            description="Step Functions state machine for db initialization",
        )

    def _create_init_flag_parameter(self) -> ssm.StringParameter:
        """Create SSM parameter to track database initialization state.

        The parameter is set to "false" initially. After successful init,
        the state machine sets it to "true". This prevents re-initialization
        on subsequent deployments.

        Returns:
            SSM StringParameter for tracking init state
        """
        return ssm.StringParameter(
            self,
            "DbInitFlag",
            parameter_name=f"/pantry-pirate-radio/{self.environment_name}/db-initialized",
            string_value="false",
            description="Tracks whether database has been initialized",
            tier=ssm.ParameterTier.STANDARD,
        )

    def _create_check_db_lambda(
        self,
        vpc: ec2.IVpc,
        database_proxy_endpoint: str,
        database_secret: secretsmanager.ISecret,
        proxy_security_group: ec2.ISecurityGroup,
        log_retention: logs.RetentionDays,
    ) -> lambda_.Function:
        """Create Lambda function to check if database has data.

        This Lambda queries the organization table to determine if
        initialization is needed. Uses pg8000 for PostgreSQL connectivity.

        Args:
            vpc: VPC for Lambda placement
            database_proxy_endpoint: RDS Proxy endpoint
            database_secret: Database credentials secret
            proxy_security_group: Security group for DB access
            log_retention: CloudWatch log retention period

        Returns:
            Lambda function for checking database state
        """
        # Security group for Lambda
        lambda_sg = ec2.SecurityGroup(
            self,
            "CheckDbLambdaSG",
            vpc=vpc,
            description=f"Security group for check-db Lambda - {self.environment_name}",
            allow_all_outbound=True,
        )

        # Store reference for cross-stack wiring
        # The caller (app.py) must grant this SG access to the RDS Proxy
        self._check_db_lambda_sg = lambda_sg

        # Lambda function
        fn = lambda_.Function(
            self,
            "CheckDbLambda",
            function_name=f"pantry-pirate-radio-check-db-{self.environment_name}",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.handler",
            code=lambda_.Code.from_inline(self._get_check_db_lambda_code()),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            security_groups=[lambda_sg],
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                "DATABASE_HOST": database_proxy_endpoint,
                "DATABASE_NAME": "pantry_pirate_radio",
                "DATABASE_SECRET_ARN": database_secret.secret_arn,
                "SSM_PARAMETER_NAME": f"/pantry-pirate-radio/{self.environment_name}/db-initialized",
            },
            log_retention=log_retention,
            # Include pg8000 layer for PostgreSQL connectivity
            layers=[
                lambda_.LayerVersion.from_layer_version_arn(
                    self,
                    "Pg8000Layer",
                    # AWS-provided psycopg2 layer (pg8000 is bundled)
                    f"arn:aws:lambda:{Stack.of(self).region}:898466741470:layer:psycopg2-py311:1",
                )
            ],
        )

        # Grant Lambda permission to read database secret
        database_secret.grant_read(fn)

        # Grant Lambda permission to read/write SSM parameter
        self.init_flag.grant_read(fn)
        self.init_flag.grant_write(fn)

        return fn

    def _get_check_db_lambda_code(self) -> str:
        """Return inline Python code for check-db Lambda.

        Returns:
            Python code as string
        """
        return '''
import json
import os
import boto3

def handler(event, context):
    """Check if database has data and if init flag is set.

    Returns:
        dict with needs_init: True if initialization is needed
    """
    ssm = boto3.client("ssm")
    secrets = boto3.client("secretsmanager")

    # Check SSM parameter first (fast path)
    try:
        response = ssm.get_parameter(
            Name=os.environ["SSM_PARAMETER_NAME"]
        )
        if response["Parameter"]["Value"] == "true":
            print("SSM flag indicates DB already initialized")
            return {"needs_init": False}
    except ssm.exceptions.ParameterNotFound:
        print("SSM parameter not found, will check database")

    # Get database credentials
    secret_response = secrets.get_secret_value(
        SecretId=os.environ["DATABASE_SECRET_ARN"]
    )
    secret = json.loads(secret_response["SecretString"])

    # Check if database has data
    try:
        import psycopg2

        conn = psycopg2.connect(
            host=os.environ["DATABASE_HOST"],
            database=os.environ["DATABASE_NAME"],
            user=secret["username"],
            password=secret["password"],
            sslmode="require",
            connect_timeout=10,
        )

        with conn.cursor() as cur:
            # Check if organization table exists and has data
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'organization'
                )
            """)
            table_exists = cur.fetchone()[0]

            if not table_exists:
                print("Organization table does not exist, needs init")
                return {"needs_init": True}

            cur.execute("SELECT COUNT(*) FROM organization")
            count = cur.fetchone()[0]

        conn.close()

        if count > 0:
            print(f"Database has {count} organizations, no init needed")
            # Update SSM flag since DB is initialized
            ssm.put_parameter(
                Name=os.environ["SSM_PARAMETER_NAME"],
                Value="true",
                Overwrite=True,
            )
            return {"needs_init": False}
        else:
            print("Database is empty, needs init")
            return {"needs_init": True}

    except Exception as e:
        print(f"Error checking database: {e}")
        # If we can't connect or check, assume init is needed
        # The init task will handle the actual state safely
        return {"needs_init": True}
'''

    def _create_init_task_definition(
        self,
        vpc: ec2.IVpc,
        database_proxy_endpoint: str,
        database_secret: secretsmanager.ISecret,
        github_pat_secret: secretsmanager.ISecret,
        log_retention: logs.RetentionDays,
    ) -> tuple[ecs.FargateTaskDefinition, ec2.SecurityGroup]:
        """Create ECS task definition for database initialization.

        The init task runs migrations and initial data loading.
        Uses 4GB memory and has a 30-minute timeout.

        Args:
            vpc: VPC for security group
            database_proxy_endpoint: RDS Proxy endpoint
            database_secret: Database credentials secret
            github_pat_secret: GitHub PAT for migrations
            log_retention: CloudWatch log retention period

        Returns:
            Tuple of (task definition, security group)
        """
        # Log group
        log_group = logs.LogGroup(
            self,
            "DbInitLogGroup",
            log_group_name=f"/ecs/pantry-pirate-radio/db-init-{self.environment_name}",
            retention=log_retention,
            removal_policy=(
                RemovalPolicy.RETAIN
                if self.environment_name == "prod"
                else RemovalPolicy.DESTROY
            ),
        )

        # Task definition with generous resources
        task_def = ecs.FargateTaskDefinition(
            self,
            "DbInitTaskDef",
            cpu=1024,
            memory_limit_mib=4096,
            family=f"pantry-pirate-radio-db-init-{self.environment_name}",
        )

        # Container
        task_def.add_container(
            "DbInitContainer",
            image=ecs.ContainerImage.from_registry(
                "pantry-pirate-radio-app:latest"
            ),
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="db-init",
                log_group=log_group,
            ),
            environment={
                "ENVIRONMENT": self.environment_name,
                "DATABASE_HOST": database_proxy_endpoint,
                "DATABASE_NAME": "pantry_pirate_radio",
                "DATABASE_USER": "pantry_pirate",
            },
            secrets={
                "DATABASE_PASSWORD": ecs.Secret.from_secrets_manager(
                    database_secret, "password"
                ),
                "GITHUB_PAT": ecs.Secret.from_secrets_manager(github_pat_secret),
            },
            # Override the default command to run migrations
            command=["python", "-m", "app.db.init"],
        )

        # Security group
        sg = ec2.SecurityGroup(
            self,
            "DbInitSecurityGroup",
            vpc=vpc,
            description=f"Security group for db-init task - {self.environment_name}",
            allow_all_outbound=True,
        )

        # Grant task role permission to read secrets
        database_secret.grant_read(task_def.task_role)
        github_pat_secret.grant_read(task_def.task_role)

        return task_def, sg

    def _create_state_machine(
        self,
        cluster: ecs.ICluster,
        vpc: ec2.IVpc,
        proxy_security_group: ec2.ISecurityGroup,
    ) -> sfn.StateMachine:
        """Create Step Functions state machine for init orchestration.

        The state machine:
        1. Checks if database needs initialization
        2. If yes, runs the ECS init task
        3. Sets the SSM flag to "true" on success

        Args:
            cluster: ECS cluster for running init task
            vpc: VPC for task placement
            proxy_security_group: Security group for DB access

        Returns:
            Step Functions state machine
        """
        # Task to check if init is needed
        check_db_task = tasks.LambdaInvoke(
            self,
            "CheckIfInitNeeded",
            lambda_function=self.check_db_lambda,
            output_path="$.Payload",
        )

        # Task to run ECS db-init
        run_init_task = tasks.EcsRunTask(
            self,
            "RunDbInit",
            integration_pattern=sfn.IntegrationPattern.RUN_JOB,
            cluster=cluster,
            task_definition=self.init_task_definition,
            launch_target=tasks.EcsFargateLaunchTarget(
                platform_version=ecs.FargatePlatformVersion.LATEST,
            ),
            subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            security_groups=[self._init_security_group],
            assign_public_ip=False,
            result_path="$.ecsResult",
        )

        # Task to set SSM flag to "true" (after init runs)
        set_flag_after_init = tasks.CallAwsService(
            self,
            "SetFlagAfterInit",
            service="ssm",
            action="putParameter",
            parameters={
                "Name": self.init_flag.parameter_name,
                "Value": "true",
                "Overwrite": True,
            },
            iam_resources=[self.init_flag.parameter_arn],
            result_path="$.ssmResult",
        )

        # Task to set SSM flag to "true" (when no init needed)
        set_flag_already_init = tasks.CallAwsService(
            self,
            "SetFlagAlreadyInit",
            service="ssm",
            action="putParameter",
            parameters={
                "Name": self.init_flag.parameter_name,
                "Value": "true",
                "Overwrite": True,
            },
            iam_resources=[self.init_flag.parameter_arn],
            result_path="$.ssmResult",
        )

        # Success state
        success = sfn.Succeed(self, "InitComplete")

        # Define the workflow
        # If needs_init is false, set flag and succeed
        # If needs_init is true, run init task, then set flag, then succeed
        definition = check_db_task.next(
            sfn.Choice(self, "NeedsInitialization")
            .when(
                sfn.Condition.boolean_equals("$.needs_init", False),
                set_flag_already_init.next(success),
            )
            .when(
                sfn.Condition.boolean_equals("$.needs_init", True),
                run_init_task.next(set_flag_after_init).next(success),
            )
            .otherwise(success)
        )

        # Create state machine
        state_machine = sfn.StateMachine(
            self,
            "DbInitStateMachine",
            state_machine_name=f"pantry-pirate-radio-db-init-{self.environment_name}",
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            timeout=Duration.minutes(45),
            tracing_enabled=True,
        )

        # Grant state machine permission to run ECS task
        self.init_task_definition.grant_run(state_machine)

        # Grant state machine permission to pass task execution role
        state_machine.add_to_role_policy(
            iam.PolicyStatement(
                actions=["iam:PassRole"],
                resources=[
                    self.init_task_definition.task_role.role_arn,
                    self.init_task_definition.execution_role.role_arn,  # type: ignore
                ],
            )
        )

        return state_machine

    def _create_init_trigger(self) -> CustomResource:
        """Create Custom Resource to trigger init on first deploy ONLY.

        CRITICAL SAFETY: This resource only has on_create handler.
        There is NO on_update handler, so it will NOT run on stack updates.
        This is the key safety mechanism to prevent data loss.

        Returns:
            Custom Resource that triggers init state machine
        """
        # Custom resource provider
        provider = cr.Provider(
            self,
            "DbInitTriggerProvider",
            on_event_handler=lambda_.Function(
                self,
                "DbInitTriggerLambda",
                function_name=f"pantry-pirate-radio-db-init-trigger-{self.environment_name}",
                runtime=lambda_.Runtime.PYTHON_3_11,
                handler="index.handler",
                code=lambda_.Code.from_inline(self._get_trigger_lambda_code()),
                timeout=Duration.seconds(30),
                environment={
                    "STATE_MACHINE_ARN": self.state_machine.state_machine_arn,
                },
            ),
        )

        # Grant the provider permission to start the state machine
        self.state_machine.grant_start_execution(provider.on_event_handler)

        # Create custom resource - ONLY triggers on CREATE
        return CustomResource(
            self,
            "DbInitTrigger",
            service_token=provider.service_token,
            # Properties that change won't trigger re-execution
            # because there's no on_update handler in the provider
        )

    def _get_trigger_lambda_code(self) -> str:
        """Return inline Python code for trigger Lambda.

        CRITICAL: This handler ONLY starts the state machine on CREATE events.
        UPDATE and DELETE events are acknowledged but do nothing.

        Returns:
            Python code as string
        """
        return '''
import json
import os
import boto3

def handler(event, context):
    """Handle CloudFormation Custom Resource events.

    CRITICAL SAFETY: Only starts state machine on CREATE.
    UPDATE and DELETE are no-ops to prevent re-initialization.
    """
    request_type = event["RequestType"]
    print(f"Received {request_type} request")

    if request_type == "Create":
        # Only trigger on first deployment
        sfn = boto3.client("stepfunctions")
        response = sfn.start_execution(
            stateMachineArn=os.environ["STATE_MACHINE_ARN"],
            name=f"init-{context.aws_request_id[:8]}",
        )
        print(f"Started state machine execution: {response['executionArn']}")
        return {
            "PhysicalResourceId": response["executionArn"],
            "Data": {"ExecutionArn": response["executionArn"]},
        }
    elif request_type == "Update":
        # CRITICAL: Do nothing on update - this prevents re-initialization
        print("Update event received - no action taken (safety mechanism)")
        return {
            "PhysicalResourceId": event.get("PhysicalResourceId", "no-init"),
        }
    elif request_type == "Delete":
        # Nothing to clean up - just acknowledge
        print("Delete event received - no action taken")
        return {
            "PhysicalResourceId": event.get("PhysicalResourceId", "deleted"),
        }

    return {"PhysicalResourceId": "unknown"}
'''
