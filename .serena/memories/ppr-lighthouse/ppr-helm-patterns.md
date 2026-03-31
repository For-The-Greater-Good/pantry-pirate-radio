# PPR-Helm Architectural Patterns for PPR-Lighthouse

## 1. API Routes (Tightbeam Proxy Pattern)

### Location: `plugins/ppr-helm/src/app/api/tightbeam/`

All routes follow the same pattern:
1. **Auth Check First** - `await requireAuth()` or `await requirePermission('action')`
2. **CSRF Token** - `requireCsrf(request)` on mutations (PUT, DELETE, POST)
3. **Get Client** - `getTightbeamClient()`
4. **Call Backend** - client method
5. **Error Handling** - Catch AuthError and TightbeamError separately

#### Search Route (GET)
**File:** `plugins/ppr-helm/src/app/api/tightbeam/search/route.ts`

```typescript
export async function GET(request: NextRequest) {
  try {
    await requireAuth();  // Just auth check, no permission needed for search

    const url = request.nextUrl;
    const params: SearchParams = {
      q: url.searchParams.get('q') ?? undefined,
      name: url.searchParams.get('name') ?? undefined,
      address: url.searchParams.get('address') ?? undefined,
      city: url.searchParams.get('city') ?? undefined,
      state: url.searchParams.get('state') ?? undefined,
      zip_code: url.searchParams.get('zip_code') ?? undefined,
      phone: url.searchParams.get('phone') ?? undefined,
      email: url.searchParams.get('email') ?? undefined,
      website: url.searchParams.get('website') ?? undefined,
      include_rejected: url.searchParams.get('include_rejected') === 'true',
      limit: url.searchParams.get('limit') ? Number(url.searchParams.get('limit')) : undefined,
      offset: url.searchParams.get('offset') ? Number(url.searchParams.get('offset')) : undefined,
    };

    const client = getTightbeamClient();
    const data = await client.search(params);
    return NextResponse.json(data);
  } catch (error) {
    if (error instanceof AuthError) {
      return NextResponse.json({ error: error.message }, { status: error.status });
    }
    if (error instanceof TightbeamError) {
      return NextResponse.json({ error: error.message }, { status: error.status });
    }
    console.error('[tightbeam/search]', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
```

#### Get Location (GET)
**File:** `plugins/ppr-helm/src/app/api/tightbeam/locations/[id]/route.ts`

```typescript
export async function GET(_request: NextRequest, { params }: RouteParams) {
  try {
    await requireAuth();
    const { id } = await params;
    const client = getTightbeamClient();
    const data = await client.getLocation(id);
    return NextResponse.json(data);
  } catch (error) {
    // Same error handling pattern...
  }
}
```

#### Update Location (PUT) - WITH PERMISSIONS
```typescript
export async function PUT(request: NextRequest, { params }: RouteParams) {
  try {
    requireCsrf(request);  // Validates X-Requested-With: XMLHttpRequest
    await requirePermission('editLocation');  // Checks role has permission
    const { id } = await params;
    const body = await request.json();
    const session = await auth();
    const callerContext = getCallerContext(session ?? {});  // Adds user context

    const client = getTightbeamClient();
    const data = await client.updateLocation(id, {
      ...body,
      caller_context: callerContext,  // Always include caller context
    });
    return NextResponse.json(data);
  } catch (error) {
    // Error handling...
  }
}
```

#### Delete Location (DELETE)
```typescript
export async function DELETE(request: NextRequest, { params }: RouteParams) {
  try {
    requireCsrf(request);
    await requirePermission('deleteLocation');
    const { id } = await params;
    let body: { reason?: string } = {};
    try {
      body = await request.json();
    } catch {
      // Body is optional for delete
    }
    const session = await auth();
    const callerContext = getCallerContext(session ?? {});

    const client = getTightbeamClient();
    const data = await client.deleteLocation(id, body.reason, callerContext);
    return NextResponse.json(data);
  } catch (error) {
    // Error handling...
  }
}
```

#### History (GET)
**File:** `plugins/ppr-helm/src/app/api/tightbeam/locations/[id]/history/route.ts`

