#!/usr/bin/env python3
"""
Rebuild content store SQLite database from existing content and result files.

This script scans the content_store directory and rebuilds the index.db
based on the actual files present, useful for recovery or migration.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
import hashlib
import argparse
import sys


def validate_hash(content_hash: str) -> bool:
    """Validate that a string is a valid SHA-256 hash."""
    if len(content_hash) != 64:
        return False
    try:
        int(content_hash, 16)
        return True
    except ValueError:
        return False


def extract_hash_from_filename(filepath: Path) -> str:
    """Extract hash from filename (removes .json extension)."""
    return filepath.stem


def rebuild_database(content_store_path: Path, verbose: bool = False):
    """
    Rebuild the content store database from existing files.
    
    Args:
        content_store_path: Path to content_store directory
        verbose: Print progress information
    """
    db_path = content_store_path / "index.db"
    content_dir = content_store_path / "content"
    results_dir = content_store_path / "results"
    
    if verbose:
        print(f"Rebuilding database at: {db_path}")
        print(f"Scanning content directory: {content_dir}")
        print(f"Scanning results directory: {results_dir}")
    
    # Backup existing database if it exists
    if db_path.exists():
        backup_path = db_path.with_suffix(f".backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        if verbose:
            print(f"Backing up existing database to: {backup_path}")
        db_path.rename(backup_path)
    
    # Create new database
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    
    # Create schema
    conn.execute("""
        CREATE TABLE IF NOT EXISTS content_index (
            hash TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            content_path TEXT NOT NULL,
            result_path TEXT,
            job_id TEXT,
            created_at TIMESTAMP NOT NULL,
            processed_at TIMESTAMP
        )
    """)
    
    # Scan content files
    content_files = {}
    if content_dir.exists():
        for content_file in content_dir.glob("*/*.json"):
            content_hash = extract_hash_from_filename(content_file)
            if not validate_hash(content_hash):
                if verbose:
                    print(f"Skipping invalid hash in filename: {content_file}")
                continue
            
            content_files[content_hash] = content_file
            
            # Try to read timestamp from file
            created_at = datetime.utcnow()
            try:
                with open(content_file, 'r') as f:
                    data = json.load(f)
                    if 'timestamp' in data:
                        created_at = datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                if verbose:
                    print(f"Could not read timestamp from {content_file}: {e}")
    
    if verbose:
        print(f"Found {len(content_files)} content files")
    
    # Scan result files
    result_files = {}
    if results_dir.exists():
        for result_file in results_dir.glob("*/*.json"):
            content_hash = extract_hash_from_filename(result_file)
            if not validate_hash(content_hash):
                if verbose:
                    print(f"Skipping invalid hash in filename: {result_file}")
                continue
            
            result_files[content_hash] = result_file
    
    if verbose:
        print(f"Found {len(result_files)} result files")
    
    # Build index entries
    entries_added = 0
    entries_skipped = 0
    
    # Process all unique hashes
    all_hashes = set(content_files.keys()) | set(result_files.keys())
    
    for content_hash in all_hashes:
        content_path = content_files.get(content_hash)
        result_path = result_files.get(content_hash)
        
        # Determine status
        status = "completed" if result_path else "pending"
        
        # Get timestamps and job_id
        created_at = datetime.utcnow()
        processed_at = None
        job_id = None
        
        # Try to read content file for created_at
        if content_path and content_path.exists():
            try:
                with open(content_path, 'r') as f:
                    data = json.load(f)
                    if 'timestamp' in data:
                        created_at = datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
            except Exception as e:
                if verbose:
                    print(f"Error reading content file {content_path}: {e}")
        
        # Try to read result file for job_id and processed_at
        if result_path and result_path.exists():
            try:
                with open(result_path, 'r') as f:
                    data = json.load(f)
                    if 'job_id' in data:
                        job_id = data['job_id']
                    if 'timestamp' in data:
                        processed_at = datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
            except Exception as e:
                if verbose:
                    print(f"Error reading result file {result_path}: {e}")
        
        # If we have a result but no content file, create expected content path
        if not content_path:
            prefix = content_hash[:2]
            content_path = content_dir / prefix / f"{content_hash}.json"
        
        # Insert into database
        try:
            conn.execute("""
                INSERT INTO content_index 
                (hash, status, content_path, result_path, job_id, created_at, processed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                content_hash,
                status,
                str(content_path),
                str(result_path) if result_path else None,
                job_id,
                created_at,
                processed_at
            ))
            entries_added += 1
            
            if verbose and entries_added % 100 == 0:
                print(f"Processed {entries_added} entries...")
                
        except sqlite3.IntegrityError as e:
            if verbose:
                print(f"Skipping duplicate entry for hash {content_hash}: {e}")
            entries_skipped += 1
    
    conn.commit()
    
    # Get statistics
    cursor = conn.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending
        FROM content_index
    """)
    
    stats = cursor.fetchone()
    conn.close()
    
    print(f"\nDatabase rebuild complete!")
    print(f"Total entries: {stats[0]}")
    print(f"Completed: {stats[1]}")
    print(f"Pending: {stats[2]}")
    print(f"Entries added: {entries_added}")
    print(f"Entries skipped: {entries_skipped}")
    
    return {
        'total': stats[0],
        'completed': stats[1],
        'pending': stats[2],
        'added': entries_added,
        'skipped': entries_skipped
    }


def verify_database(content_store_path: Path):
    """Verify the rebuilt database integrity."""
    db_path = content_store_path / "index.db"
    
    if not db_path.exists():
        print("ERROR: Database does not exist!")
        return False
    
    conn = sqlite3.connect(db_path)
    
    # Check for orphaned entries (entries without files)
    cursor = conn.execute("""
        SELECT hash, content_path, result_path 
        FROM content_index 
        LIMIT 10
    """)
    
    orphaned = []
    for row in cursor.fetchall():
        content_hash, content_path, result_path = row
        
        if content_path and not Path(content_path).exists():
            if result_path and Path(result_path).exists():
                # This is OK - we have result but no content
                pass
            else:
                orphaned.append((content_hash, 'content'))
        
        if result_path and not Path(result_path).exists():
            orphaned.append((content_hash, 'result'))
    
    if orphaned:
        print(f"\nWarning: Found {len(orphaned)} orphaned database entries")
        for hash_val, file_type in orphaned[:5]:
            print(f"  - {hash_val[:16]}... missing {file_type} file")
        if len(orphaned) > 5:
            print(f"  ... and {len(orphaned) - 5} more")
    
    conn.close()
    return True


def main():
    parser = argparse.ArgumentParser(description='Rebuild content store SQLite database')
    parser.add_argument(
        'content_store_path',
        type=Path,
        help='Path to content_store directory'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Print verbose output'
    )
    parser.add_argument(
        '--verify',
        action='store_true',
        help='Verify database after rebuild'
    )
    
    args = parser.parse_args()
    
    if not args.content_store_path.exists():
        print(f"ERROR: Content store path does not exist: {args.content_store_path}")
        sys.exit(1)
    
    # Rebuild database
    try:
        stats = rebuild_database(args.content_store_path, args.verbose)
        
        # Verify if requested
        if args.verify:
            print("\nVerifying database...")
            if verify_database(args.content_store_path):
                print("Database verification complete")
        
    except Exception as e:
        print(f"ERROR: Failed to rebuild database: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()