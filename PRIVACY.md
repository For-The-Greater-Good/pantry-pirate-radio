# Privacy Policy

## Overview

Pantry Pirate Radio is a food security data aggregation system that collects and processes publicly available information about food assistance programs to help people find food resources in their communities.

## Data We Collect

### Public Food Resource Information
- Organization names and contact information
- Program descriptions and eligibility requirements
- Location data (addresses, coordinates)
- Service hours and availability
- Program types and services offered

### System Data
- API usage statistics (anonymized)
- System performance metrics
- Error logs (without personal identifiers)

## Data Sources

All data is collected from publicly available sources including:
- Government agencies and their websites
- Non-profit organizations' public websites
- Public databases and APIs
- Community resource directories

## How We Process Data

### Data Collection
- Automated scraping of public websites and APIs
- Manual verification of data accuracy
- Regular updates to ensure current information

### Data Processing
- LLM-based data standardization using OpenReferral HSDS format
- Geographic validation and coordinate generation
- Duplicate detection and removal
- Data quality scoring and validation

### Data Storage
- All data is stored in PostgreSQL with PostGIS extensions
- Regular automated backups with configurable retention
- Version tracking for all data changes

## Data Usage

### Intended Use
- Providing food resource information to individuals and families in need
- Supporting researchers and policymakers working on food security
- Enabling other applications and services to access standardized food resource data

### API Access
- Public API endpoints for accessing food resource data
- Rate limiting based on fair use policies
- No authentication required for public data access

## Data Retention

### Resource Data
- Food resource information is retained indefinitely to maintain historical records
- Inactive or closed programs are marked as such but preserved for research purposes

### System Logs
- Performance and error logs are retained for 30 days
- Backup files are retained according to configured retention policies

### Version History
- All data changes are tracked with timestamps
- Historical versions are maintained for audit purposes

## Data Security

### Technical Measures
- All data is considered public information
- No personally identifiable information (PII) is collected
- Secure database configuration with regular updates
- API rate limiting to prevent abuse

### Access Controls
- Read-only public API access
- Administrative access restricted to authorized personnel
- Regular security audits and updates

## Data Sharing

### Public API
- All processed data is available through public API endpoints
- Data is provided in OpenReferral HSDS format
- No restrictions on use of public data

### Research and Academic Use
- Aggregated data may be shared with researchers
- No individual-level data is shared
- All shared data maintains public source attribution

## User Rights

Since we only collect publicly available information and do not collect personal data:
- No personal accounts or profiles are created
- No personal information is stored or processed
- No cookies or tracking mechanisms are used for individuals

### Contact Information
If you have questions about data accuracy or wish to report issues:
- Submit issues through our GitHub repository
- Contact information is available in our public documentation

## Data Quality and Accuracy

### Verification Process
- Regular automated checks for data freshness
- Community feedback mechanisms for corrections
- Source attribution for all data points

### Error Reporting
- Users can report inaccurate or outdated information
- Issues are tracked and addressed through our public issue tracker
- Updates are processed regularly

## Changes to This Policy

This privacy policy may be updated to reflect changes in our data practices or legal requirements. All changes will be:
- Documented in our version control system
- Announced through our public communication channels
- Effective immediately upon posting

## Compliance

This system is designed to comply with:
- Public information access laws
- Fair use principles for web scraping
- OpenReferral HSDS data standards
- General data protection best practices

## Contact

For questions about this privacy policy or our data practices:
- GitHub Issues: [Project Repository](https://github.com/For-The-Greater-Good/pantry-pirate-radio/issues)
- Documentation: Available in the project repository

Last updated: January 2024