Simple GET with auth check, calls `client.getHistory(id)`.

#### Restore Location (POST)
**File:** `plugins/ppr-helm/src/app/api/tightbeam/locations/[id]/restore/route.ts`

Similar pattern to DELETE but uses `requirePermission('restoreLocation')` and calls `client.restoreLocation()`.

---

## 2. Server-Side API Client (TightbeamClient)

**File:** `plugins/ppr-helm/src/lib/api/tightbeam-client.ts`

### Initialization
```typescript
class TightbeamClient {
  private baseUrl: string;
  private apiKey: string;
  private keyHeader: string;

  constructor() {
    const writeApiUrl = process.env.WRITE_API_LAMBDA_URL ?? '';
    if (!writeApiUrl) {
      console.warn('[TightbeamClient] WRITE_API_LAMBDA_URL not set...');
    }
    this.baseUrl = writeApiUrl.replace(/\/$/, '');
    this.apiKey = process.env.WRITE_API_KEY ?? '';
    this.keyHeader = 'x-write-api-key';
  }
}
```

**Environment Variables Required:**
- `WRITE_API_LAMBDA_URL` - Base URL to Tightbeam/ppr-write-api Lambda
- `WRITE_API_KEY` - API key for authentication

### Private Request Method
```typescript
private async request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `${this.baseUrl}${path}`;
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      [this.keyHeader]: this.apiKey,  // x-write-api-key header
      'x-api-key-name': 'ppr-helm',   // Identifies the caller
      ...options.headers,
    },
  });

  if (!response.ok) {
    const body = await response.text();
    throw new TightbeamError(response.status, body, path);
  }

  return response.json() as Promise<T>;
}
```

### Public Methods
```typescript
async search(params: SearchParams): Promise<SearchResponse> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      query.set(key, String(value));
    }
  }
  return this.request<SearchResponse>(`/search?${query.toString()}`);
}

async getLocation(id: string): Promise<LocationDetail> {
  return this.request<LocationDetail>(`/locations/${encodeURIComponent(id)}`);
}

async getHistory(id: string): Promise<HistoryResponse> {
  return this.request<HistoryResponse>(`/locations/${encodeURIComponent(id)}/history`);
}

async updateLocation(id: string, data: LocationUpdateRequest): Promise<LocationUpdateResponse> {
  return this.request<LocationUpdateResponse>(`/locations/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

async deleteLocation(id: string, reason?: string, callerContext?: CallerContext): Promise<MutationResponse> {
  return this.request<MutationResponse>(`/locations/${encodeURIComponent(id)}`, {
    method: 'DELETE',
    body: JSON.stringify({ reason, caller_context: callerContext }),
  });
}

async restoreLocation(id: string, reason?: string, callerContext?: CallerContext): Promise<MutationResponse> {
  return this.request<MutationResponse>(`/locations/${encodeURIComponent(id)}/restore`, {
    method: 'POST',
    body: JSON.stringify({ reason, caller_context: callerContext }),
  });
}
```

### Error Handling
```typescript
export class TightbeamError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: string,
    public readonly path: string,
  ) {
    super(`Tightbeam API error ${status} on ${path}: ${body}`);
    this.name = 'TightbeamError';
  }
}

let _client: TightbeamClient | null = null;

export function getTightbeamClient(): TightbeamClient {
  if (!_client) _client = new TightbeamClient();
  return _client;
}
```

---

## 3. Authentication & Authorization

### Session Management
**File:** `plugins/ppr-helm/src/lib/auth/session.ts`

#### JWT Creation (HS256)
```typescript
import { SignJWT, jwtVerify } from 'jose';

const secretStr = process.env.AUTH_SECRET || process.env.NEXTAUTH_SECRET;
if (!secretStr && process.env.AUTH_PROVIDER !== 'mock') {
  throw new Error('AUTH_SECRET or NEXTAUTH_SECRET must be set...');
}
const SECRET = new TextEncoder().encode(secretStr || 'dev-fallback');

