# Helm Enhancement Phase 2: Typeform Report Queue

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Typeform report intake system: standalone Lambda receives webhook, writes to DynamoDB, Helm UI displays a queue for editors to review and resolve reports.

**Architecture:** Typeform webhook → API Gateway → Lambda → DynamoDB. Helm BFF reads DynamoDB via server-side client. Mock mode for local dev (no AWS needed).

**Tech Stack:** CDK (Python), Lambda (Python), Next.js 15, TypeScript, DynamoDB, Vitest

**Prerequisite:** Phase 1 complete (types, permissions, i18n entries already exist)

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `infra/helm_constructs.py` | HelmReports + HelmWebhook CDK constructs |
| Modify | `infra/helm_stack.py` | Orchestrate constructs, add secrets, alarms, outputs |
| Modify | `infra/tests/test_helm_stack.py` | Tests for DynamoDB, Lambda, alarms |
| Create | `lambda/typeform_webhook/handler.py` | HMAC validation, parse payload, write DynamoDB |
| Create | `lambda/typeform_webhook/requirements.txt` | boto3 (bundled in Lambda runtime) |
| Create | `src/lib/api/reports-client.ts` | Server-side DynamoDB client with mock mode |
| Create | `src/lib/mocks/reports.ts` | Mock report data fixtures |
| Create | `src/app/api/reports/route.ts` | GET list reports |
| Create | `src/app/api/reports/[id]/route.ts` | GET detail, PUT update status |
| Create | `src/hooks/use-reports.ts` | TanStack Query CRUD hook |
| Create | `src/components/reports/report-queue-table.tsx` | Paginated reports table |
| Create | `src/components/reports/report-status-badge.tsx` | Status badge (CVA) |
| Create | `src/components/reports/report-actions.tsx` | Resolve/dismiss buttons |
| Create | `src/components/reports/report-filters.tsx` | Status filter |
| Create | `src/app/(dashboard)/reports/page.tsx` | Queue page |
| Create | `src/app/(dashboard)/reports/[id]/page.tsx` | Detail page |
| Create | `src/app/(dashboard)/reports/[id]/loading.tsx` | Loading skeleton |
| Create | `src/app/(dashboard)/reports/[id]/error.tsx` | Error boundary |
| Create | `src/app/(dashboard)/reports/loading.tsx` | Queue loading skeleton |
| Create tests for all new components, hooks, routes, CDK, and Lambda |

---

### Task 1: CDK — DynamoDB Reports Table + Typeform Secret

**Files:**
- Create: `plugins/ppr-helm/infra/helm_constructs.py`
- Modify: `plugins/ppr-helm/infra/helm_stack.py`

- [ ] **Step 1: Create `helm_constructs.py` with HelmReports construct**

```python
"""Reusable CDK constructs for ppr-helm plugin."""

from __future__ import annotations

from aws_cdk import (
    Duration,
    RemovalPolicy,
    aws_dynamodb as dynamodb,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cw_actions,
    aws_sns as sns,
)
from constructs import Construct


class HelmReports(Construct):
    """DynamoDB table for Typeform report queue."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        environment_name: str,
        alarm_topic: sns.ITopic,
    ) -> None:
        super().__init__(scope, construct_id)

        self.table = dynamodb.Table(
            self,
            "ReportsTable",
            table_name=f"ppr-helm-reports-{environment_name}",
            partition_key=dynamodb.Attribute(
                name="typeform_response_id",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=(
                RemovalPolicy.DESTROY
                if environment_name == "dev"
                else RemovalPolicy.RETAIN
            ),
            time_to_live_attribute="resolved_ttl",
            point_in_time_recovery=True,
        )

        self.table.add_global_secondary_index(
            index_name="status-created-index",
            partition_key=dynamodb.Attribute(
                name="status",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="created_at",
                type=dynamodb.AttributeType.STRING,
            ),
        )

        # CloudWatch alarms (Principle XIV)
        cloudwatch.Alarm(
            self,
            "ThrottledRequests",
            alarm_name=f"ppr-helm-reports-throttled-{environment_name}",
            alarm_description="DynamoDB reports table throttled requests",
            metric=self.table.metric_throttled_requests_for_table(),
            threshold=1,
            evaluation_periods=1,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        ).add_alarm_action(cw_actions.SnsAction(alarm_topic))

        cloudwatch.Alarm(
            self,
            "SystemErrors",
            alarm_name=f"ppr-helm-reports-errors-{environment_name}",
            alarm_description="DynamoDB reports table system errors",
            metric=self.table.metric_system_errors_for_operations(),
            threshold=1,
            evaluation_periods=1,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        ).add_alarm_action(cw_actions.SnsAction(alarm_topic))
```

