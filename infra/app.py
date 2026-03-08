#!/usr/bin/env python3
"""CDK App entry point for Pantry Pirate Radio infrastructure.

Usage:
    cd infra
    cdk synth                    # Synthesize CloudFormation templates
    cdk deploy --all             # Deploy all stacks
    cdk deploy StorageStack-dev  # Deploy specific stack

Environment Configuration:
    Set CDK_DEPLOY_ENVIRONMENT to control target environment:
    - dev (default): Development environment
    - staging: Staging/test environment
    - prod: Production environment

    Set CDK_DEPLOY_ACCOUNT and CDK_DEPLOY_REGION for target AWS account/region.
"""

import os

import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2

from stacks.bastion_stack import BastionStack
from stacks.batch_stack import BatchInferenceStack
from stacks.compute_stack import ComputeStack
from stacks.database_stack import DatabaseStack
from stacks.db_init_stack import DbInitStack
from stacks.ecr_stack import ECRStack
from stacks.lambda_api_stack import LambdaApiStack
from stacks.metabase_access_stack import MetabaseAccessStack
from stacks.monitoring_stack import MonitoringStack
from stacks.pipeline_stack import PipelineStack
from stacks.queue_stack import QueueStack
from stacks.secrets_stack import SecretsStack
from stacks.services_stack import ServiceConfig, ServicesStack
from stacks.storage_stack import StorageStack

# Get deployment configuration from environment
environment_name = os.environ.get("CDK_DEPLOY_ENVIRONMENT", "dev")
account = os.environ.get("CDK_DEPLOY_ACCOUNT", os.environ.get("CDK_DEFAULT_ACCOUNT"))
region = os.environ.get("CDK_DEPLOY_REGION", os.environ.get("CDK_DEFAULT_REGION"))
certificate_arn = os.environ.get("CDK_CERTIFICATE_ARN")
domain_name = os.environ.get("CDK_DOMAIN_NAME")
alert_email = os.environ.get("CDK_ALERT_EMAIL")
bedrock_model_id = os.environ.get(
    "CDK_BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0"
)

app = cdk.App()

# Create environment
env = cdk.Environment(account=account, region=region)

# Secrets Stack - GitHub PAT and LLM API keys
secrets_stack = SecretsStack(
    app,
    f"SecretsStack-{environment_name}",
    environment_name=environment_name,
    env=env,
    description=f"Pantry Pirate Radio secrets management ({environment_name})",
)

# ECR Stack - Container image repositories
ecr_stack = ECRStack(
    app,
    f"ECRStack-{environment_name}",
    environment_name=environment_name,
    env=env,
    description=f"Pantry Pirate Radio container repositories ({environment_name})",
)

# Storage Stack - S3 bucket and DynamoDB tables
storage_stack = StorageStack(
    app,
    f"StorageStack-{environment_name}",
    environment_name=environment_name,
    env=env,
    description=f"Pantry Pirate Radio storage infrastructure ({environment_name})",
)

# Queue Stack - SQS queues for pipeline stages
queue_stack = QueueStack(
    app,
    f"QueueStack-{environment_name}",
    environment_name=environment_name,
    env=env,
    description=f"Pantry Pirate Radio queue infrastructure ({environment_name})",
)

# Compute Stack - VPC + ECS cluster for all Fargate services
compute_stack = ComputeStack(
    app,
    f"ComputeStack-{environment_name}",
    environment_name=environment_name,
    max_capacity=5,
    ecr_repository=ecr_stack.repositories.get("worker"),
    llm_queue_url=queue_stack.llm_queue.queue_url,
    sqs_jobs_table_name=storage_stack.jobs_table.table_name,
    validator_queue_url=queue_stack.validator_queue.queue_url,
    env=env,
    description=f"Pantry Pirate Radio compute infrastructure ({environment_name})",
)

# Database Stack - Aurora Serverless v2 + RDS Proxy
database_stack = DatabaseStack(
    app,
    f"DatabaseStack-{environment_name}",
    vpc=compute_stack.vpc,
    environment_name=environment_name,
    env=env,
    description=f"Pantry Pirate Radio database infrastructure ({environment_name})",
)

