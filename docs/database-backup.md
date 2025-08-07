# Database Backup and Restore

This document describes the database backup and restore mechanisms for Pantry Pirate Radio, including both SQL dumps and automated PostgreSQL backups.

## Overview

The project uses SQL dumps as the primary backup strategy:

1. **SQL Dumps** - Complete database snapshots stored in the HAARRRvest repository for fast initialization

## SQL Dumps

SQL dumps are the primary mechanism for database backup and restore, providing fast initialization from known-good states.

### Creating SQL Dumps

SQL dumps are automatically created during HAARRRvest publishing, but can also be created manually:

```bash
# Create SQL dump using bouy (runs in container)
./bouy exec app bash /app/scripts/create-sql-dump.sh

# The dump will be created in the HAARRRvest repository:
# /data-repo/sql_dumps/pantry_pirate_radio_YYYY-MM-DD_HH-MM-SS.sql
# /data-repo/sql_dumps/latest.sql (symlink to most recent)
```

### SQL Dump Safety Features

The SQL dump creation includes several safety mechanisms:

- **Record Count Ratcheting**: Tracks maximum known record count to prevent accidental data loss
- **Threshold Checking**: Requires 90% of previous maximum records (configurable via `SQL_DUMP_RATCHET_PERCENTAGE`)
- **Minimum Records**: Default minimum of 100 records required (`SQL_DUMP_MIN_RECORDS`)
- **Override Option**: Set `ALLOW_EMPTY_SQL_DUMP=true` to force dump creation

The ratchet file (`sql_dumps/.record_count_ratchet`) tracks:
```json
{
  "max_record_count": 25000,
  "updated_at": "2024-01-15T10:30:00",
  "updated_by": "create-sql-dump.sh"
}
```

### Restoring from SQL Dumps

#### Automatic Restoration

SQL dumps are automatically restored during container initialization when using `--with-init`:

```bash
# Start services with database initialization
./bouy up --with-init

# The init process will:
# 1. Look for sql_dumps/latest.sql in HAARRRvest repository
# 2. Drop and recreate the database
# 3. Restore from the SQL dump
# 4. Complete in under 5 minutes for typical datasets
```

#### Manual Restoration

To manually restore a SQL dump:

```bash
# Stop dependent services
./bouy down app worker recorder reconciler

# List available SQL dumps
./bouy exec db ls -la /data-repo/sql_dumps/

# Restore specific dump (replace DUMP_FILE with actual filename)
./bouy exec db bash -c 'psql -U $POSTGRES_USER -d postgres -c "DROP DATABASE IF EXISTS $POSTGRES_DB;"'
./bouy exec db bash -c 'psql -U $POSTGRES_USER -d postgres -c "CREATE DATABASE $POSTGRES_DB;"'
./bouy exec db bash -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB < /data-repo/sql_dumps/DUMP_FILE'

# Restart services
./bouy up app worker recorder reconciler
```

### SQL Dump Format

SQL dumps are created with these characteristics:
- **Format**: Plain SQL (uncompressed for Git tracking)
- **Options**: `--no-owner --no-privileges --if-exists --clean`
- **Content**: Complete database including schema and data
- **Size**: Typically 50-200 MB for production datasets

## Automated Backups (Deprecated)

**Note:** The automated backup service (`db-backup`) has been deprecated and removed from the Docker Compose configuration. Users should implement their own backup strategy based on their specific infrastructure and requirements.

For database backups, consider:
- Using the SQL dump functionality described above
- Implementing platform-specific backup solutions (AWS RDS snapshots, Google Cloud SQL backups, etc.)
- Setting up PostgreSQL continuous archiving and point-in-time recovery (PITR)
- Using third-party backup tools like pgBackRest or Barman

## Backup Strategy

| Feature | SQL Dumps |
|---------|-----------|
| **Frequency** | On-demand / After publishing |
| **Storage** | HAARRRvest repository (Git) |
| **Format** | Plain SQL |
| **Use Case** | Distribution & initialization |
| **Availability** | All environments |
| **Retention** | Manual management |
| **Size** | 50-200 MB |