- [ ] **Step 2: Add Typeform secret + reports construct to helm_stack.py**

In `helm_stack.py`, import from helm_constructs:
```python
from helm_constructs import HelmReports
```

Add after the CloudWatch alarm section (before Outputs), using the existing `alarm_topic`:

```python
        # --- Reports Queue (DynamoDB) ---
        self.reports = HelmReports(
            self, "Reports",
            environment_name=environment_name,
            alarm_topic=alarm_topic,
        )

        # --- Typeform Signing Secret ---
        self.typeform_secret = secretsmanager.Secret(
            self,
            "TypeformSigningSecret",
            secret_name=f"ppr-helm/typeform-signing-{environment_name}",
            description="Typeform webhook signing secret for report intake",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                exclude_punctuation=True,
                password_length=64,
            ),
            removal_policy=(
                RemovalPolicy.DESTROY
                if environment_name == "dev"
                else RemovalPolicy.RETAIN
            ),
        )
```

Add new outputs:
```python
        CfnOutput(self, "ReportsTableName",
                  value=self.reports.table.table_name)
        CfnOutput(self, "TypeformSecretArn",
                  value=self.typeform_secret.secret_arn)
```

- [ ] **Step 3: Run CDK tests**

Run: `cd plugins/ppr-helm && python -m pytest infra/tests/ -v`

- [ ] **Step 4: Commit**

```
feat(helm): add DynamoDB reports table and Typeform signing secret
```

---

### Task 2: CDK Tests for New Resources

**Files:**
- Modify: `plugins/ppr-helm/infra/tests/test_helm_stack.py`

- [ ] **Step 1: Add test classes**

```python
class TestReportsTable:
    def test_reports_table_created(self, template: Template) -> None:
        template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {"TableName": "ppr-helm-reports-test"},
        )

    def test_reports_table_has_gsi(self, template: Template) -> None:
        from aws_cdk.assertions import Match
        template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {
                "GlobalSecondaryIndexes": Match.array_with([
                    Match.object_like({
                        "IndexName": "status-created-index",
                    }),
                ]),
            },
        )

    def test_reports_table_on_demand(self, template: Template) -> None:
        template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {"BillingMode": "PAY_PER_REQUEST"},
        )

    def test_reports_table_has_ttl(self, template: Template) -> None:
        template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {
                "TimeToLiveSpecification": {
                    "AttributeName": "resolved_ttl",
                    "Enabled": True,
                },
            },
        )

    def test_reports_table_has_pitr(self, template: Template) -> None:
        template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {
                "PointInTimeRecoverySpecification": {
                    "PointInTimeRecoveryEnabled": True,
                },
            },
        )


class TestTypeformSecret:
    def test_typeform_secret_created(self, template: Template) -> None:
        template.resource_count_is("AWS::SecretsManager::Secret", 2)

    def test_typeform_secret_name(self, template: Template) -> None:
        template.has_resource_properties(
            "AWS::SecretsManager::Secret",
            {"Name": "ppr-helm/typeform-signing-test"},
        )


class TestReportsAlarms:
    def test_reports_alarms_created(self, template: Template) -> None:
        # 1 auth alarm + 2 reports alarms = 3 total
        template.resource_count_is("AWS::CloudWatch::Alarm", 3)
```

- [ ] **Step 2: Update existing TestSecrets count**

Change `TestSecrets.test_session_secret_created` from `resource_count_is(..., 1)` to `resource_count_is(..., 2)`.

- [ ] **Step 3: Update TestAlarms count**

Change `TestAlarms.test_auth_alarm_created` from `resource_count_is(..., 1)` to `resource_count_is(..., 3)`.

- [ ] **Step 4: Run tests**

