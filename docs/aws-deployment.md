# AWS Deployment Guide

This guide covers deploying Pantry Pirate Radio on AWS using CDK infrastructure.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Architecture](#architecture)
- [Local vs AWS Architecture Comparison](#local-vs-aws-architecture-comparison)
- [First-Time Setup](#first-time-setup)
- [Deployment](#deployment)
- [Configuration](#configuration)
- [Operations](#operations)
- [Monitoring](#monitoring)
- [Cost Optimization](#cost-optimization)
- [Troubleshooting](#troubleshooting)

## Overview

The AWS deployment provides a production-ready, scalable infrastructure using:

- **ECS Fargate**: Serverless containers for LLM workers and services
- **SQS FIFO Queues**: Reliable job delivery with exactly-once processing
- **S3 + DynamoDB**: Cloud-native content store replacing local filesystem
- **Aurora Serverless v2**: Auto-scaling PostgreSQL database
- **AWS Bedrock**: Native LLM provider (Claude models)
- **Step Functions**: Scraper orchestration
- **CloudWatch**: Monitoring and alerting

## Prerequisites

### AWS Account Setup

1. **AWS Account** with appropriate permissions
2. **AWS CLI** configured with credentials:
   ```bash
   aws configure
   # Or use SSO:
   aws sso login --profile your-profile
   ```

3. **Docker** for building CDK container:
   ```bash
   docker --version  # 20.10+
   ```

### Required Permissions

The deploying user/role needs:
- CloudFormation full access
- ECS, ECR, EC2, VPC permissions
- S3, DynamoDB, SQS permissions
- IAM role creation
- Secrets Manager access
- Bedrock model invocation

## Architecture

```
EventBridge (daily) ──► Step Functions State Machine
                              │
                              ▼
                    ┌─────────────────────────────────┐
                    │ Map State (MaxConcurrency=10)   │
                    │   Fargate Scraper Tasks         │
                    └─────────────────────────────────┘
                              │
                              ▼
                    S3 Content Store (SHA-256 dedup)
                              │
                              ▼
                    SQS LLM Queue (FIFO)
                              │
                              ▼
                    Fargate Worker Service
                    (Bedrock LLM)
                              │
                              ▼
                    SQS Validator Queue ──► Validator Service
                              │
                              ▼
                    SQS Reconciler Queue ──► Reconciler Service
                              │
                              ▼
                    Aurora Serverless v2 PostgreSQL
                              │
                              ▼
                    Publisher Service ──► GitHub (HAARRRvest)
```

### Stack Dependencies

```
SecretsStack (standalone)
ECRStack (standalone)

StorageStack ─────┐
                  ├──► ComputeStack ──┬──► DatabaseStack
QueueStack ───────┘                   │
                                      ├──► ServicesStack ──► PipelineStack
                                      │
                                      └──► APIStack
                                                │
                                                ▼
                                         MonitoringStack
```

## Local vs AWS Architecture Comparison

The application supports two deployment modes with different underlying infrastructure:

| Component | Local (Docker) | AWS |
|-----------|---------------|-----|
| **Content Store** | SQLite + filesystem | S3 + DynamoDB |
| **Job Queue** | Redis + RQ | SQS FIFO |
| **LLM Provider** | OpenAI/Claude API | AWS Bedrock |
| **Worker** | Docker container (RQ worker) | Fargate task (custom worker) |
| **Database** | PostgreSQL container | Aurora Serverless v2 |
| **Scheduling** | Manual / cron | EventBridge + Step Functions |
| **Secrets** | `.env` file | AWS Secrets Manager |

### Backend Abstraction Layer

The codebase uses Protocol-based abstractions to support both environments:

#### Content Store Backend

- **Local**: `FileContentStoreBackend` - SQLite database + JSON files on filesystem
- **AWS**: `S3ContentStoreBackend` - S3 for content/results + DynamoDB for index

```python
# Configured via environment variables
CONTENT_STORE_BACKEND=file    # Local development
CONTENT_STORE_BACKEND=s3      # AWS deployment

# S3 backend additional configuration
CONTENT_STORE_S3_BUCKET=pantry-pirate-radio-content-dev
DYNAMODB_CONTENT_TABLE=pantry-pirate-radio-content-index-dev
```

The S3 backend provides:
- SHA-256 content deduplication (same as local)
- DynamoDB index for status tracking and job associations
- S3 for blob storage (raw content and LLM results)
- Automatic retry with exponential backoff for AWS throttling

#### Queue Backend

- **Local**: `RedisQueueBackend` - Redis + RQ for job queuing
- **AWS**: `SQSQueueBackend` - SQS FIFO queues + DynamoDB for job metadata

```python
# Configured via environment variables
QUEUE_BACKEND=redis    # Local development
QUEUE_BACKEND=sqs      # AWS deployment

# SQS backend additional configuration
SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/.../llm-queue.fifo
SQS_JOBS_TABLE=pantry-pirate-radio-jobs-dev
```

The SQS backend provides:
- FIFO ordering with message deduplication
- Visibility timeout management for long-running LLM jobs
- Dead-letter queues for failed messages
- Job status tracking via DynamoDB

#### Fargate Worker

AWS uses a custom `FargateWorker` instead of RQ workers:

- Polls SQS FIFO queue for jobs
- Extends message visibility during long-running LLM calls
- Handles graceful shutdown on SIGTERM/SIGINT
- Automatic retry with exponential backoff on failures
- Scales based on queue depth via ECS auto-scaling

#### Bedrock LLM Provider

AWS deployments use Bedrock instead of direct API calls:

```python
LLM_PROVIDER=bedrock
LLM_MODEL_NAME=anthropic.claude-sonnet-4-6
AWS_DEFAULT_REGION=us-east-1
```

Features:
- Uses Converse API with tool_use for structured output
- Same prompt format as Claude API provider
- IAM-based authentication (no API keys needed)
- Model access must be enabled in Bedrock console

## First-Time Setup

### 1. Bootstrap CDK

```bash
cd infra

# Build CDK Docker image
docker build -t pantry-pirate-radio-cdk .

# Bootstrap CDK (one-time per account/region)
./scripts/bootstrap.sh dev
```

The bootstrap script:
- Creates CDK bootstrap resources
- Creates ECR repositories for all services
- Creates IAM role for GitHub Actions OIDC
- Outputs GitHub secrets to configure

### 2. Configure GitHub Secrets

After bootstrap, add these secrets to your GitHub repository:

| Secret | Description |
|--------|-------------|
| `AWS_DEPLOY_ROLE_ARN` | IAM role ARN (output from bootstrap) |
| `AWS_ACCOUNT_ID` | Your AWS account ID |
| `CDK_CERTIFICATE_ARN` | (Optional) ACM certificate for HTTPS |
| `CDK_DOMAIN_NAME` | (Optional) Custom domain name |
| `CDK_ALERT_EMAIL` | (Optional) Email for CloudWatch alerts |

### 3. Deploy Infrastructure

```bash
# Deploy all stacks
./scripts/deploy.sh dev

# Or deploy specific stack
./scripts/deploy.sh dev --stack StorageStack

# Preview changes without deploying
./scripts/deploy.sh dev --diff
```

## Deployment

### Automated Deployment (GitHub Actions)

Push to `main` triggers automatic deployment:

1. **cdk-test.yml**: Runs on PRs to `infra/**`, posts diff as comment
2. **deploy-aws.yml**: Deploys on push to main

### Manual Deployment

```bash
cd infra

# Full deployment
./scripts/deploy.sh dev

# Specific environment
./scripts/deploy.sh staging
./scripts/deploy.sh prod

# Preview changes
./scripts/deploy.sh dev --diff

# Generate CloudFormation only
./scripts/deploy.sh dev --synth
```

### Destroying Infrastructure

```bash
# Remove all stacks (WARNING: deletes data in dev)
./scripts/deploy.sh dev --destroy

# In production, deletion protection prevents accidental deletion
```

## Configuration

### Environment Variables

Set these before deployment:

```bash
export CDK_DEPLOY_ENVIRONMENT=dev      # dev, staging, prod
export CDK_DEPLOY_ACCOUNT=123456789012
export CDK_DEPLOY_REGION=us-east-1

# Optional
export CDK_CERTIFICATE_ARN=arn:aws:acm:...
export CDK_DOMAIN_NAME=api.example.com
export CDK_ALERT_EMAIL=alerts@example.com
```

### Content Store Backend

The content store automatically uses S3+DynamoDB in AWS:

```python
# Environment variables set by CDK
CONTENT_STORE_BACKEND=s3
S3_CONTENT_BUCKET=pantry-pirate-radio-content-dev
DYNAMODB_CONTENT_TABLE=pantry-pirate-radio-content-index-dev
```

### Queue Backend

SQS FIFO queues replace Redis RQ:

```python
# Environment variables set by CDK
QUEUE_BACKEND=sqs
SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/.../llm-queue.fifo
SQS_JOBS_TABLE=pantry-pirate-radio-jobs-dev
```

### LLM Provider

AWS Bedrock is the default LLM provider:

```python
LLM_PROVIDER=bedrock
LLM_MODEL_NAME=anthropic.claude-sonnet-4-6
AWS_DEFAULT_REGION=us-east-1
```

## Operations

### Viewing Logs

```bash
# View worker logs
aws logs tail /ecs/pantry-pirate-radio-worker-dev --follow

# View API logs
aws logs tail /ecs/pantry-pirate-radio-api-dev --follow
```

### Scaling Workers

```bash
# Update desired count
aws ecs update-service \
  --cluster pantry-pirate-radio-dev \
  --service pantry-pirate-radio-worker-dev \
  --desired-count 3
```

### Running Scrapers

Scrapers are orchestrated by Step Functions:

```bash
# Start scraper execution manually
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:...:scraper-pipeline-dev \
  --input '{"scrapers": ["all"]}'

# Check execution status
aws stepfunctions describe-execution \
  --execution-arn arn:aws:states:...:execution/...
```

### ECS Exec (Container Debugging)

```bash
# Connect to running container
aws ecs execute-command \
  --cluster pantry-pirate-radio-dev \
  --task <task-id> \
  --container worker \
  --interactive \
  --command "/bin/bash"
```

### Checking Queue Depth

```bash
# Get approximate message count
aws sqs get-queue-attributes \
  --queue-url https://sqs.../llm-queue.fifo \
  --attribute-names ApproximateNumberOfMessages
```

## Monitoring

### CloudWatch Dashboard

A dashboard is automatically created with metrics for:
- API response times and error rates
- Worker CPU and memory utilization
- Queue depth and age
- DynamoDB throttling
- Database connections

Access via AWS Console > CloudWatch > Dashboards.

### Alarms

Automatic alarms are configured for:
- API CPU > 80%
- Queue depth > 1000 messages
- Dead letter queue messages
- DynamoDB throttling

### Metrics

Custom metrics are emitted to CloudWatch:
- `jobs_processed` - LLM jobs completed
- `jobs_failed` - LLM jobs failed
- `scraper_items` - Items scraped per run
- `content_deduplicated` - Duplicate content blocked

## Cost Optimization

### Development Environment

```
| Resource              | Dev Config         | Monthly Cost |
|-----------------------|--------------------|--------------|
| Aurora Serverless v2  | 0.5-2 ACU          | ~$10-30      |
| RDS Proxy             | Single instance    | ~$18         |
| Secrets Manager       | 4 secrets          | ~$1.60       |
| Fargate Services      | 5 services         | ~$50-70      |
| Fargate Tasks         | ~1hr/day scrapers  | ~$5-10       |
| Step Functions        | ~30 trans/day      | ~$0.75       |
| SQS                   | 4 FIFO queues      | ~$1          |
| S3                    | Content store      | ~$1-5        |
| DynamoDB              | On-demand          | ~$1-5        |
| NAT Gateway           | 1 (dev only)       | ~$32         |
| **Total**             |                    | **~$120-175/month** |
```

### Cost Reduction Tips

1. **NAT Gateway**: Use VPC endpoints to reduce NAT costs
2. **Fargate Spot**: Use Spot capacity for non-critical workers
3. **Auto-scaling**: Scale to zero during off-hours
4. **Reserved Capacity**: Use savings plans for steady workloads

## Troubleshooting

### CDK Deployment Fails

```bash
# Check CloudFormation events
aws cloudformation describe-stack-events \
  --stack-name StorageStack-dev

# Rollback stuck stack
aws cloudformation continue-update-rollback \
  --stack-name StorageStack-dev

# Debug CDK
cdk synth --debug
```

### Worker Not Processing

1. Check SQS queue has messages:
   ```bash
   aws sqs get-queue-attributes --queue-url ... \
     --attribute-names ApproximateNumberOfMessages
   ```

2. Check worker logs:
   ```bash
   aws logs tail /ecs/pantry-pirate-radio-worker-dev --follow
   ```

3. Verify IAM permissions:
   - SQS: ReceiveMessage, DeleteMessage, ChangeMessageVisibility
   - DynamoDB: GetItem, PutItem, UpdateItem
   - Bedrock: InvokeModel

### Database Connection Issues

1. Check RDS Proxy status:
   ```bash
   aws rds describe-db-proxies --db-proxy-name pantry-pirate-radio-proxy-dev
   ```

2. Verify security groups allow traffic from Fargate

3. Check Secrets Manager credentials are valid

### Content Store Issues

1. Verify S3 bucket exists and is accessible
2. Check DynamoDB table exists
3. Look for throttling errors in CloudWatch

## Testing Infrastructure

### Running CDK Tests

```bash
cd infra

# Build test container
docker build -t pantry-pirate-radio-cdk .

# Run all tests
docker run --rm pantry-pirate-radio-cdk pytest -v

# Run specific test file
docker run --rm pantry-pirate-radio-cdk pytest tests/test_storage_stack.py -v
```

### Integration Testing

After deployment:

```bash
# Health check
curl https://api.yourdomain.com/health

# Test API endpoints
curl https://api.yourdomain.com/api/v1/organizations
```

---

*This AWS deployment guide is maintained alongside the CDK infrastructure. For local development, see the main [Deployment Guide](deployment.md).*
