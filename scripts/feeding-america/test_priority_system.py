#!/usr/bin/env python3
"""Test the priority system for scraper task selection."""

import subprocess
import sys


def run_command(cmd):
    """Run a command and return output."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, shell=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")
        return None


def main():
    """Test the priority system."""
    print("🧪 Testing Priority System for Scraper Tasks")
    print("=" * 60)
    
    # Test 1: Show priority statistics
    print("\n1️⃣ Priority Statistics (from prioritize_scraper_issues.py):")
    output = run_command("./scripts/feeding-america/prioritize_scraper_issues.py --stats-only | grep -A5 'Priority Distribution'")
    if output:
        print(output)
    
    # Test 2: List tasks with new priority system
    print("\n2️⃣ Task List with Priority Grouping:")
    print("(This would show priority groups after issues are updated)")
    output = run_command("./scripts/feeding-america/pick_next_scraper_task.py --list | head -15")
    if output:
        print(output)
    
    # Test 3: Test --top-priority flag
    print("\n3️⃣ Testing --top-priority Flag:")
    print("Command: ./scripts/feeding-america/pick_next_scraper_task.py --top-priority --list")
    print("(Would filter to show only CRITICAL priority tasks)")
    
    # Test 4: Show how selection works
    print("\n4️⃣ Selection Algorithm:")
    print("- Default: Always picks from CRITICAL if available")
    print("- Otherwise: Weighted selection favoring higher priorities")
    print("- --top-priority: Only selects from CRITICAL tasks")
    
    print("\n✅ Priority System Features:")
    print("- prioritize_scraper_issues.py: Analyzes and updates issue titles")
    print("- pick_next_scraper_task.py: Selects tasks based on priority")
    print("- Population-based ranking: CRITICAL (5M+), HIGH (1-5M), MEDIUM (500K-1M), LOW (<500K)")
    
    print("\n📝 To apply priority updates to all issues:")
    print("./scripts/feeding-america/prioritize_scraper_issues.py")
    print("\n📝 To pick a high-priority task:")
    print("./scripts/feeding-america/pick_next_scraper_task.py --top-priority")


if __name__ == "__main__":
    main()