# Replay Module

The replay module allows you to recreate database records from JSON files saved by the recorder service. This is useful for recovering from database resets or migrations without re-running expensive LLM processing.

## Features

- Single file or batch directory processing
- Dry run mode for validation
- Smart filtering of completed jobs
- Comprehensive error handling and logging
- CLI interface with multiple options

## Usage

### Process a single file

```bash
python -m app.replay --file outputs/job_123.json
```

### Process all files in a directory

```bash
python -m app.replay --directory outputs/
```

### Use default output directory

```bash
python -m app.replay --use-default-output-dir
```

### Dry run mode

Preview what would be processed without making changes:

```bash
python -m app.replay --directory outputs/ --dry-run
```

### Custom file patterns

Process only files matching a specific pattern:

```bash
python -m app.replay --directory outputs/ --pattern "job_2025*.json"
```

### Verbose mode

Enable detailed logging:

```bash
python -m app.replay --directory outputs/ --verbose
```

## How it Works

1. Reads JSON files from recorder service output
2. Validates job data and filters completed jobs
3. Reconstructs `JobResult` objects with proper types
4. Sends jobs to reconciler queue for database processing
5. Reports success/failure statistics

## Notes

- Only completed jobs with valid results are processed
- Failed jobs and incomplete jobs are skipped
- The replay preserves original job IDs and metadata
- Processing is idempotent - safe to run multiple times