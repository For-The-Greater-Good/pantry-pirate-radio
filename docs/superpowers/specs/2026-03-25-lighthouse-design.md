# Lighthouse: Self-Service Location Verification System

## Context

**Problem**: Food bank programs currently report data updates through a manual loop — a spreadsheet tracks "days since last update", Zapier runs daily, updates arrive via Slack/email, and staff manually update the spreadsheet then push data through. This doesn't scale to the 25-40k email addresses and 2-3k SMS-capable contacts PPR will have at full scale.

**Goal**: Replace the manual spreadsheet+Zapier+Slack loop with an automated, end-to-end self-service system where programs can confirm or update their data via tokenized links (no auth). The system auto-sends outreach (email → SMS escalation) when data goes stale, and programs respond with a single click to confirm or an optional form to edit.

**Constraints**:
- Lighthouse is its own plugin: `plugins/ppr-lighthouse/` — NO modifications to core PPR or ppr-helm
- Reads/writes PPR data exclusively via existing Tightbeam API
- No-auth for program-facing portal pages (JWT token in URL is the credential)
- Cognito for admin pages (shares Helm's Cognito User Pool — Lighthouse validates Helm's JWT tokens)
- AWS-native: SendGrid for email, Twilio for SMS (already have 10DLC A2P approved)
- Must comply with constitution (TDD, file size limits, observability, dual-env compatibility)
- Own Next.js app, own Amplify hosting, own CDK stacks, own compose overlay

---

## Architecture Overview

```
                    ┌─────────────────────────────────────┐
                    │     Lighthouse Admin (Cognito)        │
                    │  /admin/outreach — manage configs     │
                    │  /admin/outreach/dashboard — activity  │
                    └──────────┬──────────────────────────┘
                               │ CRUD
                               ▼
┌─────────────┐     ┌─────────────────────┐     ┌──────────────────┐
│ EventBridge │────▶│  Outreach Lambda     │────▶│ SendGrid (email) │
│ (M-F 10AM)  │     │  - Query stale orgs  │     │ Twilio (SMS)     │
└─────────────┘     │  - Generate JWT       │     └──────────────────┘
                    │  - Dispatch messages  │
                    │  - Log + metrics      │              │
                    └──────────┬───────────┘     email/SMS with
                               │                 tokenized link
                               ▼                       │
                    ┌─────────────────────┐            ▼
                    │  DynamoDB Tables     │  ┌─────────────────────┐
                    │  - OutreachConfig    │  │ Program clicks link  │
                    │  - OutreachContact   │  │ /portal/{jwt-token}  │
                    │  - OutreachLog       │  │                     │
                    └─────────────────────┘  │ [Confirm] or [Edit] │
                                             └──────────┬──────────┘
                                                        │
                                                        ▼
                                             ┌─────────────────────┐
                                             │ Tightbeam PUT API    │
                                             │ caller_context:      │
                                             │  source=self_service │
                                             └─────────────────────┘
```

---

## Federation-Aware Design Notes

Lighthouse solves the immediate problem (replace the manual spreadsheet+Zapier+Slack loop). But its architecture is remarkably close to what a federated food bank data network would require — inspired by Google's Open Product Recovery (OPR) and fediverse/ActivityPub patterns. The following design choices keep the door open for federation without adding scope to Lighthouse.

**Context**: OPR proved that federated surplus-goods coordination works when each org runs a node speaking a shared protocol. The fediverse proved that decentralized data networks scale when identity, discovery, and trust are standardized. PPR already has the shared protocol (HSDS), the trust layer (confidence scoring), and the write path (Tightbeam). Lighthouse adds org identity and self-service data management — the remaining prerequisites for federation.

### Design Choice 1: Durable Org Identity

Lighthouse generates ephemeral JWT tokens per outreach cycle. But the org's relationship with PPR is persistent. `OutreachConfig.org_api_key` (nullable, unused in Lighthouse) gives each enrolled org a stable identity that can evolve into a persistent portal login or a federation node credential.

### Design Choice 2: Portal-First Route Structure

Routes are named as a portal that starts with verification, not a verification flow that might become a portal:

```
/portal/[token]          <- token-gated entry (Lighthouse)
/portal/[org-slug]       <- future: persistent login (Federation)
  /portal/.../locations  <- view & manage locations
  /portal/.../history    <- audit trail
  /portal/.../feed       <- future: org's HSDS feed URL
```

The same LocationCard, EditForm, and ConfirmButton components serve both flows. Naming them generically (not "VerificationCard") keeps them reusable.

### Design Choice 3: Rich caller_context

The Tightbeam caller_context includes `source_type` and `actor_type` fields beyond what Lighthouse strictly needs. This means the audit trail already distinguishes *how* data arrived — verification-prompted vs proactive vs automated — enabling confidence scoring to adapt as new data sources appear.

### Design Choice 4: Node Registry Fields

