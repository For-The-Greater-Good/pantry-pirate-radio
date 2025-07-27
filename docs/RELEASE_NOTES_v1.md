# 🏴‍☠️ Pantry Pirate Radio v1.0 - "Hoist the Jolly Roger"

*Ahoy, food security advocates! We're raising our flag and setting sail on the open seas of data liberation!*

## 🎉 Initial Public Release

We're thrilled to announce the first public release of **Pantry Pirate Radio** - a distributed food security data aggregation system that breaks down information barriers by unifying scattered food resource data into a standardized, accessible format.

## 🗺️ Charting New Waters

### What is Pantry Pirate Radio?

Pantry Pirate Radio is your trusty crew for navigating the choppy waters of food security data. We sail the digital seas, collecting treasures of information from various ports (data sources), and deliver them in a unified, HSDS-compliant format that makes public resources truly accessible.

### 🏴‍☠️ Why "Pirates"?

Like the radio pirates of old who broke broadcasting monopolies to bring music to the masses, we're breaking down information silos to bring food security data to everyone who needs it. No gatekeepers, no barriers - just open access to vital community resources.

## ⚓ Key Features in v1.0

### 🌊 Full HSDS v3.1.1 Compliance
- Complete implementation of OpenReferral Human Services Data Specification
- AI-powered field validation with confidence scoring (minimum 0.85 threshold)
- Sophisticated TypedDict schema enforcement across all entities
- Weighted validation system for required fields (0.05-0.25 deductions)

### 🦜 Dual LLM Provider System
- **OpenAI Integration**: Via OpenRouter API with structured JSON output
- **Claude Integration**: Native Claude Code SDK with two authentication methods:
  - API key authentication for production deployments
  - CLI authentication with shared state across scaled workers
- Intelligent retry logic:
  - Authentication failures: 5-minute retries for 1 hour
  - Quota exceeded: Exponential backoff (1h → 4h max)
- Provider selection via `LLM_PROVIDER` environment variable

### 🗃️ Content-Addressable Deduplication
- SHA-256 based content store preventing duplicate LLM processing
- SQLite index for O(1) lookup performance
- Automatic integration with scrapers and workers
- Synced to HAARRRvest repository for durable backup
- Saves 20-30% on LLM processing costs through deduplication

### 🗺️ Geographic Intelligence System
- Continental US coverage (25°N to 49°N, -125°W to -67°W)
- PostGIS spatial indexing with optimized queries
- Smart grid generation (80-mile diagonal maximum)
- Automatic request partitioning for large areas
- Tile-based caching for API performance

### 🏴‍☠️ Powerful Scraper Framework
Build scrapers in minutes with our comprehensive toolkit:

**Base Framework**:
- `ScraperJob` base class handles the entire lifecycle
- Built-in `ScraperUtils` for queue management and grid generation
- `GeocoderUtils` with rate-limited geocoding (Nominatim & ArcGIS)
- Automatic content deduplication via SHA-256 hashing
- Prometheus metrics for monitoring scraper performance

**Developer Tools**:
- Standard headers management with browser-like User-Agent
- Geographic grid generation for area-based searches
- Priority-based job submission to Redis queue
- Metadata tracking (scraper_id, source_type, priority)
- Test mode for validation without processing

**Easy Implementation**:
```python
class YourScraper(ScraperJob):
    def __init__(self):
        super().__init__(scraper_id="your_scraper")

    async def scrape(self) -> str:
        # Your data collection logic here
        return json.dumps(data)
```

**Production Ready**:
- Rate limiting and retry logic built-in
- Error recovery and circuit breaking
- Parallel execution support
- Comprehensive test framework
- Currently powering 12+ scrapers with hundreds more planned

### ⚙️ Microservices Architecture
- **Scrapers**: Inherit from `ScraperJob` base class with built-in utilities
- **Redis Queue**: Priority-based job processing with metadata tracking
- **LLM Workers**: Horizontally scalable with shared authentication
- **Reconciler**: Version-controlled entity deduplication
- **Recorder**: JSON archival with daily organization
- **HAARRRvest Publisher**: Automated Git-based data publishing
- **API Server**: Read-only HSDS endpoints with OpenAPI docs

