# PostgreSQL Database Backup

This document describes the automated PostgreSQL database backup solution implemented in this project.

## Overview

The project uses the `prodrigestivill/postgres-backup-local` Docker image to perform automated backups of the PostgreSQL database. This service is configured to:

- Run backups every 15 minutes
- Maintain backups with a retention policy
- Store backups in a dedicated Docker volume

## Configuration

The backup service is configured in the `docker-compose.yml` and `docker-compose.dev.yml` files. The key configuration parameters are:

- `SCHEDULE`: Cron expression for backup frequency (default: `*/15 * * * *` - every 15 minutes)
- `BACKUP_KEEP_DAYS`: Number of days to keep daily backups (default: 7)
- `BACKUP_KEEP_WEEKS`: Number of weeks to keep weekly backups (default: 4)
- `BACKUP_KEEP_MONTHS`: Number of months to keep monthly backups (default: 12)

## Retention Policy

The backup service implements the following retention policy:

- All backups from the last 24 hours are kept
- One backup per day is kept for the last 7 days
- One backup per week is kept for the last 4 weeks
- One backup per month is kept for the last 12 months

This policy ensures that recent backups are available for quick recovery, while older backups are pruned to save disk space.

## Backup Storage

Backups are stored in a dedicated Docker volume named `postgres_backups`. This volume persists across container restarts and can be accessed by other containers if needed.

## Backup Format

Backups are created using `pg_dump` and are stored as compressed SQL files. Each backup file is named with a timestamp, making it easy to identify when the backup was created.

## Monitoring

The backup service exposes a health check endpoint on port 8080 that can be used to monitor the status of the backup service. This endpoint returns HTTP 200 if the service is healthy and the last backup was successful.

## Manual Backup

To manually trigger a backup, you can run:

```bash
docker-compose exec db-backup sh -c 'PGPASSWORD=$POSTGRES_PASSWORD pg_dump -h $POSTGRES_HOST -U $POSTGRES_USER -d $POSTGRES_DB | gzip > /backups/manual-$(date "+%Y-%m-%d_%H-%M-%S").sql.gz'
```

## Restoring from Backup

To restore from a backup, you can use the following steps:

1. List available backups:

```bash
docker-compose exec db-backup ls -la /backups
```

2. Choose a backup file and restore it:

```bash
# Stop services that depend on the database
docker-compose stop app worker recorder reconciler

# Restore the backup
docker-compose exec db-backup sh -c 'gunzip -c /backups/BACKUP_FILENAME.sql.gz | PGPASSWORD=$POSTGRES_PASSWORD psql -h $POSTGRES_HOST -U $POSTGRES_USER -d $POSTGRES_DB'

# Restart services
docker-compose start app worker recorder reconciler
```

Replace `BACKUP_FILENAME.sql.gz` with the actual backup file name.

## Customization

If you need to customize the backup configuration, you can modify the environment variables in the `docker-compose.yml` file. For example, to change the backup frequency to hourly, you would change the `SCHEDULE` variable to `0 * * * *`.
