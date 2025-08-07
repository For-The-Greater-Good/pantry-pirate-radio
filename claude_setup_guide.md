# Claude Authentication Setup Guide

## Quick Start

1. **Initial setup and start containers:**
   ```bash
   ./bouy setup                # Interactive setup wizard (if not done already)
   ./bouy up                   # Start all services
   ```

2. **Check Claude status:**
   ```bash
   curl http://localhost:8080/health
   # Or use bouy to check service status
   ./bouy ps
   ```

3. **If authentication is needed:**
   ```bash
   ./bouy claude-auth setup
   # Or directly via exec:
   ./bouy exec worker python -m app.claude_auth_manager setup
   ```

4. **Verify authentication:**
   ```bash
   curl http://localhost:8080/health
   ./bouy claude-auth status
   ```

## Scaling Workers with Shared Authentication

Claude authentication is shared across all worker containers using Docker volumes:

```bash
# Scale to multiple workers - all share the same authentication
./bouy up --scale worker=3

# Check health across all workers
curl http://localhost:8080/health  # Worker 1
curl http://localhost:8081/health  # Worker 2
curl http://localhost:8082/health  # Worker 3

# Authenticate once via any worker - applies to all
./bouy claude-auth setup

# Or scale first, then authenticate
./bouy up --scale worker=5
./bouy claude-auth setup
```

**Key Benefits:**
- ✅ **One-time setup**: Authenticate once, works for all workers
- ✅ **Persistent storage**: Authentication survives container restarts
- ✅ **Easy scaling**: Add workers without re-authentication
- ✅ **Consistent state**: All workers share the same Claude account

## Available Commands

### Authentication Management
```bash
# Interactive setup (recommended)
./bouy claude-auth setup

# Check status
./bouy claude-auth status

# Test request
./bouy claude-auth test

# View config files
./bouy claude-auth config

# Alternative: Direct execution
./bouy exec worker python -m app.claude_auth_manager setup
./bouy exec worker python -m app.claude_auth_manager status
./bouy exec worker python -m app.claude_auth_manager test
./bouy exec worker python -m app.claude_auth_manager config

# Direct Claude CLI access
./bouy exec worker claude
```

### Health Monitoring
```bash
# Quick status (any worker)
curl http://localhost:8080/health

# Check all scaled workers
for port in {8080..8089}; do
  echo "Worker on port $port:"
  curl -s http://localhost:$port/health | jq '.authenticated' 2>/dev/null || echo "Not available"
done

# Detailed authentication status
curl http://localhost:8080/auth
```

### Container Management
```bash
# Watch worker logs (all workers)
./bouy logs worker
./bouy logs -f worker        # Follow logs

# Check running services
./bouy ps

# Open shell in worker container
./bouy shell worker

# Execute commands in container
./bouy exec worker bash

# Restart workers (preserves authentication)
./bouy down
./bouy up --scale worker=3
```

## What Happens

### Container Startup
- Container starts with startup script
- Checks Claude authentication automatically
- Shows clear instructions if setup needed
- Starts health server on ports 8080-8089
- Starts RQ worker process
- **Shared authentication** loaded from Docker volume

### When Jobs Run
- **If authenticated**: Jobs process normally across all workers
- **If not authenticated**: Jobs safely retry every 5 minutes
- **If quota exceeded**: Jobs retry with exponential backoff (1h, 1.5h, 2.25h, up to 4h)

### Authentication States
- ✅ **Ready**: Claude authenticated, all workers processing jobs
- ⚠️ **Auth Required**: Jobs queued on all workers, retrying every 5 minutes
- 🔄 **Quota Exceeded**: Jobs queued on all workers, intelligent backoff retry
- ❌ **Failed**: After max retries, jobs fail with clear instructions

## Docker Volume Configuration

The shared authentication uses a Docker volume managed by bouy:

```yaml
# In docker-compose.yml
services:
  worker:
    volumes:
      - claude_config:/root/.config/claude  # Shared Claude authentication

volumes:
  claude_config:  # Shared Claude authentication across worker containers
```

Bouy automatically manages this volume configuration when you use:
- `./bouy up` - Creates and mounts the volume
- `./bouy down` - Stops containers but preserves volume
- `./bouy clean` - Removes containers AND volumes

This means:
- Authentication persists across container restarts
- All scaled workers use the same authentication
- No need to re-authenticate when scaling up/down
- Volume can be backed up/restored for deployment

## Troubleshooting

### Check Container and Volume Status
```bash
# Check all containers
./bouy ps

# Check worker logs
./bouy logs worker

# Inspect the shared volume
docker volume inspect $(docker compose config --volumes | grep claude)

# Check authentication files in volume
./bouy exec worker ls -la ~/.config/claude/
```

### Check Authentication Across Workers
```bash
# Test authentication on multiple workers
./bouy claude-auth status
./bouy up --scale worker=3
curl http://localhost:8080/health
curl http://localhost:8081/health
curl http://localhost:8082/health
```

### Reset Authentication (All Workers)
```bash
# Remove shared authentication volume
./bouy down
docker volume rm $(docker compose config --volumes | grep claude)
./bouy up

# Re-authenticate (applies to all workers)
./bouy claude-auth setup
```

### Manual Authentication
```bash
# Interactive setup via any worker
./bouy shell worker
claude  # Run interactive Claude CLI setup
exit

# Or directly:
./bouy exec worker claude

# Verify it works across all workers
curl http://localhost:8080/health
curl http://localhost:8081/health
```

## Production Considerations

### For Production Deployments:
1. **Use API keys** instead of CLI authentication for predictable billing
2. **Backup the claude_config volume** for disaster recovery
3. **Monitor health endpoints** across all workers
4. **Set up alerting** for authentication failures
5. **Use horizontal scaling** based on queue depth

### For Development:
1. **Use CLI authentication** for Claude Max account benefits
2. **Scale workers** based on processing needs
3. **Use health endpoints** to verify setup
4. **Let retry system handle** temporary issues

The system is designed to be resilient - jobs won't be lost, they'll just wait for authentication to be completed across all workers!