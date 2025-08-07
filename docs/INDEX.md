# 📚 Pantry Pirate Radio Documentation Index

Welcome to the Pantry Pirate Radio documentation hub! This index provides a comprehensive map of all documentation in the project, organized by category and user level.

## 🚀 Quick Navigation

### For New Contributors
- **Start Here:** [Quick Start Guide](quickstart.md) - Get running in under 10 minutes
- **Setup Wizard:** [Bouy Setup Guide](../BOUY.md#installation) - Interactive configuration
- **Basic Concepts:** [Overview](../README.md#overview) - Mission and core concepts

### For Developers
- **Development Setup:** [CLAUDE.md](../CLAUDE.md) - Development workflow with Claude Code
- **Architecture:** [System Architecture](architecture.md) - Technical design and components
- **API Reference:** [API Documentation](../API_DOCUMENTATION.md) - Complete API endpoints

### For System Administrators
- **Deployment:** [Deployment Guide](deployment.md) - Production deployment
- **Docker Management:** [Bouy Documentation](../BOUY.md) - Fleet management tool
- **Database:** [Database Backup](database-backup.md) - Backup and restore procedures

---

## 📖 Documentation by Category

### 🎯 Getting Started
**For beginners and first-time users**

| Document | Description | User Level |
|----------|-------------|------------|
| [README.md](../README.md) | Project overview, mission, and quick start | Beginner |
| [quickstart.md](quickstart.md) | Complete setup guide in under 10 minutes | Beginner |
| [getting-started-locally.md](getting-started-locally.md) | Local development setup without Docker | Intermediate |
| [docker-quickstart.md](docker-quickstart.md) | Docker-specific quick start guide | Beginner |
| [codespaces-setup.md](codespaces-setup.md) | GitHub Codespaces development | Beginner |
| [claude_setup_guide.md](../claude_setup_guide.md) | Claude AI integration setup | Intermediate |

### 🛠️ Development Guides
**For active contributors and developers**

| Document | Description | User Level |
|----------|-------------|------------|
| [CLAUDE.md](../CLAUDE.md) | Claude Code development workflow and commands | Developer |
| [BOUY.md](../BOUY.md) | Docker fleet management tool reference | Developer |
| [docker-development.md](docker-development.md) | Docker-based development workflow | Developer |
| [test-environment-setup.md](test-environment-setup.md) | Testing environment configuration | Developer |
| [troubleshooting.md](troubleshooting.md) | Common issues and solutions | All |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | Contribution guidelines and standards | Developer |

### 🏗️ Architecture & Design
**Technical architecture and system design**

| Document | Description | User Level |
|----------|-------------|------------|
| [architecture.md](architecture.md) | System architecture and design patterns | Advanced |
| [docker-startup-sequence.md](docker-startup-sequence.md) | Container initialization sequence | Advanced |
| [multi-worker-support.md](multi-worker-support.md) | Distributed worker architecture | Advanced |
| [worker.md](worker.md) | Background job processing system | Advanced |
| [reconciler.md](reconciler.md) | Data reconciliation and deduplication | Advanced |
| [llm.md](llm.md) | LLM integration and configuration | Advanced |

### 📡 API & Data Standards
**API reference and data specifications**

| Document | Description | User Level |
|----------|-------------|------------|
| [API_DOCUMENTATION.md](../API_DOCUMENTATION.md) | Complete REST API reference | Developer |
| [api.md](api.md) | API implementation details | Developer |
| [api-examples.md](api-examples.md) | API usage examples and patterns | Developer |
| [hsds_index.md](hsds_index.md) | Human Services Data Specification overview | All |
| [HSDS Documentation](HSDS/) | Full HSDS v3.1.1 specification | Advanced |

### 🕷️ Data Collection (Scrapers)
**Web scraper documentation and patterns**

| Document | Description | User Level |
|----------|-------------|------------|
| [scrapers.md](scrapers.md) | Scraper system overview | Developer |
| [scraper-patterns.md](scraper-patterns.md) | Common scraping patterns and best practices | Developer |
| [Scraper Documentation](scrapers/) | Individual scraper documentation | Developer |
| [Scraper Template](scrapers/TEMPLATE.md) | Template for new scraper documentation | Developer |
| [Scraper Status](scrapers/SCRAPER_DOCUMENTATION_STATUS.md) | Documentation status tracker | Maintainer |

### 💾 Data Management
**Database, storage, and data handling**

| Document | Description | User Level |
|----------|-------------|------------|
| [database-backup.md](database-backup.md) | Backup and restore procedures | Admin |
| [datasette.md](datasette.md) | Datasette data viewer configuration | Developer |
| [recorder.md](recorder.md) | Data recording and replay system | Developer |
| [haarrrvest-publisher.md](haarrrvest-publisher.md) | HAARRRvest repository publisher | Advanced |
| [haarrvest-quickstart.md](haarrvest-quickstart.md) | HAARRRvest quick setup | Intermediate |

### 🚀 Deployment & Operations
**Production deployment and operations**

| Document | Description | User Level |
|----------|-------------|------------|
| [deployment.md](deployment.md) | Production deployment guide | Admin |
| [GITHUB_WORKFLOWS.md](GITHUB_WORKFLOWS.md) | CI/CD pipeline documentation | DevOps |
| [GITHUB_SECURITY_SETTINGS.md](GITHUB_SECURITY_SETTINGS.md) | Security configuration | Admin |
| [setup-github-pages-data.md](setup-github-pages-data.md) | GitHub Pages data publishing | Admin |

### 📋 Policies & Standards
**Project policies and standards**

| Document | Description | User Level |
|----------|-------------|------------|
| [PRIVACY.md](../PRIVACY.md) | Privacy policy and data handling | All |
| [SECURITY.md](../SECURITY.md) | Security policy and reporting | All |
| [LICENSE](../LICENSE) | Project license (sandia-ftgg-nc-os-1.0) | All |

### 📊 Data Analysis
**SQL queries and data analysis tools**

| Document | Location | Description |
|----------|----------|-------------|
| Organization Directory | [queries/01_organization_contact_directory.sql](queries/01_organization_contact_directory.sql) | Contact information query |
| Location Details | [queries/02_location_details.sql](queries/02_location_details.sql) | Location data query |
| Service Offerings | [queries/03_service_offerings.sql](queries/03_service_offerings.sql) | Available services query |
| Outreach Model | [queries/04_comprehensive_outreach_model.sql](queries/04_comprehensive_outreach_model.sql) | Full outreach data |
| Optimized Model | [queries/05_optimized_outreach_model.sql](queries/05_optimized_outreach_model.sql) | Performance-optimized query |

### 🌍 Geographic Data
**Geographic reference data and utilities**

| Document | Description | Purpose |
|----------|-------------|---------|
| [GeoJson States](GeoJson/States/) | US state ZIP code GeoJSON files | Geographic boundaries |
| [GeoJson README](GeoJson/States/README.md) | GeoJSON data documentation | Data format reference |

---

## 🎓 Documentation by User Level

### 👶 Beginner
Start here if you're new to the project:
1. [README.md](../README.md) - Project overview
2. [quickstart.md](quickstart.md) - Quick setup guide
3. [docker-quickstart.md](docker-quickstart.md) - Docker basics
4. [BOUY.md](../BOUY.md#installation) - Setup wizard

### 👨‍💻 Developer
For active development:
1. [CLAUDE.md](../CLAUDE.md) - Development workflow
2. [architecture.md](architecture.md) - System design
3. [API_DOCUMENTATION.md](../API_DOCUMENTATION.md) - API reference
4. [scrapers.md](scrapers.md) - Data collection system

### 🚀 Advanced
For system administrators and architects:
1. [deployment.md](deployment.md) - Production deployment
2. [multi-worker-support.md](multi-worker-support.md) - Scaling
3. [reconciler.md](reconciler.md) - Data processing
4. [GITHUB_WORKFLOWS.md](GITHUB_WORKFLOWS.md) - CI/CD

---

## 🔍 Key Documentation Relationships

### Core Documentation Flow
```
README.md (Overview)
    ├── quickstart.md (Getting Started)
    │   ├── BOUY.md (Docker Management)
    │   └── CLAUDE.md (Development)
    ├── architecture.md (Technical Design)
    │   ├── API_DOCUMENTATION.md (API)
    │   ├── scrapers.md (Data Collection)
    │   └── reconciler.md (Processing)
    └── deployment.md (Production)
        ├── GITHUB_WORKFLOWS.md (CI/CD)
        └── database-backup.md (Operations)
```

### Data Flow Documentation
```
scrapers.md (Collection)
    ├── scraper-patterns.md (Patterns)
    ├── scrapers/* (Individual Scrapers)
    └── recorder.md (Recording)
        └── reconciler.md (Processing)
            └── haarrrvest-publisher.md (Publishing)
                └── datasette.md (Viewing)
```

---

## 📝 Most Important Documents for New Contributors

1. **[README.md](../README.md)** - Start here for project overview
2. **[quickstart.md](quickstart.md)** - Get the system running quickly
3. **[CLAUDE.md](../CLAUDE.md)** - Essential development workflow
4. **[BOUY.md](../BOUY.md)** - Docker management commands
5. **[architecture.md](architecture.md)** - Understand the system design
6. **[API_DOCUMENTATION.md](../API_DOCUMENTATION.md)** - API endpoints and usage
7. **[CONTRIBUTING.md](../CONTRIBUTING.md)** - How to contribute

---

## 🔧 Specialized Documentation

### HSDS (Human Services Data Specification)
The [HSDS directory](HSDS/) contains the complete OpenReferral HSDS v3.1.1 specification:
- [Overview](HSDS/docs/hsds/overview.md) - HSDS introduction
- [Schema Reference](HSDS/docs/hsds/schema_reference.md) - Data model
- [API Reference](HSDS/docs/hsds/api_reference.md) - HSDS API spec
- [Field Guidance](HSDS/docs/hsds/field_guidance.md) - Field usage
- [Use Cases](HSDS/docs/hsds/use_cases.md) - Implementation examples

### Scraper Documentation
Individual scraper documentation in [scrapers/](scrapers/):
- Currently documented: 15+ scrapers
- Template available for new scrapers
- Status tracking for documentation completeness

### Examples and Templates
- [examples/](../examples/) - Code examples and samples
- [scrapers/TEMPLATE.md](scrapers/TEMPLATE.md) - Scraper documentation template
- [api-examples.md](api-examples.md) - API usage examples

---

## 📌 Quick Links

### Essential Commands
- **Setup:** `./bouy setup`
- **Start:** `./bouy up`
- **Test:** `./bouy test`
- **Logs:** `./bouy logs app`
- **Stop:** `./bouy down`

### Service URLs (Development)
- **API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs
- **Datasette:** http://localhost:8001 (production mode)
- **RQ Dashboard:** http://localhost:9181

### Support Resources
- **GitHub Issues:** [Report problems](https://github.com/For-The-Greater-Good/pantry-pirate-radio/issues)
- **Discussions:** [Ask questions](https://github.com/For-The-Greater-Good/pantry-pirate-radio/discussions)
- **Security:** [Security policy](../SECURITY.md)

---

## 📈 Documentation Maintenance

This index is maintained as part of the project documentation. When adding new documentation:
1. Add entry to appropriate category section
2. Update user level classification
3. Add to documentation relationships if applicable
4. Update "Most Important Documents" if relevant

Last Updated: 2025-08-07