async function createSessionCookie(sub: string, email: string, groups: string[]) {
  const role = getRoleFromGroups(groups);
  const jwt = await new SignJWT({ sub, email, role, groups })
    .setProtectedHeader({ alg: 'HS256' })
    .setExpirationTime('8h')
    .setIspisuedAt()
    .sign(SECRET);

  const cookieStore = await cookies();
  cookieStore.set('helm-session', jwt, {
    httpOnly: true,
    secure: true,
    sameSite: 'lax',
    path: '/',
    maxAge: 8 * 60 * 60,
  });
}
```

**Key Points:**
- Uses `jose` library for JWT signing/verification
- HS256 algorithm (symmetric, shared secret)
- 8-hour expiration
- Stores in httpOnly, secure cookie named `helm-session`

#### Auth Provider Support
```typescript
const isMock = process.env.AUTH_PROVIDER === 'mock';
const user = isMock
  ? await authenticateMock(email)
  : await authenticateCognito(email, password);
```

**Environment Variables:**
- `AUTH_PROVIDER` - Either `'mock'` (development) or Cognito (production)
- `AUTH_SECRET` or `NEXTAUTH_SECRET` - Secret for JWT signing
- `COGNITO_CLIENT_ID` - AWS Cognito client ID
- `COGNITO_ISSUER` - Cognito issuer URL (parsed for region)
- `MOCK_USER_ROLE` - Default role in mock mode (default: `'admin'`)

#### Verify Session
```typescript
export async function auth(): Promise<Session | null> {
  try {
    const cookieStore = await cookies();
    const token = cookieStore.get('helm-session')?.value;
    if (!token) return null;

    const { payload } = await jwtVerify(token, SECRET);

    const id = typeof payload.sub === 'string' ? payload.sub : '';
    if (!id) return null;

    return {
      user: {
        id,
        email: typeof payload.email === 'string' ? payload.email : '',
        name: null,
        role: isRole(payload.role) ? payload.role : 'editor',
        groups: Array.isArray(payload.groups) ? (payload.groups as string[]) : [],
      },
    };
  } catch {
    return null;
  }
}
```

### Permissions & Roles
**File:** `plugins/ppr-helm/src/lib/auth/roles.ts`

```typescript
export const ROLES = {
  ADMIN: 'admin',
  EDITOR: 'editor',
} as const;

export interface Permission {
  search: boolean;
  viewDetail: boolean;
  editLocation: boolean;
  deleteLocation: boolean;
  restoreLocation: boolean;
  manageUsers: boolean;
  viewReports: boolean;
  resolveReports: boolean;
}

const ROLE_PERMISSIONS: Record<Role, Permission> = {
  admin: {
    search: true,
    viewDetail: true,
    editLocation: true,
    deleteLocation: true,
    restoreLocation: true,
    manageUsers: true,
    viewReports: true,
    resolveReports: true,
  },
  editor: {
    search: true,
    viewDetail: true,
    editLocation: true,
    deleteLocation: false,      // Editors cannot delete
    restoreLocation: false,     // Editors cannot restore
    manageUsers: false,
    viewReports: true,
    resolveReports: true,
  },
};

export function hasPermission(role: Role, action: keyof Permission): boolean {
  return getPermissions(role)[action];
}

export function getRoleFromGroups(groups: string[]): Role {
  if (groups.includes(ROLES.ADMIN)) return ROLES.ADMIN;
  return ROLES.EDITOR;
}
```

### Middleware
**File:** `plugins/ppr-helm/src/lib/auth/middleware.ts`

```typescript
export async function requireAuth(): Promise<AuthenticatedUser> {
  const session = await auth();
  if (!session?.user) {
    throw new AuthError('Unauthorized', 401);
  }
  return {
    id: session.user.id,
    email: session.user.email,
    role: session.user.role,
    groups: session.user.groups,
  };
}

export async function requirePermission(action: keyof Permission): Promise<AuthenticatedUser> {
  const user = await requireAuth();
  if (!hasPermission(user.role, action)) {
    throw new AuthError('Forbidden', 403);
  }
  return user;
}

