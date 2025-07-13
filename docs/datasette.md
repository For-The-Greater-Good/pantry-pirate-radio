# Datasette Exporter for Pantry Pirate Radio

This module provides functionality to export data from the Pantry Pirate Radio PostgreSQL database to SQLite files compatible with [Datasette](https://datasette.io/).

## Overview

Datasette is an open-source tool for exploring and publishing data. It helps people take data of any shape or size and publish it as an interactive, explorable website and accompanying API.

This exporter allows you to:

1. Export HSDS data from PostgreSQL to SQLite
2. Run exports on a schedule
3. Maintain a history of exports
4. Serve the data using Datasette with interactive visualizations and advanced features

## Installed Plugins

The Datasette instance comes with the following plugins pre-installed:

1. **[datasette-cluster-map](https://github.com/simonw/datasette-cluster-map)** - Adds a map visualization with clustering for geographic data
2. **[datasette-leaflet](https://github.com/simonw/datasette-leaflet)** - Adds Leaflet maps for latitude/longitude columns
3. **[datasette-graphql](https://github.com/simonw/datasette-graphql)** - Adds GraphQL API support to Datasette
4. **[datasette-dashboards](https://github.com/rclement/datasette-dashboards)** - Adds dashboards with charts and visualizations
5. **[datasette-block-robots](https://github.com/simonw/datasette-block-robots)** - Blocks search engines from indexing the Datasette instance

## Usage

### Command Line Interface

The exporter provides a command-line interface with two main commands:

#### One-time Export

```bash
python -m app.datasette export --output my_export.sqlite
```

Options:
- `--output`, `-o`: Output SQLite file path (default: pantry_pirate_radio.sqlite)
- `--tables`, `-t`: Tables to export (can be used multiple times, defaults to HSDS core tables)
- `--batch-size`, `-b`: Batch size for processing rows (default: 1000)
- `--verbose`, `-v`: Enable verbose logging

#### Scheduled Export

```bash
python -m app.datasette schedule
```

Options:
- `--output-dir`, `-d`: Directory to store SQLite files (default: /data)
- `--interval`, `-i`: Time between exports in seconds (default: from EXPORT_INTERVAL env var or 3600)
- `--filename-template`, `-f`: Template for output filenames (default: pantry_pirate_radio_{timestamp}.sqlite)
- `--keep-latest/--no-keep-latest`: Whether to maintain a 'latest.sqlite' symlink (default: true)
- `--max-files`, `-m`: Maximum number of export files to keep (default: 5, 0 for unlimited)
- `--verbose`, `-v`: Enable verbose logging

### Docker Integration

The exporter is integrated into the Docker Compose setup with two services:

1. `datasette-exporter`: Exports data from PostgreSQL to SQLite on a schedule
2. `datasette`: Serves the exported SQLite file using Datasette

To start these services:

```bash
docker-compose up -d datasette-exporter datasette
```

The Datasette web interface will be available at http://localhost:8001/

## Configuration

The exporter can be configured using environment variables:

- `DATABASE_URL`: PostgreSQL connection string
- `OUTPUT_DIR`: Directory to store SQLite files
- `EXPORT_INTERVAL`: Time between exports in seconds

These can be set in the `.env` file or passed directly to the Docker container.

## Implementation Details

### Architecture

The exporter consists of several components:

1. **Exporter Module**: Core functionality to export data from PostgreSQL to SQLite
2. **Scheduler**: Runs exports on a schedule and manages file retention
3. **CLI**: Command-line interface for manual and scheduled exports
4. **Docker Integration**: Containerized deployment with Datasette

### Data Flow

```
PostgreSQL Database → Exporter → SQLite File → Datasette → Web Interface
```

### Handling PostGIS Data

The exporter handles PostGIS spatial data by:

1. Extracting latitude and longitude as separate columns
2. Storing them as standard numeric values in SQLite
3. Preserving the original coordinate system (WGS 84)

### Tables Exported

By default, the exporter exports the core HSDS tables:

- `organization`: Food pantry/provider details
- `location`: Physical service locations
- `service`: Food distribution programs
- `service_at_location`: Service availability

Additional tables can be specified using the `--tables` option.

### Views Created

The exporter creates several SQL views to make data exploration easier:

- `locations_by_scraper`: Groups locations by their source scraper
- `multi_source_locations`: Shows locations that have data from multiple scrapers
- `location_with_services`: Simplified view of locations with their services and organizations
- `organization_with_services`: Simplified view of organizations with their services
- `service_with_locations`: Simplified view of services with their locations and organizations

These views provide different perspectives on the data and make it easier to explore relationships between entities.

## Development

### Running Tests

```bash
pytest tests/test_datasette
```

### Adding New Features

To add support for additional tables or custom export logic:

1. Modify the `export_to_sqlite` function in `app/datasette/exporter.py`
2. Add appropriate tests in `tests/test_datasette/`
3. Update this documentation as needed
