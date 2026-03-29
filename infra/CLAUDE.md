# CLAUDE.md - CDK Infrastructure

This file provides guidance for working with the AWS CDK infrastructure for Pantry Pirate Radio.

## Quick Reference

```bash
# Deployment (all CDK operations run in Docker — no local Node.js/CDK needed)
./bouy deploy dev                    # Full deploy (build + CDK + push + redeploy)
./bouy deploy dev --diff             # Show CDK diff without deploying
./bouy deploy dev --infra-only       # CDK deploy only (assumes images exist)
./bouy deploy dev --images-only      # Build and push Docker images only
./bouy deploy dev --destroy          # Tear down all stacks

# Run CDK tests
cd infra && docker build -t pantry-pirate-radio-cdk . && docker run --rm pantry-pirate-radio-cdk pytest -v

# First-time setup
./scripts/bootstrap.sh dev       # Bootstrap CDK + create ECR repos + IAM roles
```

## Project Structure

```
infra/
├── app.py                    # CDK app entry point
├── plugin_discovery.py       # Plugin CDK stack discovery
├── cdk.json                  # CDK configuration
├── requirements.txt          # Python dependencies
├── Dockerfile                # Container for CDK operations
├── pytest.ini                # Test configuration
├── stacks/
│   ├── __init__.py
│   ├── api_stack.py          # ALB + Fargate API (21 tests)
│   ├── batch_stack.py        # Bedrock Batch Inference (12 tests)
│   ├── compute_stack.py      # VPC + ECS Fargate Workers (20 tests)
│   ├── database_stack.py     # Aurora Serverless v2 + RDS Proxy (22 tests)
│   ├── ecr_stack.py          # ECR container repositories (16 tests)
│   ├── metabase_access_stack.py # NLB for Metabase Cloud
│   ├── monitoring_stack.py   # CloudWatch orchestrator (delegates to dashboard + alarms modules)
│   ├── monitoring_dashboard.py # CloudWatch dashboard sections
│   ├── monitoring_dashboard_queues.py # SQS queue + pipeline dashboard sections
│   ├── monitoring_alarms.py  # CloudWatch alarm definitions
│   ├── pipeline_stack.py     # Step Functions + EventBridge (16 tests)
│   ├── queue_stack.py        # SQS FIFO queues (17 tests)
│   ├── secrets_stack.py      # Secrets Manager (9 tests)
│   ├── services_stack.py     # Fargate services (23 tests)
│   ├── storage_stack.py      # S3 + DynamoDB (19 tests)
│   └── submarine_stack.py    # Submarine Step Functions orchestration
├── tests/
│   ├── conftest.py
│   ├── test_api_stack.py
│   ├── test_batch_stack.py
│   ├── test_compute_stack.py
│   ├── test_database_stack.py
│   ├── test_ecr_stack.py
│   ├── test_metabase_stack.py
│   ├── test_monitoring_stack.py
│   ├── test_pipeline_stack.py
│   ├── test_queue_stack.py
│   ├── test_secrets_stack.py
│   ├── test_services_stack.py
│   ├── test_storage_stack.py
│   └── test_tags.py
└── scripts/
    ├── bootstrap.sh          # One-time AWS setup
    └── deploy.sh             # Deployment script
```

## Stack Overview

### SecretsStack
- **GitHub PAT Secret**: For HAARRRvest repository access
- **LLM API Keys Secret**: Anthropic/OpenRouter API keys
- **Note**: Database credentials managed by DatabaseStack (avoids cyclic dependencies)

### ECRStack
- **ECR Repositories**: Container image repositories for all services
- **Services**: worker, validator, reconciler, publisher, recorder, scraper, app, api-lambda
- **Repository naming**: `pantry-pirate-radio-{service}-{environment}`
- **Image scanning**: Enabled on push for vulnerability detection
- **Lifecycle rules**: Keep last 10 images, delete untagged images after 1 day (7 in prod)
- **Environment config**: Dev repos can be deleted, prod repos are retained

### StorageStack
- **S3 Bucket**: Content store with encryption, versioning, lifecycle rules
- **DynamoDB Jobs Table**: `job_id` PK, TTL, status GSI for queries
- **DynamoDB Content Index**: `content_hash` PK for deduplication

