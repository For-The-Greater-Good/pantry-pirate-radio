# Troubleshooting Guide

This guide helps you diagnose and resolve common issues with Pantry Pirate Radio.

## Table of Contents

- [Quick Diagnosis](#quick-diagnosis)
- [Installation Issues](#installation-issues)
- [Database Problems](#database-problems)
- [Docker Issues](#docker-issues)
- [API Issues](#api-issues)
- [Worker Problems](#worker-problems)
- [Scraper Issues](#scraper-issues)
- [Performance Problems](#performance-problems)
- [LLM Provider Issues](#llm-provider-issues)
- [Monitoring and Logging](#monitoring-and-logging)
- [Common Error Messages](#common-error-messages)
- [Getting Help](#getting-help)

## Quick Diagnosis

### System Health Check

```bash
# Check all services
./bouy ps

# Check application health
curl -f http://localhost:8000/health

# Check logs for errors
./bouy logs --tail 50 app
```

### Common Commands

```bash
# Restart all services
./bouy restart

# Rebuild and restart
./bouy down
./bouy build --no-cache
./bouy up

# Check resource usage
docker stats

# View detailed logs
./bouy logs -f [service_name]
```

## Installation Issues

### Bouy Setup Problems

**Problem**: Bouy commands don't work or setup fails

**Solution**:
```bash
# Make bouy executable
chmod +x bouy

# Run setup wizard
./bouy setup

# Check Docker is running
docker version

# If Docker not running, start it:
# macOS/Windows: Start Docker Desktop
# Linux: sudo systemctl start docker
```

### Docker Installation Issues

**Problem**: Docker commands fail with permission errors

**Solution**:
```bash
# Add user to docker group
sudo usermod -aG docker $USER

# Restart session or run
newgrp docker

# Test docker
docker run hello-world
```

### Docker Version Issues

**Problem**: Docker version too old or not installed

**Solution**:
```bash
# Check Docker version (need 20.10+)
docker --version

# Install/update Docker
# macOS/Windows: Download Docker Desktop from docker.com
# Linux:
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
```

## Database Problems

### Connection Issues

**Problem**: Database connection refused or timeout

**Diagnosis**:
```bash
# Check if database is running
./bouy ps | grep db

# Check database logs
./bouy logs db

# Test connection
./bouy exec db psql -U postgres -d pantry_pirate_radio -c "SELECT 1;"
```

**Solutions**:
```bash
# Restart database
./bouy restart db

# Check environment variables
./bouy exec app printenv | grep DATABASE_URL

# Reset database
./bouy down
./bouy clean  # WARNING: Removes all data
./bouy up --with-init
```

### Migration Issues

**Problem**: Database migrations fail

**Diagnosis**:
```bash
# Check if database tables exist
./bouy exec db psql -U postgres -d pantry_pirate_radio -c "\dt"

# Check record counts
./bouy exec db psql -U postgres -d pantry_pirate_radio -c "SELECT COUNT(*) FROM organization;"
```

**Solutions**:
```bash
# Reinitialize database with SQL dumps
./bouy down
./bouy clean
./bouy up --with-init

# Or start with empty database
./bouy up
```

### PostGIS Extension Issues

**Problem**: PostGIS functions not available

**Solution**:
```bash
# PostGIS is automatically installed in the Docker image
# Verify installation
./bouy exec db psql -U postgres -d pantry_pirate_radio -c "SELECT PostGIS_version();"

# If missing, recreate database
./bouy down
./bouy clean
./bouy up --with-init
```

## Docker Issues

### Container Won't Start

**Problem**: Services fail to start

**Diagnosis**:
```bash
# Check container status
./bouy ps

# View startup logs
./bouy logs [service_name]

# Check resource usage
docker system df
```

**Solutions**:
```bash
# Clean up stopped containers
./bouy down
docker system prune -f

# Rebuild containers
./bouy build --no-cache
./bouy up
```

### Port Already in Use

**Problem**: Port 8000 already in use

**Solutions**:
```bash
# Find what's using the port
sudo lsof -i :8000

# Kill the process
sudo kill -9 [PID]

# Or change port in .env file
API_PORT=8001

# Restart with new port
./bouy up
```

### Volume Mount Issues

**Problem**: Files not persisting or permission errors

**Solutions**:
```bash
# Fix ownership
sudo chown -R $USER:$USER outputs/ archives/

# Check mount points
./bouy exec app ls -la /app/outputs

# Recreate volumes
./bouy clean  # WARNING: Removes all data
./bouy up
```

## API Issues

### 500 Internal Server Error

**Problem**: API returns 500 errors

**Diagnosis**:
```bash
# Check application logs
./bouy logs -f app

# Check database connectivity
./bouy exec app python -c "from app.core.database import engine; print('Connected!' if engine else 'Failed')"

# Test specific endpoint
curl -v http://localhost:8000/health
```

**Solutions**:
```bash
# Restart application
./bouy restart app

# Check environment variables
./bouy exec app printenv | grep -E "(DATABASE_URL|REDIS_URL)"

# Reinitialize database
./bouy down
./bouy up --with-init
```

### API Timeout Issues

**Problem**: API requests timeout

**Solutions**:
```bash
# Increase timeout in .env
WORKER_TIMEOUT=300

# Check resource limits
docker stats app

# Scale workers
./bouy up --scale worker=3
```

### CORS Issues

**Problem**: Browser blocks API requests

**Solution**:
```bash
# Check CORS settings in .env
ALLOWED_ORIGINS=https://yourdomain.com,http://localhost:3000

# Restart application
./bouy restart app
```

## Worker Problems

### Workers Not Processing Jobs

**Problem**: Jobs stuck in queue

**Diagnosis**:
```bash
# Check worker logs
./bouy logs -f worker

# Check Redis queue lengths
./bouy exec cache redis-cli llen llm
./bouy exec cache redis-cli llen recorder

# Monitor worker activity
./bouy exec cache redis-cli monitor
```

**Solutions**:
```bash
# Restart workers
./bouy restart worker

# Scale workers
./bouy up --scale worker=3

# Clear failed jobs (WARNING: Clears all Redis data)
./bouy exec cache redis-cli flushdb
```

### LLM Processing Failures

**Problem**: LLM jobs fail consistently

**Diagnosis**:
```bash
# Check API key configuration
./bouy exec worker printenv | grep -E "(ANTHROPIC_API_KEY|OPENROUTER_API_KEY)"

# Check LLM provider
./bouy exec worker printenv | grep LLM_PROVIDER

# For Claude auth status
./bouy claude-auth status
```

**Solutions**:
```bash
# For Claude provider
./bouy claude-auth setup

# For OpenAI provider, set in .env
OPENROUTER_API_KEY=your_key
LLM_MODEL_NAME=gpt-4

# Restart workers
./bouy restart worker
```

## Scraper Issues

### Scraper Fails to Collect Data

**Problem**: Scrapers return no data or error

**Diagnosis**:
```bash
# List available scrapers
./bouy scraper --list

# Test specific scraper (dry run)
./bouy scraper-test nyc_efap_programs

# Check scraper logs
./bouy logs -f scraper

# Run scraper normally
./bouy scraper nyc_efap_programs
```

**Solutions**:
```bash
# Update scraper code for website changes
# Check robots.txt compliance
# Implement rate limiting
# Use different user agent
```

### Rate Limiting Issues

**Problem**: Scrapers blocked by rate limits

**Solutions**:
```bash
# Increase delays in scraper
time.sleep(2)  # Add delays between requests

# Implement exponential backoff
# Use rotating proxies
# Respect robots.txt
```

## Performance Problems

### High Memory Usage

**Problem**: Services using too much memory

**Diagnosis**:
```bash
# Check memory usage
docker stats

# Check process memory
./bouy exec app ps aux --sort=-%mem

# Monitor memory over time
watch -n 5 docker stats
```

**Solutions**:
```bash
# Increase memory limits
deploy:
  resources:
    limits:
      memory: 2G

# Optimize database queries
# Reduce batch sizes
# Implement pagination
```

### Slow Database Queries

**Problem**: Database queries take too long

**Diagnosis**:
```bash
# Check active queries
./bouy exec db psql -U postgres -d pantry_pirate_radio -c "SELECT * FROM pg_stat_activity WHERE state = 'active';"

# Check database size
./bouy exec db psql -U postgres -d pantry_pirate_radio -c "SELECT pg_database_size('pantry_pirate_radio');"
```

**Solutions**:
```bash
# Add database indexes
# Optimize queries
# Use connection pooling
# Implement caching
```

## LLM Provider Issues

### LLM API Issues

**Problem**: LLM API calls fail

**Diagnosis**:
```bash
# Check which provider is configured
./bouy exec worker printenv | grep LLM_PROVIDER

# For Claude
./bouy claude-auth test

# For OpenAI
curl -H "Authorization: Bearer $OPENROUTER_API_KEY" https://openrouter.ai/api/v1/models
```

**Solutions**:
```bash
# Switch providers in .env
LLM_PROVIDER=claude  # or openai

# For Claude issues
./bouy claude-auth setup

# Restart workers
./bouy restart worker
```

## Monitoring and Logging

### Logs Not Appearing

**Problem**: No logs visible

**Solutions**:
```bash
# Check log levels
LOG_LEVEL=DEBUG

# Verify log directory
ls -la logs/

# Check log rotation
logrotate -f /etc/logrotate.d/pantry-pirate-radio
```

### Metrics Not Collecting

**Problem**: Prometheus metrics not available

**Solutions**:
```bash
# Check metrics endpoint
curl http://localhost:8000/metrics

# Verify Prometheus configuration
# Check scrape targets
```

## Common Error Messages

### "Database connection failed"

**Cause**: Database not running or wrong credentials

**Solution**:
```bash
# Check database status
./bouy ps | grep db

# Verify credentials
./bouy exec app printenv | grep DATABASE_URL
```

### "Redis connection refused"

**Cause**: Redis not running or wrong configuration

**Solution**:
```bash
# Start Redis (cache service)
./bouy up cache

# Check Redis logs
./bouy logs cache
```

### "Module not found"

**Cause**: Docker image not built properly

**Solution**:
```bash
# Rebuild Docker image
./bouy build --no-cache
./bouy up
```

### "Permission denied"

**Cause**: File system permissions

**Solution**:
```bash
# Fix permissions
sudo chown -R $USER:$USER .
chmod +x scripts/*
```

## Getting Help

### Before Reporting Issues

1. **Check the logs**: `./bouy logs -f [service]`
2. **Test isolation**: Try with minimal configuration
3. **Check dependencies**: Verify all required services are running with `./bouy ps`
4. **Review documentation**: Check relevant sections
5. **Search existing issues**: Look for similar problems

### Information to Include

When reporting issues, include:

- Operating system and version
- Docker and Docker Compose versions
- Python version
- Complete error messages
- Steps to reproduce
- Configuration files (without secrets)
- Log output

### Community Resources

- **GitHub Issues**: https://github.com/For-The-Greater-Good/pantry-pirate-radio/issues
- **Documentation**: Check all files in `docs/`
- **API Reference**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health
- **Bouy Help**: Run `./bouy --help` for command reference

### Debug Mode

Enable debug mode for detailed logging:

```bash
# Set environment variables in .env
LOG_LEVEL=DEBUG
DEBUG=true

# Restart services
./bouy restart

# Or use verbose mode with bouy
./bouy --verbose up
```

---

*This troubleshooting guide is regularly updated. For the latest information, visit our [GitHub repository](https://github.com/For-The-Greater-Good/pantry-pirate-radio).*