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

- **Operating System**: Linux (Ubuntu 20.04+ recommended)
- **Docker**: 20.10+
- **Docker Compose**: 2.0+
- **Memory**: 8GB minimum, 16GB recommended
- **Storage**: 50GB minimum, 200GB+ recommended for production
- **Network**: Internet access for data scraping and LLM services

### External Services

- **Database**: PostgreSQL 14+ with PostGIS extension
- **Cache**: Redis 7.0+
- **LLM Provider**: OpenAI API key
- **Monitoring**: Prometheus and Grafana (optional)

## Environment Setup

### 1. Clone and Configure

```bash
# Clone the repository
git clone https://github.com/***REMOVED_USER***/pantry-pirate-radio.git
cd pantry-pirate-radio

# Create environment configuration
cp .env.example .env
```

### 2. Environment Variables

Edit `.env` with your production settings:

```bash
# Database Configuration
DATABASE_URL=postgresql://user:password@localhost:5432/pantry_pirate_radio
POSTGRES_DB=pantry_pirate_radio
POSTGRES_USER=pantry_pirate_radio
POSTGRES_PASSWORD=your_secure_password

# Redis Configuration
REDIS_URL=redis://localhost:6379/0

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000

# LLM Configuration
OPENROUTER_API_KEY=your_openrouter_api_key
LLM_MODEL_NAME=anthropic/claude-3-sonnet

# Content Store Configuration
CONTENT_STORE_PATH=/path/to/content/store
CONTENT_STORE_ENABLED=true

# Output Configuration
OUTPUT_DIR=./outputs
BACKUP_KEEP_DAYS=30

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

# Monitoring
PROMETHEUS_MULTIPROC_DIR=./metrics
```

## Docker Deployment

### Production Docker Compose

Create a `docker-compose.prod.yml` file:

```yaml
version: '3.8'

services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
      target: app
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://pantry_pirate_radio:${POSTGRES_PASSWORD}@db:5432/pantry_pirate_radio
      - REDIS_URL=redis://redis:6379/0
      - OPENROUTER_API_KEY=${OPENROUTER_API_KEY}
    depends_on:
      - db
      - redis
    volumes:
      - ./outputs:/app/outputs
      - ./logs:/app/logs
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  worker:
    build:
      context: .
      dockerfile: Dockerfile
      target: worker
    environment:
      - DATABASE_URL=postgresql://pantry_pirate_radio:${POSTGRES_PASSWORD}@db:5432/pantry_pirate_radio
      - REDIS_URL=redis://redis:6379/0
      - OPENROUTER_API_KEY=${OPENROUTER_API_KEY}
    depends_on:
      - db
      - redis
    volumes:
      - ./outputs:/app/outputs
      - ./logs:/app/logs
    restart: unless-stopped
    deploy:
      replicas: 3

  recorder:
    build:
      context: .
      dockerfile: Dockerfile
      target: recorder
    environment:
      - DATABASE_URL=postgresql://pantry_pirate_radio:${POSTGRES_PASSWORD}@db:5432/pantry_pirate_radio
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - db
      - redis
    volumes:
      - ./outputs:/app/outputs
      - ./archives:/app/archives
    restart: unless-stopped

  reconciler:
    build:
      context: .
      dockerfile: Dockerfile
      target: reconciler
    environment:
      - DATABASE_URL=postgresql://pantry_pirate_radio:${POSTGRES_PASSWORD}@db:5432/pantry_pirate_radio
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - db
      - redis
    restart: unless-stopped

  haarrrvest-publisher:
    build:
      context: .
      dockerfile: Dockerfile
      target: production-base
    command: python -m app.haarrrvest_publisher.service
    environment:
      - DATABASE_URL=postgresql://pantry_pirate_radio:${POSTGRES_PASSWORD}@db:5432/pantry_pirate_radio
      - REDIS_URL=redis://redis:6379/0
      - DATA_REPO_URL=${DATA_REPO_URL}
      - DATA_REPO_TOKEN=${DATA_REPO_TOKEN}
      - PUBLISHER_CHECK_INTERVAL=${PUBLISHER_CHECK_INTERVAL:-300}
      - DAYS_TO_SYNC=${DAYS_TO_SYNC:-7}
    depends_on:
      - db
      - redis
      - recorder
    volumes:
      - ./outputs:/app/outputs
      - haarrrvest_repo:/data-repo
      - ./scripts:/app/scripts:ro
    restart: unless-stopped

  scraper:
    build:
      context: .
      dockerfile: Dockerfile
      target: scraper
    environment:
      - DATABASE_URL=postgresql://pantry_pirate_radio:${POSTGRES_PASSWORD}@db:5432/pantry_pirate_radio
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - db
      - redis
    volumes:
      - ./outputs:/app/outputs
    restart: unless-stopped

  db:
    image: postgis/postgis:14-3.2
    environment:
      - POSTGRES_DB=pantry_pirate_radio
      - POSTGRES_USER=pantry_pirate_radio
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init-scripts:/docker-entrypoint-initdb.d
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U pantry_pirate_radio"]
      interval: 30s
      timeout: 10s
      retries: 3

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 30s
      timeout: 10s
      retries: 3

  db-backup:
    build:
      context: .
      dockerfile: Dockerfile
      target: db-backup
    environment:
      - DATABASE_URL=postgresql://pantry_pirate_radio:${POSTGRES_PASSWORD}@db:5432/pantry_pirate_radio
      - BACKUP_KEEP_DAYS=${BACKUP_KEEP_DAYS}
    depends_on:
      - db
    volumes:
      - ./backups:/app/backups
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl
    depends_on:
      - app
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
  haarrrvest_repo:
```

