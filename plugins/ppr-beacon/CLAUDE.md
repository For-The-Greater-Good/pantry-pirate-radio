# ppr-beacon

Static site generator for SEO-optimized food pantry mini-sites on plentiful.org/providers.

You must follow the constitution in [constitution.md](constitution.md) when doing any work in this repository.

## Architecture

Python static site generator → Jinja2 templates → S3 + CloudFront. Reads directly from PostgreSQL via RDS Proxy (same pattern as ppr-write-api). Zero JS required for content.

```
PostgreSQL (via RDS Proxy)  →  data_source.py  →  builder.py  →  renderer.py  →  Static HTML
                                                                                      ↓
                                                                               S3 + CloudFront
```

## Commands

```bash
# Via PPR (when installed as plugin)
./bouy beacon build                    # Generate all static pages
./bouy beacon build --location ID      # Generate single location (preview)
./bouy beacon build --state IL         # Generate all locations in a state
./bouy beacon serve                    # Local HTTP preview on :8888
./bouy beacon status                   # Show build statistics
```

## URL Structure (Hub & Spoke)

```
plentiful.org/providers/                                          → Homepage
plentiful.org/providers/illinois/                                 → State page
plentiful.org/providers/illinois/springfield/                     → City page
plentiful.org/providers/illinois/springfield/community-food-bank  → Location detail
plentiful.org/providers/org/feeding-america-eastern-illinois      → Org hub
```

## Source Structure

```
app/
  builder.py       # Orchestrator: query → render → write files
  cli.py           # CLI entrypoint for build/serve/status
  config.py        # Configuration from env vars
  data_source.py   # psycopg2 queries with quality gate
  models.py        # Pydantic context models
  renderer.py      # Jinja2 engine with custom filters
  schema_org.py    # FoodEstablishment + BreadcrumbList JSON-LD
  sitemap.py       # XML sitemap + robots.txt generation
  slug.py          # Deterministic URL slug generation

templates/
  base.html        # Plentiful design system layout
  home.html        # Homepage (browse by state)
  state.html       # State page (cities listing)
  city.html        # City page (location cards)
  location.html    # Location detail page
  organization.html # Org hub page
  partials/        # Header, footer

static/
  css/beacon.css   # Plentiful design system (plain CSS, <15KB)
  js/              # ~1KB analytics tracker
  fonts/           # Noto Sans/Serif (woff2, self-hosted)

infra/
  beacon_stack.py  # CDK: S3, CloudFront, Lambda, Step Functions, EventBridge

tests/
  test_slug.py, test_schema_org.py, test_models.py, test_sitemap.py
```

## Quality Gate

Only human-verified locations get mini-sites:

```sql
WHERE verified_by IN ('admin', 'source') AND confidence_score >= 93
```

## Environment Variables

```bash
# Database (same as ppr-write-api)
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_USER=postgres
DATABASE_PASSWORD=pirate
DATABASE_NAME=pantry_pirate_radio

# AWS
DATABASE_SECRET_ARN=arn:aws:secretsmanager:...
DATABASE_PROXY_ENDPOINT=proxy.rds.amazonaws.com

# Beacon
BEACON_BASE_URL=https://plentiful.org/providers
BEACON_OUTPUT_DIR=./output
BEACON_S3_BUCKET=ppr-beacon-site-dev
BEACON_CLOUDFRONT_DIST_ID=E1234567890
BEACON_ANALYTICS_ENDPOINT=https://analytics.example.com/events
```

## SEO Features

- Schema.org JSON-LD: `FoodEstablishment`, `Organization`, `BreadcrumbList`
- Open Graph + Twitter Card meta tags
- XML sitemap with `lastmod` dates
- `robots.txt` with sitemap reference
- Semantic HTML5 structure
- Click-to-call `tel:` links
- Google Maps directions links
- Zero required JS for content
- Page budget: <100KB HTML, <15KB CSS

## Design System

Styled after plentiful-fe (plentiful.org frontend):
- Fonts: Noto Sans (400, 700) + Noto Serif (400, italic)
- Colors: Green `#00CD96`, black `#0F0F0F`, white `#FFFFFF`
- Buttons: Pill-shaped, `border: 2px solid #0F0F0F`
- Cards: `border-radius: 16px`, white background
- Base font: `62.5%` (10px), rem sizing
- Mobile-first responsive (640, 768, 1024, 1280px breakpoints)

## Testing

```bash
# Run from plugin directory
python -m pytest tests/ -v

# Tests cover:
# - URL slug generation (edge cases, unicode, empty strings)
# - JSON-LD structure validation (Schema.org compliance)
# - Pydantic model validation
# - Sitemap XML structure
```
