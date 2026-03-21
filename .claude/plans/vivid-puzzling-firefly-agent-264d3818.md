# AWS CDK Infrastructure Plan: Remaining Pipeline Migration

## Executive Summary

This plan outlines the remaining CDK infrastructure needed to complete Pantry Pirate Radio's AWS migration. The architecture adds PostgreSQL (Aurora Serverless v2 with PostGIS), additional ECS Fargate services (Validator, Reconciler, Publisher), and secrets management.

## Current State Analysis

### Already Implemented (in `/Users/bryanmoran/code/for-the-greater-good/pantry-pirate-radio/infra/stacks/`)

| Stack | Resources | Status |
|-------|-----------|--------|
| StorageStack | S3 content store, DynamoDB (jobs, content index) | Complete |
| QueueStack | SQS FIFO + DLQ (replaces Redis RQ) | Complete |
| ComputeStack | VPC (2 AZs), ECS Cluster, Fargate Worker | Complete |
| APIStack | ALB + Fargate API | Complete (not deploying) |
| MonitoringStack | CloudWatch dashboards, alarms, SNS | Complete |

### Missing Components

1. **DatabaseStack** - Aurora Serverless v2 PostgreSQL with PostGIS
2. **ServicesStack** - Validator, Reconciler, Publisher ECS services
3. **SecretsStack** - Secrets Manager for credentials and API keys

---

## Architecture Design

### Service Flow (AWS Migration)

```
Local Scrapers                   AWS Cloud
     |                              |
     v                              v
S3 Content Store  -->  SQS FIFO Queue
                            |
                            v
                    ECS Fargate Worker (LLM)
                            |
                            v
                    [Validation Queue - internal]
                            |
                            v
                    ECS Fargate Validator
                            |
                            v
                    ECS Fargate Reconciler --> Aurora PostgreSQL
                                                    |
                                                    v
                                            ECS Fargate Publisher --> GitHub
```

### Key Design Decisions

1. **Aurora Serverless v2** over Aurora Provisioned
   - Scales to zero ACUs when idle (cost-efficient for dev)
   - Instant scaling for production bursts
   - PostGIS extension supported
   - PITR for prod environments

2. **Separate ServicesStack** over extending ComputeStack
   - Clear separation of concerns
   - Independent deployment lifecycles
   - Better IAM permission scoping
   - Reuses VPC/Cluster from ComputeStack

3. **Dedicated SecretsStack**
   - Centralized secrets management
   - Automatic credential rotation for database
   - GitHub PAT for publisher isolated

4. **Internal Communication Pattern**
   - Services communicate via SQS (Validator -> Reconciler)
   - No Redis/ElastiCache - SQS only
   - Database accessed via Security Groups

---

## Stack Implementations

### 1. SecretsStack (New File: `infra/stacks/secrets_stack.py`)

**Purpose**: Centralized secrets management

**Resources**:
- `AWS::SecretsManager::Secret` - Database credentials (auto-generated)
- `AWS::SecretsManager::Secret` - GitHub PAT for publisher
- `AWS::SecretsManager::Secret` - LLM API keys (Anthropic/OpenRouter)

**Key Features**:
- Auto-rotation for database credentials
- Environment-specific secret naming
- Cross-stack secret references via ARN exports

```python
# Pseudo-structure
class SecretsStack(Stack):
    def __init__(self, ...):
        # Database credentials - auto-generated with rotation
        self.db_secret = secretsmanager.Secret(
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"username": "pantry_admin"}',
                generate_string_key="password",
                exclude_punctuation=True,
            )
        )
        
        # GitHub PAT - externally provided
        self.github_secret = secretsmanager.Secret(
            secret_name=f"pantry-pirate-radio/github-pat-{env}"
        )
        
        # LLM API keys
        self.llm_secrets = secretsmanager.Secret(
            secret_name=f"pantry-pirate-radio/llm-api-keys-{env}"
        )
    
    def grant_read(self, role: iam.IRole) -> None:
        """Grant read access to all secrets."""
```

**IAM Permissions**:
- ECS tasks can read secrets
- Secrets rotation Lambda has write access (if enabled)

---

### 2. DatabaseStack (New File: `infra/stacks/database_stack.py`)

**Purpose**: Aurora Serverless v2 PostgreSQL with PostGIS

**Resources**:
- `AWS::RDS::DBCluster` - Aurora Serverless v2 cluster
- `AWS::RDS::DBInstance` - Writer instance
- `AWS::EC2::SecurityGroup` - Database access SG
- `AWS::RDS::DBParameterGroup` - PostGIS configuration

**Configuration by Environment**:

