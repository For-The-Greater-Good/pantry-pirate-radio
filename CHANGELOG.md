# Changelog

All notable changes to Pantry Pirate Radio will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Repository references cleanup and documentation updates
- CONTRIBUTING.md with comprehensive development guidelines
- CHANGELOG.md for version history tracking

### Changed
- Updated all repository URLs from GitLab to GitHub
- Fixed broken documentation links
- Improved repository structure for public release

### Fixed
- Updated badges to use GitHub Actions instead of GitLab CI
- Fixed placeholder URLs in datasette-metadata.json
- Updated clone URLs in documentation

## [0.1.0] - 2024-XX-XX

### Added
- Initial release of Pantry Pirate Radio
- AI-powered food security data aggregation system
- Full OpenReferral HSDS v3.1.1 compliance
- Multi-stage Docker architecture with containerized services
- FastAPI server with comprehensive API endpoints
- Redis-based distributed job processing
- LLM-powered data normalization and alignment
- PostgreSQL database with PostGIS for geographic data
- Multiple scraper implementations for data collection
- Reconciler service for data consistency and versioning
- Recorder service for job result archival
- Comprehensive test suite with 90% minimum coverage
- Prometheus metrics integration
- DevContainer support for development
- Complete documentation and API reference

### Core Features
- Data aggregation from multiple food security sources
- Geographic intelligence with continental US coverage
- AI integration for HSDS schema alignment
- Distributed processing pipeline
- Version-controlled data management
- RESTful API with OpenAPI documentation
- Monitoring and metrics collection

### Technical Implementation
- Python 3.11+ with Poetry for dependency management
- FastAPI for API server
- SQLAlchemy with PostgreSQL and PostGIS
- Redis for job queues and caching
- Pydantic for data validation
- Docker Compose for service orchestration
- Comprehensive testing with pytest
- Code quality tools: mypy, ruff, black, bandit
- Security scanning and validation

---

## Release Notes

### Version 0.1.0

This is the initial public release of Pantry Pirate Radio, an AI-powered food security data aggregation system. The system implements the OpenReferral Human Services Data Specification (HSDS) v3.1.1 to provide unified access to food security resources across the continental United States.

**Key Highlights:**
- **AI-Powered Data Processing**: Uses large language models to normalize and align data from various sources into HSDS-compliant format
- **Geographic Intelligence**: Comprehensive coverage of continental US with PostGIS-optimized spatial queries
- **Distributed Architecture**: Scalable containerized services for data collection, processing, and serving
- **High-Quality Data**: Maintains version history, validates data integrity, and provides confidence scoring
- **Developer-Friendly**: Complete API documentation, comprehensive tests, and development tools

**Getting Started:**
See our [README.md](README.md) for quick start instructions and [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.

**License:**
This software is released into the public domain under the Unlicense.