# Replay Module

The replay module allows you to recreate database records from JSON files saved by the recorder service. This is essential for recovering from database resets, migrations, or replaying historical data without re-running expensive LLM processing.

**Important Update (Issue #369):** As of this update, the replay tool now routes through the validation service by default for data enrichment and quality control, ensuring consistency with the production pipeline. Use the `--skip-validation` flag to bypass validation and route directly to the reconciler (legacy behavior).

## Purpose and Benefits

The replay system provides critical capabilities for data management and debugging:

- **Data Recovery**: Restore database state after migrations, resets, or failures
- **Cost Savings**: Avoid re-running expensive LLM API calls by replaying saved results
- **Debugging**: Replay specific scraper runs or date ranges to debug processing issues
- **Testing**: Use recorded data for integration testing without hitting live APIs
- **Auditing**: Replay historical data to verify processing consistency
- **Migration Support**: Easily migrate data between database schemas or environments

## Architecture Overview

The replay system works in conjunction with the recorder service:

1. **Recorder Service**: Automatically saves all job results to JSON files organized by date and scraper
2. **Replay Module**: Reads these JSON files and routes them through the validation service (default) or directly to the reconciler (with `--skip-validation`)
3. **Validation Service** (default path): Enriches data with confidence scores, quality checks, and geocoding corrections before sending to the reconciler
4. **Reconciler**: Processes validated jobs, creating database records with enhanced data quality

## Data Recording Process

The recorder service automatically captures all job results with the following structure:

```
outputs/
├── daily/
│   ├── 2025-08-07/
│   │   ├── scrapers/
│   │   │   ├── freshtrak/
│   │   │   │   ├── 1754541721.120277.json
│   │   │   │   └── ...
│   │   │   └── other-scraper/
│   │   │       └── ...
│   │   ├── processed/
│   │   │   ├── f0b82a5e-a792-470b-8c91-0657e1423dd9.json
│   │   │   └── ...
│   │   └── summary.json
│   └── 2025-08-08/
│       └── ...
└── latest -> daily/2025-08-07  (symlink to most recent day)
```

Recording happens automatically when:
- Scrapers complete data extraction
- LLM processing finishes
- Reconciler processes job results

## Usage with Bouy Commands

### Basic Replay Operations

```bash
# Replay all recorded data from default outputs directory (validates by default)
./bouy replay --use-default-output-dir

# Replay specific directory (validates by default)
./bouy replay --directory outputs/daily/2025-08-07

# Replay single file (validates by default)
./bouy replay --file outputs/daily/2025-08-07/processed/job_123.json

# Skip validation - route directly to reconciler (legacy mode)
./bouy replay --file outputs/daily/2025-08-07/processed/job_123.json --skip-validation

# Dry run - preview what would be processed
./bouy replay --use-default-output-dir --dry-run

# Verbose mode for detailed logging
./bouy replay --use-default-output-dir --verbose
```

### Advanced Replay Scenarios

```bash
# Replay only today's scraper results (with validation)
./bouy replay --directory outputs/daily/$(date +%Y-%m-%d)/scrapers

# Replay specific scraper's data (with validation)
./bouy replay --directory outputs/daily/2025-08-07/scrapers/freshtrak

# Replay with custom pattern (e.g., specific job IDs)
./bouy replay --directory outputs --pattern "f0b82a5e*.json"

# Replay processed LLM results only (with validation)
./bouy replay --directory outputs/daily/2025-08-07/processed

# Legacy mode - bypass validation for debugging
./bouy replay --directory outputs/daily/2025-08-07 --skip-validation
```

## JSON Format Documentation

### Scraper Job Result Format

```json
{
  "job_id": "1754541721.120277",
  "job": {
    "id": "1754541721.120277",
    "prompt": "Extract organization data from the following HTML...",
    "format": {
      "type": "object",
      "properties": {
        "organizations": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "name": {"type": "string"},
              "address": {"type": "string"},
              "phone": {"type": "string"}
            }
          }
        }
      }
    },
    "provider_config": {
      "model": "gpt-4",
      "temperature": 0.3
    },
    "metadata": {
      "scraper_id": "freshtrak",
      "source_url": "https://example.com/pantries",
      "timestamp": "2025-08-07T10:15:21.120277"
    },
    "created_at": "2025-08-07T10:15:21.120277+00:00"
  },
  "result": {
    "organizations": [
      {
        "name": "Community Food Pantry",
        "address": "123 Main St, Springfield, OH 45501",
        "phone": "(937) 555-0123"
      }
    ]
  },
  "error": null,
  "completed_at": "2025-08-07T10:15:25.543210+00:00",
  "processing_time": 4.423,
  "retry_count": 0
}
```

### Processed LLM Result Format

```json
{
  "job_id": "f0b82a5e-a792-470b-8c91-0657e1423dd9",
  "job": {
    "id": "f0b82a5e-a792-470b-8c91-0657e1423dd9",
    "prompt": "Standardize the following organization data...",
    "format": {
      "type": "object",
      "properties": {
        "standardized_data": {"type": "object"}
      }
    },
    "provider_config": {
      "temperature": 0.7,
      "model": "claude-3-sonnet"
    },
    "metadata": {
      "processing_stage": "standardization",
      "original_scraper": "freshtrak"
    },
    "created_at": "2025-08-07T11:30:20.394449+00:00"
  },
  "result": {
    "text": "Standardized organization data...",
    "model": "claude-3-sonnet",
    "usage": {
      "total_tokens": 1500,
      "prompt_tokens": 1000,
      "completion_tokens": 500
    }
  },
  "error": null,
  "completed_at": "2025-08-07T11:30:22.123456+00:00",
  "processing_time": 1.729,
  "retry_count": 0
}
```

## Validation Integration

### Why Validation is Now Default

As of Issue #369, the replay tool routes through the validation service by default to ensure:

1. **Data Enrichment**: Adds confidence scores, quality metrics, and data completeness checks
2. **Geocoding Correction**: Fixes invalid coordinates (0,0) and enhances location accuracy
3. **Consistency**: Replayed data receives the same processing as live data
4. **Quality Control**: Identifies and flags problematic data before database insertion

### When to Use --skip-validation

Use the `--skip-validation` flag in these scenarios:

- **Testing Reconciler Logic**: When debugging reconciler-specific issues
- **Performance Testing**: To measure reconciler performance without validation overhead
- **Emergency Recovery**: When validation service is unavailable but data recovery is critical
- **Legacy Compatibility**: For systems expecting direct reconciler routing

### Data Flow Comparison

**Default Flow (with validation):**
```
JSON Files → Replay Tool → Validation Service → Reconciler → Database
                              ↓
                     (Enrichment & QC)
```

**Legacy Flow (with --skip-validation):**
```
JSON Files → Replay Tool → Reconciler → Database
```

## Practical Use Cases

### 1. Database Recovery After Migration

```bash
# After database migration or reset
./bouy up --with-init                    # Initialize new database
./bouy replay --use-default-output-dir   # Restore all data (with validation)
```

### 2. Debugging Scraper Issues

```bash
# Replay specific scraper's data to debug processing (with validation)
./bouy replay --directory outputs/daily/2025-08-07/scrapers/problematic-scraper --verbose

# Test changes with dry run first
./bouy replay --file outputs/daily/2025-08-07/scrapers/test-case.json --dry-run

# Debug without validation to isolate reconciler issues
./bouy replay --file outputs/daily/2025-08-07/scrapers/test-case.json --skip-validation --verbose
```

### 3. Data Recovery from Specific Date Range

```bash
# Replay last 7 days of data
for date in $(seq 0 6); do
  replay_date=$(date -d "$date days ago" +%Y-%m-%d)
  ./bouy replay --directory outputs/daily/$replay_date
done
```

### 4. Testing Database Changes

```bash
# Test database schema changes with real data (with validation)
./bouy replay --directory outputs/daily/2025-08-07 --dry-run
# If dry run succeeds, run actual replay
./bouy replay --directory outputs/daily/2025-08-07

# Test without validation if focusing on schema compatibility
./bouy replay --directory outputs/daily/2025-08-07 --skip-validation --dry-run
```

## Integration with System Components

### Scraper Integration

Scrapers automatically record their results through the recorder service:
1. Scraper extracts data from source
2. Sends to LLM for processing
3. Recorder saves result to organized directory structure
4. Replay can recreate this data anytime

### Reconciler Integration

The replay module integrates with the data pipeline:

**Default Path (with validation):**
1. Reads saved JobResult from JSON
2. Reconstructs LLMJob and LLMResponse objects
3. Sends to validation service for enrichment
4. Validator adds confidence scores and quality metrics
5. Validated data sent to reconciler
6. Reconciler creates/updates database records

**Legacy Path (with --skip-validation):**
1. Reads saved JobResult from JSON
2. Reconstructs LLMJob and LLMResponse objects
3. Sends directly to `process_job_result()` in reconciler
4. Reconciler creates/updates database records

### HAARRRvest Publisher Integration

After replaying data:
```bash
# Replay data first (with validation for best quality)
./bouy replay --use-default-output-dir

# Then publish to HAARRRvest
./bouy haarrrvest run
```

Note: Using validation ensures HAARRRvest receives enriched data with confidence scores and corrected geocoding.

## Troubleshooting

### Common Issues and Solutions

#### 1. "File not found" Errors
```bash
# Check if outputs directory exists
ls -la outputs/

# Ensure OUTPUT_DIR environment variable is set
echo $OUTPUT_DIR

# Use explicit directory path
./bouy replay --directory /absolute/path/to/outputs
```

#### 2. "Invalid JSON" Errors
```bash
# Validate JSON file manually
jq . outputs/daily/2025-08-07/processed/job_123.json

# Skip corrupted files by processing directory without pattern
./bouy replay --directory outputs --pattern "*.json" --dry-run
```

#### 3. Database Connection Issues
```bash
# Ensure database is running
./bouy ps

# Check database initialization
./bouy exec db psql -U postgres -c "\\dt"

# Restart services if needed
./bouy down && ./bouy up
```

#### 4. Memory Issues with Large Datasets
```bash
# Process in smaller batches by date
./bouy replay --directory outputs/daily/2025-08-07

# Or by specific scrapers
./bouy replay --directory outputs/daily/2025-08-07/scrapers/scraper-name
```

#### 5. Duplicate Data Concerns
The replay system is idempotent - running multiple times is safe:
- Uses original job IDs to prevent duplicates
- Reconciler handles deduplication
- Database constraints prevent duplicate records

## Performance Considerations

- **File Size Limit**: Maximum 100MB per JSON file for security
- **Batch Processing**: Files are processed sequentially to avoid overwhelming the database
- **Progress Logging**: Updates every 500 files during batch operations
- **Memory Usage**: Each file is processed individually to minimize memory footprint
- **Database Load**: Reconciler queues prevent database overload

## Security Notes

- **Path Validation**: Prevents directory traversal attacks
- **File Size Limits**: Protects against memory exhaustion
- **Allowed Directories**: Restricts file access to specified directories
- **JSON Validation**: Safely parses JSON with error handling
- **No Code Execution**: Only data is replayed, never executable code

## Limitations

- Only processes completed jobs with valid results
- Failed jobs and errors are logged but not replayed
- Requires original job ID to maintain consistency
- JSON files must match expected JobResult schema
- Maximum file size of 100MB per JSON file
- Date-based directory structure is expected for batch operations

## Best Practices

1. **Regular Backups**: Keep outputs directory backed up for disaster recovery
2. **Dry Run First**: Always test with `--dry-run` before actual replay
3. **Use Validation**: Keep default validation enabled for best data quality
4. **Monitor Logs**: Use `--verbose` flag when debugging issues
5. **Batch by Date**: Process one day at a time for large datasets
6. **Verify Results**: Check database after replay to confirm data integrity
7. **Clean Old Data**: Archive old JSON files to manage disk space
8. **Skip Validation Sparingly**: Only use `--skip-validation` for specific debugging needs