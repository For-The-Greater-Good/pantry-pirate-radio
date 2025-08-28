# HAARRRvest Repository Size Optimization

## Problem
The HAARRRvest publisher's `/data-repo` directory was growing excessively large on production hosts, with the `.git` folder becoming bloated due to:
- Frequent commits (every 5 minutes)
- Large binary files (SQL dumps, SQLite databases)
- Full git history retention
- No garbage collection or cleanup

## Solution Implemented

### 1. Reduced Commit Frequency
- Changed from 5 minutes (300s) to 12 hours (43200s)
- Reduces commits by 144x
- Configurable via `PUBLISHER_CHECK_INTERVAL` environment variable

### 2. Git Garbage Collection
- Runs `git gc --aggressive --prune=now` after each push
- Removes unreferenced objects and compresses repository

### 3. Shallow Clone Maintenance
- Maintains shallow clone with `--depth=1` on fetches
- Limits history to most recent commits only
- Prevents historical data accumulation

### 4. Repository Size Monitoring
- Monitors `.git` folder size continuously
- Alerts at 5GB (warning) and 10GB (critical)
- Automatically triggers deep cleanup when threshold exceeded

### 5. Periodic Maintenance Routines

#### Weekly Cleanup (7 days)
- Removes old branches
- Runs aggressive git gc
- Repacks repository with optimal settings
- Cleans reflog

#### Monthly Cleanup (30 days)
- Performs deep repository analysis
- If >20GB: performs fresh shallow clone
- Preserves content_store during re-clone
- Resets repository to minimal size

## Configuration

### Environment Variables
```bash
# Publishing interval (default: 12 hours)
PUBLISHER_CHECK_INTERVAL=43200

# Days of data to sync (default: 7)
DAYS_TO_SYNC=7

# Error retry delay (default: 60 seconds)
ERROR_RETRY_DELAY=60
```

## Expected Results

### Before Optimization
- `.git` folder: Several GB
- Growth rate: ~100MB/day
- Commit frequency: Every 5 minutes

### After Optimization
- `.git` folder: <1GB typical, max 10GB before cleanup
- Growth rate: Minimal (shallow history)
- Commit frequency: Every 6 hours (configurable)
- Automatic cleanup when size thresholds reached

## Monitoring

The publisher logs repository sizes at each run:
```
Repository sizes - Total: 250.3MB, .git: 45.2MB, Data: 205.1MB
```

Warnings are logged when thresholds are exceeded:
```
⚠️ .git folder is 5500.5MB - approaching size limit
⚠️ .git folder is 12500.3MB - exceeds 10GB threshold!
```

## Manual Intervention

If the repository becomes corrupted or needs manual cleanup:

1. **Quick cleanup** (in container):
```bash
cd /data-repo
git gc --aggressive --prune=all
git repack -a -d -f --depth=250 --window=250
```

2. **Fresh clone** (nuclear option):
```bash
cd /data-repo
# Backup content_store if needed
cp -r content_store /tmp/content_store_backup
# Remove everything except directory
rm -rf .git *
# Fresh shallow clone
git clone --depth=1 --single-branch --branch main https://github.com/For-The-Greater-Good/HAARRRvest.git .
# Restore content_store
cp -r /tmp/content_store_backup content_store
```

## Implementation Details

Key changes in `app/haarrrvest_publisher/service.py`:

1. `_get_repository_size()` - Monitors repository and .git sizes
2. `_check_and_cleanup_repository()` - Checks thresholds and triggers cleanup
3. `_perform_deep_cleanup()` - Aggressive git maintenance
4. `_maintain_shallow_clone()` - Keeps repository shallow
5. `_perform_periodic_maintenance()` - Weekly/monthly cleanup
6. `_perform_fresh_clone()` - Nuclear option for size reset

## Deployment

To deploy these changes:

1. Update the pantry-pirate-radio codebase
2. Rebuild the haarrrvest-publisher container
3. Set `PUBLISHER_CHECK_INTERVAL=43200` in environment
4. Restart the publisher service

The optimizations will take effect immediately, with the first cleanup occurring at the next threshold breach or scheduled maintenance window.