### QueueStack
- **LLM Queue**: Raw content to HSDS alignment (600s visibility)
- **Validator Queue**: Data enrichment and confidence scoring (600s visibility)
- **Reconciler Queue**: Canonical record creation (300s visibility)
- **Recorder Queue**: Job result archiving (120s visibility)
- **Submarine Queue**: Web crawl jobs for Fargate crawlers (600s visibility)
- **Submarine Staging Queue**: Crawled content awaiting batch extraction (300s visibility)
- **Submarine Extraction Queue**: On-demand extraction fallback when <100 records (600s visibility)
- **Dead Letter Queues**: One per main queue, 14-day retention

### BatchInferenceStack
- **SQS Staging Queue**: FIFO queue for scraper output staging (300s visibility, DLQ)
- **S3 Batch Bucket**: JSONL I/O for Bedrock batch jobs (7-day lifecycle)
- **Bedrock Service Role**: IAM role trusting `bedrock.amazonaws.com` for batch jobs
- **Batcher Lambda**: Drains staging queue, decides batch (>= 100 records) vs on-demand. Also handles submarine source (`source="submarine"` param) for submarine batch extraction
- **Result Processor Lambda**: Routes batch output downstream (validator/reconciler/recorder for scrapers, reconciler-only for submarine)
- **EventBridge Rule**: Triggers result processor on `Batch Inference Job State Change`

### ComputeStack
- **VPC**: 2 AZs, public/private subnets, NAT gateways
- **ECS Cluster**: Container Insights enabled
- **Fargate Worker Service**: Processes LLM jobs from SQS
- **IAM Roles**: Bedrock invoke, SQS, DynamoDB, S3 permissions

### DatabaseStack
- **Aurora Serverless v2**: PostgreSQL 15 with PostGIS extension
- **RDS Proxy**: Connection pooling with IAM authentication
- **Geocoding Cache Table**: DynamoDB table for geocoding results
- **Database Credentials**: Auto-generated, stored in Secrets Manager
- **Environment Config** (unified sizing for cost parity):
  | Config | Dev | Prod |
  |--------|-----|------|
  | Min ACU | 0.5 | 0.5 |
  | Max ACU | 2 | 2 |
  | Multi-AZ | No | No |
  | DynamoDB PITR | No | Yes |
  | Deletion Protection | No | Yes |
  | Backup Retention | 30 days | 30 days |
  | Removal Policy | DESTROY | RETAIN |

### ServicesStack
Fargate services for pipeline stages:
| Service | CPU | Memory | Scaling | SQS Queue |
|---------|-----|--------|---------|-----------|
| Validator | 512 | 1024MB | 1-5 | validator.fifo |
| Reconciler | 512 | 1024MB | **1 only** | reconciler.fifo |
| Publisher | 256 | 512MB | 1 | (polls DB) |
| Recorder | 256 | 512MB | 1-2 | recorder.fifo |
| Scraper (task) | 512 | 1024MB | N/A | Step Functions |
| Submarine (crawl) | 512 | 1024MB | 0-4 | submarine.fifo |
| Submarine (extract) | 512 | 1024MB | 0-2 | submarine-extraction.fifo |

### PipelineStack
- **Step Functions State Machine**: Scraper orchestration with Map state
- **EventBridge Rule**: Daily schedule at 2 AM UTC (disabled in dev)
- **Map State**: Runs scrapers in parallel (MaxConcurrency=0 (unlimited))
- **Retry/Catch**: 2 attempts with 60s backoff, failures recorded

### SubmarineStack
- **Step Functions State Machine**: Submarine scan + batch extraction orchestration
  - `RunSubmarineScan` (ECS task) → `WaitForCrawlSoak` (30min) → `CheckCrawlersDone` (Lambda polls queue) → `RunBatcher` (Lambda, source="submarine") → `ScanComplete`
  - Check-queue Lambda loops every 5min until submarine queue is empty
  - Batcher decides: ≥100 records → Bedrock batch (50% off), <100 → on-demand extraction queue
- **EventBridge Rule**: Weekly schedule (prod only, disabled in dev)
- **Check-Queue Lambda**: Inline Python 3.12, checks SQS queue depth
- **IAM Role**: ECS runTask + Lambda invoke permissions