Run: `cd plugins/ppr-helm && python -m pytest infra/tests/ -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```
test(helm): add CDK tests for reports table and typeform secret
```

---

### Task 3: Mock Report Data + Server Client

**Files:**
- Create: `plugins/ppr-helm/src/lib/mocks/reports.ts`
- Create: `plugins/ppr-helm/src/lib/api/reports-client.ts`

- [ ] **Step 1: Create mock data**

Create `src/lib/mocks/reports.ts`:
```typescript
import type { Report } from '@/lib/api/types';

export const MOCK_REPORTS: Report[] = [
  {
    typeform_response_id: 'tf-001',
    organization_id: '25344',
    issue_types: ['other'],
    additional_info: 'Staff behavior was unacceptable',
    reporter_email: 'reporter1@example.com',
    follow_up_consent: true,
    status: 'new',
    assigned_to: null,
    created_at: '2026-03-23T10:00:00Z',
    resolved_at: null,
    resolved_by: null,
  },
  {
    typeform_response_id: 'tf-002',
    organization_id: '25831',
    issue_types: ['location_incorrect'],
    additional_info: null,
    reporter_email: 'reporter2@example.com',
    follow_up_consent: false,
    status: 'new',
    assigned_to: null,
    created_at: '2026-03-23T11:00:00Z',
    resolved_at: null,
    resolved_by: null,
  },
  {
    typeform_response_id: 'tf-003',
    organization_id: '25802',
    issue_types: ['services_wrong'],
    additional_info: 'Not much information listed',
    reporter_email: 'reporter3@example.com',
    follow_up_consent: true,
    status: 'resolved',
    assigned_to: 'admin@example.com',
    created_at: '2026-03-22T09:00:00Z',
    resolved_at: '2026-03-22T15:00:00Z',
    resolved_by: 'admin@example.com',
  },
];
```

- [ ] **Step 2: Create reports-client.ts**

Create `src/lib/api/reports-client.ts`:
```typescript
import 'server-only';

import type {
  Report,
  ReportsListResponse,
  ReportStatus,
  ReportUpdateRequest,
} from '@/lib/api/types';

const TABLE_NAME = process.env.REPORTS_DYNAMODB_TABLE || '';

function isMockMode(): boolean {
  return !TABLE_NAME;
}

// In-memory store for mock mode
let mockReports: Report[] | null = null;

async function getMockReports(): Promise<Report[]> {
  if (!mockReports) {
    const { MOCK_REPORTS } = await import('@/lib/mocks/reports');
    mockReports = [...MOCK_REPORTS];
  }
  return mockReports;
}

export async function listReports(filters?: {
  status?: ReportStatus;
  limit?: number;
  cursor?: string;
}): Promise<ReportsListResponse> {
  if (isMockMode()) {
    let reports = await getMockReports();
    if (filters?.status) {
      reports = reports.filter((r) => r.status === filters.status);
    }
    return { reports, total: reports.length };
  }

  const { DynamoDBClient } = await import('@aws-sdk/client-dynamodb');
  const { DynamoDBDocumentClient, QueryCommand, ScanCommand } = await import(
    '@aws-sdk/lib-dynamodb'
  );
  const client = DynamoDBDocumentClient.from(new DynamoDBClient({}));

  if (filters?.status) {
    const result = await client.send(
      new QueryCommand({
        TableName: TABLE_NAME,
        IndexName: 'status-created-index',
        KeyConditionExpression: '#s = :status',
        ExpressionAttributeNames: { '#s': 'status' },
        ExpressionAttributeValues: { ':status': filters.status },
        ScanIndexForward: false,
        Limit: filters.limit ?? 50,
      })
    );
    return {
      reports: (result.Items ?? []) as Report[],
      total: result.Count ?? 0,
    };
  }

  const result = await client.send(
    new ScanCommand({
      TableName: TABLE_NAME,
      Limit: filters?.limit ?? 50,
    })
  );
  return {
    reports: (result.Items ?? []) as Report[],
    total: result.Count ?? 0,
  };
}

export async function getReport(id: string): Promise<Report | null> {
  if (isMockMode()) {
    const reports = await getMockReports();
    return reports.find((r) => r.typeform_response_id === id) ?? null;
  }

  const { DynamoDBClient } = await import('@aws-sdk/client-dynamodb');
  const { DynamoDBDocumentClient, GetCommand } = await import(
    '@aws-sdk/lib-dynamodb'
  );
  const client = DynamoDBDocumentClient.from(new DynamoDBClient({}));

  const result = await client.send(
    new GetCommand({
      TableName: TABLE_NAME,
      Key: { typeform_response_id: id },
    })
  );
  return (result.Item as Report) ?? null;
}