`OutreachConfig` includes nullable `feed_url` and `push_enabled` fields. They cost nothing (empty DynamoDB attributes aren't stored) but prevent a schema migration when federation features land.

### Design Choice 5: Bidirectional Handler Structure

The Outreach Lambda is structured as "for each org, determine what action to take based on its state" rather than "send emails to stale orgs." This naturally extends to: "if org has feed_url, poll it; if org is stale, send outreach; if org has push_enabled, check incoming webhooks."

---

## Component Design

### 1. LighthouseStack (CDK) — `plugins/ppr-lighthouse/infra/lighthouse_stack.py`

New plugin with its own CDK stack, Next.js app, and Amplify hosting.

**Plugin structure**:
```
plugins/ppr-lighthouse/
  plugin.yml                    # Plugin manifest
  CLAUDE.md                     # Dev guide
  .docker/
    Dockerfile                  # Next.js build/runtime
    compose.yml                 # Docker Compose overlay (port 3002)
  infra/
    __init__.py
    lighthouse_stack.py         # CDK stack (DynamoDB, Lambdas, EventBridge, SNS, Amplify)
    outreach_lambda/            # Lambda code (see Section 3)
    tests/
  src/                          # Next.js app
    app/
      portal/                   # Public portal (no auth)
      (dashboard)/              # Admin pages (Cognito-protected)
      api/                      # API routes
    components/
    lib/
  tests/                        # Vitest tests
```

**Resources**:

| Resource | Type | Purpose |
|----------|------|---------|
| `OutreachConfig` | DynamoDB Table | Per-org config: enabled, last_confirmed_at. PK: `organization_id` |
| `OutreachContact` | DynamoDB Table | 1-N contacts per org. PK: `organization_id`, SK: `contact_id` |
| `OutreachLog` | DynamoDB Table | Outreach event history. PK: `organization_id`, SK: `timestamp`. TTL: 90 days |
| `OutreachLambda` | Lambda (Python 3.12, ARM64) | Dispatches email/SMS based on playbook + staleness rules |
| `DeliveryWebhookLambda` | Lambda (Python 3.12, ARM64) | Receives SendGrid/Twilio delivery webhooks, updates OutreachLog |
| `DeliveryPollerLambda` | Lambda (Python 3.12, ARM64) | Polls SendGrid/Twilio APIs for delivery status (fallback for missed webhooks) |
| `OutreachSchedule` | EventBridge Rule | Cron: M-F at 10 AM ET — triggers OutreachLambda |
| `DeliveryPollerSchedule` | EventBridge Rule | Every 30 min — triggers DeliveryPollerLambda |
| `WebhookApiGateway` | API Gateway HTTP API | Public endpoint for SendGrid/Twilio webhook POSTs → DeliveryWebhookLambda |
| `OutreachEventsTopic` | SNS Topic | Publishes confirmation/update/bounce/delivery events |
| `JwtSigningKey` | Secrets Manager Secret | 64-char random key for signing verification tokens |
| `SendGridApiKey` | Secrets Manager Secret | SendGrid API key for email dispatch |
| `SendGridWebhookKey` | Secrets Manager Secret | SendGrid webhook signing key for verification |
| `TwilioCredentials` | Secrets Manager Secret | Twilio Account SID + Auth Token + Message Service SID |
| CloudWatch Alarms | Alarms | Lambda errors/throttles, DynamoDB throttles/errors → centralized SNS alert topic |
| CloudWatch Dashboard | Dashboard widgets | Outreach volume, delivery rates, bounce rates, confirmation rates |

**Constitution XIV compliance**: All alarms route to `pantry-pirate-radio-alerts-{env}` by ARN convention (Plugin Exception).

**plugin.yml**:
```yaml
name: ppr-lighthouse
version: 0.1.0
description: Self-service location verification portal with automated outreach
env_vars:
  - name: PPR_API_URL
    required: true
    description: PPR Tightbeam API base URL
  - name: PPR_TIGHTBEAM_API_KEY
    required: true
    description: API key for Tightbeam write access
  - name: LIGHTHOUSE_JWT_SECRET
    required: false
    description: JWT signing key (Secrets Manager in AWS, .env locally)
docker:
  compose: .docker/compose.yml
cdk_stacks:
  - module: lighthouse_stack
    class: LighthouseStack
commands:
  - status
  - logs
```

### 2. DynamoDB Schema Detail

**OutreachConfig** (pay-per-request):
```
PK: organization_id (S)
Attributes:
  enabled: BOOL (default false)
  last_confirmed_at: S (ISO 8601)
  organization_name: S (denormalized for display)
  org_api_key: S (nullable — persistent org identity, generated on enrollment)
  feed_url: S (nullable — future: org's self-hosted HSDS feed endpoint)
  push_enabled: BOOL (default false — future: org pushes updates vs PPR pulls)
  created_at: S
  updated_at: S
```
Note: Escalation logic is driven by the playbook in code + OutreachLog history. No per-org escalation config needed. The Lambda calculates `days_stale` from `last_confirmed_at` and checks OutreachLog to see which playbook steps have already fired.

Note: `org_api_key`, `feed_url`, and `push_enabled` are nullable/defaulted and unused in Lighthouse. They exist to support the federation evolution path (see appendix) without requiring a schema migration later.

**OutreachContact** (pay-per-request):
```
PK: organization_id (S)
SK: contact_id (S) — ULID
Attributes:
  name: S
  email: S (nullable)
  phone: S (nullable, E.164 format)
  role: S (e.g., "Director", "Coordinator")
  preferred_channel: S (email|sms|both)
  seeded_from_ppr: BOOL
  created_at: S
  updated_at: S
```

**OutreachLog** (pay-per-request, TTL on `expires_at`):
```
PK: organization_id (S)
SK: timestamp (S) — ISO 8601
Attributes:
  action: S (sent|delivered|bounced|failed|opened|clicked|confirmed|updated)
  contact_id: S
  channel: S (email|sms|web)
  playbook_step: N (index into PLAYBOOK list, e.g., 0, 1, 2)
  provider_message_id: S (SendGrid message ID or Twilio SID — for webhook correlation)
  delivery_status: S (queued|sent|delivered|bounced|failed|opened|clicked)
  token_hash: S (first 8 chars of token for tracing)
  details: M (error codes, bounce reason, changed fields, etc.)
  expires_at: N (epoch, TTL — 90 days from creation)
GSI: provider_message_id-index (PK: provider_message_id) — for webhook lookups
```

### 3. Outreach Playbook & Channel Abstraction

The escalation sequence is defined in code as a **playbook** — a list of steps, each with a day offset and one or more channel actions. Message copy lives in template files on disk with `{{variable}}` substitution. Channels are pluggable — adding voice later means a new channel class + new template files + new playbook steps.

#### Directory structure

```
plugins/ppr-lighthouse/infra/outreach_lambda/
  handler.py              # Lambda entry point
  playbook.py             # Escalation sequence + channel registry
  channels/
    __init__.py
    base.py               # OutreachChannel protocol
    email.py              # SendGridChannel
    sms.py                # TwilioSMSChannel
    # voice.py            # Future: TwilioVoiceChannel
  templates/
    email/
      gentle_reminder.html
      second_notice.html
    sms/
      quick_check_in.txt
      urgent_update_needed.txt
    # voice/              # Future
  requirements.txt        # PyJWT, boto3, sendgrid, twilio
```

#### Playbook definition (`playbook.py`)

```python
# Channel registry — add new channels here
CHANNELS = {
    "email": "channels.email.SendGridChannel",
    "sms": "channels.sms.TwilioSMSChannel",
    # "voice": "channels.voice.TwilioVoiceChannel",
}

# Escalation sequence — edit this list to change outreach behavior
# Each step fires once when days_stale >= day (tracked via OutreachLog)
PLAYBOOK = [
    {
        "day": 14,
        "actions": [
            {"channel": "email", "template": "gentle_reminder"},
        ],
    },
    {
        "day": 21,
        "actions": [
            {"channel": "email", "template": "second_notice"},
            {"channel": "sms", "template": "quick_check_in"},
        ],
    },
    {
        "day": 30,
        "actions": [
            {"channel": "sms", "template": "urgent_update_needed"},
        ],
    },
]
```

#### Channel protocol (`channels/base.py`)

```python
from dataclasses import dataclass
from typing import Protocol

@dataclass
class SendResult:
    success: bool
    channel: str
    provider_id: str | None = None   # e.g., SendGrid message ID, Twilio SID
    error: str | None = None

class OutreachChannel(Protocol):
    """All channels implement this interface. Adding voice = new class + register in CHANNELS."""
    def send(self, contact: dict, rendered_content: str, subject: str | None = None) -> SendResult: ...
```

#### Template variables

Templates use `{{variable}}` syntax (simple string replacement, no logic):

| Variable | Source | Example |
|----------|--------|---------|
| `{{org_name}}` | OutreachConfig.organization_name | "Greater Springfield Food Bank" |
| `{{location_count}}` | Tightbeam search result count | "3" |
| `{{verify_url}}` | Generated JWT link | "https://helm.pantrypirate.radio/verify/eyJ..." |
| `{{locations_summary}}` | Formatted list from Tightbeam | "Main Pantry (123 Main St), Mobile North (456 Oak Ave)" |
| `{{days_stale}}` | Calculated | "21" |
| `{{contact_name}}` | OutreachContact.name | "Jane Smith" |

### 4. Outreach Lambda — `plugins/ppr-lighthouse/infra/outreach_lambda/handler.py`

Python 3.12 Lambda (bundled as zip with dependencies):

**Execution flow**:
1. Scan `OutreachConfig` for `enabled = true`
2. For each enabled org, calculate `days_stale` from `last_confirmed_at`
3. Query `OutreachLog` to determine which playbook steps have already fired for this staleness cycle
4. For each playbook step where `days_stale >= step.day` and step hasn't fired yet:
   - Generate JWT token for org (if not already generated this cycle)
   - Fetch contacts from `OutreachContact`
   - Render templates with variables (org data from Tightbeam, contact info, verify URL)
   - For each action in the step, dispatch via the appropriate channel
   - Write to `OutreachLog` for each send (includes `provider_message_id` for webhook correlation)
5. When a confirmation/update resets `last_confirmed_at`, the staleness counter resets and all steps become eligible to fire again in the next cycle
6. Publish CloudWatch custom metrics: `OutreachEmailsSent`, `OutreachSMSSent`, `StaleOrgsCount`, `PlaybookStepsFired`
7. Publish summary to SNS topic

### 5. Delivery Tracking (Webhooks + Polling)

Two mechanisms for tracking message delivery status — webhooks for real-time, polling as fallback.

#### Delivery Webhook Lambda

**Endpoint**: API Gateway HTTP API → `DeliveryWebhookLambda`
**URL**: `https://{api-id}.execute-api.{region}.amazonaws.com/webhooks/delivery`

Handles POST callbacks from:
- **SendGrid Event Webhook**: delivered, bounced, dropped, deferred, open, click
  - Verified via SendGrid's signed webhook verification (signing key in Secrets Manager)
- **Twilio Status Callback**: queued, sent, delivered, undelivered, failed
  - Verified via Twilio request signature validation

**Flow**:
1. Verify webhook signature (reject if invalid)
2. Extract `provider_message_id` from payload
3. Query `OutreachLog` GSI (`provider_message_id-index`) to find the log entry
4. Update log entry's `delivery_status` and `details` with provider event data
5. If bounce/fail: publish to SNS topic (for alerting)
6. Publish CloudWatch metrics: `DeliverySuccess`, `DeliveryBounce`, `DeliveryFail` by channel

#### Delivery Poller Lambda

**Schedule**: Every 30 minutes via EventBridge

**Flow**:
1. Query `OutreachLog` for recent entries (last 24h) where `delivery_status = 'sent'` (still pending)
2. For each, call the appropriate provider API to check status:
   - SendGrid: GET `/v3/messages/{message_id}`
   - Twilio: GET `/2010-04-01/Accounts/{sid}/Messages/{sid}.json`
3. Update `delivery_status` in OutreachLog
4. Catch any events missed by webhooks

This is the belt-and-suspenders fallback. Most updates arrive via webhook in seconds; the poller catches stragglers.

#### Delivery Status Lifecycle

```
sent → delivered    (happy path)
sent → bounced      (bad email/phone)
sent → failed       (provider error)
sent → deferred     (temporary, will retry — SendGrid only)
delivered → opened  (email opened — SendGrid only)
opened → clicked    (link clicked — SendGrid only)
```

**JWT Token structure**:
```json
{
  "org_id": "abc-123",
  "iat": 1711180800,
  "exp": 1714468800,
  "iss": "ppr-lighthouse"
}
```
- Signed with HS256 using Secrets Manager key
- Expiry: last playbook step day + 30 days (generous window)
- Stateless validation — no token table needed

**SendGrid integration**: SendGrid v3 Mail Send API. Email templates are HTML files loaded from `templates/email/`.

**Twilio integration**: Twilio Messaging Service SID (already 10DLC A2P approved). SMS templates are text files from `templates/sms/`.

### 4. Verification Portal (Next.js) — `plugins/ppr-lighthouse/src/app/portal/`

Public route (no Cognito auth). This is the page programs see when they click the link. Named "portal" rather than "verify" to support evolution toward persistent org dashboards (see Federation-Aware Design Notes and Appendix).

**Route**: `/portal/[token]`

**Flow**:
1. `page.tsx` — Server component, validates JWT via API route
2. API route `/api/portal/validate` — Validates JWT signature + expiry using secret from env var (Secrets Manager → Amplify env var)
3. API route `/api/portal/confirm` — Calls Tightbeam PUT with caller_context (see below)
4. API route `/api/portal/update` — Calls Tightbeam PUT with changed fields + same caller_context

**caller_context schema** (federation-aware):
```json
{
  "source": "self_service",
  "source_type": "verification",
  "org_id": "abc-123",
  "actor_type": "program_staff",
  "channel": "email_link",
  "token_hash": "a1b2c3d4"
}
```
The `source_type` and `actor_type` fields distinguish how data arrived. This enables confidence scoring to differentiate verification-prompted confirmations from proactive portal updates, and later from automated feed ingestion (`source_type: "feed_poll"`, `actor_type: "automated_node"`).

**Page layout**:
- Header: "Pantry Pirate Radio — Location Portal"
- Org name prominently displayed
- Card per location showing: name, address, phone, hours
- Each card has: [Confirm Correct] and [Edit Details] buttons
- Bottom: [Confirm ALL Locations] button
- Edit expands inline form pre-filled with current data
- Success state: "Thank you! Your data has been confirmed/updated."
- Expired/invalid token: "This verification link has expired. Contact us at [email]."

**Tightbeam integration**: Next.js API routes proxy to PPR's Tightbeam API using the existing pattern in `src/app/api/tightbeam/` — the API key is already available as `PPR_TIGHTBEAM_API_KEY` env var.

### 5. Lighthouse Admin Pages (Cognito-protected)

Lighthouse runs its own Next.js app with its own Cognito User Pool and Amplify hosting. Admin routes are Cognito-protected; portal routes are public (JWT-gated).

**a. Outreach Management** (`/admin/outreach`)
- Table of all organizations with columns: Name, Enabled (toggle), Last Confirmed, Days Stale, Current Playbook Step, Contacts
- Bulk enable/disable
- Filter by status (stale, confirmed, in-progress)
- Search by org name
- "Seed contacts from PPR" button (pulls org contacts via Tightbeam search)

**b. Outreach Org Detail** (`/admin/outreach/[org_id]`)
- Enable/disable toggle
- Contact management: add/edit/remove contacts, set preferred channel per contact
- "Import from PPR" button to seed contacts
- Outreach history timeline (from OutreachLog — shows every send, delivery status, confirm, update)
- Current playbook position indicator (which steps have fired, which are upcoming)
- Per-message delivery status: sent → delivered/bounced/failed with timestamps and provider details

**c. Outreach Dashboard** (`/admin/outreach/dashboard`)
- Summary cards: Total enabled orgs, Stale count, Emails sent (30d), SMS sent (30d), Confirmation rate
- **Delivery metrics**: Delivery rate, bounce rate, failure rate — by channel (email vs SMS)
- Recent activity feed (confirmations + updates + bounces)
- Stale programs list (sorted by days stale)
- Charts: confirmations over time, outreach volume, delivery rates over time
- Playbook overview: current step distribution across all orgs
- **Bounce/failure alerts**: Orgs with recent delivery failures highlighted for manual attention

**API routes**: New API routes in `src/app/api/outreach/` that CRUD DynamoDB tables. These use the AWS SDK (DynamoDB Document Client) — credentials come from Amplify's IAM role.

### 6. LighthouseStack CDK Resources (Amplify + Shared Cognito + Infra)

Lighthouse owns its own Amplify hosting and backend infra. It shares Helm's Cognito User Pool for admin auth (no duplicate user management).

**Shared Cognito** (from HelmStack via plugin_context):
- Lighthouse receives `cognito_user_pool_id` and `cognito_issuer` from plugin_context
- Admin routes validate Helm's Cognito JWTs — same users, same groups, same session
- No Cognito resources created in LighthouseStack

**Amplify Hosting**:
- Next.js SSR (WEB_COMPUTE platform)
- GitHub repo: `For-The-Greater-Good/ppr-lighthouse`
- Env vars at app level: PPR_API_URL, PPR_TIGHTBEAM_API_KEY, COGNITO_CLIENT_ID, COGNITO_ISSUER, LIGHTHOUSE_JWT_SECRET, DynamoDB table names
- Service role with IAM permissions for DynamoDB (all 3 tables) + Secrets Manager (JWT key)

**Lambda + DynamoDB + EventBridge + SNS + API Gateway**: All in the same stack (see Section 1 resource table).

### 7. Helm Integration

Helm embeds Lighthouse's admin pages so operators don't context-switch between apps.

**Helm-side changes** (small — adds a link/iframe in Helm's sidebar):
- New sidebar item: "Outreach" → links to Lighthouse admin URL
- Helm passes Cognito session/JWT to Lighthouse (same User Pool, so tokens are valid in both apps)
- Option A: Helm iframes Lighthouse admin pages directly
- Option B: Helm links out to Lighthouse admin (simpler, avoids iframe CSP issues)

**Lighthouse-side auth**:
- Admin routes validate Cognito JWTs using `jose` library (same pattern as Helm)
- Checks `cognito:groups` claim for `admin` or `editor`
- Public portal routes (`/portal/[token]`) bypass auth entirely — JWT token in URL is the credential

**plugin_context extension** (in `infra/app.py`):
```python
# After HelmStack is instantiated, add Cognito refs to plugin_context
_plugin_context["cognito"] = {
    "user_pool_id": helm_stack.user_pool.user_pool_id,
    "issuer": f"https://cognito-idp.{region}.amazonaws.com/{helm_stack.user_pool.user_pool_id}",
}
```
LighthouseStack reads these from plugin_context and passes them to Amplify as env vars.

**Note**: This is the only touch point between Helm and Lighthouse. Lighthouse doesn't import Helm code, doesn't share Amplify, doesn't share DynamoDB. It just trusts Helm's Cognito tokens.

### 8. Constitutional Compliance Requirements

These requirements must be satisfied during implementation:

1. **Principle VII (Privacy)**: Outreach contacts (email, phone) are organizational business contacts, not PII of vulnerable populations. All test data MUST use fictional contacts (`555-xxx-xxxx` phones, `example.com` emails, clearly fake names). Secrets in Secrets Manager, `.env` for local.

2. **Principle IX (File Size)**: No file may exceed 600 lines. Lambda code is already split across handler.py, playbook.py, channels/*.py, delivery_webhook.py, delivery_poller.py. LighthouseStack CDK must stay under 600 — split into sub-constructs if it grows.

3. **Principle X (Quality Gates)**: Lambda Python code must pass black, ruff, mypy, bandit. Plugin needs a `./bouy ppr-lighthouse test` command or integration into `./bouy test` to run quality checks on plugin Python code. Next.js code uses ESLint, Prettier, Vitest.

4. **Principle XII (Structured Logging)**: All Lambda code MUST use Python `structlog` (not `print()` or bare `logging`). Log entries must include structured context: org_id, operation, channel, playbook_step, provider_message_id where applicable.

5. **Principle XIV (Observability)**: CloudWatch alarms for all 3 Lambdas (errors + throttles), all 3 DynamoDB tables (throttles + system errors), API Gateway (4xx, 5xx). All alarms route to `pantry-pirate-radio-alerts-{env}` by ARN convention (Plugin Exception). Dashboard widgets for outreach volume, delivery rates, bounce rates, confirmation rates.

6. **Principle XV (Dual Environment)**: Portal works locally via Docker compose (port 3002). Outreach dispatch is AWS-only (documented, like Bedrock batch). JWT validated via `.env` locally, Secrets Manager on AWS. SendGrid/Twilio in dry-run mode locally.

### 7. Dual Environment Compatibility (Constitution XV)

| Component | AWS | Local Docker |
|-----------|-----|-------------|
| Portal + admin pages | Amplify hosting | Docker compose (port 3002) |
| Tightbeam API calls | Lambda API Gateway | Local FastAPI (port 8000) |
| JWT validation | Secrets Manager key | `.env` JWT_SIGNING_KEY |
| DynamoDB tables | Real DynamoDB | DynamoDB Local (or mock in tests) |
| Outreach Lambda | EventBridge → Lambda | Manual trigger via bouy command (future) |
| Delivery webhooks | API Gateway → Lambda | Not applicable locally (mocked in tests) |
| Delivery poller | EventBridge → Lambda | Not applicable locally (mocked in tests) |
| SendGrid/Twilio | Real APIs | Dry-run mode (log only, no actual send) |

**Local dev**: The verification page and admin pages work against local PPR. Outreach dispatch is AWS-only (like Bedrock batch). Tests mock DynamoDB and external APIs.

---

## Implementation Plan

### Phase 0: Repo + Plugin Scaffold
1. Create private repo `For-The-Greater-Good/ppr-lighthouse` on GitHub
2. Initialize repo with plugin directory structure (plugin.yml, .docker/, infra/, src/, tests/)
3. Add as git submodule to PPR: `git submodule add git@github.com:For-The-Greater-Good/ppr-lighthouse.git plugins/ppr-lighthouse`
4. Update PPR `.gitmodules` (same pattern as ppr-helm and ppr-tightbeam submodules)
5. Create `plugin.yml` manifest with env_vars, docker compose overlay, CDK stack declaration
6. Create `.docker/Dockerfile` (Next.js, based on ppr-helm's pattern)
7. Create `.docker/compose.yml` overlay (port 3002, depends on `app`)
8. Initialize Next.js project in `src/` (TypeScript, Tailwind, App Router — matching ppr-helm's stack)
9. Verify `./bouy up` discovers and starts the plugin service
10. Verify `git submodule update --init --recursive` pulls ppr-lighthouse correctly

### Phase 1: CDK Infrastructure (LighthouseStack)
1. Create `plugins/ppr-lighthouse/infra/lighthouse_stack.py`
2. Read Cognito config from plugin_context (shared with Helm — no Cognito creation)
3. Add DynamoDB tables (OutreachConfig, OutreachContact, OutreachLog + GSI for provider_message_id)
4. Add Secrets Manager secrets (JWT key, session secret, SendGrid API key, SendGrid webhook signing key, Twilio creds)
5. Add SNS topic (lighthouse-events)
6. Add API Gateway HTTP API for delivery webhooks
7. Add Amplify Hosting (Next.js SSR, env vars at app level including Cognito refs)
8. Add CloudWatch alarms + dashboard widgets (all 3 Lambdas + DynamoDB + API Gateway)
9. Add EventBridge rules (outreach dispatch daily, delivery poller every 30 min — both disabled initially)
10. Update `infra/app.py` to pass Cognito refs in plugin_context for Lighthouse
11. Write CDK tests in `plugins/ppr-lighthouse/infra/tests/test_lighthouse_stack.py`

### Phase 2: Playbook, Channels & Outreach Lambda
1. Create channel protocol (`channels/base.py` — `OutreachChannel` + `SendResult`)
2. Create `channels/email.py` — `SendGridChannel` implementation
3. Create `channels/sms.py` — `TwilioSMSChannel` implementation
4. Create `playbook.py` — channel registry + escalation step definitions
5. Create email templates (`templates/email/*.html`) with `{{variable}}` placeholders
6. Create SMS templates (`templates/sms/*.txt`) with `{{variable}}` placeholders
7. Create template renderer (load file, substitute `{{variables}}`)
8. Create `handler.py` — Lambda entry point with staleness query, playbook step resolution, dispatch loop
9. Implement JWT generation (PyJWT + Secrets Manager)
10. Implement CloudWatch metrics publishing
11. Implement SNS event publishing
12. Write tests for: channels (mocked SendGrid/Twilio), playbook step resolution, template rendering, handler orchestration
13. Add Lambda function + dependencies to LighthouseStack CDK

### Phase 3: Verification Portal (Public)
1. Create `plugins/ppr-lighthouse/src/app/portal/[token]/page.tsx`
2. Create API route `src/app/api/portal/validate/route.ts` (JWT validation)
3. Create API route `src/app/api/portal/confirm/route.ts` (confirm → Tightbeam PUT)
4. Create API route `src/app/api/portal/update/route.ts` (edit → Tightbeam PUT)
5. Create React components: LocationCard, ConfirmButton, EditForm
6. Handle token expiry/invalid states
7. Write Vitest tests for all components and API routes

### Phase 4: Delivery Tracking
1. Create `plugins/ppr-lighthouse/infra/outreach_lambda/delivery_webhook.py` — webhook handler
2. Implement SendGrid webhook signature verification
3. Implement Twilio request signature validation
4. Implement OutreachLog update logic (lookup by provider_message_id GSI → update delivery_status)
5. Create `plugins/ppr-lighthouse/infra/outreach_lambda/delivery_poller.py` — polling handler
6. Implement SendGrid message status polling
7. Implement Twilio message status polling
8. Publish CloudWatch metrics: DeliverySuccess, DeliveryBounce, DeliveryFail (by channel)
9. Publish bounce/failure events to SNS topic
10. Write tests for: webhook verification, status update logic, poller logic
11. Add both Lambdas + API Gateway to LighthouseStack CDK

### Phase 5: Lighthouse Admin Pages + Helm Integration
1. Create auth middleware (validate Helm's Cognito JWTs using `jose`, matching ppr-helm's auth pattern)
2. Create outreach API routes (`src/app/api/outreach/`) for DynamoDB CRUD
3. Create `/admin/outreach` — org list with enable/disable toggles
4. Create `/admin/outreach/[org_id]` — org config + contact management + delivery status per message
5. Create `/admin/outreach/dashboard` — activity + delivery metrics dashboard
6. Add DynamoDB Document Client integration
7. Add "Outreach" sidebar link in Helm → Lighthouse admin URL
8. Write Vitest tests for admin pages and API routes

### Phase 6: Integration & Polish
1. Enable EventBridge rules (outreach dispatch + delivery poller)
2. Configure SendGrid webhook URL → API Gateway endpoint
3. Configure Twilio status callback URL → API Gateway endpoint
4. End-to-end test: enable org → trigger Lambda → receive email → check delivery status → click link → confirm → verify in DynamoDB + Tightbeam audit
5. Create ppr-lighthouse CLAUDE.md with plugin commands and architecture
6. Update main project CLAUDE.md with ppr-lighthouse plugin reference

---

## Critical Files

### Existing (read/reference only — NO modifications to core PPR or ppr-helm)
- `plugins/ppr-helm/infra/helm_stack.py` — reference for CDK patterns (Cognito, Amplify, env vars, alarms)
- `plugins/ppr-helm/infra/tests/test_helm_stack.py` — reference for CDK test patterns
- `plugins/ppr-helm/src/app/api/tightbeam/` — reference for Tightbeam proxy pattern
- `plugins/ppr-helm/src/lib/api/` — reference for API client patterns
- `plugins/ppr-helm/src/lib/config.ts` — reference for env var validation pattern
- `infra/app.py` (lines 475-533) — plugin discovery/instantiation (auto-discovers ppr-lighthouse)

### New files to create

**Plugin scaffold**:
- `plugins/ppr-lighthouse/plugin.yml` — plugin manifest
- `plugins/ppr-lighthouse/CLAUDE.md` — dev guide
- `plugins/ppr-lighthouse/.docker/Dockerfile` — Next.js build/runtime
- `plugins/ppr-lighthouse/.docker/compose.yml` — Docker Compose overlay (port 3002)
- `plugins/ppr-lighthouse/src/` — Next.js app (App Router, TypeScript, Tailwind)
- `plugins/ppr-lighthouse/src/lib/auth/` — Cognito JWT validation (shares Helm's User Pool)
- `plugins/ppr-lighthouse/src/lib/config.ts` — env var validation

**CDK & Lambda infrastructure**:
- `plugins/ppr-lighthouse/infra/lighthouse_stack.py` — CDK stack
- `plugins/ppr-lighthouse/infra/outreach_lambda/handler.py` — Lambda entry point
- `plugins/ppr-lighthouse/infra/outreach_lambda/playbook.py` — Channel registry + escalation steps
- `plugins/ppr-lighthouse/infra/outreach_lambda/channels/__init__.py`
- `plugins/ppr-lighthouse/infra/outreach_lambda/channels/base.py` — OutreachChannel protocol + SendResult
- `plugins/ppr-lighthouse/infra/outreach_lambda/channels/email.py` — SendGridChannel
- `plugins/ppr-lighthouse/infra/outreach_lambda/channels/sms.py` — TwilioSMSChannel
- `plugins/ppr-lighthouse/infra/outreach_lambda/templates/email/gentle_reminder.html`
- `plugins/ppr-lighthouse/infra/outreach_lambda/templates/email/second_notice.html`
- `plugins/ppr-lighthouse/infra/outreach_lambda/templates/sms/quick_check_in.txt`
- `plugins/ppr-lighthouse/infra/outreach_lambda/templates/sms/urgent_update_needed.txt`
- `plugins/ppr-lighthouse/infra/outreach_lambda/delivery_webhook.py` — Webhook handler (SendGrid + Twilio callbacks)
- `plugins/ppr-lighthouse/infra/outreach_lambda/delivery_poller.py` — Polling handler (fallback status checks)
- `plugins/ppr-lighthouse/infra/outreach_lambda/requirements.txt` — PyJWT, boto3, sendgrid, twilio
- `plugins/ppr-lighthouse/infra/tests/test_lighthouse_stack.py` — CDK tests
- `plugins/ppr-lighthouse/infra/tests/test_outreach_lambda/` — Lambda unit tests (handler, webhook, poller, channels, playbook)

**Next.js verification portal (public)**:
- `plugins/ppr-lighthouse/src/app/portal/[token]/page.tsx` — public portal page (token-gated)
- `plugins/ppr-lighthouse/src/app/api/portal/validate/route.ts` — JWT validation
- `plugins/ppr-lighthouse/src/app/api/portal/confirm/route.ts` — confirm → Tightbeam PUT
- `plugins/ppr-lighthouse/src/app/api/portal/update/route.ts` — edit → Tightbeam PUT
- `plugins/ppr-lighthouse/src/components/portal/` — LocationCard, ConfirmButton, EditForm

**Next.js admin pages (Cognito-protected)**:
- `plugins/ppr-lighthouse/src/app/api/outreach/` — admin CRUD routes for DynamoDB
- `plugins/ppr-lighthouse/src/app/(dashboard)/outreach/` — admin pages (list, detail, dashboard)
- `plugins/ppr-lighthouse/src/components/outreach/` — admin outreach components

---

## Verification

### CDK Tests
```bash
cd plugins/ppr-lighthouse && python -m pytest infra/tests/test_lighthouse_stack.py -v
```
Verify: DynamoDB tables, Lambdas, EventBridge rules, SNS topic, API Gateway, Cognito, Amplify, CloudWatch alarms all present in synthesized template.

### Next.js Tests
```bash
cd plugins/ppr-lighthouse && npm test
```
Verify: Portal page renders, JWT validation works, confirm/edit flows work, admin CRUD works.

### Integration Test (Manual)
1. Deploy LighthouseStack: `./bouy deploy dev --infra-only --stack LighthouseStack-dev`
2. Enable outreach for a test org via Lighthouse admin
3. Manually invoke Lambda: `aws lambda invoke --function-name ppr-lighthouse-outreach-dev ...`
4. Check email received with tokenized link
5. Click link → portal page loads with correct org data
6. Click "Confirm" → verify Tightbeam audit trail shows `source: self_service, source_type: verification`
7. Check DynamoDB OutreachLog has confirmation entry
8. Check delivery status updates via webhook
9. Check CloudWatch metrics published

### Local Dev Test
1. `./bouy up` — start services (includes ppr-lighthouse via compose overlay)
2. Navigate to `http://localhost:3002/portal/[test-jwt]`
3. Portal page loads with local PPR data
4. Confirm/edit flows work against local Tightbeam API

---

## Appendix: Federation Evolution Path

*This section is aspirational. None of it is in scope for Lighthouse. It documents the trajectory that informed the federation-aware design choices above, so future contributors understand why certain schema fields exist and where this could go.*

**Inspiration**: Google's Open Product Recovery (OPR) — a federated protocol where each org runs a node, publishes surplus goods availability, and other nodes discover and consume feeds. The fediverse/ActivityPub — decentralized data networks where identity, discovery, and a shared protocol enable independent nodes to interoperate. PPR already has the shared protocol (HSDS), the trust layer (confidence scoring), and the write path (Tightbeam).

### Stage 0: Lighthouse (This Plan)
- PPR sends outreach when data is stale
- Orgs click links, confirm/edit via portal, done
- All initiated by PPR
- **What it builds**: Org identity, self-service data correction, contact registry, freshness tracking

### Stage 1: Persistent Portal
**Trigger**: Orgs ask "can I just update this whenever, not wait for your email?"

- Convert token-gated `/portal/[token]` to persistent `/portal/[org-slug]` with API key auth (using `org_api_key` from OutreachConfig)
- Food bank bookmarks their portal URL, updates data proactively
- Outreach emails still fire for stale data, but link goes to the same persistent portal
- `last_confirmed_at` updates on every portal visit, not just email-prompted ones
- Confidence scoring adjustment: proactive portal updates score higher than email-prompted confirmations (`source_type: "proactive"` vs `"verification"`)

*Mostly free if Lighthouse routes are designed right — it's a login page + session, not a new system.*

### Stage 2: Push Notifications (Org to PPR)
**Trigger**: Some orgs update frequently and want PPR to know immediately

- Portal updates already go through Tightbeam — add an SNS "org updated" event
- The Outreach Lambda's bidirectional handler checks for incoming updates, not just outgoing outreach
- OutreachLog tracks both directions: PPR-to-org outreach AND org-to-PPR updates
- Staleness model evolves: "days since last update from any source" instead of "days since last confirmation"

*OPR's pattern: orgs are now actively publishing, not just responding to prompts.*

### Stage 3: HSDS Feed Endpoints
**Trigger**: A regional network says "we maintain our data in [system X], can we just give you a feed?"

- Orgs with `feed_url` populated get polled by the Outreach Lambda (bidirectional handler)
- Feed format: HSDS JSON (the schema PPR uses everywhere)
- Lambda fetches feed, diffs against current data, ingests changes via Tightbeam
- `caller_context: {source: "self_service", source_type: "feed_poll", actor_type: "automated_node"}`
- Confidence scoring: feed-sourced data gets 85-95 (self-published, automated, but not human-verified each time)
- PPR stops scraping orgs that publish their own feed — scrapers become the fallback

*The big unlock. PPR shifts from "scraper of everything" to "aggregator that prefers authoritative sources."*

### Stage 4: Discovery and Multi-Aggregator
**Trigger**: Another project wants to consume the same feeds

- PPR publishes `/.well-known/hsds-directory.json` — lists participating orgs and their feed URLs
- Other aggregators discover and subscribe to the same feeds
- PPR becomes one node in a network, not the sole aggregator
- HSDS is the ActivityPub equivalent — the shared protocol everyone speaks

### Stage 5: Full Federation
**Trigger**: Critical mass of orgs publishing HSDS feeds

- Orgs discover each other, not just through PPR
- Surplus/availability signals flow between nodes (OPR pattern for real-time capacity)
- PPR's role shifts from "scraper + aggregator" to "aggregator + trust authority" — confidence scoring becomes a reputation system
- HAARRRvest becomes a federation-wide public index, not just PPR's output

### What Makes This Realistic

The key insight is that each stage only activates when there's organic demand, and each stage builds on the infrastructure of the previous one:

| Stage | Prerequisite | New Infrastructure |
|-------|-------------|-------------------|
| 0 (Lighthouse) | Manual spreadsheet pain | LighthouseStack, portal, playbook |
| 1 (Persistent Portal) | Orgs wanting proactive access | Login page + API key auth |
| 2 (Push) | Frequent updaters | SNS event + bidirectional handler |
| 3 (HSDS Feeds) | Orgs with existing data systems | Feed poller in Lambda |
| 4 (Discovery) | External aggregator interest | `.well-known` endpoint |
| 5 (Federation) | Critical mass of publishers | Protocol spec + governance |

Lighthouse creates the demand for Stage 1 by making self-service data management easy. Stage 1 creates demand for Stage 2 by making proactive updates normal. And so on. The federation doesn't need to be planned — it emerges from making each step useful on its own.
