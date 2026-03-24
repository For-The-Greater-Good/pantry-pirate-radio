# Helm Enhancement Phase 3: ALS Address Autocomplete

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Amazon Location Services address autocomplete to the edit form, with Cognito Identity Pool for browser-side map tile auth, and CDK infrastructure for all new AWS resources.

**Architecture:** BFF proxy for ALS autocomplete suggestions. Cognito Identity Pool for browser-side map tiles (Phase 4). CDK provisions Identity Pool, Map resource, IAM policies. Mock mode for local dev.

**Tech Stack:** CDK (Python), Next.js 15, TypeScript, @aws-sdk/client-location, MapLibre GL JS (Phase 4)

**Prerequisite:** Phase 1+2 complete.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `infra/helm_constructs.py` | Add HelmAuth (Identity Pool), HelmMap constructs |
| Modify | `infra/helm_stack.py` | Wire new constructs, IAM, env vars, outputs |
| Modify | `infra/tests/test_helm_stack.py` | Tests for Identity Pool, Map, IAM |
| Modify | `infra/../../infra/app.py` | Add place_index to plugin_context |
| Create | `src/lib/api/als-client.ts` | Server-side ALS client with mock mode |
| Create | `src/lib/mocks/als-suggestions.ts` | Mock ALS data |
| Create | `src/app/api/als/suggestions/route.ts` | BFF proxy for ALS suggestions |
| Create | `src/app/api/als/credentials/route.ts` | Temp Cognito Identity Pool creds |
| Create | `src/hooks/use-address-autocomplete.ts` | Debounced ALS search + resolve |
| Create | `src/components/locations/address-autocomplete.tsx` | Autocomplete dropdown UI |
| Modify | `src/components/locations/edit-form-ptf-fields.tsx` | Integrate autocomplete |
| Create tests for all new files |

---

### Task 1: CDK — Identity Pool + Map Resource

Add Cognito Identity Pool and ALS Map resource constructs to `helm_constructs.py`, wire them in `helm_stack.py`, and update `infra/app.py` to pass place_index references via plugin_context.

**Files:**
- Modify: `plugins/ppr-helm/infra/helm_constructs.py`
- Modify: `plugins/ppr-helm/infra/helm_stack.py`
- Modify: `infra/app.py`

**What to add to `helm_constructs.py`:**

```python
from aws_cdk import aws_location as location, aws_cognito as cognito, aws_iam as iam

class HelmMap(Construct):
    """ALS Map resource for location visualization."""
    def __init__(self, scope, construct_id, *, environment_name):
        super().__init__(scope, construct_id)
        self.map_resource = location.CfnMap(
            self, "MapResource",
            map_name=f"ppr-helm-map-{environment_name}",
            configuration=location.CfnMap.MapConfigurationProperty(
                style="VectorEsriNavigation",
            ),
            description="Map tiles for ppr-helm location management UI",
        )

class HelmIdentityPool(Construct):
    """Cognito Identity Pool for browser-side ALS credentials."""
    def __init__(self, scope, construct_id, *, environment_name, user_pool, app_client, map_arn):
        super().__init__(scope, construct_id)

        self.identity_pool = cognito.CfnIdentityPool(
            self, "IdentityPool",
            identity_pool_name=f"ppr-helm-identity-{environment_name}",
            allow_unauthenticated_identities=True,
            cognito_identity_providers=[
                cognito.CfnIdentityPool.CognitoIdentityProviderProperty(
                    client_id=app_client.user_pool_client_id,
                    provider_name=user_pool.user_pool_provider_name,
                ),
            ],
        )

        # Unauthenticated role — map tiles only
        unauth_role = iam.Role(
            self, "UnauthRole",
            assumed_by=iam.FederatedPrincipal(
                "cognito-identity.amazonaws.com",
                conditions={"StringEquals": {"cognito-identity.amazonaws.com:aud": self.identity_pool.ref},"ForAnyValue:StringLike": {"cognito-identity.amazonaws.com:amr": "unauthenticated"}},
                assume_role_action="sts:AssumeRoleWithWebIdentity",
            ),
        )
        unauth_role.add_to_policy(iam.PolicyStatement(
            actions=["geo:GetMap*"],
            resources=[map_arn],
        ))

        # Authenticated role — same map permissions
        auth_role = iam.Role(
            self, "AuthRole",
            assumed_by=iam.FederatedPrincipal(
                "cognito-identity.amazonaws.com",
                conditions={"StringEquals": {"cognito-identity.amazonaws.com:aud": self.identity_pool.ref},"ForAnyValue:StringLike": {"cognito-identity.amazonaws.com:amr": "authenticated"}},
                assume_role_action="sts:AssumeRoleWithWebIdentity",
            ),
        )
        auth_role.add_to_policy(iam.PolicyStatement(
            actions=["geo:GetMap*"],
            resources=[map_arn],
        ))

        cognito.CfnIdentityPoolRoleAttachment(
            self, "RoleAttachment",
            identity_pool_id=self.identity_pool.ref,
            roles={"unauthenticated": unauth_role.role_arn, "authenticated": auth_role.role_arn},
        )
```

