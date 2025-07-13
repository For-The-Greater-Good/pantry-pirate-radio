# HSDS Directory Structure and Contents

## Core Documentation
- `README.md` - Overview of Open Referral and HSDS
- `CODE_OF_CONDUCT.md` - Project code of conduct
- `CONTRIBUTING.md` - Contribution guidelines
- `LICENSE` - CC BY-SA license information
- `core_tables.csv` - Core table definitions

## Schema Definitions (`/schema/`)
1. Core Objects
   - `organization.json` - Organization schema
   - `service.json` - Service schema
   - `location.json` - Location schema
   - `service_at_location.json` - Service-Location link schema
   - `program.json` - Program collections schema

2. Supporting Objects
   - Contact & Communication
     - `contact.json` - Contact information
     - `phone.json` - Phone numbers
     - `email.json` - Email addresses
     - `url.json` - URL definitions

   - Location & Access
     - `address.json` - Physical addresses
     - `service_area.json` - Service coverage areas
     - `accessibility.json` - Accessibility features
     - `schedule.json` - Operating hours

   - Service Details
     - `cost_option.json` - Service costs
     - `service_capacity.json` - Capacity limits
     - `required_document.json` - Required documentation
     - `language.json` - Language support

   - Classification & Metadata
     - `taxonomy.json` - Classification system
     - `taxonomy_term.json` - Classification terms
     - `attribute.json` - Additional attributes
     - `metadata.json` - Change tracking
     - `meta_table_description.json` - Table descriptions

   - Organization Details
     - `funding.json` - Funding sources
     - `organization_identifier.json` - External IDs
     - `unit.json` - Organizational units

3. API Definitions
   - `openapi.json` - OpenAPI specification

4. Reference Files
   - `/schema/compiled/` - Compiled reference schemas
   - `/schema/simple/schema.csv` - Simplified schema reference

## Example Data (`/examples/`)
1. Core Object Examples
   - Organization Examples
     - `organization_full.json` - Complete organization example
     - `organization_list.json` - List of organizations
   - Service Examples
     - `service_full.json` - Complete service example
     - `service_list.json` - List of services
   - Location Examples
     - `location.json` - Location example
     - `service_at_location_full.json` - Service-Location link
     - `service_at_location_list.json` - List of service-location links

2. Taxonomy Examples
   - `taxonomy.json` - Taxonomy system example
   - `taxonomy_list.json` - List of taxonomies
   - `taxonomy_term.json` - Individual term example
   - `taxonomy_term_list.json` - List of taxonomy terms

3. Format Examples
   - `base.json` - Base JSON structure
   - `tabular.json` - Tabular data format

4. CSV Examples (`/examples/csv/`)
   - Core Tables
     - `organizations.csv` - Organization data
     - `services.csv` - Service data
     - `locations.csv` - Location data
     - `programs.csv` - Program data
     - `service_at_location.csv` - Service-Location links

   - Contact & Communication
     - `contacts.csv` - Contact information
     - `phones.csv` - Phone numbers
     - `addresses.csv` - Physical addresses
     - `url.csv` - URLs and links

   - Service Details
     - `service_capacity.csv` - Capacity information
     - `service_areas.csv` - Coverage areas
     - `cost_options.csv` - Pricing options
     - `required_documents.csv` - Required documentation
     - `languages.csv` - Language support
     - `accessibility.csv` - Accessibility features
     - `schedules.csv` - Operating hours

   - Classification & Metadata
     - `taxonomies.csv` - Classification systems
     - `taxonomy_terms.csv` - Classification terms
     - `attributes.csv` - Additional attributes
     - `metadata.csv` - Change tracking
     - `meta_table_descriptions.csv` - Table descriptions

   - Organization Details
     - `units.csv` - Organizational units
     - `funding.csv` - Funding sources
     - `organization_identifiers.csv` - External IDs

   - Configuration
     - `datapackage.json` - Dataset configuration

5. Tools and Configuration
   - `make_datapackages.py` - Example generation script
   - `datapackage.json` - Package configuration

## Database Support (`/database/`)
- `database_postgresql.sql` - PostgreSQL schema
- `database_mysql.sql` - MySQL schema
- Build scripts:
    - `build_database_postgresql.sh`
    - `build_database_mysql.sh`
    - `requirements_build_database.in` - Build dependencies



## Documentation (`/docs/`)

1. Core Documentation
   - `hsds/overview.md` - HSDS overview and model
   - `hsds/schema_reference.md` - Schema documentation
   - `hsds/api_reference.md` - API documentation
   - `hsds/database_schemas.md` - Database implementation
   - `hsds/changelog.md` - Version history
   - `hsds/hsds_faqs.md` - Frequently asked questions

2. Implementation Guides
   - `hsds/mapping_guidance.md` - Data mapping guide
   - `hsds/conformance.md` - Conformance rules
   - `hsds/field_guidance.md` - Field usage guide
   - `hsds/identifiers.md` - ID management guide
   - `hsds/serialization.md` - Data serialization formats

3. Extension and Profiles
   - `hsds/extending.md` - Extension guidelines
   - `hsds/profiles.md` - Profile definitions
   - `hsds/using_profiles.md` - Profile usage guide
   - `hsds/use_cases.md` - Implementation examples

4. Additional Resources
   - `figures/` - Diagrams and images
   - `_static/` - Static assets
   - `_templates/` - Documentation templates

## Python Tools (`/python/`)
- `openreferral/` - Python utilities
    - `__init__.py` - Package initialization
    - `utils.py` - Utility functions
    - `svg_utils.py` - SVG generation tools

## Validation and Build Tools
- `validate_examples_json_schema.sh` - Schema validation script
- `openapi-examples-map.json` - OpenAPI example mappings
- Build configuration:
    - `requirements.in` - Primary requirements
    - `requirements.txt` - Locked dependencies

## Configuration Files
- `datapackage.json` - Package metadata
- `.readthedocs.yaml` - Documentation build config
- `.gitmodules` - Git submodule configuration
- `.gitignore` - Git ignore patterns
