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

from stacks.api_stack import APIStack
from stacks.compute_stack import ComputeStack
from stacks.database_stack import DatabaseStack
from stacks.db_init_stack import DbInitStack
from stacks.ecr_stack import ECRStack
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
    github_pat_secret=secrets_stack.github_pat_secret,
    llm_api_keys_secret=secrets_stack.llm_api_keys_secret,
    data_repo_url="https://github.com/For-The-Greater-Good/HAARRRvest.git",
)

# Services Stack - Fargate services for pipeline stages + Scraper task
services_stack = ServicesStack(
    app,
    f"ServicesStack-{environment_name}",
    vpc=compute_stack.vpc,
    cluster=compute_stack.cluster,
    environment_name=environment_name,
    config=service_config,
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
    environment_name=environment_name,
    env=env,
    description=f"Pantry Pirate Radio database initialization ({environment_name})",
)

# Pipeline Stack - Step Functions for scraper orchestration
pipeline_stack = PipelineStack(
    app,
    f"PipelineStack-{environment_name}",
    cluster=compute_stack.cluster,
    scraper_task_definition=services_stack.scraper_task_definition,
    environment_name=environment_name,
    schedule_enabled=(environment_name == "prod"),  # Only enable schedule in prod
    env=env,
    description=f"Pantry Pirate Radio scraper pipeline ({environment_name})",
)

# API Stack - ALB + Fargate for FastAPI (keeping local for now, but stack exists)
api_stack = APIStack(
    app,
    f"APIStack-{environment_name}",
    vpc=compute_stack.vpc,
    cluster=compute_stack.cluster,
    environment_name=environment_name,
    certificate_arn=certificate_arn,
    domain_name=domain_name,
    env=env,
    description=f"Pantry Pirate Radio API infrastructure ({environment_name})",
)

# Monitoring Stack - CloudWatch dashboards and alarms
monitoring_stack = MonitoringStack(
    app,
    f"MonitoringStack-{environment_name}",
    environment_name=environment_name,
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

# API Stack - needs read access to storage and write access to LLM queue
api_stack.grant_database_read(
    storage_stack.jobs_table,
    storage_stack.content_index_table,
)
api_stack.grant_queue_write(queue_stack.llm_queue)

# Wire security groups for database access
# Services that need to connect to the database via RDS Proxy
database_stack.allow_connection_from(services_stack.validator_security_group)
database_stack.allow_connection_from(services_stack.reconciler_security_group)
database_stack.allow_connection_from(services_stack.publisher_security_group)
database_stack.allow_connection_from(services_stack.recorder_security_group)
database_stack.allow_connection_from(services_stack.scraper_security_group)
database_stack.allow_connection_from(compute_stack.worker_security_group)
database_stack.allow_connection_from(api_stack.api_service.service.connections.security_groups[0])

# DbInit Stack - needs database access for Lambda and ECS tasks
database_stack.allow_connection_from(db_init_stack.check_db_lambda_security_group)
database_stack.allow_connection_from(db_init_stack.init_task_security_group)

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
# - Read GitHub PAT for HAARRRvest repository access
# - Read database credentials
secrets_stack.github_pat_secret.grant_read(services_stack.publisher_task_role)
database_stack.database_credentials_secret.grant_read(services_stack.publisher_task_role)

# Recorder permissions:
# - Consume from recorder queue
# - Read/write content bucket and content index table
queue_stack.recorder_queue.grant_consume_messages(services_stack.recorder_task_role)
storage_stack.content_bucket.grant_read_write(services_stack.recorder_task_role)
storage_stack.content_index_table.grant_read_write_data(services_stack.recorder_task_role)

# Scraper permissions:
# - Send messages to LLM queue
# - Read/write content bucket and content index table
# - Read database credentials
queue_stack.llm_queue.grant_send_messages(services_stack.scraper_task_role)
storage_stack.content_bucket.grant_read_write(services_stack.scraper_task_role)
storage_stack.content_index_table.grant_read_write_data(services_stack.scraper_task_role)
database_stack.database_credentials_secret.grant_read(services_stack.scraper_task_role)

# Worker (LLM) permissions:
# - Send messages to validator queue (after LLM processing)
# - Read LLM API keys secret
queue_stack.validator_queue.grant_send_messages(compute_stack.task_role)
secrets_stack.llm_api_keys_secret.grant_read(compute_stack.task_role)

# Add stack dependencies (deployment order)

# Compute depends on storage and queues
compute_stack.add_dependency(storage_stack)
compute_stack.add_dependency(queue_stack)

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

# Pipeline depends on services (needs scraper task definition)
pipeline_stack.add_dependency(services_stack)

# DbInit depends on compute (needs VPC and cluster)
db_init_stack.add_dependency(compute_stack)
# DbInit depends on database (needs proxy endpoint and credentials)
db_init_stack.add_dependency(database_stack)
# DbInit depends on secrets (needs GitHub PAT)
db_init_stack.add_dependency(secrets_stack)

# API depends on compute
api_stack.add_dependency(compute_stack)

# Monitoring depends on all other stacks
monitoring_stack.add_dependency(compute_stack)
monitoring_stack.add_dependency(api_stack)
monitoring_stack.add_dependency(database_stack)
monitoring_stack.add_dependency(services_stack)
monitoring_stack.add_dependency(pipeline_stack)
monitoring_stack.add_dependency(db_init_stack)

app.synth()
