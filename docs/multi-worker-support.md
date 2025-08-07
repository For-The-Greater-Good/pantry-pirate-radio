# Multi-Worker Support Documentation

This document describes the multi-worker architecture in Pantry Pirate Radio, enabling parallel processing of jobs for improved performance and scalability. The system supports both multiple workers per container and scaling containers horizontally.

## Overview

We've added support for running multiple RQ workers within a single container, allowing for better resource utilization and faster job processing. This is particularly useful for LLM processing tasks that can benefit from parallelization.

## Architecture Overview

The multi-worker system uses a unified Docker image (`pantry-pirate-radio:latest`) with intelligent routing based on service type and configuration. Workers can be scaled in two dimensions:
1. **Vertical Scaling**: Multiple worker processes per container (`WORKER_COUNT`)
2. **Horizontal Scaling**: Multiple container instances (Docker Compose scaling)

## Implementation Details

### 1. Multi-Worker Script (`scripts/multi_worker.sh`)

Manages multiple RQ worker processes within a single container:
- **Process Management**: Runs workers in parallel with individual PID tracking
- **Worker Naming**: Unique names using container hostname and worker index
- **Queue Support**: Configurable queue via `QUEUE_NAME` (default: llm)
- **Claude Integration**: Uses custom Claude worker for LLM queue
- **Auto-Recovery**: Automatically restarts failed workers after 10 seconds
- **Signal Handling**: Graceful shutdown on SIGTERM/SIGINT
- **Redis Cleanup**: Removes stale worker registrations on startup

### 2. Container Startup Script (`scripts/container_startup.sh`)

Orchestrates worker initialization with Claude authentication:
- **Claude CLI Check**: Verifies Claude CLI installation
- **Authentication Status**: Checks and reports Claude auth state
- **Worker Count Validation**: Ensures WORKER_COUNT is 1-20
- **Health Server**: Optionally starts health endpoint on port 8080
- **Mode Selection**:
  - Single worker: Direct execution with Claude worker for LLM queue
  - Multi-worker: Delegates to `multi_worker.sh`
- **User Guidance**: Provides authentication instructions if needed

### 3. Docker Configuration

#### Unified Dockerfile (`.docker/images/app/Dockerfile`)
- **Single Image**: All services use the same base image
- **Claude CLI**: Installed globally via npm
- **Playwright**: Chromium browser for web scraping
- **Scripts**: All startup and worker scripts included
- **Entrypoint**: `docker-entrypoint.sh` routes to appropriate service

#### Docker Compose Configuration (`.docker/compose/base.yml`)
- **Worker Service**:
  ```yaml
  worker:
    image: pantry-pirate-radio:latest
    command: ["worker"]
    ports:
      - "8080-8089:8080"  # Health check port range
    environment:
      - CLAUDE_HEALTH_SERVER=true
      - QUEUE_NAME=llm
      - WORKER_COUNT=${WORKER_COUNT:-1}
  ```
- **Port Range**: 8080-8089 allows up to 10 container instances
- **Shared Volumes**: Claude config shared across all workers

### 4. Worker Types and Queue Processing

#### LLM Queue Workers
- **Script**: `scripts/claude_worker.py`
- **Features**: Claude authentication, retry logic, health checks
- **Queue**: Processes 'llm' queue by default
- **Authentication**: Integrates with Claude CLI or API key

#### Standard Workers
- **Command**: Standard RQ worker via `rq.cli`
- **Queues**: recorder, reconciler, scraper, etc.
- **Usage**: For non-LLM processing tasks

### 5. Health Monitoring

#### Claude Health Server
- **Endpoint**: `http://localhost:8080/health`
- **Enabled via**: `CLAUDE_HEALTH_SERVER=true`
- **Response**: JSON with worker status and auth state
- **Port Range**: 8080-8089 for multiple containers

## Usage

### Using Bouy Commands (Recommended)

```bash
# Start with default single worker
./bouy up worker

# Start with multiple workers per container
WORKER_COUNT=4 ./bouy up worker

# View worker logs
./bouy logs worker

# Check worker status
./bouy ps | grep worker
```

### Running Multiple Workers in a Single Container

```bash
# Set via environment variable
export WORKER_COUNT=4
./bouy up worker

# Or inline
WORKER_COUNT=4 ./bouy up worker

# Verify in logs
./bouy logs worker | grep "Starting 4 RQ workers"
```

### Scaling Worker Containers

```bash
# Start services first
./bouy up

# Scale to multiple containers
docker compose -f .docker/compose/base.yml scale worker=3

# Verify scaling
./bouy ps | grep worker
```

### Combining Both Approaches

Maximize parallelism with both vertical and horizontal scaling:

```bash
# Set workers per container
export WORKER_COUNT=2

# Start services
./bouy up

# Scale containers
docker compose -f .docker/compose/base.yml scale worker=3

# Results: 3 containers × 2 workers = 6 total workers
# Each worker appears as: worker-<container-id>-<worker-number>
```

## Benefits

