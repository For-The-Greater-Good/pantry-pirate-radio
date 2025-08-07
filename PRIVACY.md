# Privacy Policy

> **📚 Documentation**: For complete project documentation including architecture, API reference, and deployment guides, visit our **[Documentation Hub](docs/INDEX.md)**.

## Overview

Pantry Pirate Radio is an AI-powered food security data aggregation system that collects and processes publicly available information about food assistance programs to help people find food resources in their communities. This system operates with a privacy-first design, collecting only public information and never storing personal user data.

## Data We Collect

### Public Food Resource Information
- Organization names and contact information
- Program descriptions and eligibility requirements
- Location data (addresses, geographic coordinates)
- Service hours and availability schedules
- Program types and services offered
- Accessibility information
- Required documents for services

### System Operational Data
- API usage statistics (fully anonymized)
- System performance metrics
- Error logs (without personal identifiers)
- Scraper execution logs (public data sources only)
- Content store efficiency metrics
- Geographic query patterns (aggregated only)

### What We DO NOT Collect
- Personal user information
- Individual search queries
- User location data
- Cookies or tracking identifiers
- Authentication credentials (API is public)
- Any form of personally identifiable information (PII)

## Data Sources

All data is collected from publicly available sources:

### Primary Sources
- Government agency websites and databases
- Non-profit organization public websites
- Public APIs (Vivery, Plentiful, FreshTrak, etc.)
- Community resource directories
- Food bank network websites
- USDA and state food program databases

### Collection Methods
- **Automated Scrapers**: Run via `./bouy scraper --all`
- **API Integrations**: Direct API connections where available
- **Manual Updates**: Community-submitted corrections
- **HAARRRvest Publishing**: Standardized data distribution

## How We Process Data

### Data Collection Pipeline
```bash
# Scraper execution
./bouy scraper --all              # Run all scrapers
./bouy scraper scouting-party     # Parallel execution
./bouy scraper-test --all         # Dry run testing
```

### Data Processing Stages

1. **Collection Phase**:
   - Scrapers collect raw data from public sources
   - Rate limiting ensures respectful data collection
   - Content store manages deduplication

2. **Standardization Phase**:
   - LLM-based alignment to OpenReferral HSDS format
   - Geographic coordinate validation and correction
   - Detection and filtering of invalid coordinates (0,0)
   - Address standardization and geocoding

3. **Quality Assurance**:
   - Duplicate detection and merging
   - Data validation against HSDS schema
   - Version tracking for all changes
   - Automated quality scoring

### Data Storage Architecture
- **Primary Database**: PostgreSQL with PostGIS extensions
- **Cache Layer**: Redis for performance optimization
- **Content Store**: Deduplicated content management
- **Backup System**: Automated daily backups
- **Version Control**: Complete audit trail of all changes

## Data Usage

### Intended Use Cases
- Providing free access to food resource information
- Supporting individuals and families seeking food assistance
- Enabling researchers studying food security
- Facilitating policymakers addressing food access issues
- Powering third-party applications via standardized API

### API Access
- **Public Endpoints**: http://localhost:8000/api/v1/
- **Documentation**: http://localhost:8000/docs
- **Rate Limiting**: Fair use policies enforced
- **Authentication**: None required (public data)
- **Data Format**: OpenReferral HSDS standard

### Data Viewing Options
```bash
# API endpoints (when running)
./bouy up
# Then access: http://localhost:8000/docs

# Datasette viewer (production mode)
./bouy up --prod
# Then access: http://localhost:8001

# Direct database queries
./bouy shell app
# Run SQL queries for analysis
```

## Data Retention

### Resource Data Retention
- **Active Programs**: Retained indefinitely with regular updates
- **Inactive Programs**: Marked as inactive but preserved for historical analysis
- **Closed Programs**: Archived with closure date for research purposes
- **Version History**: All changes tracked with timestamps

### System Data Retention
- **API Logs**: 30-day rolling retention
- **Error Logs**: 30-day retention for debugging
- **Performance Metrics**: 90-day aggregated retention
- **Backup Files**: Configurable retention (default: 7 daily, 4 weekly)
- **Content Store**: Permanent storage with deduplication

### Data Archival
```bash
# Record scraper results
./bouy recorder                   # Save to JSON archives

# Replay archived data
./bouy replay --directory outputs/ # Process archived data
```

