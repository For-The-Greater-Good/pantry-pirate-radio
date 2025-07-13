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
docker-compose ps

# Check application health
curl -f http://localhost:8000/health

# Check logs for errors
docker-compose logs --tail=50 app
```

### Common Commands

```bash
# Restart all services
docker-compose restart

# Rebuild and restart
docker-compose down
docker-compose up -d --build

# Check resource usage
docker stats

# View detailed logs
docker-compose logs -f [service_name]
```

## Installation Issues

### Poetry Installation Problems

**Problem**: Poetry installation fails or poetry commands don't work

**Solution**:
```bash
# Reinstall Poetry
curl -sSL https://install.python-poetry.org | python3 -
source ~/.bashrc

# Or use pip
pip install poetry

# Verify installation
poetry --version
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

### Python Version Issues

**Problem**: Python 3.11+ not available

**Solution**:
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3.11 python3.11-venv

# Or use pyenv
curl https://pyenv.run | bash
pyenv install 3.11.7
pyenv global 3.11.7
```

## Database Problems

### Connection Issues

**Problem**: Database connection refused or timeout

**Diagnosis**:
```bash
# Check if database is running
docker-compose ps db

# Check database logs
docker-compose logs db

# Test connection
docker-compose exec db psql -U pantry_pirate_radio -c "SELECT 1;"
```

**Solutions**:
```bash
# Restart database
docker-compose restart db

# Check environment variables
echo $DATABASE_URL

# Reset database
docker-compose down -v
docker-compose up -d db
```

### Migration Issues

**Problem**: Database migrations fail

**Diagnosis**:
```bash
# Check migration status
docker-compose exec app python -m alembic current

# Check migration history
docker-compose exec app python -m alembic history
```

**Solutions**:
```bash
# Force migration
docker-compose exec app python -m alembic upgrade head

# Reset migrations (development only)
docker-compose exec app python -m alembic downgrade base
docker-compose exec app python -m alembic upgrade head
```

### PostGIS Extension Issues

**Problem**: PostGIS functions not available

**Solution**:
```bash
# Install PostGIS extension
docker-compose exec db psql -U pantry_pirate_radio -c "CREATE EXTENSION IF NOT EXISTS postgis;"

# Verify installation
docker-compose exec db psql -U pantry_pirate_radio -c "SELECT PostGIS_version();"
```

## Docker Issues

### Container Won't Start

**Problem**: Services fail to start

**Diagnosis**:
```bash
# Check container status
docker-compose ps

# View startup logs
docker-compose logs [service_name]

# Check resource usage
docker system df
```

**Solutions**:
```bash
# Clean up stopped containers
docker-compose down
docker system prune -f

# Rebuild containers
docker-compose build --no-cache
docker-compose up -d
```

### Port Already in Use

**Problem**: Port 8000 already in use

**Solutions**:
```bash
# Find what's using the port
sudo lsof -i :8000

# Kill the process
sudo kill -9 [PID]

# Or change port in docker-compose.yml
ports:
  - "8001:8000"
```

### Volume Mount Issues

**Problem**: Files not persisting or permission errors

**Solutions**:
```bash
# Fix ownership
sudo chown -R $USER:$USER outputs/ archives/

# Check mount points
docker-compose exec app ls -la /app/outputs

# Recreate volumes
docker-compose down -v
docker-compose up -d
```

## API Issues

### 500 Internal Server Error

**Problem**: API returns 500 errors

**Diagnosis**:
```bash
# Check application logs
docker-compose logs -f app

# Check database connectivity
docker-compose exec app python -c "from app.core.database import engine; print(engine.connect())"

# Test specific endpoint
curl -v http://localhost:8000/api/v1/health
```

**Solutions**:
```bash
# Restart application
docker-compose restart app

# Check environment variables
docker-compose exec app printenv | grep -E "(DATABASE_URL|REDIS_URL)"

# Verify database schema
docker-compose exec app python -c "from app.core.database import Base, engine; Base.metadata.create_all(engine)"
```

### API Timeout Issues

**Problem**: API requests timeout

**Solutions**:
```bash
# Increase timeout in docker-compose.yml
environment:
  - TIMEOUT=300