1. **Improved Performance**: Parallel processing of LLM and other jobs
2. **Better Resource Utilization**: Optimal use of CPU and memory
3. **Flexible Scaling**: Two-dimensional scaling options
4. **Fault Tolerance**: Automatic worker restart on failure
5. **Graceful Shutdown**: Clean signal handling and Redis cleanup
6. **Claude Integration**: Native support for Claude API/CLI
7. **Unified Architecture**: Single image simplifies deployment
8. **Health Monitoring**: Built-in health check endpoints

## Monitoring

### RQ Dashboard
- **URL**: http://localhost:9181
- **Features**: Real-time job processing, queue status, worker health
- **Worker Identification**: `worker-<container-id>-<number>`

### Health Endpoints
```bash
# Check worker health (if CLAUDE_HEALTH_SERVER=true)
curl http://localhost:8080/health

# Response example:
{
  "status": "healthy",
  "claude_authenticated": true,
  "worker_count": 4,
  "queue": "llm"
}
```

### Logs
```bash
# View all worker logs
./bouy logs worker

# Follow specific worker container
docker logs -f pantry-pirate-radio_worker_1

# Filter for specific worker
./bouy logs worker | grep "worker-.*-2"
```

### Redis Monitoring
```bash
# Check worker registrations
./bouy exec cache redis-cli
> KEYS rq:worker:*
> HGETALL rq:worker:<worker-name>
```

## Troubleshooting

### Workers Not Starting

1. **Check logs**:
   ```bash
   ./bouy logs worker
   ./bouy logs worker | grep ERROR
   ```

2. **Verify dependencies**:
   ```bash
   ./bouy ps | grep -E "(cache|db)"
   ./bouy exec cache redis-cli ping
   ```

3. **Check environment**:
   ```bash
   ./bouy exec worker env | grep -E "(WORKER_COUNT|QUEUE_NAME|REDIS_URL)"
   ```

4. **Verify Claude authentication** (for LLM workers):
   ```bash
   ./bouy exec worker python -m app.claude_auth_manager status
   ```

### Performance Issues

1. **Monitor resources**:
   ```bash
   docker stats --no-stream
   ./bouy exec worker top
   ```

2. **Optimization strategies**:
   - **CPU-bound tasks**: WORKER_COUNT = CPU cores
   - **I/O-bound tasks**: WORKER_COUNT = 2-4 × CPU cores
   - **Memory constraints**: Reduce WORKER_COUNT or scale horizontally

3. **Recommended configurations**:
   ```bash
   # Development (4-core machine)
   WORKER_COUNT=2 ./bouy up worker
   
   # Production (8-core server)
   WORKER_COUNT=4 ./bouy up
   docker compose scale worker=2  # 8 total workers
   ```

### Signal Handling and Graceful Shutdown

1. **Proper shutdown**:
   ```bash
   # Graceful stop (SIGTERM)
   ./bouy down
   
   # Stop specific service
   docker compose -f .docker/compose/base.yml stop worker
   ```

2. **Force shutdown** (only if necessary):
   ```bash
   docker compose -f .docker/compose/base.yml kill worker
   ```

3. **Cleanup stale workers**:
   ```bash
   # Remove dead worker registrations
   ./bouy exec cache redis-cli --eval "
     local keys = redis.call('keys', 'rq:worker:*')
     for i=1,#keys do
       redis.call('del', keys[i])
     end
     return #keys
   " 0
   ```

### Worker Recovery

Workers automatically restart on failure:
- **Detection**: Health check every 5 seconds
- **Grace Period**: 10-second delay before restart
- **Cleanup**: Stale registrations removed
- **Logging**: Restart events logged with timestamps

## Environment Variables Reference

| Variable | Default | Range | Description |
|----------|---------|-------|-------------|
| `WORKER_COUNT` | 1 | 1-20 | Workers per container |
| `QUEUE_NAME` | llm | - | Queue to process |
| `CLAUDE_HEALTH_SERVER` | true | true/false | Enable health endpoint |
| `REDIS_URL` | redis://cache:6379 | - | Redis connection |
| `LLM_PROVIDER` | claude | claude/openai | LLM provider selection |
| `ANTHROPIC_API_KEY` | - | - | Claude API key (if not using CLI) |

## Best Practices

1. **Development Environment**:
   ```bash
   WORKER_COUNT=2 ./bouy up worker  # Light load
   ```

2. **Production Environment**:
   ```bash
   # High throughput
   WORKER_COUNT=4 ./bouy up
   docker compose scale worker=3  # 12 total workers
   ```

3. **Resource Monitoring**:
   - Set up alerts for high CPU/memory usage
   - Monitor queue lengths in RQ Dashboard
   - Track job failure rates

4. **Scaling Strategy**:
   - Start with vertical scaling (increase WORKER_COUNT)
   - Add horizontal scaling when hitting container limits
   - Use health endpoints for load balancer integration

5. **Debugging**:
   ```bash
   # Single worker for easier debugging
   WORKER_COUNT=1 ./bouy up worker
   ./bouy logs -f worker
   ```