export function requireCsrf(request: Request): void {
  if (request.headers.get('x-requested-with') !== 'XMLHttpRequest') {
    throw new AuthError('CSRF validation failed', 403);
  }
}

export function getCallerContext(session: Session | null): CallerContext {
  return {
    user_id: session?.user?.id,
    username: session?.user?.email ?? undefined,
    groups: session?.user?.groups ?? [],
    source: 'ppr-helm',
  };
}
```

**Key Pattern:** `getCallerContext` extracts user info from session and always passes `source: 'ppr-helm'`.

---

## 4. Client-Side Hooks

### useAuth
**File:** `plugins/ppr-helm/src/hooks/use-auth.ts`

```typescript
export function useAuthRole(role: Role) {
  const can = (action: keyof Permission): boolean => {
    return hasPermission(role, action);
  };

  return { role, can };
}
```

Usage: Check permissions in components with `can('editLocation')`.

### useLocations
**File:** `plugins/ppr-helm/src/hooks/use-locations.ts`

```typescript
const { data, isLoading, error } = useQuery<SearchResponse>({
  queryKey: ['locations', searchParams],
  queryFn: async () => {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(searchParams)) {
      if (value !== undefined && value !== null && value !== '') {
        query.set(key, String(value));
      }
    }
    const response = await fetch(`/api/tightbeam/search?${query.toString()}`);
    if (!response.ok) throw new Error('Search failed');
    return response.json();
  },
});

const setSearchParams = useCallback((params: SearchParams) => {
  const query = new URLSearchParams();
  // ... build query string ...
  router.push(`/locations?${query.toString()}`);
}, [router]);
```

**Pattern:** URL-driven search with React Query + Next.js routing.

### useMutation
**File:** `plugins/ppr-helm/src/hooks/use-mutation.ts`

```typescript
type MutationType = 'update' | 'delete' | 'restore';

export function useMutation(locationId: string) {
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mutate = async (
    type: MutationType,
    data?: LocationUpdateRequest | { reason?: string },
  ): Promise<LocationUpdateResponse | MutationResponse | null> => {
    setIsPending(true);
    setError(null);

    try {
      const url = `/api/tightbeam/locations/${locationId}${type === 'restore' ? '/restore' : ''}`;
      const method = type === 'update' ? 'PUT' : type === 'delete' ? 'DELETE' : 'POST';

      const response = await fetch(url, {
        method,
        headers: { 
          'Content-Type': 'application/json', 
          'X-Requested-With': 'XMLHttpRequest'  // CSRF token
        },
        body: JSON.stringify(data ?? {}),
      });

      if (!response.ok) {
        const body = await response.json().catch(() => ({ error: 'Unknown error' }));
        throw new Error(body.error ?? `Request failed with status ${response.status}`);
      }

      return await response.json();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      setError(message);
      return null;
    } finally {
      setIsPending(false);
    }
  };

  return { mutate, isPending, error };
}
```

**Key Pattern:** 
- Sets `X-Requested-With: XMLHttpRequest` for CSRF protection
- Three methods: PUT (update), DELETE (delete), POST (restore)
- Path varies: `/restore` appended for restore action
- Returns typed response or null on error

---

## 5. Component Patterns

### Search Form
**File:** `plugins/ppr-helm/src/components/locations/search-form.tsx`

```typescript
interface SearchFormProps {
  params: SearchParams;
  onChange: (params: SearchParams) => void;
}

export function SearchForm({ params, onChange }: SearchFormProps) {
  const [query, setQuery] = useState(params.q ?? '');
  const debouncedQuery = useDebounce(query, 300);

  useEffect(() => {
    onChange({ ...params, q: debouncedQuery || undefined, offset: 0 });
  }, [debouncedQuery]);

  return (
    <div>
      <input
        type="search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={t('search.placeholder')}
      />
      {/* Filter fields: name, city, state, zip_code */}
    </div>
  );
}
```

**Pattern:** Debounced search input, collapsible filter panel with 4 fields.

### Results Table
**File:** `plugins/ppr-helm/src/components/locations/results-table.tsx`

```typescript
interface ResultsTableProps {
  data: SearchResponse | undefined;
  isLoading: boolean;
  onPageChange: (offset: number) => void;
}