| Setting | Dev | Staging | Prod |
|---------|-----|---------|------|
| Min ACUs | 0.5 | 0.5 | 2 |
| Max ACUs | 2 | 4 | 16 |
| PITR | Disabled | Enabled | Enabled |
| Deletion Protection | No | Yes | Yes |
| Multi-AZ | No | No | Yes |
| Backup Retention | 1 day | 7 days | 30 days |
| RemovalPolicy | DESTROY | RETAIN | RETAIN |

**PostGIS Setup**:
```sql
-- Extensions to enable (via custom parameter group or init script)
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
```

**Key Implementation Details**:

```python
class DatabaseStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.IVpc,
        secrets_stack: SecretsStack,
        environment_name: str = "dev",
        min_acu: float = 0.5,
        max_acu: float = 2,
        **kwargs,
    ) -> None:
        # Security Group allowing ECS access
        self.security_group = ec2.SecurityGroup(
            self, "DatabaseSG",
            vpc=vpc,
            description="Allow PostgreSQL access from ECS services",
        )
        
        # Aurora Serverless v2 Cluster
        self.cluster = rds.DatabaseCluster(
            self, "AuroraCluster",
            engine=rds.DatabaseClusterEngine.aurora_postgres(
                version=rds.AuroraPostgresEngineVersion.VER_15_4,
            ),
            credentials=rds.Credentials.from_secret(secrets_stack.db_secret),
            serverless_v2_min_capacity=min_acu,
            serverless_v2_max_capacity=max_acu,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            security_groups=[self.security_group],
            # PostGIS requires specific parameter group
            parameter_group=self._create_postgis_parameter_group(),
            backup=rds.BackupProps(
                retention=Duration.days(self._get_backup_days()),
            ),
            deletion_protection=environment_name == "prod",
            removal_policy=self._get_removal_policy(),
        )
        
        # Connection endpoint for ECS services
        self.endpoint = self.cluster.cluster_endpoint
        
    def grant_connect(self, role: iam.IRole) -> None:
        """Grant database connection to role."""
        
    def allow_from_security_group(self, sg: ec2.ISecurityGroup) -> None:
        """Allow inbound from service security group."""
```

**Outputs**:
- Cluster endpoint hostname
- Cluster port
- Security group ID
- Secret ARN for credentials

---

### 3. ServicesStack (New File: `infra/stacks/services_stack.py`)

**Purpose**: Additional ECS Fargate services (Validator, Reconciler, Publisher)

**Dependencies**:
- VPC and ECS Cluster from ComputeStack
- SQS Queue from QueueStack
- Database from DatabaseStack
- Secrets from SecretsStack

**Services Overview**:

| Service | CPU | Memory | Scaling | Role |
|---------|-----|--------|---------|------|
| Validator | 512 | 1024 | 1-5 | Data quality scoring |
| Reconciler | 512 | 1024 | 1-3 | Deduplication, canonical records |
| Publisher | 256 | 512 | 1 | GitHub sync |

**Service Definitions**:

```python
class ServicesStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.IVpc,
        cluster: ecs.ICluster,
        queue_stack: QueueStack,
        database_stack: DatabaseStack,
        secrets_stack: SecretsStack,
        storage_stack: StorageStack,
        environment_name: str = "dev",
        **kwargs,
    ) -> None:
        
        # Shared service security group
        self.services_sg = ec2.SecurityGroup(
            self, "ServicesSG",
            vpc=vpc,
        )
        
        # Allow services to connect to database
        database_stack.allow_from_security_group(self.services_sg)
        
        # ========== VALIDATOR SERVICE ==========
        self.validator_task_def = self._create_task_definition(
            "Validator",
            cpu=512,
            memory=1024,
        )
        self.validator_service = self._create_service(
            "Validator",
            task_def=self.validator_task_def,
            command=["validator"],
            desired_count=1,
            max_capacity=5,
        )
        
        # ========== RECONCILER SERVICE ==========
        self.reconciler_task_def = self._create_task_definition(
            "Reconciler",
            cpu=512,
            memory=1024,
        )
        self.reconciler_service = self._create_service(
            "Reconciler",
            task_def=self.reconciler_task_def,
            command=["reconciler"],
            desired_count=1,
            max_capacity=3,
        )
        
        # ========== PUBLISHER SERVICE ==========
        self.publisher_task_def = self._create_task_definition(
            "Publisher",
            cpu=256,
            memory=512,
        )
        self.publisher_service = self._create_service(
            "Publisher",
            task_def=self.publisher_task_def,
            command=["publisher"],
            desired_count=1,  # Always 1, no scaling
            max_capacity=1,
        )
        
        # Grant permissions
        self._grant_all_permissions()
```

**Environment Variables for Services**:

