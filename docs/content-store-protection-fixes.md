# Content Store Protection Fixes

This document explains the fixes implemented to prevent content store data loss that was occurring during HAARRRvest publisher operations.

## Problem Summary

The content store dashboard was showing dramatic drops in total content count (from ~30k to ~1k) when:
1. The HAARRRvest publisher container was restarted
2. During regular publishing cycles when git operations occurred

### Root Causes Identified

1. **Git Stash Data Loss**: The publisher's `git stash` operation was destroying content store data because:
   - Content store files were tracked by git
   - `git stash` operations removed tracked files from the working directory
   - Even though code attempted to preserve content_store, the stash operation affected tracked files

2. **Race Conditions in Statistics**: Multiple separate SQL queries for statistics could return inconsistent results during concurrent operations

3. **SQLite Concurrency Issues**: Default SQLite journal mode wasn't optimal for concurrent access

## Fixes Implemented

### 1. Protected Git Stash Operations (`app/haarrrvest_publisher/service.py`)

**Before**: Destructive stash operations that removed content store data
```python
# Old problematic code
self._run_command(["git", "stash", "push", "-m", "Publisher auto-stash"], cwd=self.data_repo_path)
```

**After**: Content store protection with selective stashing
```python
def _safe_git_stash_with_content_store_protection(self):
    """Stash changes while protecting content store data."""
    
    # First, commit any content store changes immediately to protect them
    content_store_path = self.data_repo_path / "content_store"
    if content_store_path.exists():
        logger.info("Protecting content store: committing changes before stash")
        self._run_command(["git", "add", "content_store/"], cwd=self.data_repo_path)
        
        # Check if there are actually changes to commit
        code, out, err = self._run_command(
            ["git", "diff", "--cached", "--name-only"], cwd=self.data_repo_path
        )
        if out.strip():
            # Commit content store changes with a clear message
            commit_msg = f"Auto-commit content store updates - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            self._run_command([
                "git", "commit", "-m", commit_msg
            ], cwd=self.data_repo_path)
            logger.info("Content store changes committed successfully")
    
    # Now check for any remaining non-content-store changes to stash
    code, out, err = self._run_command(
        ["git", "status", "--porcelain"], cwd=self.data_repo_path
    )
    if out.strip():
        # Only stash non-content-store files using pathspec exclusion
        logger.info("Stashing non-content-store changes")
        self._run_command([
            "git", "stash", "push", "-m", "Publisher auto-stash (excluding content_store)",
            "--", ".", ":(exclude)content_store"
        ], cwd=self.data_repo_path)
    else:
        logger.info("No additional changes to stash after content store commit")
```

**Key improvements:**
- Content store changes are **committed before any stash operations**
- Uses git pathspec exclusion `:(exclude)content_store` to prevent stashing content store files
- Maintains version control for content store while preventing data loss

### 2. Integrity Verification

Added before/after checks for git operations:
```python
def _verify_content_store_integrity(self, before_stats, after_stats):
    """Verify content store wasn't damaged by git operations."""
    if before_stats and after_stats:
        before_count = before_stats.get('total_content', 0)
        after_count = after_stats.get('total_content', 0)
        
        if after_count < before_count * 0.95:  # 5% tolerance for edge cases
            raise Exception(
                f"CRITICAL: Content store data loss detected during git operations! "
                f"Before: {before_count}, After: {after_count}"
            )
        elif before_count > 0:  # Only log if we had data to begin with
            logger.info(f"Content store integrity verified: {after_count} items preserved")
```

### 3. Atomic Statistics Queries (`app/content_store/store.py`)

**Before**: Multiple separate queries that could be inconsistent
```python
# Old problematic code
total = conn.execute("SELECT COUNT(*) FROM content_index").fetchone()[0]
processed = conn.execute("SELECT COUNT(*) FROM content_index WHERE status = 'completed'").fetchone()[0]
pending = conn.execute("SELECT COUNT(*) FROM content_index WHERE status = 'pending'").fetchone()[0]
```

**After**: Single atomic query with WAL mode
```python
def get_statistics(self) -> dict:
    """Get statistics about stored content."""
    db_path = self.content_store_path / "index.db"

    # Use a single transaction to get all counts atomically
    with sqlite3.connect(db_path) as conn:
        # Enable WAL mode for better concurrent access
        conn.execute("PRAGMA journal_mode=WAL")
        
        # Get all statistics in a single query to ensure consistency
        cursor = conn.execute("""
            SELECT 
                COUNT(*) as total_content,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as processed_content,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending_content
            FROM content_index
        """)
        
        row = cursor.fetchone()
        total = row[0] or 0
        processed = row[1] or 0
        pending = row[2] or 0
```

**Key improvements:**
- Single SQL query ensures consistent counts
- WAL mode enables better concurrent access
- Eliminates race conditions between separate queries

### 4. Dashboard Resilience (`app/content_store/dashboard.py`)

**Before**: No error handling for database locks or temporary issues

**After**: Retry logic and graceful degradation
```python
def api_stats():
    """API endpoint for dashboard data with improved error handling."""
    try:
        # Get basic stats with retry logic
        max_retries = 3
        stats = None
        for attempt in range(max_retries):
            try:
                stats = store.get_statistics()
                break
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                    # Brief delay before retry for database lock
                    import time
                    time.sleep(0.1 * (attempt + 1))  # Exponential backoff
                    continue
                raise
        
        if stats is None:
            return jsonify({"error": "Content store temporarily unavailable"}), 503
```

**Key improvements:**
- Exponential backoff retry for database locks
- Graceful error handling with meaningful error messages
- Continues operation even if some components fail

## Testing

Created comprehensive test suite (`scripts/test-content-store-protection.py`) that verifies:

1. **Statistics Consistency**: Multiple rapid statistics calls return consistent results
2. **Git Stash Protection**: Simulates git operations and verifies content store preservation
3. **WAL Mode**: Confirms SQLite WAL mode is properly enabled

## Deployment Impact

### Immediate Benefits
- **Eliminates data loss** during HAARRRvest publisher operations
- **Prevents dashboard count drops** from 30k to 1k scenario
- **Improves reliability** of content store operations

### Performance Benefits
- WAL mode improves concurrent access performance
- Single atomic queries reduce database contention
- Retry logic handles temporary issues gracefully

### Operational Benefits
- Content store remains in version control (HAARRRvest repo)
- Integrity verification alerts to any unexpected data loss
- Better error messages for troubleshooting

## Monitoring

The fixes include enhanced logging to monitor:
- Content store counts before/after git operations
- Git stash protection activities
- Database retry attempts
- Integrity verification results

## Future Enhancements

Additional improvements that could be implemented:

1. **File Locking**: Advisory locks during critical operations
2. **Backup/Restore**: Automatic backup before risky operations  
3. **Metrics**: Prometheus metrics for content store health
4. **Alerting**: Automated alerts on significant count drops

## Configuration

No configuration changes required. The fixes are automatically active and backward compatible.

## Rollback Plan

If issues arise, the fixes can be disabled by:
1. Reverting to the old git stash logic in HAARRRvest publisher
2. Reverting to separate SQL queries in content store statistics
3. Removing retry logic from dashboard

However, this would restore the original data loss vulnerability.

---

**Status**: ✅ **DEPLOYED AND TESTED**  
**Risk Level**: 🟢 **LOW** - Backward compatible improvements  
**Impact**: 🔴 **HIGH** - Prevents critical data loss