export async function updateReport(
  id: string,
  update: ReportUpdateRequest,
  resolvedBy?: string
): Promise<Report | null> {
  if (isMockMode()) {
    const reports = await getMockReports();
    const idx = reports.findIndex((r) => r.typeform_response_id === id);
    if (idx === -1) return null;
    reports[idx] = {
      ...reports[idx],
      status: update.status,
      assigned_to: update.assigned_to ?? reports[idx].assigned_to,
      resolved_at:
        update.status === 'resolved' || update.status === 'dismissed'
          ? new Date().toISOString()
          : reports[idx].resolved_at,
      resolved_by:
        update.status === 'resolved' || update.status === 'dismissed'
          ? (resolvedBy ?? null)
          : reports[idx].resolved_by,
    };
    return reports[idx];
  }

  const { DynamoDBClient } = await import('@aws-sdk/client-dynamodb');
  const { DynamoDBDocumentClient, UpdateCommand } = await import(
    '@aws-sdk/lib-dynamodb'
  );
  const client = DynamoDBDocumentClient.from(new DynamoDBClient({}));

  const now = new Date().toISOString();
  const isResolved =
    update.status === 'resolved' || update.status === 'dismissed';

  const result = await client.send(
    new UpdateCommand({
      TableName: TABLE_NAME,
      Key: { typeform_response_id: id },
      UpdateExpression:
        'SET #s = :status, assigned_to = :assigned' +
        (isResolved ? ', resolved_at = :now, resolved_by = :by' : ''),
      ExpressionAttributeNames: { '#s': 'status' },
      ExpressionAttributeValues: {
        ':status': update.status,
        ':assigned': update.assigned_to ?? null,
        ...(isResolved ? { ':now': now, ':by': resolvedBy ?? null } : {}),
      },
      ReturnValues: 'ALL_NEW',
    })
  );
  return (result.Attributes as Report) ?? null;
}
```

- [ ] **Step 3: Commit**

```
feat(helm): add reports mock data and DynamoDB server client
```

---

### Task 4: Reports BFF API Routes

**Files:**
- Create: `plugins/ppr-helm/src/app/api/reports/route.ts`
- Create: `plugins/ppr-helm/src/app/api/reports/[id]/route.ts`

- [ ] **Step 1: Create list route** at `src/app/api/reports/route.ts`:

```typescript
import { NextRequest, NextResponse } from 'next/server';
import { requirePermission, AuthError } from '@/lib/auth/middleware';
import { listReports } from '@/lib/api/reports-client';
import type { ReportStatus } from '@/lib/api/types';