# Batch Inference Stack - Bedrock batch processing (staging queue, Lambdas, EventBridge)
batch_stack = BatchInferenceStack(
    app,
    f"BatchStack-{environment_name}",
    environment_name=environment_name,
    content_bucket=storage_stack.content_bucket,
    jobs_table=storage_stack.jobs_table,
    llm_queue=queue_stack.llm_queue,
    validator_queue=queue_stack.validator_queue,
    reconciler_queue=queue_stack.reconciler_queue,
    recorder_queue=queue_stack.recorder_queue,
    vpc=compute_stack.vpc,
    bedrock_model_id=bedrock_model_id,
    ecr_repository=ecr_stack.repositories.get("batch-lambda"),
    env=env,
    description=f"Pantry Pirate Radio batch inference infrastructure ({environment_name})",
)

# Create service configuration for environment variables and secrets
service_config = ServiceConfig(
    database_host=database_stack.proxy_endpoint,
    database_name=database_stack.database_name,
    database_user="pantry_pirate",
    database_secret=database_stack.database_credentials_secret,
    queue_urls=queue_stack.queue_urls,
    content_bucket_name=storage_stack.content_bucket.bucket_name,
    content_index_table_name=storage_stack.content_index_table.table_name,
    geocoding_cache_table_name=database_stack.geocoding_cache_table.table_name,
    jobs_table_name=storage_stack.jobs_table.table_name,
    github_pat_secret=secrets_stack.github_pat_secret,
    llm_api_keys_secret=secrets_stack.llm_api_keys_secret,
    data_repo_url="https://github.com/For-The-Greater-Good/HAARRRvest.git",
    exports_bucket_name=storage_stack.exports_bucket.bucket_name,
)

# Services Stack - Fargate services for pipeline stages + Scraper task
services_stack = ServicesStack(
    app,
    f"ServicesStack-{environment_name}",
    vpc=compute_stack.vpc,
    cluster=compute_stack.cluster,
    environment_name=environment_name,
    config=service_config,
    ecr_repositories=ecr_stack.repositories,
    env=env,
    description=f"Pantry Pirate Radio pipeline services ({environment_name})",
)

# Database Initialization Stack - Safe first-deploy only initialization
# CRITICAL: This stack only triggers initialization on CREATE, never on UPDATE
db_init_stack = DbInitStack(
    app,
    f"DbInitStack-{environment_name}",
    vpc=compute_stack.vpc,
    cluster=compute_stack.cluster,
    database_proxy_endpoint=database_stack.proxy_endpoint,
    database_secret=database_stack.database_credentials_secret,
    github_pat_secret=secrets_stack.github_pat_secret,
    proxy_security_group=database_stack.proxy_security_group,
    ecr_repository=ecr_stack.repositories.get("worker"),
    environment_name=environment_name,
    env=env,
    description=f"Pantry Pirate Radio database initialization ({environment_name})",
)

# Pipeline Stack - Step Functions for scraper orchestration + publisher schedule
pipeline_stack = PipelineStack(
    app,
    f"PipelineStack-{environment_name}",
    cluster=compute_stack.cluster,
    scraper_task_family=f"pantry-pirate-radio-scraper-{environment_name}",
    publisher_task_family=f"pantry-pirate-radio-publisher-{environment_name}",
    environment_name=environment_name,
    schedule_enabled=(environment_name == "prod"),  # Only enable schedule in prod
    publisher_schedule_enabled=(environment_name == "prod"),
    staging_queue_url=batch_stack.staging_queue.queue_url,
    batcher_lambda_arn=batch_stack.batcher_lambda.function_arn,
    env=env,
    description=f"Pantry Pirate Radio scraper pipeline ({environment_name})",
)

# Lambda API Stack — serverless read-only HSDS API
lambda_api_stack = LambdaApiStack(
    app,
    f"LambdaApiStack-{environment_name}",
    vpc=compute_stack.vpc,
    environment_name=environment_name,
    database_proxy_endpoint=database_stack.proxy_endpoint,
    database_name=database_stack.database_name,
    database_user="pantry_pirate",
    database_secret=database_stack.database_credentials_secret,
    proxy_security_group=database_stack.proxy_security_group,
    ecr_repository=ecr_stack.repositories.get("api-lambda"),
    memory_size=1024,
    timeout_seconds=30,
    provisioned_concurrent=2 if environment_name == "prod" else None,
    env=env,
    description=f"Pantry Pirate Radio serverless API ({environment_name})",
)
lambda_api_stack.add_dependency(compute_stack)
lambda_api_stack.add_dependency(database_stack)
lambda_api_stack.add_dependency(ecr_stack)
lambda_api_stack.grant_database_access(database_stack.proxy_security_group)

