# Recorder Service

## Overview

The recorder service is a critical component of Pantry Pirate Radio's data processing pipeline, responsible for saving job results from the LLM processing system to organized JSON files. It works as an RQ worker that processes jobs from the "recorder" queue.

Key responsibilities:
- Processing job results from the recorder queue
- Creating organized date-based directory structures
- Saving job results as JSON files
- Maintaining daily summaries
- Tracking processing metrics

```plaintext
┌─────────────┐
│  LLM Jobs   │
└─────┬───────┘
      │
      ▼
┌──────────────────┐
│  Redis Queue     │
│   (recorder)     │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│    Recorder      │
│  RQ Worker       │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Output Files    │
│  - JSON Results  │
│  - Daily Summary │
└──────────────────┘
```

## Architecture

### Core Components

1. **RQ Worker Implementation**
   - Processes jobs from "recorder" queue
   - Handles job result serialization
   - Manages Redis connections
   - Implements retry logic

2. **File System Organization**
   - **Date-based structure**: `outputs/daily/YYYY-MM-DD/`
   - **Scraper-specific directories**: `outputs/daily/YYYY-MM-DD/scrapers/{scraper_id}/`
   - **Processed results**: `outputs/daily/YYYY-MM-DD/processed/`
   - **Latest symlink**: `outputs/latest` → points to most recent date directory
   - **Daily summaries**: `outputs/daily/YYYY-MM-DD/summary.json`
   - Automatic directory creation and management
   - Consistent file naming using job IDs

3. **Redis Integration**
   - RQ (Redis Queue) for job processing
   - Connection pooling and retry logic
   - Health check monitoring
   - Job status tracking

## Running the Recorder Service

### Using Bouy Commands

```bash
# Start recorder service
./bouy recorder

# The recorder will:
# 1. Start cache (Redis) if not running
# 2. Verify Redis connectivity
# 3. Start the RQ worker for the "recorder" queue
# 4. Process jobs continuously

# View recorder logs
./bouy logs recorder

# Check recorder status
./bouy ps | grep recorder

# Stop recorder
./bouy down recorder
```

### Manual Execution (Debug Mode)

```bash
# Run recorder directly in container
./bouy exec app python -m app.recorder

# With custom output directory
./bouy exec app bash -c "OUTPUT_DIR=/custom/path python -m app.recorder"
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `REDIS_URL` | Redis connection string | Required |
| `OUTPUT_DIR` | Directory for JSON output files | `outputs` |
| `ARCHIVE_DIR` | Directory for archive files | `archives` |

### Directory Structure

Default directory layout created automatically:
```
outputs/
├── daily/
│   └── YYYY-MM-DD/
│       ├── summary.json
│       ├── scrapers/
│       │   └── {scraper_id}/
│       │       └── {job_id}.json
│       └── processed/
│           └── {job_id}.json
└── latest -> daily/YYYY-MM-DD (symlink to most recent date)
```

## Job Result Processing

### How Jobs Are Processed

1. **Job Submission**: Other services enqueue jobs to the "recorder" queue
2. **Worker Processing**: RQ worker picks up jobs and calls `record_result()`
3. **Data Extraction**: Job metadata determines directory structure
4. **File Creation**: Results saved as JSON with proper formatting
5. **Summary Update**: Daily summary file updated with job info
6. **Symlink Update**: Latest symlink points to current date directory

### Job Result Format

Saved job results include complete job information:

```json
{
  "job_id": "unique-job-id",
  "job": {
    "created_at": "2025-02-17T06:46:23Z",
    "metadata": {
      "scraper_id": "nyc_efap_programs",
      "source_url": "https://example.com/page"
    }
  },
  "status": "completed",
  "result": {
    "text": "processed content",
    "model": "model name",
    "usage": {
      "total_tokens": 150
    },
    "validation_details": {
      "hallucination_detected": false,
      "mismatched_fields": [],
      "suggested_corrections": {}
    }
  },
  "retry_count": 0,
  "completed_at": "2025-02-17T06:47:23Z",
  "processing_time": 60.0
}
```

### Daily Summary Format

Each day's activities are summarized in `outputs/daily/YYYY-MM-DD/summary.json`:

```json
{
  "date": "2025-07-23",
  "total_jobs": 42,
  "scrapers": {
    "nyc_efap_programs": {
      "count": 15,
      "first_job": "2025-07-23T00:15:00Z",
      "last_job": "2025-07-23T23:45:00Z"
    },
    "foodhelp_org": {
      "count": 27,
      "first_job": "2025-07-23T01:00:00Z",
      "last_job": "2025-07-23T22:30:00Z"
    }
  },
  "jobs": [
    {
      "job_id": "abc-123",
      "scraper_id": "nyc_efap_programs",
      "timestamp": "2025-07-23T00:15:00Z"
    }
  ]
}
```

## Replay Functionality

The recorder service works in conjunction with the replay utility to restore data:

### Replaying Recorded Jobs

```bash
# Replay from default output directory
./bouy replay --use-default-output-dir

# Replay specific file
./bouy replay --file outputs/daily/2025-01-15/scrapers/nyc_efap/job123.json

# Replay entire directory
./bouy replay --directory outputs/daily/2025-01-15/