# Check resource limits
docker stats app

# Scale workers
docker-compose up -d --scale worker=3
```

### CORS Issues

**Problem**: Browser blocks API requests

**Solution**:
```bash
# Check CORS settings in .env
ALLOWED_ORIGINS=https://yourdomain.com,http://localhost:3000

# Restart application
docker-compose restart app
```

## Worker Problems

### Workers Not Processing Jobs

**Problem**: Jobs stuck in queue

**Diagnosis**:
```bash
# Check worker logs
docker-compose logs -f worker

# Check Redis queue
docker-compose exec redis redis-cli llen queue:default

# Monitor worker activity
docker-compose exec redis redis-cli monitor
```

**Solutions**:
```bash
# Restart workers
docker-compose restart worker

# Scale workers
docker-compose up -d --scale worker=3

# Clear failed jobs
docker-compose exec redis redis-cli flushdb
```

### LLM Processing Failures

**Problem**: LLM jobs fail consistently

**Diagnosis**:
```bash
# Check API key configuration
docker-compose exec worker python -c "import os; print(os.getenv('OPENROUTER_API_KEY'))"

# Test LLM connectivity
docker-compose exec worker python -c "from app.llm.providers import get_provider; print(get_provider().test_connection())"
```

**Solutions**:
```bash
# Verify API key
echo $OPENROUTER_API_KEY

# Switch to different model
LLM_MODEL_NAME=anthropic/claude-3-haiku

# Restart workers
docker-compose restart worker
```

## Scraper Issues

### Scraper Fails to Collect Data

**Problem**: Scrapers return no data or error

**Diagnosis**:
```bash
# Test specific scraper
docker-compose exec app python -m app.scraper nyc_efap_programs

# Check scraper logs
docker-compose logs -f scraper

# Test manually
docker-compose exec scraper python -c "from app.scraper.nyc_efap_programs_scraper import NYCEFAPProgramsScraper; s = NYCEFAPProgramsScraper(); s.scrape()"
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
docker-compose exec app ps aux --sort=-%mem

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
# Check slow queries
docker-compose exec db psql -U pantry_pirate_radio -c "SELECT query, mean_exec_time FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;"

# Check active queries
docker-compose exec db psql -U pantry_pirate_radio -c "SELECT * FROM pg_stat_activity WHERE state = 'active';"
```

**Solutions**:
```bash
# Add database indexes
# Optimize queries
# Use connection pooling
# Implement caching
```

## LLM Provider Issues

### OpenAI API Issues

**Problem**: OpenAI API calls fail

**Diagnosis**:
```bash
# Test API key
curl -H "Authorization: Bearer $OPENROUTER_API_KEY" https://api.openai.com/v1/models

# Check quota usage
# Verify API key permissions
```

**Solutions**:
```bash
# Rotate API keys
# Implement retry logic
# Use different model
# Use different model or provider
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
docker-compose ps db

# Verify credentials
echo $DATABASE_URL
```

### "Redis connection refused"

**Cause**: Redis not running or wrong configuration

**Solution**:
```bash
# Start Redis
docker-compose up -d redis

# Check Redis logs
docker-compose logs redis
```

### "Module not found"

**Cause**: Python dependencies not installed

**Solution**:
```bash
# Reinstall dependencies
docker-compose build --no-cache
poetry install
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

1. **Check the logs**: `docker-compose logs -f [service]`
2. **Test isolation**: Try with minimal configuration
3. **Check dependencies**: Verify all required services are running
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

- **GitHub Issues**: https://github.com/***REMOVED_USER***/pantry-pirate-radio/issues
- **Documentation**: Check all files in `docs/`
- **API Reference**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

### Debug Mode

Enable debug mode for detailed logging:

```bash
# Set environment variables
LOG_LEVEL=DEBUG
DEBUG=true

# Restart services
docker-compose restart
```

---

*This troubleshooting guide is regularly updated. For the latest information, visit our [GitHub repository](https://github.com/***REMOVED_USER***/pantry-pirate-radio).*