### LambdaApiStack
- **Lambda (DockerImageFunction)**: ARM64, 1024MB, 30s timeout, VPC private subnets, X-Ray tracing
- **API Gateway HTTP API (v2)**: `$default` catch-all route → Lambda, CORS preflight
- **Security Group**: Lambda → RDS Proxy access
- **IAM**: Secrets Manager read for DB credentials
- **ECR Repository**: `api-lambda` (slim ~300MB image)
- **Cost**: ~$2/mo dev (vs ~$55/mo Fargate ALB)

### APIStack (LEGACY — NOT DEPLOYED)
- **Status**: Replaced by LambdaApiStack. Stack code preserved in `stacks/api_stack.py`
- **Application Load Balancer**: Internet-facing, optional HTTPS
- **Fargate API Service**: FastAPI application
- **Auto-scaling**: CPU (70%) and request-based (1000/target)
- **Health Check**: `/health` endpoint

### MetabaseAccessStack
- **Network Load Balancer**: Internet-facing NLB in public subnets, TCP 5432
- **NLB Security Group**: Restricted to Metabase Cloud static IPs (us-east-1)
- **IP Target Group**: Points at RDS Proxy private IPs
- **Lambda (IP Sync)**: Resolves proxy DNS every minute, syncs target group IPs
- **EventBridge Rule**: Triggers IP sync Lambda every 1 minute
- **Custom Resource**: Seeds initial IPs at deploy time
- **Cost**: ~$17/month (NLB ~$16 + Lambda ~$0.50)

### BastionStack
- **EC2 t4g.nano**: SSM Session Manager for ad-hoc port forwarding to Aurora
- **No SSH**: Access via SSM only

### MonitoringStack
Split into three modules: `monitoring_stack.py` (orchestrator), `monitoring_dashboard.py` + `monitoring_dashboard_queues.py` (12 dashboard sections), `monitoring_alarms.py` (37+ alarms).
- **CloudWatch Dashboard**: Lambda API, ECS Services, SQS Queues, Pipeline Overview, Aurora, RDS Proxy, DynamoDB, Bedrock LLM, Batch Inference (conditional), Geocoding, Auto-Scaling, S3 Storage
- **SNS Topic**: Alert notifications
- **Alarms (37+ base)**: Lambda errors/throttles/error-rate-%, API Gateway 5xx/4xx (conditional), SQS queue depths, DLQ messages, DynamoDB throttles/system-errors, Bedrock throttles, Aurora ACU/connections, RDS Proxy connections, Fargate CPU/memory per service, Step Functions failures, Location Service errors, S3 4xx/5xx per bucket, batch Lambda errors/throttles (conditional)

## Environment Variables

```bash
# Required for deployment
CDK_DEPLOY_ENVIRONMENT=dev|staging|prod
CDK_DEPLOY_ACCOUNT=123456789012
CDK_DEPLOY_REGION=us-east-1

# Optional
CDK_CERTIFICATE_ARN=arn:aws:acm:...    # For HTTPS
CDK_DOMAIN_NAME=api.example.com        # Custom domain
CDK_ALERT_EMAIL=alerts@example.com     # Alert notifications
CDK_BEDROCK_MODEL_ID=us.anthropic.claude-haiku-4-5-20251001-v1:0  # Bedrock model for dashboard metrics
```

## Testing

All CDK tests use `aws_cdk.assertions` for template validation:

```bash
# Run all tests in Docker (recommended)
docker build -t pantry-pirate-radio-cdk .
docker run --rm pantry-pirate-radio-cdk pytest -v

# Run specific test file
docker run --rm pantry-pirate-radio-cdk pytest tests/test_storage_stack.py -v

# Run with local Python (requires aws-cdk-lib installed)
cd infra
pip install -r requirements.txt
pytest -v
```

### Test Categories
- **Resource Creation**: Verify correct AWS resources are created
- **Properties**: Validate resource configuration (encryption, TTL, etc.)
- **Environment Variations**: Test dev vs prod differences (PITR, retention)
- **Attributes**: Ensure stack exposes required attributes for cross-stack refs

## Stack Dependencies