export async function GET(request: NextRequest) {
  try {
    await requirePermission('viewReports');

    const url = request.nextUrl;
    const status = url.searchParams.get('status') as ReportStatus | null;
    const limit = url.searchParams.get('limit')
      ? Number(url.searchParams.get('limit'))
      : undefined;

    const data = await listReports({
      status: status ?? undefined,
      limit,
    });
    return NextResponse.json(data);
  } catch (error) {
    if (error instanceof AuthError) {
      return NextResponse.json({ error: error.message }, { status: error.status });
    }
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
```

- [ ] **Step 2: Create detail + update route** at `src/app/api/reports/[id]/route.ts`:

```typescript
import { NextRequest, NextResponse } from 'next/server';
import { requirePermission, AuthError } from '@/lib/auth/middleware';
import { getReport, updateReport } from '@/lib/api/reports-client';
import { auth } from '@/lib/auth/session';

interface RouteParams {
  params: Promise<{ id: string }>;
}

export async function GET(_request: NextRequest, { params }: RouteParams) {
  try {
    await requirePermission('viewReports');
    const { id } = await params;
    const report = await getReport(id);
    if (!report) {
      return NextResponse.json({ error: 'Report not found' }, { status: 404 });
    }
    return NextResponse.json(report);
  } catch (error) {
    if (error instanceof AuthError) {
      return NextResponse.json({ error: error.message }, { status: error.status });
    }
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}

export async function PUT(request: NextRequest, { params }: RouteParams) {
  try {
    await requirePermission('resolveReports');
    const { id } = await params;
    const body = await request.json();
    const session = await auth();
    const resolvedBy = session?.user?.email ?? null;

    const updated = await updateReport(id, body, resolvedBy);
    if (!updated) {
      return NextResponse.json({ error: 'Report not found' }, { status: 404 });
    }
    return NextResponse.json(updated);
  } catch (error) {
    if (error instanceof AuthError) {
      return NextResponse.json({ error: error.message }, { status: error.status });
    }
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
```

- [ ] **Step 3: Commit**

```
feat(helm): add reports BFF API routes
```

---

### Task 5: Reports Hook

**Files:**
- Create: `plugins/ppr-helm/src/hooks/use-reports.ts`
- Create: `plugins/ppr-helm/tests/hooks/use-reports.test.ts`

- [ ] **Step 1: Write tests**

- [ ] **Step 2: Implement hook** following `use-users.ts` pattern:
  - `useQuery` for report list with status filter
  - `useMutation` for status updates with `invalidateQueries`
  - URL-based filters via search params

- [ ] **Step 3: Run tests**

- [ ] **Step 4: Commit**

```
feat(helm): add use-reports hook with TanStack Query
```

---

### Task 6: Report Queue UI Components

**Files:**
- Create: `plugins/ppr-helm/src/components/reports/report-status-badge.tsx`
- Create: `plugins/ppr-helm/src/components/reports/report-queue-table.tsx`
- Create: `plugins/ppr-helm/src/components/reports/report-actions.tsx`
- Create: `plugins/ppr-helm/src/components/reports/report-filters.tsx`
- Create tests for each

- [ ] **Step 1: Create report-status-badge.tsx** (follows confidence-badge.tsx pattern)
- [ ] **Step 2: Create report-queue-table.tsx** (follows results-table.tsx pattern)
- [ ] **Step 3: Create report-actions.tsx** (resolve/dismiss buttons)
- [ ] **Step 4: Create report-filters.tsx** (status dropdown)
- [ ] **Step 5: Write tests for all components**
- [ ] **Step 6: Commit**

```
feat(helm): add report queue UI components
```

---

### Task 7: Report Queue Pages

**Files:**
- Create: `plugins/ppr-helm/src/app/(dashboard)/reports/page.tsx`
- Create: `plugins/ppr-helm/src/app/(dashboard)/reports/loading.tsx`
- Create: `plugins/ppr-helm/src/app/(dashboard)/reports/[id]/page.tsx`
- Create: `plugins/ppr-helm/src/app/(dashboard)/reports/[id]/loading.tsx`
- Create: `plugins/ppr-helm/src/app/(dashboard)/reports/[id]/error.tsx`

- [ ] **Step 1: Create queue page** — lists reports with filters
- [ ] **Step 2: Create detail page** — shows report + linked location side-by-side
- [ ] **Step 3: Create loading/error skeletons**
- [ ] **Step 4: Commit**

```
feat(helm): add report queue and detail pages
```

---

### Task 8: Typeform Lambda

**Files:**
- Create: `plugins/ppr-helm/lambda/typeform_webhook/handler.py`
- Create: `plugins/ppr-helm/lambda/typeform_webhook/requirements.txt`

- [ ] **Step 1: Implement Lambda handler**
  - Validates HMAC-SHA256 from `x-typeform-signature` header
  - Parses Typeform webhook payload
  - Extracts: organization_id, issue_types, additional_info, reporter_email, follow_up_consent
  - Writes to DynamoDB with status=new
  - Returns 200 within 5s

- [ ] **Step 2: Write unit tests** (pure Python, mock boto3)

- [ ] **Step 3: Commit**

```
feat(helm): add Typeform webhook Lambda handler
```

---

### Task 9: Final Verification

- [ ] **Step 1: Run full Vitest suite** — `cd plugins/ppr-helm && npx vitest run`
- [ ] **Step 2: Run typecheck** — `npx tsc --noEmit`
- [ ] **Step 3: Run lint on changed files**
- [ ] **Step 4: Run CDK tests** — `python -m pytest infra/tests/ -v`
- [ ] **Step 5: Build** — `npm run build`