# Monitoring Stack - CloudWatch dashboards and alarms
monitoring_stack = MonitoringStack(
    app,
    f"MonitoringStack-{environment_name}",
    environment_name=environment_name,
    bedrock_model_id=bedrock_model_id,
    alert_email=alert_email,
    env=env,
    description=f"Pantry Pirate Radio monitoring infrastructure ({environment_name})",
)

# Grant permissions between stacks

# Compute Stack (LLM Workers) - needs queue, storage, and Bedrock access
compute_stack.grant_queue_access(queue_stack.llm_queue)
compute_stack.grant_storage_access(
    storage_stack.content_bucket,
    storage_stack.jobs_table,
    storage_stack.content_index_table,
)

# Wire security groups for database access
# Services that need to connect to the database via RDS Proxy
# Note: ServicesStack grants its own access to avoid circular cross-stack
# references (ServicesStack depends on DatabaseStack, so DatabaseStack
# cannot reference ServicesStack security groups).
services_stack.grant_database_access(database_stack.proxy_security_group)
database_stack.allow_connection_from(compute_stack.worker_security_group)

# DbInit Stack - needs database access for Lambda and ECS tasks
# Use L1 constructs scoped to db_init_stack to avoid circular cross-stack
# references (DbInitStack depends on DatabaseStack).
ec2.CfnSecurityGroupIngress(
    db_init_stack,
    "CheckDbLambdaToProxyIngress",
    group_id=database_stack.proxy_security_group.security_group_id,
    source_security_group_id=db_init_stack.check_db_lambda_security_group.security_group_id,
    ip_protocol="tcp",
    from_port=5432,
    to_port=5432,
    description="Allow check-db Lambda to connect to RDS Proxy",
)
ec2.CfnSecurityGroupIngress(
    db_init_stack,
    "InitTaskToProxyIngress",
    group_id=database_stack.proxy_security_group.security_group_id,
    source_security_group_id=db_init_stack.init_task_security_group.security_group_id,
    ip_protocol="tcp",
    from_port=5432,
    to_port=5432,
    description="Allow init task to connect to RDS Proxy",
)

# Grant IAM permissions to services

# Validator permissions:
# - Consume from validator queue, send to reconciler queue
# - Read/write geocoding cache (DynamoDB)
# - Read content bucket
# - Read database credentials
queue_stack.validator_queue.grant_consume_messages(services_stack.validator_task_role)
queue_stack.reconciler_queue.grant_send_messages(services_stack.validator_task_role)
database_stack.geocoding_cache_table.grant_read_write_data(services_stack.validator_task_role)
storage_stack.content_bucket.grant_read(services_stack.validator_task_role)
database_stack.database_credentials_secret.grant_read(services_stack.validator_task_role)

# Reconciler permissions:
# - Consume from reconciler queue, send to recorder queue
# - Read database credentials
queue_stack.reconciler_queue.grant_consume_messages(services_stack.reconciler_task_role)
queue_stack.recorder_queue.grant_send_messages(services_stack.reconciler_task_role)
database_stack.database_credentials_secret.grant_read(services_stack.reconciler_task_role)

# Publisher permissions:
# - Write to exports bucket (upload SQLite)
# - Read database credentials
storage_stack.exports_bucket.grant_write(services_stack.publisher_task_role)
database_stack.database_credentials_secret.grant_read(services_stack.publisher_task_role)

# Recorder permissions:
# - Consume from recorder queue
# - Read/write content bucket and content index table
queue_stack.recorder_queue.grant_consume_messages(services_stack.recorder_task_role)
storage_stack.content_bucket.grant_read_write(services_stack.recorder_task_role)
storage_stack.content_index_table.grant_read_write_data(services_stack.recorder_task_role)

# Scraper permissions:
# - Send messages to LLM queue and staging queue (batch inference)
# - Read/write content bucket and content index table
# - Read/write jobs table (SQS backend needs job status tracking)
# - Read database credentials
queue_stack.llm_queue.grant_send_messages(services_stack.scraper_task_role)
batch_stack.staging_queue.grant_send_messages(services_stack.scraper_task_role)
storage_stack.content_bucket.grant_read_write(services_stack.scraper_task_role)
storage_stack.content_index_table.grant_read_write_data(services_stack.scraper_task_role)
storage_stack.jobs_table.grant_read_write_data(services_stack.scraper_task_role)
database_stack.database_credentials_secret.grant_read(services_stack.scraper_task_role)

# Worker (LLM) permissions:
# - Send messages to validator queue (after LLM processing)
# - Read LLM API keys secret
queue_stack.validator_queue.grant_send_messages(compute_stack.task_role)
secrets_stack.llm_api_keys_secret.grant_read(compute_stack.task_role)