export function ResultsTable({ data, isLoading, onPageChange }: ResultsTableProps) {
  if (isLoading) return <LoadingState />;
  if (!data || data.results.length === 0) return <EmptyState />;

  return (
    <div>
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>City</th>
            <th>State</th>
            <th>Zip</th>
            <th>Confidence</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {data.results.map((location) => (
            <tr key={location.id}>
              <td><Link href={`/locations/${location.id}`}>{location.name}</Link></td>
              <td>{location.city}</td>
              {/* ... other fields ... */}
              <td><ConfidenceBadge score={location.confidence_score} /></td>
              <td><StatusBadge status={location.validation_status} /></td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Pagination */}
      <button onClick={() => onPageChange(Math.max(0, data.offset - data.limit))}>Previous</button>
      <button onClick={() => onPageChange(data.offset + data.limit)}>Next</button>
    </div>
  );
}
```

### Location Detail View
**File:** `plugins/ppr-helm/src/components/locations/location-detail.tsx`

```typescript
interface LocationDetailViewProps {
  detail: LocationDetail;
  role: Role;
}

export function LocationDetailView({ detail, role }: LocationDetailViewProps) {
  const { location, sources } = detail;

  return (
    <div>
      <LocationHeader location={location} />
      <LocationFields location={location} />
      <LocationActions location={location} role={role} />
      <SourceRecords sources={sources} />
    </div>
  );
}

function LocationActions({ location, role }: { location: LocationResult; role: Role }) {
  const isRejected = location.validation_status === 'rejected';
  const canEdit = hasPermission(role, 'editLocation') && !isRejected;
  const canDelete = hasPermission(role, 'deleteLocation') && !isRejected;
  const canRestore = hasPermission(role, 'restoreLocation') && isRejected;

  return (
    <div className="flex gap-3">
      {canEdit && <Link href={`/locations/${location.id}/edit`}>Edit</Link>}
      <Link href={`/locations/${location.id}/history`}>View History</Link>
      {canDelete && <DeleteDialog locationId={location.id} locationName={location.name} />}
      {canRestore && <RestoreDialog locationId={location.id} locationName={location.name} />}
    </div>
  );
}
```

**Pattern:** 
- Permission checks with `hasPermission(role, 'action')`
- Status-based visibility (rejected = read-only, can restore)
- Delete/Restore in modal dialogs

### Badges
**File:** `plugins/ppr-helm/src/components/locations/confidence-badge.tsx`

```typescript
export function ConfidenceBadge({ score }: { score: number | null }) {
  if (score === null) return <span>--</span>;

  let colorClass: string;
  if (score >= 70) colorClass = 'bg-confidence-high/10 text-confidence-high';
  else if (score >= 30) colorClass = 'bg-confidence-mid/10 text-confidence-mid';
  else colorClass = 'bg-confidence-low/10 text-confidence-low';

  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${colorClass}`}>{score}</span>;
}
```

**File:** `plugins/ppr-helm/src/components/locations/status-badge.tsx`

```typescript
const STATUS_STYLES: Record<string, string> = {
  verified: 'bg-confidence-high/10 text-confidence-high',
  needs_review: 'bg-confidence-mid/10 text-confidence-mid',
  rejected: 'bg-confidence-low/10 text-confidence-low',
};

export function StatusBadge({ status }: { status: string | null }) {
  if (!status) return <span>--</span>;
  const style = STATUS_STYLES[status] ?? 'bg-divider text-text-secondary';
  const label = t(STATUS_KEYS[status]);
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${style}`}>{label}</span>;
}
```

### Delete Dialog
**File:** `plugins/ppr-helm/src/components/locations/delete-dialog.tsx`

```typescript
export function DeleteDialog({ locationId, locationName }: DeleteDialogProps) {
  const router = useRouter();
  const { mutate, isPending, error } = useMutation(locationId);
  const [isOpen, setIsOpen] = useState(false);
  const [reason, setReason] = useState('');

  const handleDelete = async () => {
    const result = await mutate('delete', { reason });
    if (result) {
      setIsOpen(false);
      router.push('/locations');
    }
  };

  return (
    <>
      <button onClick={() => setIsOpen(true)}>Delete</button>

      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-md rounded-lg bg-surface p-6">
            <h2>Delete Location</h2>
            <p>Are you sure?</p>
            {locationName && <p className="font-medium">{locationName}</p>}
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Why are you deleting?"
              rows={2}
            />
            {error && <p role="alert" className="text-confidence-low">{error}</p>}
            <div className="flex justify-end gap-3">
              <button onClick={() => setIsOpen(false)}>Cancel</button>
              <button onClick={handleDelete} disabled={isPending}>Confirm</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
```

**Pattern:** Modal dialog with optional reason textarea, calls `useMutation('delete', { reason })`.

### Restore Dialog
**File:** `plugins/ppr-helm/src/components/locations/restore-dialog.tsx`

Same as DeleteDialog but calls `mutate('restore', { reason })` and refreshes page instead of redirecting.

### Edit Form
**File:** `plugins/ppr-helm/src/components/locations/edit-form.tsx`

```typescript
export function EditForm({ detail }: EditFormProps) {
  const location = detail.location;
  const router = useRouter();
  const { mutate, isPending, error } = useMutation(location.id);

  const [form, setForm] = useState<LocationUpdateRequest>({
    name: location.name ?? undefined,
    address_1: location.address_1 ?? undefined,
    // ... other fields ...
    schedules: (detail.schedules ?? []).map(s => ({ id: s.id, ... })),
    phones: (detail.phones ?? []).map(p => ({ id: p.id, ... })),
    languages: (detail.languages ?? []).map(l => ({ id: l.id, ... })),
    accessibility: detail.accessibility ? { ... } : {},
  });

  const numericFields = new Set(['latitude', 'longitude']);

  const handleChange = (field: keyof LocationUpdateRequest, value: string) => {
    const parsed = numericFields.has(field) && value ? Number(value) : value || undefined;
    setForm((prev) => ({ ...prev, [field]: parsed }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const result = await mutate('update', form);
    if (result) {
      router.push(`/locations/${location.id}`);
      router.refresh();
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <PrimaryFieldsSection form={form} onChange={handleChange} />
      <ScheduleEditor schedules={form.schedules ?? []} onChange={...} />
      <AdvancedFieldsSection form={form} onChange={...} />
      <div className="flex gap-3">
        <button type="submit" disabled={isPending}>Save</button>
        <button type="button" onClick={() => router.back()}>Cancel</button>
      </div>
    </form>
  );
}
```

**Pattern:**
- State management with `LocationUpdateRequest` type
- Numeric field handling (latitude/longitude)
- Sub-components for sections (Primary, Schedule, Advanced)
- Calls `mutate('update', form)` on submit
- Redirects to detail view on success

---

## 6. Type Definitions

**File:** `plugins/ppr-helm/src/lib/api/types.ts`

### Core Types
```typescript
export type ValidationStatus = 'verified' | 'needs_review' | 'rejected';
export type ScheduleFreq = 'WEEKLY' | 'MONTHLY';
export type AttendingType = 'physical' | 'virtual' | 'hybrid';
export type Weekday = 'MO' | 'TU' | 'WE' | 'TH' | 'FR' | 'SA' | 'SU';

export interface CallerContext {
  user_id: string | undefined;
  username: string | undefined;
  groups: string[];
  source: 'ppr-helm';
}
```

### Search Response
```typescript
export interface LocationResult {
  id: string;
  name: string | null;
  organization_name: string | null;
  address_1: string | null;
  city: string | null;
  state: string | null;
  postal_code: string | null;
  latitude: number | null;
  longitude: number | null;
  phone: string | null;
  email: string | null;
  website: string | null;
  description: string | null;
  confidence_score: number | null;
  validation_status: ValidationStatus | null;
}

export interface SearchResponse {
  results: LocationResult[];
  total: number;
  limit: number;
  offset: number;
}

export interface SearchParams {
  q?: string;
  name?: string;
  address?: string;
  city?: string;
  state?: string;
  zip_code?: string;
  phone?: string;
  email?: string;
  website?: string;
  include_rejected?: boolean;
  limit?: number;
  offset?: number;
}
```

### Location Detail
```typescript
export interface LocationDetail {
  location: LocationResult;
  sources: SourceRecord[];
  schedules?: ScheduleRecord[];
  phones?: PhoneRecord[];
  languages?: LanguageRecord[];
  accessibility?: AccessibilityRecord | null;
}
```

### Update Request/Response
```typescript
export interface LocationUpdateRequest {
  name?: string;
  address_1?: string;
  address_2?: string;
  city?: string;
  state?: string;
  postal_code?: string;
  latitude?: number;
  longitude?: number;
  phone?: string;
  email?: string;
  website?: string;
  description?: string;
  alternate_name?: string;
  transportation?: string;
  location_type?: string;
  schedules?: ScheduleUpdate[];
  phones?: PhoneUpdate[];
  languages?: LanguageUpdate[];
  accessibility?: AccessibilityUpdate;
  caller_context?: CallerContext;
}

export interface LocationUpdateResponse {
  location_id: string;
  source_id: string;
  audit_id: string;
  message: string;
}

export interface MutationResponse {
  location_id: string;
  audit_id: string;
  message: string;
}
```

---

## Key Patterns for PPR-Lighthouse

### 1. Authentication Pattern
- Use `jose` library for HS256 JWT
- Store JWT in httpOnly secure cookie
- Verify on server with `jwtVerify(token, SECRET)`
- Include `sub` (user ID), `email`, `role`, `groups` in payload
- 8-hour expiration typical

### 2. API Route Pattern
```
1. Auth check (requireAuth or requirePermission)
2. CSRF check if mutation (requireCsrf)
3. Get client instance (getTightbeamClient)
4. Build params from request
5. Call client method
6. Catch AuthError and TightbeamError separately
7. Return JSON response
```

### 3. Caller Context Pattern
Always extract from session and pass to mutations:
```typescript
const session = await auth();
const callerContext = getCallerContext(session ?? {});
const data = await client.updateLocation(id, { ...body, caller_context: callerContext });
```

### 4. Permission Pattern
- Check at route level with `requirePermission('actionName')`
- Check at component level with `hasPermission(role, 'actionName')`
- Hide/disable UI elements based on permissions + location status

### 5. CSRF Pattern
Client sends: `'X-Requested-With': 'XMLHttpRequest'`
Server checks: `request.headers.get('x-requested-with') === 'XMLHttpRequest'`

### 6. Status-Based UI
- `validation_status === 'rejected'` → Read-only, show restore button
- `validation_status !== 'rejected'` + `canEdit` → Show edit button
- `validation_status !== 'rejected'` + `canDelete` → Show delete button

### 7. Search Pattern
- URL-driven state with query string parameters
- Debounced search input (300ms)
- React Query for caching
- Pagination with offset/limit
- Default limit = 20

### 8. Mutation Pattern
- 3 types: 'update' (PUT), 'delete' (DELETE), 'restore' (POST)
- Optional reason text for delete/restore
- Uses `useMutation` hook that returns `{ mutate, isPending, error }`
- Redirect or refresh on success

### 9. Component Composition
- Dumb badge components (ConfidenceBadge, StatusBadge)
- Smart container components (LocationDetailView)
- Modal dialogs for destructive actions (Delete, Restore)
- Form sections composed together (PrimaryFields, Schedule, Advanced)

### 10. Env Var Validation
PPR-Helm doesn't have explicit config validation, but key env vars are:
- `WRITE_API_LAMBDA_URL` - Backend API
- `WRITE_API_KEY` - API authentication
- `AUTH_PROVIDER` - 'mock' or 'cognito'
- `AUTH_SECRET` / `NEXTAUTH_SECRET` - JWT signing secret
- `COGNITO_CLIENT_ID` - For Cognito auth
- `COGNITO_ISSUER` - For Cognito auth
- `MOCK_USER_ROLE` - Default role in mock mode

