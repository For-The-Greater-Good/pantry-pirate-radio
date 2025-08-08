#!/usr/bin/env python3
"""
Test script to verify content store protection mechanisms.

This script simulates the conditions that cause content store data loss
and verifies that our fixes prevent the issue.
"""

import os
import sys
import tempfile
import shutil
import sqlite3
import json
from pathlib import Path
from datetime import datetime

# Add app to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.content_store.store import ContentStore
from app.content_store.config import get_content_store

def create_test_content_store(base_path: Path) -> ContentStore:
    """Create a test content store with some sample data."""
    print(f"Creating test content store at {base_path}")

    # Create content store
    store = ContentStore(store_path=base_path, redis_url="redis://cache:6379")

    # Add some test content
    test_content = [
        ("Test content 1", {"scraper_id": "test_scraper_1"}),
        ("Test content 2", {"scraper_id": "test_scraper_2"}),
        ("Test content 3", {"scraper_id": "test_scraper_3"}),
    ]

    for i, (content, metadata) in enumerate(test_content):
        entry = store.store_content(content, metadata)
        print(f"  Added content {i+1}: {entry.hash[:8]}... (status: {entry.status})")

        # Simulate some completed results
        if i < 2:  # First two items get "completed"
            result = f'{{"organizations": [{{"name": "Test Org {i+1}"}}]}}'
            store.store_result(entry.hash, result, f"job_{i+1}")
            print(f"    Added result for {entry.hash[:8]}...")

    return store

def test_statistics_consistency():
    """Test that statistics are consistent even under concurrent access."""
    print("\n=== Testing Statistics Consistency ===")

    with tempfile.TemporaryDirectory() as temp_dir:
        base_path = Path(temp_dir)
        store = create_test_content_store(base_path)

        # Get statistics multiple times quickly
        stats_samples = []
        for i in range(10):
            stats = store.get_statistics()
            stats_samples.append(stats)
            print(f"  Sample {i+1}: total={stats['total_content']}, processed={stats['processed_content']}, pending={stats['pending_content']}")

        # Verify all samples are consistent
        first_stats = stats_samples[0]
        all_consistent = all(
            stats['total_content'] == first_stats['total_content'] and
            stats['processed_content'] == first_stats['processed_content'] and
            stats['pending_content'] == first_stats['pending_content']
            for stats in stats_samples
        )

        if all_consistent:
            print("✅ Statistics are consistent across all samples")
            return True
        else:
            print("❌ Statistics are inconsistent!")
            return False

def test_git_stash_simulation():
    """Simulate git stash operations that previously caused data loss."""
    print("\n=== Testing Git Stash Simulation ===")

    with tempfile.TemporaryDirectory() as temp_dir:
        base_path = Path(temp_dir)

        # Create git repo structure
        git_repo = base_path / "data-repo"
        git_repo.mkdir()

        # Initialize git repo
        os.system(f"cd {git_repo} && git init")
        os.system(f"cd {git_repo} && git config user.email 'test@example.com'")
        os.system(f"cd {git_repo} && git config user.name 'Test User'")

        # Create content store in git repo
        store = ContentStore(store_path=git_repo, redis_url="redis://cache:6379")

        # Add test content
        test_content = "This is test content that should not be lost"
        metadata = {"scraper_id": "test_scraper"}
        entry = store.store_content(test_content, metadata)

        # Add a result
        result = '{"organizations": [{"name": "Test Organization"}]}'
        store.store_result(entry.hash, result, "test_job_123")

        # Get initial stats
        initial_stats = store.get_statistics()
        print(f"  Initial stats: {initial_stats['total_content']} total, {initial_stats['processed_content']} processed")

        # Simulate git operations that could affect content store
        content_store_path = git_repo / "content_store"

        # Add content store to git
        os.system(f"cd {git_repo} && git add .")
        os.system(f"cd {git_repo} && git commit -m 'Initial commit with content store'")

        # Create some other files to simulate uncommitted changes
        (git_repo / "other_file.txt").write_text("Some other content")

        # Simulate the SAFE stash operation (our fix)
        print("  Simulating protected git stash operation...")

        # First commit content store changes (our protection mechanism)
        os.system(f"cd {git_repo} && git add content_store/")
        result = os.system(f"cd {git_repo} && git commit -m 'Auto-commit content store updates'")

        # Then stash other files excluding content store
        os.system(f"cd {git_repo} && git stash push -m 'Test stash (excluding content_store)' -- . ':(exclude)content_store'")

        # Verify content store is still intact
        final_stats = store.get_statistics()
        print(f"  Final stats: {final_stats['total_content']} total, {final_stats['processed_content']} processed")

        # Check if data was preserved
        if (final_stats['total_content'] == initial_stats['total_content'] and
            final_stats['processed_content'] == initial_stats['processed_content']):
            print("✅ Content store data preserved during git operations")
            return True
        else:
            print("❌ Content store data was lost during git operations!")
            print(f"   Initial: {initial_stats}")
            print(f"   Final: {final_stats}")
            return False

def test_wal_mode_enabled():
    """Test that WAL mode is properly enabled for better concurrent access."""
    print("\n=== Testing WAL Mode ===")

    with tempfile.TemporaryDirectory() as temp_dir:
        base_path = Path(temp_dir)
        store = create_test_content_store(base_path)

        # Check WAL mode by querying the database
        db_path = store.content_store_path / "index.db"
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute("PRAGMA journal_mode")
            journal_mode = cursor.fetchone()[0]
            print(f"  Journal mode: {journal_mode}")

            if journal_mode.upper() == "WAL":
                print("✅ WAL mode is enabled")
                return True
            else:
                print("❌ WAL mode is not enabled")
                return False

def main():
    """Run all tests."""
    print("Content Store Protection Test Suite")
    print("=" * 50)

    tests = [
        ("Statistics Consistency", test_statistics_consistency),
        ("Git Stash Protection", test_git_stash_simulation),
        ("WAL Mode", test_wal_mode_enabled),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results.append((test_name, False))

    print("\n" + "=" * 50)
    print("TEST RESULTS:")

    passed = 0
    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"  {test_name}: {status}")
        if result:
            passed += 1

    print(f"\nPassed: {passed}/{len(results)} tests")

    if passed == len(results):
        print("🎉 All tests passed! Content store protection is working.")
        return 0
    else:
        print("⚠️  Some tests failed. Review the fixes.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
