# Docker Configuration

This directory contains all Docker-related configuration files for the Pantry Pirate Radio project.

## Structure

```
.docker/
├── compose/           # Docker Compose files
│   ├── base.yml      # Base service definitions
│   ├── docker-compose.dev.yml         # Development environment
│   ├── docker-compose.dev-with-init.yml  # Dev with DB initialization
│   ├── docker-compose.prod.yml        # Production configuration
│   ├── docker-compose.test.yml        # Test environment
│   ├── docker-compose.with-init.yml   # Base with DB initialization
│   └── docker-compose.github-actions.yml  # CI/CD configuration
├── images/           # Dockerfiles
│   ├── app/         # Main application Dockerfile (multi-stage)
│   └── datasette/   # Datasette service Dockerfile
└── scripts/         # Docker-related scripts
    ├── build.sh     # Build all images
    ├── dev.sh       # Quick dev startup
    └── test.sh      # Run tests in Docker
```

## Usage

### Using the Main Convenience Script

The project includes a `docker.sh` script in the root directory for easy Docker management:

```bash
# Start development environment
./docker.sh up

# Start production environment
./docker.sh up --prod

# Start with database initialization
./docker.sh up --with-init

# View logs
./docker.sh logs [SERVICE]

# Open shell in container
./docker.sh shell app

# Run tests
./docker.sh test

# Stop and clean up
./docker.sh clean
```

### Direct Docker Compose Usage

If you prefer using docker compose directly:

```bash
# Development
docker compose -f .docker/compose/base.yml -f .docker/compose/docker-compose.dev.yml up -d

# Production
docker compose -f .docker/compose/docker-compose.prod.yml up -d

# Test
docker compose -f .docker/compose/docker-compose.test.yml run --rm test
```

### Environment Variables

All services use environment variables from the `.env` file in the project root. Copy `.env.example` to `.env` and configure as needed.

## Services

- **app**: FastAPI application server
- **worker**: Redis queue worker for LLM processing
- **recorder**: Records job results to JSON files
- **scraper**: Runs food security data scrapers
- **reconciler**: Reconciles data from multiple sources
- **haarrrvest-publisher**: Publishes data to HAARRRvest repository
- **db**: PostgreSQL with PostGIS
- **cache**: Redis for job queuing
- **datasette**: Data exploration interface
- **rq-dashboard**: Redis queue monitoring

## Backward Compatibility

A symlink `docker-compose.yml` is maintained in the root directory pointing to `.docker/compose/base.yml` for backward compatibility with existing scripts and workflows.