### Deploy with Docker Compose

```bash
# Build and start services
docker-compose -f docker-compose.prod.yml up -d

# Check service status
docker-compose -f docker-compose.prod.yml ps

# View logs
docker-compose -f docker-compose.prod.yml logs -f app
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
   docker-compose exec worker python -m app.content_store status

   # Generate report
   docker-compose exec worker python -m app.content_store report -o /tmp/report.json
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
# Create database user and schema
psql -h your-db-host -U postgres -c "CREATE USER pantry_pirate_radio WITH PASSWORD 'your_password';"
psql -h your-db-host -U postgres -c "CREATE DATABASE pantry_pirate_radio OWNER pantry_pirate_radio;"
psql -h your-db-host -U postgres -d pantry_pirate_radio -c "CREATE EXTENSION postgis;"

# Run migrations
docker-compose exec app python -m alembic upgrade head
```

### Database Maintenance

```bash
# Backup database
pg_dump -h your-db-host -U pantry_pirate_radio pantry_pirate_radio | gzip > backup_$(date +%Y%m%d).sql.gz

# Restore database
gunzip -c backup_20240101.sql.gz | psql -h your-db-host -U pantry_pirate_radio pantry_pirate_radio
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

### Automated Backups

```bash
#!/bin/bash
# backup-script.sh

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups"

# Database backup
pg_dump -h db -U pantry_pirate_radio pantry_pirate_radio | gzip > "$BACKUP_DIR/db_backup_$DATE.sql.gz"

# File system backup
tar -czf "$BACKUP_DIR/files_backup_$DATE.tar.gz" outputs/ archives/

# Clean old backups
find "$BACKUP_DIR" -name "*.gz" -mtime +30 -delete
```

### Disaster Recovery

```bash
# Stop services
docker-compose down

# Restore database
gunzip -c /backups/db_backup_latest.sql.gz | psql -h db -U pantry_pirate_radio pantry_pirate_radio

# Restore files
tar -xzf /backups/files_backup_latest.tar.gz

# Restart services
docker-compose up -d
```

## Scaling

### Horizontal Scaling

```bash
# Scale worker services
docker-compose up -d --scale worker=6

# Scale Kubernetes deployment
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
# Update Docker images
docker-compose pull
docker-compose up -d

# Clean up unused resources
docker system prune -f

# Database maintenance
docker-compose exec db psql -U pantry_pirate_radio -c "VACUUM ANALYZE;"

# Check disk space
df -h
du -sh outputs/ archives/
```

### Health Checks

```bash
# Application health
curl -f http://localhost:8000/health

# Database health
docker-compose exec db pg_isready -U pantry_pirate_radio

# Redis health
docker-compose exec redis redis-cli ping
```

## Troubleshooting

### Common Issues

#### Service Won't Start

```bash
# Check logs
docker-compose logs -f app

# Check configuration
docker-compose config

# Verify environment variables
docker-compose exec app printenv
```

#### Database Connection Issues

```bash
# Test database connectivity
docker-compose exec app python -c "from app.core.database import engine; print(engine.connect())"

# Check database logs
docker-compose logs -f db
```

#### Performance Issues

```bash
# Monitor resource usage
docker stats

# Check Redis queue status
docker-compose exec redis redis-cli monitor

# Analyze slow queries
docker-compose exec db psql -U pantry_pirate_radio -c "SELECT * FROM pg_stat_activity WHERE state = 'active';"
```

#### Worker Issues

```bash
# Check worker status
docker-compose exec worker python -m rq worker --help

# Monitor job queue
docker-compose exec redis redis-cli llen queue:default
```

### Support

For additional support:
- Check the [Issues](https://github.com/***REMOVED_USER***/pantry-pirate-radio/issues) page
- Review the [API documentation](api.md)
- Consult the [Architecture documentation](architecture.md)

---

*This deployment guide is maintained by the Pantry Pirate Radio team. For the latest updates, visit our [GitHub repository](https://github.com/***REMOVED_USER***/pantry-pirate-radio).*