# Configure auto-scaling based on SQS queue depth
compute_stack.configure_auto_scaling(queue_stack.llm_queue)
services_stack.configure_auto_scaling(
    validator_queue=queue_stack.validator_queue,
    reconciler_queue=queue_stack.reconciler_queue,
    recorder_queue=queue_stack.recorder_queue,
)

# Add stack dependencies (deployment order)

# Compute depends on storage, queues, and ECR (needs image repos)
compute_stack.add_dependency(storage_stack)
compute_stack.add_dependency(queue_stack)
compute_stack.add_dependency(ecr_stack)

# Database depends on compute (needs VPC)
database_stack.add_dependency(compute_stack)

# Services depends on compute (needs VPC and cluster)
services_stack.add_dependency(compute_stack)
# Services also depends on database (needs proxy endpoint and secrets)
services_stack.add_dependency(database_stack)
# Services depends on secrets (needs GitHub PAT)
services_stack.add_dependency(secrets_stack)
# Services depends on storage (needs bucket and table names)
services_stack.add_dependency(storage_stack)
# Services depends on queue (needs queue URLs)
services_stack.add_dependency(queue_stack)
# Services depends on ECR (needs image repos)
services_stack.add_dependency(ecr_stack)

# Batch depends on compute (VPC), storage, and queues
batch_stack.add_dependency(compute_stack)
batch_stack.add_dependency(storage_stack)
batch_stack.add_dependency(queue_stack)
batch_stack.add_dependency(ecr_stack)

# Pipeline depends on compute (needs cluster), services (task def), and batch (staging queue + Lambda)
pipeline_stack.add_dependency(compute_stack)
pipeline_stack.add_dependency(services_stack)
pipeline_stack.add_dependency(batch_stack)

# DbInit depends on compute (needs VPC and cluster)
db_init_stack.add_dependency(compute_stack)
# DbInit depends on database (needs proxy endpoint and credentials)
db_init_stack.add_dependency(database_stack)
# DbInit depends on secrets (needs GitHub PAT)
db_init_stack.add_dependency(secrets_stack)

# Bastion Stack (dev only) - SSM port forwarding to Aurora for Metabase
if environment_name == "dev":
    bastion_stack = BastionStack(
        app,
        f"BastionStack-{environment_name}",
        vpc=compute_stack.vpc,
        environment_name=environment_name,
        env=env,
        description=f"Pantry Pirate Radio bastion for SSM port forwarding ({environment_name})",
    )
    bastion_stack.add_dependency(compute_stack)
    bastion_stack.add_dependency(database_stack)

    # Allow bastion to connect to RDS Proxy
    ec2.CfnSecurityGroupIngress(
        bastion_stack,
        "BastionToProxyIngress",
        group_id=database_stack.proxy_security_group.security_group_id,
        source_security_group_id=bastion_stack.bastion_security_group.security_group_id,
        ip_protocol="tcp",
        from_port=5432,
        to_port=5432,
        description="Allow bastion to connect to RDS Proxy",
    )

    # Metabase Access Stack — NLB for Metabase Cloud to reach Aurora via RDS Proxy
    metabase_stack = MetabaseAccessStack(
        app,
        f"MetabaseAccessStack-{environment_name}",
        vpc=compute_stack.vpc,
        proxy_endpoint=database_stack.proxy_endpoint,
        environment_name=environment_name,
        env=env,
        description=f"Pantry Pirate Radio NLB for Metabase Cloud access ({environment_name})",
    )
    metabase_stack.add_dependency(compute_stack)
    metabase_stack.add_dependency(database_stack)

    # Allow NLB targets to reach RDS Proxy
    ec2.CfnSecurityGroupIngress(
        metabase_stack,
        "NlbToProxyIngress",
        group_id=database_stack.proxy_security_group.security_group_id,
        source_security_group_id=metabase_stack.nlb_security_group.security_group_id,
        ip_protocol="tcp",
        from_port=5432,
        to_port=5432,
        description="Allow NLB to reach RDS Proxy for Metabase Cloud",
    )

# Monitoring depends on all other stacks
monitoring_stack.add_dependency(compute_stack)
monitoring_stack.add_dependency(database_stack)
monitoring_stack.add_dependency(services_stack)
monitoring_stack.add_dependency(pipeline_stack)
monitoring_stack.add_dependency(db_init_stack)
monitoring_stack.add_dependency(lambda_api_stack)

app.synth()