## Data Security

### Technical Security Measures
- **Containerization**: All services run in isolated Docker containers
- **Network Isolation**: Internal Docker networks for service communication
- **No PII Storage**: System design prevents PII collection
- **Input Validation**: All data validated via Pydantic models
- **SQL Injection Prevention**: Parameterized queries only
- **Rate Limiting**: API abuse prevention

### Access Control
- **Public Data**: Read-only access via API
- **Administrative Access**: Limited to authorized maintainers
- **Database Access**: Restricted to application services
- **Monitoring**: Continuous security scanning via CI/CD

### Security Testing
```bash
# Run security scans
./bouy test --bandit       # Security linting
./bouy test --safety       # Dependency vulnerabilities
./bouy test --pip-audit    # Package auditing
```

## Data Sharing

### Public API Distribution
- **Format**: OpenReferral HSDS standard
- **Access**: Unrestricted for public benefit
- **Updates**: Real-time as data is processed
- **Attribution**: Source information maintained

### HAARRRvest Integration
- **Purpose**: Standardized data distribution to food assistance networks
- **Format**: HSDS-compliant JSON
- **Frequency**: Configurable (default: daily)
- **Access**: Via HAARRRvest repository

### Research Collaboration
- **Data Availability**: Aggregated datasets for research
- **Format**: CSV, JSON, or SQL dumps
- **Attribution**: Required for all uses
- **Contact**: Via GitHub issues for data requests

## User Rights

### As a Data Consumer
Since we only process public information:
- No user accounts or authentication required
- No personal data collection or storage
- No tracking or profiling of API users
- Full transparency in data sources

### Corrections and Updates
- **Report Issues**: GitHub issues for data corrections
- **Community Contributions**: Pull requests welcome
- **Feedback Mechanism**: API includes feedback endpoints
- **Response Time**: Issues addressed within 7 days

## Data Quality Assurance

### Automated Quality Checks
```bash
# Test data quality
./bouy test --pytest tests/test_reconciler/
./bouy test --pytest tests/test_llm/test_validation.py
```

### Manual Verification
- Community review of data accuracy
- Regular audits of high-traffic resources
- Cross-referencing with official sources
- Feedback loop integration

## Transparency

### Open Source
- **Code**: Fully open source on GitHub
- **Documentation**: Comprehensive public documentation
- **Data Pipeline**: Transparent processing steps
- **Issue Tracking**: Public issue tracker

### Data Lineage
- Every data point traceable to source
- Processing steps documented
- Version history maintained
- Change logs available

## Compliance

This system is designed to comply with:

### Legal Frameworks
- **Public Information Laws**: Only public data collected
- **Web Scraping Ethics**: Respectful rate limiting and robots.txt compliance
- **Fair Use Doctrine**: Educational and charitable purpose
- **GDPR Principles**: Privacy by design, no PII collection

### Industry Standards
- **OpenReferral HSDS**: Full compliance with data standard
- **REST API Standards**: Following best practices
- **Security Standards**: OWASP guidelines followed
- **Accessibility**: WCAG considerations in data presentation

## Changes to This Policy

### Update Process
- Changes tracked in version control
- Community review via pull requests
- Announcement via repository releases
- Effective immediately upon merge to main branch

### Version History
- All versions available in Git history
- Major changes highlighted in releases
- Semantic versioning for policy updates

## Contact Information

### For Privacy Inquiries
- **GitHub Issues**: [Project Repository](https://github.com/For-The-Greater-Good/pantry-pirate-radio/issues)
- **Documentation Hub**: [Complete documentation index](docs/INDEX.md)
- **Community Discussion**: GitHub Discussions

### For Data Corrections
- **Issue Template**: Use "Data Correction" template
- **Include**: Resource name, location, correction needed
- **Response Time**: Within 7 business days

## Developer Privacy

### For Contributors
- Use `./bouy setup` for secure configuration
- Never commit `.env` files
- Test data must use fictional information
- Follow security guidelines in CONTRIBUTING.md

### Testing with Privacy
```bash
# Use test data only
./bouy test               # All tests with sanitized data
./bouy scraper-test NAME  # Dry run without data collection
```

---

**Last Updated**: January 2025
**Policy Version**: 2.0.0
**Effective Date**: Immediate