# Deployment Guide

This guide covers deploying Pantry Pirate Radio in production environments.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Environment Setup](#environment-setup)
- [Docker Deployment](#docker-deployment)
- [Kubernetes Deployment](#kubernetes-deployment)
- [Configuration Management](#configuration-management)
- [Database Setup](#database-setup)
- [Monitoring and Logging](#monitoring-and-logging)
- [Security Considerations](#security-considerations)
- [Backup and Recovery](#backup-and-recovery)
- [Scaling](#scaling)
- [Maintenance](#maintenance)
- [Troubleshooting](#troubleshooting)

## Prerequisites

### System Requirements

- **Operating System**: Linux (Ubuntu 20.04+ recommended), macOS, or Windows with WSL2
- **Docker**: 20.10+ (Docker Desktop for Mac/Windows, Docker Engine for Linux)
- **Memory**: 8GB minimum, 16GB recommended
- **Storage**: 50GB minimum, 200GB+ recommended for production
- **Network**: Internet access for data scraping and LLM services

### External Services

- **LLM Provider**: Claude (Anthropic) or OpenAI API key
- **Geocoding** (optional): ArcGIS API key for higher limits
- **HAARRRvest** (optional): GitHub Personal Access Token for publishing
- **Monitoring**: Prometheus and Grafana (optional)

## Environment Setup

### 1. Clone and Configure

```bash
# Clone the repository
git clone https://github.com/For-The-Greater-Good/pantry-pirate-radio.git
cd pantry-pirate-radio

# Run interactive setup wizard (recommended)
./bouy setup

# Or manually create environment configuration
cp .env.example .env
```

### 2. Environment Variables

The setup wizard will guide you through configuration, or edit `.env` manually:

```bash
# Database Configuration (managed by Docker)
DATABASE_URL=postgresql://postgres:your_secure_password@db:5432/pantry_pirate_radio
DATABASE_URL_SYNC=postgresql+psycopg2://postgres:your_secure_password@db:5432/pantry_pirate_radio
POSTGRES_DB=pantry_pirate_radio
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_secure_password

# Redis Configuration (managed by Docker)
REDIS_URL=redis://cache:6379/0

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000

# LLM Configuration (choose one provider)
## Option 1: Claude
LLM_PROVIDER=claude
ANTHROPIC_API_KEY=your_anthropic_key  # Optional, can use CLI auth

## Option 2: OpenAI
LLM_PROVIDER=openai
OPENROUTER_API_KEY=your_openrouter_api_key
LLM_MODEL_NAME=gpt-4

# Geocoding Configuration
GEOCODING_PROVIDER=arcgis
ARCGIS_API_KEY=your_arcgis_key  # Optional for higher limits
GEOCODING_ENABLE_FALLBACK=true
GEOCODING_CACHE_TTL=2592000  # 30 days

# Content Store Configuration
CONTENT_STORE_PATH=/app/data/content_store
CONTENT_STORE_ENABLED=true

# Output Configuration
OUTPUT_DIR=/app/outputs

# Security
SECRET_KEY=your_secret_key_here
ALLOWED_ORIGINS=https://yourdomain.com

# Worker Configuration
WORKER_CONCURRENCY=4
WORKER_TIMEOUT=3600

# HAARRRvest Publisher Configuration
DATA_REPO_URL=https://github.com/For-The-Greater-Good/HAARRRvest.git
DATA_REPO_TOKEN=your_github_personal_access_token
PUBLISHER_CHECK_INTERVAL=300
DAYS_TO_SYNC=7
PUBLISHER_PUSH_ENABLED=true  # Enable pushing to remote

# Monitoring
PROMETHEUS_MULTIPROC_DIR=./metrics
```

## Docker Deployment with Bouy

### Using Bouy for Production

The bouy command handles all Docker operations with proper configuration:

```bash
# Production deployment uses the unified Docker image
# All services are defined in .docker/compose/base.yml
# Production overrides in .docker/compose/docker-compose.prod.yml

# Key production features:
# - Unified image for all services (pantry-pirate-radio:latest)
# - Health checks on critical services
# - Automatic restart policies
# - Resource limits enforced
# - Datasette for data exploration
# - Optimized logging

# Service configuration is managed through bouy
./bouy up --prod  # Starts all services with production settings
```

### Unified Docker Architecture

All services use the same base image with different entry points:

```yaml
# Example service definition from .docker/compose/base.yml
services:
  app:
    image: pantry-pirate-radio:latest
    command: ["app"]  # Service type
    ports:
      - "8000:8000"
    env_file: ../../.env
    volumes:
      - ../../outputs:/app/outputs
      - haarrrvest_repo:/data-repo
      - app_data:/app/data
      - claude_config:/root/.config/claude
    depends_on:
      db:
        condition: service_healthy
      cache:
        condition: service_started

  worker:
    image: pantry-pirate-radio:latest
    command: ["worker"]  # Different entry point, same image
    # ... configuration continues

volumes:
  postgres_data:
  redis_data:
  haarrrvest_repo:
  app_data:
  claude_config:
```

### Deploy with Bouy

```bash
# Start production environment with database initialization
./bouy up --prod --with-init

# Check service status
./bouy ps

# View logs
./bouy logs -f app

# Scale workers for production load
./bouy up --prod --scale worker=3

# Run health checks
./bouy exec app curl -f http://localhost:8000/health
```

## Kubernetes Deployment

### Namespace and ConfigMap

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: pantry-pirate-radio
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-config
  namespace: pantry-pirate-radio
data:
  DATABASE_URL: "postgresql://pantry_pirate_radio:password@postgres:5432/pantry_pirate_radio"
  REDIS_URL: "redis://redis:6379/0"
  API_HOST: "0.0.0.0"
  API_PORT: "8000"
```

### Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: pantry-pirate-radio-app
  namespace: pantry-pirate-radio
spec:
  replicas: 3
  selector:
    matchLabels:
      app: pantry-pirate-radio-app
  template:
    metadata:
      labels:
        app: pantry-pirate-radio-app
    spec:
      containers:
      - name: app
        image: pantry-pirate-radio:latest
        ports:
        - containerPort: 8000
        envFrom:
        - configMapRef:
            name: app-config
        env:
        - name: OPENROUTER_API_KEY
          valueFrom:
            secretKeyRef:
              name: app-secrets
              key: openrouter-api-key
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
```

### Service

```yaml
apiVersion: v1
kind: Service
metadata:
  name: pantry-pirate-radio-service
  namespace: pantry-pirate-radio
spec:
  selector:
    app: pantry-pirate-radio-app
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8000
  type: LoadBalancer
```

## Configuration Management

### Content Store Configuration

The content deduplication store prevents duplicate LLM processing:

```bash
# Content Store Settings
CONTENT_STORE_PATH=/data/content-store  # Path to store content hashes
CONTENT_STORE_ENABLED=true              # Enable deduplication (default: true if path set)
```

#### Production Considerations

1. **Storage Location**:
   - Use persistent storage (not ephemeral container storage)
   - Consider SSD for better performance
   - Estimate ~100MB per 10,000 unique content items

2. **Permissions**:
   ```bash
   # Create content store directory
   mkdir -p /data/content-store
   chown -R 1000:1000 /data/content-store  # Match container user
   chmod 755 /data/content-store
   ```

3. **Backup Strategy**:
   - Content store is automatically backed up to HAARRRvest
   - Consider additional backups for critical deployments
   - SQLite index can be rebuilt from content files if needed

4. **Docker Volume**:
   ```yaml
   volumes:
     content_store:
       driver: local
       driver_opts:
         type: none
         o: bind
         device: /data/content-store
   ```

5. **Monitoring**:
   ```bash
   # Check content store status
   ./bouy content-store status

   # Generate report
   ./bouy content-store report
   ```

### Secrets Management

```bash
# Create Kubernetes secrets
kubectl create secret generic app-secrets \
  --from-literal=openrouter-api-key=your_api_key \
  --from-literal=postgres-password=your_password \
  --from-literal=secret-key=your_secret_key \
  -n pantry-pirate-radio
```

### ConfigMap Updates

```bash
# Update configuration
kubectl patch configmap app-config -n pantry-pirate-radio --patch '{"data":{"NEW_VAR":"new_value"}}'

# Restart deployments to pick up new config
kubectl rollout restart deployment/pantry-pirate-radio-app -n pantry-pirate-radio
```

## Database Setup

### Initial Database Setup

```bash
# Database is automatically initialized with bouy
# Option 1: Start with pre-populated data from SQL dumps
./bouy up --prod --with-init

# Option 2: Start with empty database
./bouy up --prod

# Verify database is ready
./bouy exec db pg_isready -U postgres

# Check database contents
./bouy exec db psql -U postgres -d pantry_pirate_radio -c "SELECT COUNT(*) FROM organization;"
```

### Database Maintenance

```bash
# Create SQL dump for backup/distribution
./bouy exec app bash /app/scripts/create-sql-dump.sh

# Backup database manually
./bouy exec db pg_dump -U postgres pantry_pirate_radio | gzip > backup_$(date +%Y%m%d).sql.gz

# Restore database from SQL dump
./bouy down
./bouy clean  # WARNING: Removes all data
./bouy up --prod --with-init

# Or restore manually
gunzip -c backup_20240101.sql.gz | ./bouy exec -T db psql -U postgres pantry_pirate_radio
```

## Monitoring and Logging

### Prometheus Configuration

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'pantry-pirate-radio'
    static_configs:
      - targets: ['app:8000']
    metrics_path: '/metrics'
    scrape_interval: 30s
```

### Grafana Dashboard

Import the provided dashboard configuration from `monitoring/grafana-dashboard.json`.

### Log Management

```bash
# Centralized logging with ELK stack
docker run -d --name elasticsearch elasticsearch:7.14.0
docker run -d --name logstash logstash:7.14.0
docker run -d --name kibana kibana:7.14.0

# Configure log shipping
echo "*.* @@logstash:514" >> /etc/rsyslog.conf
systemctl restart rsyslog
```

## Security Considerations

### Environment Security

```bash
# Use bouy setup for secure configuration
./bouy setup  # Creates secure passwords automatically

# For production, ensure:
# - Strong database passwords
# - API keys are kept secret
# - PUBLISHER_PUSH_ENABLED=true only with valid token
# - Use HTTPS for all external access
```

### Network Security

```bash
# Configure firewall
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
```

### SSL/TLS Configuration

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    location / {
        proxy_pass http://app:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Security Headers

```bash
# Add security headers
add_header X-Frame-Options "SAMEORIGIN";
add_header X-Content-Type-Options "nosniff";
add_header X-XSS-Protection "1; mode=block";
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains";
```

## Backup and Recovery

### SQL Dump Backups

```bash
# Create SQL dump (automatically pushed to HAARRRvest)
./bouy exec app bash /app/scripts/create-sql-dump.sh

# Manual database backup
./bouy exec db pg_dump -U postgres pantry_pirate_radio > backup_$(date +%Y%m%d).sql

# Backup outputs directory
tar -czf outputs_backup_$(date +%Y%m%d).tar.gz outputs/
```

### Disaster Recovery

```bash
# Option 1: Quick recovery from SQL dumps
./bouy down
./bouy clean  # Remove corrupted data
./bouy up --prod --with-init  # Restore from SQL dumps

# Option 2: Manual restore from backup
./bouy down
gunzip -c backup_latest.sql.gz | ./bouy exec -T db psql -U postgres pantry_pirate_radio
tar -xzf outputs_backup_latest.tar.gz
./bouy up --prod

# Option 3: Replay from HAARRRvest data
./bouy replay --use-default-output-dir
```

## Scaling

### Horizontal Scaling

```bash
# Scale worker services with bouy
./bouy up --prod --scale worker=6

# Scale specific service
./bouy scale worker=10

# For Kubernetes deployment
kubectl scale deployment pantry-pirate-radio-app --replicas=5 -n pantry-pirate-radio
```

### Vertical Scaling

```yaml
# Resource limits in Kubernetes
resources:
  limits:
    cpu: 2000m
    memory: 4Gi
  requests:
    cpu: 500m
    memory: 1Gi
```

## Maintenance

### Regular Maintenance Tasks

```bash
# Update to latest version
git pull
./bouy build --no-cache
./bouy up --prod

# Clean up unused resources
docker system prune -f

# Database maintenance
./bouy exec db psql -U postgres -d pantry_pirate_radio -c "VACUUM ANALYZE;"

# Check disk space
df -h
du -sh outputs/ archives/

# Run scrapers to update data
./bouy scraper --all
```

### Health Checks

```bash
# Application health
./bouy exec app curl -f http://localhost:8000/health

# Database health
./bouy exec db pg_isready -U postgres

# Redis health
./bouy exec cache redis-cli ping

# Check all services
./bouy ps

# View service logs
./bouy logs --tail 50 app worker reconciler
```

## Troubleshooting

### Common Issues

#### Service Won't Start

```bash
# Check logs
./bouy logs -f app

# Check service status
./bouy ps

# Verify environment variables
./bouy exec app printenv | grep -E "DATABASE_URL|REDIS_URL"

# Restart service
./bouy restart app
```

#### Database Connection Issues

```bash
# Test database connectivity
./bouy exec db pg_isready -U postgres

# Check database logs
./bouy logs -f db

# Test from app container
./bouy exec app python -c "from app.core.database import engine; print('Connected!' if engine else 'Failed')"
```

#### Performance Issues

```bash
# Monitor resource usage
docker stats

# Check Redis queue status
./bouy exec cache redis-cli --stat

# Monitor queue lengths
./bouy exec cache redis-cli llen llm

# Analyze slow queries
./bouy exec db psql -U postgres -d pantry_pirate_radio -c "SELECT * FROM pg_stat_activity WHERE state = 'active';"
```

#### Worker Issues

```bash
# Check worker logs
./bouy logs -f worker

# Monitor job queue
./bouy exec cache redis-cli llen llm
./bouy exec cache redis-cli llen recorder

# Check worker health (Claude workers)
curl http://localhost:8080/health

# Scale workers if needed
./bouy up --scale worker=3
```

### Support

For additional support:
- Check the [Issues](https://github.com/For-The-Greater-Good/pantry-pirate-radio/issues) page
- Review the [API documentation](api.md)
- Consult the [Architecture documentation](architecture.md)
- Run `./bouy --help` for command reference

---

*This deployment guide is maintained by the Pantry Pirate Radio team. For the latest updates, visit our [GitHub repository](https://github.com/For-The-Greater-Good/pantry-pirate-radio).*