**What to add to `helm_stack.py`:**
- Import HelmMap, HelmIdentityPool from helm_constructs
- Create HelmMap construct
- Create HelmIdentityPool construct (after user_pool + app_client)
- Extract place_index_name/place_index_arn from plugin_context
- Grant Amplify role `geo:SearchPlaceIndexForSuggestions` + `geo:GetPlace` on place index (if amplify_role exists)
- Add env vars to Amplify: ALS_MAP_NAME, ALS_PLACE_INDEX_NAME, COGNITO_IDENTITY_POOL_ID, ALS_REGION
- Update build spec grep pattern to include `ALS_`
- Add CfnOutputs for IdentityPoolId, MapName

**What to add to `infra/app.py`:**
- Add `place_index_name` and `place_index_arn` to `_plugin_context` dict
- Add `database_stack` dependency for plugin stacks

---

### Task 2: CDK Tests for Phase 3 Resources

Add tests for Identity Pool, Map resource, and role attachments.

---

### Task 3: ALS Mock Data + Server Client

**Files:**
- Create: `plugins/ppr-helm/src/lib/mocks/als-suggestions.ts`
- Create: `plugins/ppr-helm/src/lib/api/als-client.ts`

Mock data: hardcoded address suggestions for local dev.
Client: `import 'server-only'`, dynamic import of `@aws-sdk/client-location`, mock mode when `ALS_PLACE_INDEX_NAME` is empty.

Functions: `searchSuggestions(query)`, `getPlace(placeId)`

---

### Task 4: ALS BFF Routes

**Files:**
- Create: `plugins/ppr-helm/src/app/api/als/suggestions/route.ts`
- Create: `plugins/ppr-helm/src/app/api/als/credentials/route.ts`

Suggestions route: GET, proxies to ALS via server client.
Credentials route: GET, returns temp Cognito Identity Pool creds for map tiles.

---

### Task 5: Address Autocomplete Hook

**File:** `plugins/ppr-helm/src/hooks/use-address-autocomplete.ts`

Uses existing `useDebounce` hook, TanStack Query for suggestions, mutation for place resolution.

---

### Task 6: Address Autocomplete Component

**File:** `plugins/ppr-helm/src/components/locations/address-autocomplete.tsx`

Controlled input with dropdown, ARIA combobox pattern, keyboard navigation.

---

### Task 7: Integrate Autocomplete into Edit Form

**File:** Modify `plugins/ppr-helm/src/components/locations/edit-form-ptf-fields.tsx`

Add address autocomplete above the address fields. When suggestion selected, auto-fill address_1, city, state, postal_code, latitude, longitude.

---

### Task 8: Final Verification

Run all tests, typecheck, lint, CDK tests, build.