# Dry run (preview without executing)
./bouy replay --dry-run --use-default-output-dir
```

### Replay Process

1. **File Discovery**: Finds JSON files in specified location
2. **Data Validation**: Verifies job result structure
3. **Database Population**: Inserts data into PostgreSQL
4. **Progress Tracking**: Shows files processed and records created

## Monitoring and Metrics

### Prometheus Metrics

The recorder tracks these metrics:

```python
RECORDER_JOBS = Counter(
    "recorder_jobs_total",
    "Total number of jobs recorded",
    ["scraper_id", "status"]
)
```

Available metrics:
- `recorder_jobs_total{scraper_id="...", status="success"}` - Successful recordings
- `recorder_jobs_total{scraper_id="...", status="failure"}` - Failed recordings

### Health Checks

```bash
# Check if recorder is running
./bouy ps | grep recorder

# Verify Redis connectivity
./bouy exec cache redis-cli ping

# Check recent job processing
./bouy exec app ls -la outputs/latest/

# View processing metrics
./bouy exec app python -c "
from prometheus_client import REGISTRY
for collector in REGISTRY.collect():
    if 'recorder' in collector.name:
        print(collector)
"
```

## Error Handling

### Common Issues and Solutions

1. **Redis Connection Errors**
   ```bash
   # Ensure Redis is running
   ./bouy ps | grep cache
   
   # Restart Redis if needed
   ./bouy down cache && ./bouy up cache
   
   # Check Redis logs
   ./bouy logs cache --tail 50
   ```

2. **Permission Errors**
   ```bash
   # Check output directory permissions
   ./bouy exec app ls -la outputs/
   
   # Fix permissions if needed
   ./bouy exec app chmod -R 755 outputs/
   ```

3. **Disk Space Issues**
   ```bash
   # Check available space
   ./bouy exec app df -h /app/outputs
   
   # Clean old outputs if needed
   ./bouy exec app find outputs/daily -type d -mtime +30 -exec rm -rf {} +
   ```

4. **Job Processing Failures**
   ```bash
   # Check recorder logs for errors
   ./bouy logs recorder --tail 100
   
   # Inspect failed job queue
   ./bouy exec app python -c "
   from redis import Redis
   from rq import Queue
   redis = Redis.from_url('redis://cache:6379')
   q = Queue('recorder', connection=redis)
   print(f'Failed jobs: {q.failed_job_registry.count}')
   "
   ```

## Data Management

### Backup Recorded Data

```bash
# Create archive of recorded data
./bouy exec app tar -czf outputs_backup_$(date +%Y%m%d).tar.gz outputs/

# Copy to host system
docker cp $(docker compose ps -q app):/app/outputs_backup_*.tar.gz ./
```

### Clean Old Data

```bash
# Remove data older than 30 days
./bouy exec app find outputs/daily -type d -mtime +30 -exec rm -rf {} +

# Keep only summaries older than 7 days
./bouy exec app find outputs/daily -name "*.json" ! -name "summary.json" -mtime +7 -delete
```

### Data Recovery

```bash
# If outputs are lost, replay from HAARRRvest
./bouy replay --use-default-output-dir

# Or restore from SQL dump
./bouy up --with-init
```

## Integration with Other Services

### Worker Service
- Worker enqueues completed LLM jobs to recorder queue
- Recorder processes and saves results

### Reconciler Service
- Can read recorded job results for reconciliation
- Uses outputs for data validation

### HAARRRvest Publisher
- Publishes recorded data to HAARRRvest repository
- Creates SQL dumps from recorded data

## Best Practices

1. **Regular Monitoring**: Check recorder logs daily for errors
2. **Data Retention**: Implement cleanup for old recorded data
3. **Backup Strategy**: Regular backups of outputs directory
4. **Error Recovery**: Monitor failed job queue and retry as needed
5. **Performance**: Keep output directories organized with date-based structure
6. **Documentation**: Document any custom recording workflows

## Troubleshooting Tips

### Debugging Job Recording

```bash
# Watch recorder processing in real-time
./bouy logs -f recorder

# Check job queue status
./bouy exec app python -c "
from redis import Redis
from rq import Queue
redis = Redis.from_url('redis://cache:6379')
q = Queue('recorder', connection=redis)
print(f'Jobs in queue: {len(q)}')
print(f'Failed jobs: {q.failed_job_registry.count}')
"

# Manually process a job (for debugging)
./bouy exec app python -c "
from app.recorder.utils import record_result
test_data = {
    'job_id': 'test-123',
    'job': {'created_at': '2025-01-15T10:00:00Z', 'metadata': {'scraper_id': 'test'}},
    'result': {'text': 'test content'},
    'status': 'completed'
}
result = record_result(test_data)
print(result)
"
```

### Performance Optimization

```bash
# Check I/O performance
./bouy exec app iostat -x 1

# Monitor file system usage
./bouy exec app watch -n 1 'df -h /app/outputs; ls -la outputs/latest/ | wc -l'

# Optimize with batch processing (if needed)
# Consider implementing batch saves for high-volume scenarios
```

## Related Documentation

- [Database Backup](./database-backup.md) - Backup strategies including recorded data
- [Test Environment Setup](./test-environment-setup.md) - Testing recorder functionality
- [Datasette Viewer](./datasette.md) - Viewing recorded data
- [Architecture](./architecture.md) - System design and data flow