```
SecretsStack (standalone)
ECRStack (standalone)

StorageStack ─────┐
                  ├──► ComputeStack ──┬──► DatabaseStack ──┬──► MetabaseAccessStack (dev)
QueueStack ───────┘        │          │                    └──► BastionStack (dev)
                           │          ├──► ServicesStack ──┐
                           │          │                    ├──► PipelineStack
                           │          │                    ├──► SubmarineStack (also depends on BatchStack)
                           └──► BatchStack ────────────────┘
                                      │
                                      └──► DbInitStack
                                                │
                                                ▼
                                         MonitoringStack

LambdaApiStack depends on ComputeStack + DatabaseStack + ECRStack
(APIStack exists as legacy code but is NOT deployed — replaced by LambdaApiStack)
```

Permissions are granted via helper methods:
```python
# In app.py
compute_stack.grant_queue_access(queue_stack.llm_queue)
compute_stack.grant_storage_access(storage_stack.content_bucket, ...)
services_stack.grant_database_access(database_stack.proxy_security_group)
```

## Deployment Workflow

### First-Time Setup
```bash
# 1. Bootstrap CDK and create required resources
./scripts/bootstrap.sh dev

# 2. Add GitHub secrets (output from bootstrap)
#    AWS_DEPLOY_ROLE_ARN
#    AWS_ACCOUNT_ID

# 3. Deploy infrastructure
./bouy deploy dev
```

### Regular Deployment
```bash
# Via GitHub Actions (automatic on push to main)
# Or manually:
./bouy deploy dev
```

### Destroying Infrastructure
```bash
./bouy deploy dev --destroy
```

## Common Tasks

### Adding a New Stack
1. Create `stacks/new_stack.py` with Stack class
2. Create `tests/test_new_stack.py` with tests
3. Import in `stacks/__init__.py`
4. Add to `app.py` with dependencies
5. Run tests: `docker run --rm pantry-pirate-radio-cdk pytest -v`

### Modifying Resources
1. Update the stack file
2. Update corresponding tests
3. Run `./bouy deploy dev --diff` to preview changes
4. Deploy with `./bouy deploy dev`

### Adding Environment-Specific Config
Use the `environment_name` parameter in stacks:
```python
if self.environment_name == "prod":
    # Production settings (PITR, retain on delete, etc.)
else:
    # Dev settings (destroy on delete, no PITR, etc.)
```

## CI/CD Integration

### GitHub Actions Workflows
- **cdk-test.yml**: Runs on PRs to `infra/**`, posts diff as comment
- **deploy-aws.yml**: Deploys on push to main or manual trigger

### Required GitHub Secrets
| Secret | Description |
|--------|-------------|
| `AWS_DEPLOY_ROLE_ARN` | IAM role for GitHub Actions OIDC |
| `AWS_ACCOUNT_ID` | AWS account ID |
| `CDK_CERTIFICATE_ARN` | (Optional) ACM certificate for HTTPS |
| `CDK_DOMAIN_NAME` | (Optional) Custom domain |
| `CDK_ALERT_EMAIL` | (Optional) Alert email |

## Troubleshooting

### CDK Synth Fails
```bash
# Check for AWS credentials
aws sts get-caller-identity

# Synth with debug
cdk synth --debug
```

### Tests Fail
```bash
# Run with verbose output
docker run --rm pantry-pirate-radio-cdk pytest -v --tb=long

# Run single test
docker run --rm pantry-pirate-radio-cdk pytest tests/test_storage_stack.py::TestStorageStackResources::test_creates_s3_bucket -v
```

### Deployment Fails
```bash
# Check CloudFormation events
aws cloudformation describe-stack-events --stack-name StorageStack-dev

# Rollback stuck stack
aws cloudformation continue-update-rollback --stack-name StorageStack-dev
```

## Architecture Decisions