### 🔄 Automated Publishing Pipeline
- HAARRRvest Publisher service monitors recorder outputs
- Creates date-based branches (e.g., `data-update-2025-01-27`)
- Generates SQLite database for Datasette visualization
- Exports location data for interactive web maps
- Merges to main with proper commit history
- Runs every 5 minutes or on-demand

### 📊 Enterprise-Grade Quality
- **90%+ test coverage** with pytest suite
- **Type safety** with mypy strict mode
- **Security scanning** with bandit
- **Code quality** with black, ruff, and vulture
- **CI/CD pipeline** with automated checks
- **Prometheus metrics** for monitoring
- **Health endpoints** for all services

### 🚀 Developer Experience
- **Test-Driven Development** workflow enforced
- **Poetry** for dependency management
- **Docker Compose** for local development
- **DevContainer** support for VSCode
- **Comprehensive documentation** in `/docs`
- **CLAUDE.md** for AI pair programming

## 🔧 Technical Specifications

### Database Layer
- PostgreSQL 15+ with PostGIS extensions
- HSDS-compliant schema with version tracking
- Spatial indexes on geographic data
- Automated backup with retention policies

### Processing Pipeline
```
Scrapers → Redis Queue → LLM Workers → Reconciler → PostgreSQL → API
    ↓                                       ↓
Recorder → JSON Files → HAARRRvest Publisher → HAARRRvest Repository
```

### Environment Configuration
- Comprehensive `.env.example` with all settings
- Support for multiple LLM providers
- Configurable Redis TTL (default: 30 days)
- Content store path configuration
- GitHub repository integration

## 🚀 Getting Started

```bash
# Clone the repository
git clone https://github.com/For-The-Greater-Good/pantry-pirate-radio.git
cd pantry-pirate-radio

# Copy environment variables
cp .env.example .env
# Edit .env with your API keys and configuration

# Start all services
docker-compose up -d

# Scale workers for production
docker-compose up -d --scale worker=3

# Visit the API documentation
open http://localhost:8000/docs

# Run scrapers
python -m app.scraper --list  # See available scrapers
python -m app.scraper --all --parallel --max-workers 4
```

## 🏴‍☠️ Join the Crew!

We're looking for fellow data pirates to join our mission:

- **Scraper Contributors**: Add new food resource data sources using our framework
- **Data Quality**: Help improve HSDS alignment and validation
- **API Consumers**: Build applications using our standardized data
- **Documentation**: Improve guides and examples
- **Testing**: Expand test coverage and scenarios

## 🎯 What's Next on the Horizon?

- GraphQL API endpoint for flexible queries
- Real-time WebSocket updates for data changes
- Mobile-optimized progressive web app
- Multi-language support for international expansion
- Community validation and crowdsourcing features
- Advanced analytics and trend detection

## 🙏 Acknowledgments

Special thanks to:
- The OpenReferral community for the HSDS specification
- All food banks and pantries serving communities
- Claude and the Anthropic team for AI assistance
- Our contributors and early adopters
- The open source community for amazing tools

## 📜 License

Licensed under the **Sandia Non-Commercial Open Source License (FTGG Variant)** - because food security data belongs to everyone, but we must ensure it's used ethically and for the greater good.

## 🔒 Security

- No personal data collection
- Read-only API access
- Rate limiting for fair use
- Comprehensive error handling
- Regular security updates

---

*"Information wants to be free, especially when it helps feed people!"*

**Fair winds and following seas,**
The Pantry Pirate Radio Crew 🏴‍☠️

[GitHub](https://github.com/For-The-Greater-Good/pantry-pirate-radio) | [API Docs](https://github.com/For-The-Greater-Good/pantry-pirate-radio/blob/main/API_DOCUMENTATION.md) | [Architecture](https://github.com/For-The-Greater-Good/pantry-pirate-radio/blob/main/docs/architecture.md)

*For The Greater Good (FTGG) - Making public resources truly accessible through intelligent aggregation*