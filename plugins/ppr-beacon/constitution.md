# ppr-beacon Constitution

These quality standards are NON-NEGOTIABLE for all contributions to ppr-beacon.

Beacon is a Python-only plugin: static site generator that reads from PostgreSQL and produces SEO-optimized HTML. No JavaScript framework, no build step beyond Python + Jinja2.

---

## 1. Python Strict Quality (NON-NEGOTIABLE)

All code MUST pass the same quality gates as core PPR:

- **black**: Code formatting (88 character line length)
- **ruff**: Linting with security rules (E, F, I, C90, N, B, S, RUF, UP)
- **mypy**: Type checking
- **bandit**: Security scanning
- **structlog**: All logging via structlog (not `print()` or bare `logging`)

---

## 2. SEO Correctness (NON-NEGOTIABLE)

Every generated page MUST meet these SEO requirements:

- Exactly one `<h1>` per page
- `<title>` tag present and descriptive
- `<meta name="description">` present and unique per page
- `<link rel="canonical">` with absolute URL
- Open Graph tags: `og:title`, `og:description`, `og:url`, `og:type`
- Twitter Card tags: `twitter:card`, `twitter:title`, `twitter:description`
- Schema.org JSON-LD: `FoodEstablishment` for locations, `Organization` for orgs, `BreadcrumbList` on all pages
- Semantic HTML5: `<header>`, `<main>`, `<nav>`, `<article>`, `<footer>`
- `<html lang="en">` attribute
- `<meta charset="utf-8">`
- All internal links use absolute URLs
- `tel:` links for phone numbers, Google Maps directions links for addresses

---

## 3. Page Performance (NON-NEGOTIABLE)

- Total HTML per page: < 100KB
- CSS file: < 15KB minified
- Zero required JavaScript for content rendering
- Fonts self-hosted as woff2 (no external requests for content)
- Target Lighthouse scores: Performance >= 95, SEO >= 98, Accessibility >= 90

---

## 4. Data Quality Gate (NON-NEGOTIABLE)

Only human-verified locations may have mini-sites generated.

- Quality gate: `verified_by IN ('admin', 'source') AND confidence_score >= 93`
- Source verification (Lighthouse portal) is the gold standard
- Admin verification (Helm) is high trust but below source
- No mini-site for unverified or auto-verified-only locations
- The quality gate is enforced in SQL, not application logic

---

## 5. Privacy (NON-NEGOTIABLE)

Per PPR Constitution Principle VII:

- Only public organizational data displayed (name, address, phone, hours, services)
- No Personally Identifiable Information (PII) of clients or visitors
- No tracking cookies or third-party analytics scripts
- Client-side analytics uses Beacon API only, no fingerprinting
- Test data uses fictional information (`555-xxx-xxxx`, `example.com`)

---

## 6. Test-Driven Development (NON-NEGOTIABLE)

Tests MUST be written before implementation code.

- pytest for all Python code
- Tests for: slug generation, JSON-LD output, sitemap structure, model validation
- HTML quality assertions: one h1, valid JSON-LD, canonical URLs, semantic structure
- Page budget assertions: HTML < 100KB, CSS < 15KB
- Coverage tracked per-module

---

## 7. Plentiful Design System (NON-NEGOTIABLE)

All pages MUST follow the Plentiful design system:

- **Fonts**: Noto Sans (400, 700) + Noto Serif (400, italic)
- **Colors**: Brand green `#00CD96`, black `#0F0F0F`, white `#FFFFFF`, secondary `#696969`
- **Buttons**: Pill-shaped (`border-radius: 9999px`), `border: 2px solid #0F0F0F`
- **Cards**: `border-radius: 16px`, white background
- **Base font size**: `62.5%` (10px), all sizing in rem
- **Breakpoints**: 640, 768, 1024, 1280px (mobile-first)
- **Max content width**: 1920px
- **Implementation**: Plain CSS file, no Tailwind, no build step

Visual consistency with plentiful.org is non-negotiable — these pages represent the Plentiful brand.

---

## 8. Code Quality

- Max 600 lines per source file (matching PPR constitution)
- Cyclomatic complexity <= 15 per function
- snake_case functions/variables, PascalCase classes
- Deterministic slug generation (same input always produces same URL)

---

## 9. Accessibility (NON-NEGOTIABLE)

- WCAG 2.1 AA compliance
- Semantic HTML elements (not div soup)
- Proper ARIA labels on interactive elements
- Click-to-call links usable on mobile
- Pages must render fully without JavaScript

---

## 10. AWS Observability (NON-NEGOTIABLE)

Per PPR Constitution Principle XIV (Plugin Exception):

- Build Lambda MUST have CloudWatch alarms for Errors and Throttles
- Analytics Lambda MUST have CloudWatch alarms for Errors and Throttles
- DynamoDB tables MUST have alarms for throttled requests and system errors
- Step Functions MUST have alarms for failed executions
- All alarms MUST route to `pantry-pirate-radio-alerts-{environment}` by ARN convention

---

## 11. Dual Environment Compatibility (NON-NEGOTIABLE)

Per PPR Constitution Principle XV:

- Local: `./bouy beacon build` generates files to local filesystem
- AWS: Lambda generates files to S3 + CloudFront
- Database access via RDS Proxy (AWS) or direct connection (local)
- Build commands work identically in both environments
- Static output is the same regardless of environment

---

## 12. Content Freshness

- Daily scheduled rebuild catches all data changes
- Verification events trigger incremental rebuilds for affected locations
- Sitemap `lastmod` dates reflect actual page generation time
- Stale pages (data changed but not rebuilt) MUST NOT persist beyond 24 hours

---

## 13. Documentation Maintenance (NON-NEGOTIABLE)

- CLAUDE.md updated with every code change
- constitution.md updated via amendment process (see Governance below)
- Template changes documented with variable reference
- New page types require SEO checklist review

---

## Governance

This constitution supersedes all informal practices.

### Amendment Process

1. Propose amendment in written form with rationale
2. Document impact on existing code
3. Version according to semantic versioning (MAJOR/MINOR/PATCH)
4. Add entry to Amendment Log
5. Commit with version increment and date

### Compliance Review

- All pull requests MUST pass constitution check before merge
- Principle violations MUST be explicitly justified with written rationale

---

**Version**: 1.0.0 | **Ratified**: 2026-03-30