1. **FIFO Queues**: Content-based deduplication using job_id prevents duplicate processing
2. **Fargate (not Lambda)**: 10GB Docker image + 20+ minute scrapers exceed Lambda limits
3. **DynamoDB for Jobs**: Pay-per-request, TTL for cleanup, GSI for status queries
4. **Separate VPC**: Isolated network with private subnets for workers
5. **ALB (not API Gateway)**: Better for long-running FastAPI with WebSocket potential
6. **Aurora Serverless v2**: Auto-scaling PostgreSQL, cost-effective for variable workloads
7. **RDS Proxy**: Connection pooling for Fargate services, IAM authentication
8. **Step Functions (not EventBridge Scheduler)**: Better visibility, retry logic, Map state for parallel scrapers
9. **Database Credentials in DatabaseStack**: Avoids cross-stack cyclic dependencies with SecretsStack

## Architecture Diagram

```
                          ┌─────────────────────────────────────────────────────────────────┐
                          │                         AWS Cloud                                │
                          │                                                                  │
EventBridge ──────────────┤  Step Functions State Machine                                   │
(daily, disabled)         │         │                                                       │
                          │         ▼                                                       │
                          │  ┌─────────────────────────────────────────────┐                │
                          │  │ Map State (MaxConcurrency=0 (unlimited))               │                │
                          │  │   ↓   ↓   ↓   ↓   ↓   ↓   ↓   ↓   ↓   ↓    │                │
                          │  │ Fargate Scraper Tasks                       │                │
                          │  └─────────────────────────────────────────────┘                │
                          │         │                                                       │
                          │         ▼                                                       │
                          │  S3 Content Store (SHA-256 dedup)                               │
                          │         │                                                       │
                          │         ▼                                                       │
                          │  SQS Staging Queue (FIFO)                                       │
                          │         │                                                       │
                          │         ▼                                                       │
                          │  Batcher Lambda (batch vs on-demand decision)                   │
                          │       │              │                                          │
                          │  [>=100 records] [<100 records]                                 │
                          │       │              │                                          │
                          │       ▼              ▼                                          │
                          │  Bedrock Batch    SQS LLM Queue (FIFO)                          │
                          │  (50% off)           │                                          │
                          │       │              ▼                                          │
                          │       ▼       Fargate Worker Service (Bedrock LLM)              │
                          │  Result Processor Lambda                                        │
                          │       │              │                                          │
                          │       └──────┬───────┘                                          │
                          │         │                                                       │
                          │         ▼                                                       │
                          │  SQS Validator Queue (FIFO)                                     │
                          │         │                                                       │
                          │         ▼                                                       │
                          │  Fargate Validator Service                                      │
                          │         │                                                       │
                          │         ▼                                                       │
                          │  SQS Reconciler Queue (FIFO)                                    │
                          │         │                                                       │
                          │         ▼                                                       │
                          │  Fargate Reconciler Service (single instance)                   │
                          │         │                                                       │
                          │         ▼                                                       │
                          │  Aurora Serverless v2 PostgreSQL (via RDS Proxy)                │
                          │         │                                                       │
                          │         ▼                                                       │
                          │  Fargate Publisher Service ──────────────────────────────► GitHub
                          │         │                                                       │
                          │         ▼                                                       │
                          │  SQS Recorder Queue (FIFO)                                      │
                          │         │                                                       │
                          │         ▼                                                       │
                          │  Fargate Recorder Service                                       │
                          └─────────────────────────────────────────────────────────────────┘

LOCAL: app/api stays local, connects to AWS resources via IAM credentials
```

## Cost Estimate (Dev Environment)

| Resource | Configuration | Monthly Cost |
|----------|--------------|--------------|
| Aurora Serverless v2 | 0.5-2 ACU | ~$10-30 |
| RDS Proxy | Single instance | ~$18 |
| Secrets Manager | 4 secrets | ~$1.60 |
| Fargate Services | Worker + Validator + Reconciler + Publisher + Recorder | ~$50-70 |
| Fargate Tasks (Scrapers) | ~1hr/day | ~$5-10 |
| Step Functions | ~30 transitions/day | ~$0.75 |
| SQS | 5 FIFO queues | ~$1 |
| S3 | Content + batch | ~$1-5 |
| Batch Lambdas | Batcher + Result Processor | ~$1 |
| DynamoDB | On-demand | ~$1-5 |
| NAT Gateway | 1 (dev) | ~$32 |
| **Total** | | **~$120-175/month** |

Note: NAT Gateway is the biggest cost. VPC Endpoints can reduce this.