```python
# Common for all services
common_env = {
    "ENVIRONMENT": environment_name,
    "QUEUE_BACKEND": "sqs",
    "AWS_REGION": Stack.of(self).region,
}

# Validator-specific
validator_env = {
    **common_env,
    "VALIDATOR_ENABLED": "true",
    "VALIDATOR_ENRICHMENT_ENABLED": "true",
    "VALIDATION_REJECTION_THRESHOLD": "10",
}

# Reconciler-specific
reconciler_env = {
    **common_env,
    "RECONCILER_LOCATION_TOLERANCE": "0.0001",
}

# Publisher-specific
publisher_env = {
    **common_env,
    "PUBLISHER_PUSH_ENABLED": "true",  # Only in prod
    "PUBLISHER_CHECK_INTERVAL": "43200",  # 12 hours
}
```

**Secrets Injection**:
```python
# Database URL from secrets
secrets=[
    ecs.Secret.from_secrets_manager(
        secrets_stack.db_secret,
        field="connectionString",
    ),
]

# GitHub PAT for publisher
ecs.Secret.from_secrets_manager(
    secrets_stack.github_secret,
    field="token",
)
```

**IAM Permissions Matrix**:

| Service | S3 | DynamoDB | SQS | RDS | Secrets | Bedrock |
|---------|-----|----------|-----|-----|---------|---------|
| Validator | R/W | R/W | R/W | R/W | R | - |
| Reconciler | R | R/W | R | R/W | R | - |
| Publisher | R | R | - | R | R | - |

---

### 4. Updated app.py Integration

```python
# infra/app.py modifications

from stacks.secrets_stack import SecretsStack
from stacks.database_stack import DatabaseStack
from stacks.services_stack import ServicesStack

# ... existing stacks ...

# Secrets Stack - no dependencies
secrets_stack = SecretsStack(
    app,
    f"SecretsStack-{environment_name}",
    environment_name=environment_name,
    env=env,
)

# Database Stack - depends on ComputeStack (VPC)
database_stack = DatabaseStack(
    app,
    f"DatabaseStack-{environment_name}",
    vpc=compute_stack.vpc,
    secrets_stack=secrets_stack,
    environment_name=environment_name,
    env=env,
)

# Services Stack - depends on most other stacks
services_stack = ServicesStack(
    app,
    f"ServicesStack-{environment_name}",
    vpc=compute_stack.vpc,
    cluster=compute_stack.cluster,
    queue_stack=queue_stack,
    database_stack=database_stack,
    secrets_stack=secrets_stack,
    storage_stack=storage_stack,
    environment_name=environment_name,
    env=env,
)

# Update dependencies
secrets_stack.add_dependency(storage_stack)  # After S3/DynamoDB
database_stack.add_dependency(compute_stack)
database_stack.add_dependency(secrets_stack)
services_stack.add_dependency(database_stack)
services_stack.add_dependency(queue_stack)

# Update monitoring for new services
monitoring_stack.add_dependency(services_stack)
```

---

## Testing Strategy

### Test File Structure

```
infra/tests/
├── test_secrets_stack.py     # ~15 tests
├── test_database_stack.py    # ~20 tests  
├── test_services_stack.py    # ~25 tests
└── conftest.py               # Shared fixtures
```

### Test Categories

**SecretsStack Tests** (`test_secrets_stack.py`):
1. Creates database secret with password generation
2. Creates GitHub PAT secret
3. Creates LLM API keys secret
4. Secrets have correct naming convention
5. grant_read method grants proper permissions

**DatabaseStack Tests** (`test_database_stack.py`):
1. Creates Aurora Serverless v2 cluster
2. Uses PostgreSQL 15 engine
3. Cluster has correct min/max ACU settings
4. Security group allows port 5432
5. Dev environment has DESTROY removal policy
6. Prod environment has RETAIN removal policy
7. Prod environment has deletion protection
8. Backup retention varies by environment
9. Cluster uses private subnets
10. Parameter group enables PostGIS
11. Credentials from Secrets Manager
12. grant_connect method works correctly

**ServicesStack Tests** (`test_services_stack.py`):
1. Creates Validator ECS service
2. Creates Reconciler ECS service
3. Creates Publisher ECS service
4. Services use correct CPU/memory
5. Services in private subnets
6. Services have database access
7. Services have SQS access
8. Publisher has GitHub secret access
9. Auto-scaling configured for Validator
10. Auto-scaling configured for Reconciler
11. Publisher has no scaling (always 1)
12. Services have correct environment variables
13. Services use shared security group
14. Log groups created for each service

### Running Tests

