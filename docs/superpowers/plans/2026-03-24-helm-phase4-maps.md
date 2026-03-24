# Helm Enhancement Phase 4: Map Components

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan.

**Goal:** Add interactive maps to the Helm admin interface — a search results map showing location pins, and a draggable pin on the edit form that syncs with lat/long fields and the autocomplete.

**Architecture:** MapLibre GL JS loaded via `next/dynamic` (no SSR). Cognito Identity Pool provides temp AWS credentials for ALS map tiles (from Phase 3). Mock mode shows a placeholder div in local dev.

**Tech Stack:** MapLibre GL JS, Next.js 15 dynamic imports, React context, TanStack Query

**Prerequisite:** Phases 1-3 complete (Identity Pool, credentials endpoint, autocomplete all exist).

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `src/components/providers/map-provider.tsx` | React context for ALS credentials + config |
| Create | `src/hooks/use-als-credentials.ts` | Fetch temp AWS creds for map tiles |
| Create | `src/components/map/map-container.tsx` | MapLibre GL JS init with ALS tiles |
| Create | `src/components/map/map-loading.tsx` | Loading skeleton for map |
| Create | `src/components/map/edit-map.tsx` | Draggable pin, syncs with form state |
| Create | `src/components/map/search-results-map.tsx` | Pins for search results, click to navigate |
| Create | `src/components/map/map-pins.tsx` | Clickable pin markers |
| Modify | `src/components/locations/edit-form.tsx` | Add edit map next to PTF fields |
| Modify | `src/app/(dashboard)/locations/page.tsx` | Add search results map |
| Create tests for all new files |

---

### Task 1: Install MapLibre + ALS Credentials Hook + Map Provider

Create the foundation: install maplibre-gl, create the credentials hook and map context provider.

### Task 2: Map Container + Loading Component

Create the MapLibre GL JS wrapper with `next/dynamic` (ssr: false) and mock mode fallback.

### Task 3: Edit Map (Draggable Pin)

Create the draggable pin component that syncs lat/long with the parent form state.

### Task 4: Search Results Map + Map Pins

Create the search results map with clickable pins that navigate to location detail.

### Task 5: Integrate Maps into Pages

Wire edit map into the edit form, search results map into the locations page.

### Task 6: Final Verification

Run all tests, typecheck, lint, build.
