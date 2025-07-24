# Multi-Worker Support for RQ Services

This document describes the multi-worker support added to the Pantry Pirate Radio project, enabling parallel processing of jobs for improved performance.

## Overview

We've added support for running multiple RQ workers within a single container, allowing for better resource utilization and faster job processing. This is particularly useful for LLM processing tasks that can benefit from parallelization.

## Implementation Details

### 1. Multi-Worker Script (`scripts/multi_worker.sh`)

A new script that manages multiple RQ worker processes within a single container:
- Uses process substitution to run workers in parallel
- Monitors all worker processes and exits if any fail
- Supports configurable number of workers via `WORKER_COUNT` environment variable
- Properly handles signals for graceful shutdown

### 2. Container Startup Script Updates (`scripts/container_startup.sh`)

Enhanced to support multi-worker mode:
- Checks `WORKER_COUNT` environment variable
- Falls back to single worker mode if not specified or set to 1
- Launches multi-worker script when `WORKER_COUNT` > 1

### 3. Docker Configuration Updates

#### Dockerfile
- Added `multi_worker.sh` script to the worker container
- Made both startup scripts executable

#### docker-compose.yml
- Added `WORKER_COUNT` environment variable support
- Added `QUEUE_NAME` environment variable for queue specification
- Workers can now be scaled using: `docker-compose up -d --scale worker=3`

### 4. Scraper Service Updates

Added Playwright browser support to the scraper container:
- Installed all required system dependencies for Chromium
- Added `playwright install chromium` command
- Added `playwright install-deps chromium` command
- Ensures GetFull.app browser scraper can run properly

## Usage

### Running Multiple Workers in a Single Container

Set the `WORKER_COUNT` environment variable:
```bash
WORKER_COUNT=4 docker-compose up -d worker
```

### Scaling Worker Containers

Use Docker Compose scaling:
```bash
docker-compose up -d --scale worker=3
```

### Combining Both Approaches

You can run multiple containers, each with multiple workers:
```bash
WORKER_COUNT=2 docker-compose up -d --scale worker=3
# Results in 3 containers × 2 workers = 6 total workers
```

## Benefits

1. **Improved Performance**: Parallel processing of LLM jobs
2. **Better Resource Utilization**: Full use of available CPU cores
3. **Flexible Scaling**: Scale both containers and workers per container
4. **Backward Compatible**: Falls back to single worker if not configured
5. **Graceful Shutdown**: Proper signal handling for clean exits

## Monitoring

Monitor worker status using RQ Dashboard at http://localhost:9181

Workers will appear with their container hostname and process ID, making it easy to track which worker is processing which job.

## Troubleshooting

### Workers Not Starting
- Check logs: `docker-compose logs worker`
- Verify Redis is running: `docker-compose ps redis`
- Check environment variables are set correctly

### Performance Issues
- Monitor CPU usage: `docker stats`
- Adjust `WORKER_COUNT` based on available resources
- Consider scaling containers instead of workers per container for better isolation

### Signal Handling
- The multi-worker script properly forwards signals to all child processes
- Use `docker-compose stop` for graceful shutdown
- Avoid `docker-compose kill` unless necessary