```bash
# Build CDK container
docker build -t pantry-pirate-radio-cdk -f infra/Dockerfile infra/

# Run all tests
docker run --rm pantry-pirate-radio-cdk pytest -v

# Run specific test file
docker run --rm pantry-pirate-radio-cdk pytest tests/test_database_stack.py -v
```

---

## PR Breakdown

### PR 1: SecretsStack (Foundation)
**Files**: 
- `infra/stacks/secrets_stack.py`
- `infra/tests/test_secrets_stack.py`
- `infra/stacks/__init__.py` (update exports)

**Scope**: Secrets management infrastructure
**Tests**: ~15 new tests
**Deployment**: Safe, no dependencies

### PR 2: DatabaseStack (Data Layer)
**Files**:
- `infra/stacks/database_stack.py`
- `infra/tests/test_database_stack.py`
- `infra/stacks/__init__.py` (update exports)

**Scope**: Aurora Serverless v2 with PostGIS
**Tests**: ~20 new tests
**Dependencies**: SecretsStack, ComputeStack (VPC)

### PR 3: ServicesStack (Compute Layer)
**Files**:
- `infra/stacks/services_stack.py`
- `infra/tests/test_services_stack.py`
- `infra/stacks/__init__.py` (update exports)

**Scope**: Validator, Reconciler, Publisher services
**Tests**: ~25 new tests
**Dependencies**: All previous stacks

### PR 4: Integration (Final)
**Files**:
- `infra/app.py` (stack composition)
- `infra/CLAUDE.md` (documentation update)
- `infra/scripts/deploy.sh` (update for new stacks)

**Scope**: Wire everything together
**Tests**: Integration smoke tests

---

## Deployment Sequence

1. **Deploy SecretsStack first** (no dependencies)
2. **Manually populate secrets**:
   - GitHub PAT: `aws secretsmanager put-secret-value --secret-id pantry-pirate-radio/github-pat-dev --secret-string '{"token":"ghp_xxx"}'`
   - LLM keys: Similar process
3. **Deploy DatabaseStack** (auto-generates DB password)
4. **Run database migrations** (PostGIS extension, schema)
5. **Deploy ServicesStack** (services start connecting)
6. **Verify with monitoring** (CloudWatch dashboards)

---

## Cost Estimation (Dev Environment)

| Resource | Configuration | Estimated Monthly Cost |
|----------|---------------|----------------------|
| Aurora Serverless v2 | 0.5-2 ACU, scales to zero | ~$10-30 |
| Secrets Manager | 3 secrets | ~$1.20 |
| Fargate Validator | 512 CPU, 1GB | ~$15 |
| Fargate Reconciler | 512 CPU, 1GB | ~$15 |
| Fargate Publisher | 256 CPU, 512MB | ~$8 |
| **Total Dev** | | **~$50-70/month** |

**Prod** would be higher due to:
- Higher Aurora ACU ranges
- Multi-AZ deployment
- More Fargate capacity

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| PostGIS extension fails | High | Test in dev first, use custom parameter group |
| Database credential rotation breaks services | High | Use Secrets Manager rotation with test |
| Publisher exceeds GitHub rate limits | Medium | Implement backoff, check PUBLISHER_PUSH_ENABLED |
| Aurora cold start latency | Low | Keep min ACU at 0.5 (not zero) for dev |

---

## Critical Files for Implementation

1. **`/Users/bryanmoran/code/for-the-greater-good/pantry-pirate-radio/infra/stacks/compute_stack.py`** - Pattern for ECS Fargate services, VPC reference, task definitions
2. **`/Users/bryanmoran/code/for-the-greater-good/pantry-pirate-radio/infra/stacks/storage_stack.py`** - Pattern for cross-stack grants, environment-based removal policies
3. **`/Users/bryanmoran/code/for-the-greater-good/pantry-pirate-radio/infra/app.py`** - Stack composition, dependency ordering, environment configuration
4. **`/Users/bryanmoran/code/for-the-greater-good/pantry-pirate-radio/app/database/geo_utils.py`** - PostGIS requirements (GeoAlchemy2 functions needed)
5. **`/Users/bryanmoran/code/for-the-greater-good/pantry-pirate-radio/app/core/config.py`** - Environment variables needed by services

---

## Summary

This plan adds three new CDK stacks to complete the AWS migration:

1. **SecretsStack** - Centralized credentials management
2. **DatabaseStack** - Aurora Serverless v2 PostgreSQL with PostGIS
3. **ServicesStack** - Validator, Reconciler, Publisher ECS services

The implementation follows existing patterns from the codebase, uses SQS for all inter-service communication (no Redis), and provides cost-efficient scaling with Aurora Serverless v2 and Fargate.

Total new test coverage: ~60 tests across 3 new test files.
