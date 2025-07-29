# Pantry Pirate Radio Documentation

A comprehensive guide to understanding, using, and contributing to Pantry Pirate Radio.

## Quick Navigation

### 🚀 Getting Started
- **[Quick Start Guide](quickstart.md)** - API usage in minutes
- **[Docker Quick Start](docker-quickstart.md)** - Run with Docker (`./bouy up --with-init`)
- **[Bouy Command Reference](../BOUY.md)** - Complete Docker fleet management guide
- **[Local Development Setup](getting-started-locally.md)** - Full development environment
- **[HAARRRvest Data Access](haarrvest-quickstart.md)** - Access our food resource data

### 🏗️ Architecture & Design
- **[Architecture Overview](architecture.md)** - System design and components
- **[API Reference](api.md)** - Complete endpoint documentation
- **[API Examples](api-examples.md)** - Practical usage examples
- **[HSDS Implementation](hsds_index.md)** - OpenReferral compliance details

### 👨‍💻 Development
- **[Bouy Command Reference](../BOUY.md)** - Docker fleet management with bouy
- **[Docker Development](docker-development.md)** - Container-based development
- **[Docker Startup Sequence](docker-startup-sequence.md)** - Service orchestration details
- **[Test Environment Setup](test-environment-setup.md)** - ⚠️ Critical: Configure test isolation
- **[Scraper Implementation Guide](scrapers.md)** - Adding data sources
- **[LLM System](llm.md)** - AI-powered data processing
- **[Troubleshooting](troubleshooting.md)** - Common issues and solutions

### 🔧 Services & Components
- **[Worker System](worker.md)** - Distributed job processing
- **[Reconciler Service](reconciler.md)** - Data deduplication
- **[Recorder Service](recorder.md)** - Job result archival
- **[HAARRRvest Publisher](haarrrvest-publisher.md)** - Data publishing pipeline
- **[Multi-Worker Support](multi-worker-support.md)** - Scaling workers

### 🚀 Operations & Deployment
- **[Deployment Guide](deployment.md)** - Production deployment
- **[Database Backup](database-backup.md)** - Backup strategies
- **[Secret Management](secret-management.md)** - Credential handling
- **[GitHub Workflows](GITHUB_WORKFLOWS.md)** - CI/CD pipeline
- **[GitHub Security Settings](GITHUB_SECURITY_SETTINGS.md)** - Security configuration

### 📊 Data & Queries
- **[SQL Queries](queries/)** - Example database queries
- **[Datasette Guide](datasette.md)** - Data exploration tool
- **[Individual Scrapers](scrapers/)** - Scraper-specific documentation

### 📚 Additional Resources
- **[HSDS Specification](HSDS/)** - Human Services Data Specification
- **[GeoJSON Reference](GeoJson/States/)** - US state geographic data
- **[Release Notes](RELEASE_NOTES_v1.md)** - Version 1.0 release information

### 🤝 Project Information
- **[Contributing](../CONTRIBUTING.md)** - Contribution guidelines
- **[Security Policy](../SECURITY.md)** - Security practices
- **[Privacy Policy](../PRIVACY.md)** - Data privacy
- **[Changelog](../CHANGELOG.md)** - Version history

## Finding What You Need

### By Task

**"I want to..."**

- **Use the API** → Start with [Quick Start](quickstart.md) then see [API Examples](api-examples.md)
- **Run locally with Docker** → Use [Docker Quick Start](docker-quickstart.md)
- **Set up development environment** → Follow [Getting Started Locally](getting-started-locally.md)
- **Add a new data source** → Read [Scraper Implementation Guide](scrapers.md)
- **Deploy to production** → See [Deployment Guide](deployment.md)
- **Understand the architecture** → Study [Architecture Overview](architecture.md)
- **Debug an issue** → Check [Troubleshooting](troubleshooting.md)
- **Scale the system** → Configure [Multi-Worker Support](multi-worker-support.md)

### By Component

- **API Server** → [API Reference](api.md), [API Examples](api-examples.md)
- **Scrapers** → [Scraper Guide](scrapers.md), [Individual Scrapers](../app/scraper/)
- **Workers** → [Worker System](worker.md), [LLM System](llm.md)
- **Database** → [Database Backup](database-backup.md), [SQL Queries](queries/)
- **Docker** → [Docker Development](docker-development.md), [Docker Startup](docker-startup-sequence.md)

## Key Commands Reference

```bash
# Quick start with data
./bouy up --with-init

# Development mode
./bouy up --dev

# Run tests
./bouy test --pytest

# Run scrapers
./bouy scraper --list
./bouy scraper nyc_efap_programs

# Access API docs
open http://localhost:8000/docs

# For more commands, see the Bouy Command Reference
```

## Documentation Map

```
pantry-pirate-radio/
├── BOUY.md                 # Bouy command reference
├── CLAUDE.md               # Claude AI assistant guide
├── docs/                   # Main documentation
│   ├── README.md          # This file - documentation index
│   ├── quickstart.md      # API quick start
│   ├── docker-*.md        # Docker guides
│   ├── *.md               # Service and feature docs
│   ├── queries/           # SQL examples
│   ├── HSDS/              # HSDS specification
│   └── GeoJson/           # Geographic data
├── app/scraper/*.md       # Individual scraper docs
├── CONTRIBUTING.md        # How to contribute
├── CHANGELOG.md           # Version history
├── SECURITY.md            # Security policy
├── PRIVACY.md             # Privacy policy
└── README.md              # Project overview
```

---

For the main project overview, see the [root README](../README.md).