## Database Migration Workflows

### Migrating Between Environments

```bash
# 1. Create SQL dump from source environment
./bouy exec app bash /app/scripts/create-sql-dump.sh

# 2. Copy dump to target environment
# (SQL dumps are in HAARRRvest repo, so git pull on target)

# 3. Restore on target environment
./bouy up --with-init
```

### Disaster Recovery

```bash
# Option 1: Restore from latest SQL dump
./bouy up --with-init

# Option 2: Pull fresh data from HAARRRvest
./bouy exec app python -m app.replay --use-default-output-dir
```

## Testing Database Backups

```bash
# Create test backup
./bouy exec app bash /app/scripts/create-sql-dump.sh

# Verify dump was created
./bouy exec app ls -la /data-repo/sql_dumps/

# Test restoration in isolated environment
TESTING=true ./bouy up --with-init

# Verify data integrity
./bouy exec app python -c "
from app.database import get_session
from app.models import Organization
with get_session() as session:
    count = session.query(Organization).count()
    print(f'Organizations in database: {count}')
"
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `POSTGRES_HOST` | Database host | `db` |
| `POSTGRES_PORT` | Database port | `5432` |
| `POSTGRES_USER` | Database user | `pantry_pirate_radio` |
| `POSTGRES_DB` | Database name | `pantry_pirate_radio` |
| `POSTGRES_PASSWORD` | Database password | Required |
| `SQL_DUMP_DIR` | SQL dump directory | `./sql_dumps` |
| `SQL_DUMP_MIN_RECORDS` | Minimum records for dump | `100` |
| `SQL_DUMP_RATCHET_PERCENTAGE` | Ratchet threshold | `0.9` |
| `ALLOW_EMPTY_SQL_DUMP` | Force dump creation | `false` |
| `SKIP_DB_INIT` | Skip initialization | `false` |
| `DB_INIT_DAYS_TO_SYNC` | Days of data to sync | `90` |

## Monitoring and Health Checks

### Database Health

```bash
# Check database status
./bouy exec app python -c "
from app.database import get_session
from app.models import Organization, Location, Service
with get_session() as session:
    orgs = session.query(Organization).count()
    locs = session.query(Location).count()
    svcs = session.query(Service).count()
    print(f'Database Status:')
    print(f'  Organizations: {orgs}')
    print(f'  Locations: {locs}')
    print(f'  Services: {svcs}')
"
```


## Troubleshooting

### Common Issues

1. **SQL dump restore fails**
   - Check PostgreSQL is running: `./bouy ps | grep db`
   - Verify dump file exists: `./bouy exec app ls -la /data-repo/sql_dumps/`
   - Check permissions: Ensure container user can read dump file

2. **Empty or small SQL dumps**
   - Check record count: Database may be empty
   - Review ratchet file: May need to set `ALLOW_EMPTY_SQL_DUMP=true`
   - Verify source data: Ensure database has been populated

3. **Out of disk space**
   - Clean Docker volumes: `./bouy clean` (WARNING: Deletes all data)
   - Remove old SQL dumps: Manually delete from `sql_dumps/` directory

## Best Practices

1. **Regular Testing**: Test restore procedures monthly
2. **Multiple Copies**: Keep SQL dumps in Git and consider additional backup strategies
3. **Version Control**: Commit SQL dumps to HAARRRvest repository
4. **Documentation**: Document any custom backup/restore procedures
5. **Monitoring**: Set up alerts for backup failures in production
6. **Retention Policy**: Balance storage costs with recovery needs

## Related Documentation

- [Test Environment Setup](./test-environment-setup.md) - Testing with database backups
- [Recorder Service](./recorder.md) - Capturing job results for replay
- [Datasette Viewer](./datasette.md) - Exploring backup data
- [Architecture](./architecture.md) - System design and data flow