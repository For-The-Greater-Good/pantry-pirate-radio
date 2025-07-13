# Recorder Service

## Overview

The recorder service is a critical component of Pantry Pirate Radio's data processing pipeline, responsible for persisting and archiving job results from the LLM processing system. It works in conjunction with the worker and reconciler services to ensure data durability and traceability.

Key responsibilities:
- Monitoring and saving completed LLM job results
- Creating compressed archives of raw data
- Maintaining organized output directories
- Tracking job processing metrics

```plaintext
┌─────────────┐
│  LLM Jobs   │
└─────┬───────┘
      │
      ▼
┌──────────────────┐
│  Redis Queue     │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│    Recorder      │
│  ┌────────────┐  │
│  │ Job Saver  │  │
│  └────────────┘  │
│  ┌────────────┐  │
│  │  Archiver  │  │
│  └────────────┘  │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Output Files    │
│  - JSON Results  │
│  - Archives      │
└──────────────────┘
```

## Architecture

### Core Components

1. **RecorderUtils**
   - Main utility class handling recorder operations
   - Manages Redis connections and file system operations
   - Implements async context management
   - Handles job polling and processing

2. **File System Organization**
   - `outputs/`: Directory for JSON job results
   - `archives/`: Directory for compressed raw data archives
   - Automatic directory creation and management
   - Consistent file naming conventions

3. **Redis Integration**
   - Async Redis client configuration
   - Health check monitoring
   - Connection retry handling
   - Job status tracking

## Core Features

### Job Result Processing

The recorder continuously monitors Redis for completed jobs:

```python
async def save_completed_jobs(
    self,
    scraper_id: str | None = None
) -> list[Path]:
    """Save completed job results to JSON files.

    Args:
        scraper_id: Optional scraper ID to filter jobs

    Returns:
        List of paths to saved JSON files
    """
```

Key aspects:
- Polls Redis for newly completed jobs
- Filters by scraper ID if specified
- Processes jobs in chronological order
- Maintains job status metrics

### File Management

Job results are saved as structured JSON files:

```python
async def _process_job(
    self,
    job_id: str,
    output_dir: Path
) -> Path | None:
    """Process a single job and save its result.

    Args:
        job_id: ID of job to process
        output_dir: Directory to save result

    Returns:
        Path to saved file if successful
    """
```

Features:
- Unique file naming using job IDs
- Structured JSON output
- Complete job metadata
- Processing timestamps

### Archive Creation

Raw data can be archived with metadata:

```python
async def archive_raw_data(
    self,
    content: str,
    source_url: str,
    metadata: dict[str, Any],
) -> Path:
    """Archive raw content to compressed file.

    Args:
        content: Raw content to archive
        source_url: Where the content came from
        metadata: Additional metadata

    Returns:
        Path to archive file
    """
```

Archive format:
- Compressed tar.gz files
- Timestamped filenames
- Includes raw content and metadata
- Source URL tracking

### Error Handling

Comprehensive error handling strategy:

1. **Redis Errors**
   - Connection retry logic
   - Health check monitoring
   - Graceful disconnection

2. **File System Errors**
   - Directory creation validation
   - Write permission checking
   - Disk space monitoring

3. **Job Processing Errors**
   - Invalid job data handling
   - Parsing error recovery
   - Metric tracking

### Prometheus Metrics

```python
# Job processing metrics
RECORDER_JOBS = Counter(
    "recorder_jobs_total",
    "Total number of jobs recorded",
    ["scraper_id", "status"]
)
```

Tracked metrics:
- Total jobs processed
- Success/failure rates
- Processing duration
- Archive creation stats

## Configuration

### Environment Variables

Required configuration:
- `REDIS_URL`: Redis connection string (required)

### Directory Structure

Default directories:
- `outputs/`: JSON job results
- `archives/`: Compressed archives

### Command Line Arguments

```bash
python -m app.recorder [options]

Options:
  --output-dir PATH    Directory for JSON output files
  --archive-dir PATH   Directory for archive files
  --interval SECONDS   How often to check for new jobs
```

### Redis Configuration

```python
redis = Redis.from_url(
    redis_url,
    encoding="utf-8",
    decode_responses=False,
    retry_on_timeout=True,
    socket_keepalive=True,
    health_check_interval=30,
)
```

## Usage

### Running the Service

Start the recorder service:

```bash
# Basic usage
python -m app.recorder

# Custom directories
python -m app.recorder \
  --output-dir /path/to/outputs \
  --archive-dir /path/to/archives

# Custom interval
python -m app.recorder --interval 30
```

### Job Result Format

Saved job results include:

```json
{
  "job_id": "unique-job-id",
  "job": {
    "created_at": "2025-02-17T06:46:23Z",
    ...
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

### Archive Format

Created archives contain:

```plaintext
archive_20250217_064623_scraper123.tar.gz
├── content.txt      # Raw scraped content
└── metadata.json    # Source and processing metadata
```

## Implementation Details

### Job Polling

The recorder implements an efficient polling mechanism:

1. Tracks last poll timestamp
2. Queries only new completions
3. Processes in chronological order
4. Maintains consistent intervals

### File Naming

Consistent naming conventions:
- Job results: `{job_id}.json`
- Archives: `{timestamp}_{scraper_id}.tar.gz`

### Error Recovery

Robust error handling:
1. Transaction rollback on failure
2. Automatic file cleanup
3. Redis reconnection
4. Metric recording

### Future Improvements

Potential enhancements:
1. Batch processing support
2. Compression options
3. S3/cloud storage integration
4. Enhanced monitoring
