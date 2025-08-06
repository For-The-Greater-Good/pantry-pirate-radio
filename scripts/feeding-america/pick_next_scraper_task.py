#!/usr/bin/env python3
"""Pick a random food bank scraper task and generate implementation instructions.

This script selects a random pending food bank scraper and provides all the
information needed to implement it, including file paths and commands.
"""

import argparse
import json
import random
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List


def load_tracking_data() -> Dict[str, Any]:
    """Load tracking data to get food bank information.

    Returns:
        Tracking data dictionary
    """
    tracking_file = Path("outputs/scraper_development_tracking.json")
    if not tracking_file.exists():
        print(f"Error: Tracking file not found at {tracking_file}")
        print("Run generate_scraper_tracking.py first.")
        sys.exit(1)

    with open(tracking_file) as f:
        return json.load(f)


def get_pending_tasks(data: Dict[str, Any], priority: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get all pending scraper tasks.

    Args:
        data: Tracking data
        priority: Optional priority filter (high, medium, low)

    Returns:
        List of pending tasks
    """
    pending = []

    for fb in data["food_banks"]:
        # Check if scraper task is pending
        if fb["tasks"]["scraper"]["status"] == "pending":
            # Apply priority filter if specified
            if priority and fb["priority"] != priority:
                continue
            pending.append(fb)

    return pending


def get_all_issue_priorities() -> Dict[int, str]:
    """Get priorities for all scraper issues in one batch.

    Returns:
        Dictionary mapping issue number to priority
    """
    cmd = [
        "gh", "issue", "list",
        "--label", "scraper",
        "--limit", "300",
        "--repo", "For-The-Greater-Good/pantry-pirate-radio",
        "--json", "number,title"
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        issues = json.loads(result.stdout)

        priorities = {}
        for issue in issues:
            title = issue["title"]
            issue_num = issue["number"]

            # Extract priority from title
            for priority in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
                if title.startswith(f"[{priority}]"):
                    priorities[issue_num] = priority
                    break
            else:
                priorities[issue_num] = ""

        return priorities
    except subprocess.CalledProcessError:
        return {}


def sanitize_name(name: str) -> str:
    """Sanitize name for use in Python identifiers."""
    import re
    name = re.sub(r'[^\w\s]', '', name)
    name = name.replace(' ', '_')
    name = re.sub(r'_+', '_', name)
    name = name.lower()
    name = name.strip('_')
    return name


def create_class_name(name: str) -> str:
    """Create PascalCase class name from food bank name."""
    import re
    name = re.sub(r'[^\w\s]', '', name)
    words = name.split()
    return ''.join(word.capitalize() for word in words)


def fetch_issue_body(issue_number: int) -> str:
    """Fetch the body content of a GitHub issue.

    Args:
        issue_number: GitHub issue number

    Returns:
        Issue body content
    """
    cmd = [
        "gh", "issue", "view", str(issue_number),
        "--repo", "For-The-Greater-Good/pantry-pirate-radio",
        "--json", "body",
        "--jq", ".body"
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return "Unable to fetch issue body"


def generate_task_instructions(task: Dict[str, Any]) -> str:
    """Generate detailed task instructions for implementing a scraper.

    Args:
        task: Food bank task data

    Returns:
        Formatted task instructions
    """
    fb = task["food_bank"]
    issue_num = task["issue_number"]

    # Generate names
    name = fb["name"]
    sanitized = sanitize_name(name)
    class_name = create_class_name(name)

    # File paths
    scraper_path = f"app/scraper/{sanitized}_scraper.py"
    test_path = f"tests/test_scraper/test_{sanitized}_scraper.py"

    # Get issue body for additional context
    issue_body = fetch_issue_body(issue_num)

    # Extract URLs from issue body if not in tracking data
    url = fb.get("find_food_url") or fb.get("url", "")
    if not url and "http" in issue_body:
        import re
        url_match = re.search(r'https?://[^\s<>"]+', issue_body)
        if url_match:
            url = url_match.group(0)

    # Get issue priority
    issue_priority = task.get("issue_priority", "")
    priority_badge = {
        "CRITICAL": "🔴 CRITICAL",
        "HIGH": "🟠 HIGH",
        "MEDIUM": "🟡 MEDIUM",
        "LOW": "🟢 LOW"
    }.get(issue_priority, "⚪ UNRANKED")

    instructions = f"""
# 🎯 SCRAPER IMPLEMENTATION TASK

## Food Bank: {name}
- **GitHub Issue**: #{issue_num} - https://github.com/For-The-Greater-Good/pantry-pirate-radio/issues/{issue_num}
- **State**: {fb.get('state', 'Unknown')}
- **Issue Priority**: {priority_badge}
- **URL**: {url or 'No URL available - check issue'}

## 📁 Generated Files:
- **Scraper**: @{scraper_path}
- **Tests**: @{test_path}

## 🚀 Quick Start Commands:

### 1. Generate boilerplate files:
```bash
./scripts/feeding-america/create_scraper_from_issue.py --issue {issue_num}
```

### 2. Mark as in progress:
```bash
./scripts/feeding-america/update_scraper_progress.py --issue {issue_num} --task scraper --status in_progress
```

### 3. Explore the website:
```bash
# Open in browser
open "{url}"

# Quick check for common patterns
curl -s "{url}" | grep -E "(store-locator|api|vivery|pantrynet|accessfood)"

# Check if it's already covered by Vivery
./scripts/feeding-america/check_vivery_usage.py --check-single "{url}"
```

## 🔍 Implementation Steps:

1. **Visit the website** at {url}
   - Look for "Find Food", "Locations", or "Get Help" links
   - Note the URL structure and parameters

2. **Analyze the data source**:
   - View page source (Cmd+U) - is data in HTML?
   - Open DevTools Network tab - look for API calls
   - Check for JavaScript frameworks or dynamic loading
   - See @docs/scraper-patterns.md for common patterns

3. **Choose scraping approach**:
   - **HTML**: Use `parse_html()` method with BeautifulSoup
   - **API**: Use `fetch_api_data()` method with httpx
   - **Grid Search**: Use `get_state_grid_points()` for geographic APIs

4. **Implement the scraper**:
   - Edit @{scraper_path}
   - Follow patterns from existing scrapers:
     - @app/scraper/mercer_food_finder_scraper.py (HTML example)
     - @app/scraper/plentiful_scraper.py (API example)
     - @app/scraper/vivery_api_scraper.py (Grid search example)

5. **Test the scraper**:
```bash
# Run tests
./bouy test --pytest {test_path}

# Test scraper (dry run)
./bouy scraper-test {sanitized}

# Run scraper (requires services running)
./bouy up
./bouy scraper {sanitized}
```

6. **Update progress**:
```bash
# Mark scraper as completed
./scripts/feeding-america/update_scraper_progress.py --issue {issue_num} --task scraper --status completed --file {scraper_path}

# Add implementation notes
./scripts/feeding-america/update_scraper_progress.py --issue {issue_num} --note "Uses WordPress store locator API"
```

## 📋 Checklist:
- [ ] Generated boilerplate files
- [ ] Analyzed website structure
- [ ] Identified data source (HTML/API/JS)
- [ ] Implemented scraping logic
- [ ] Added proper error handling
- [ ] Tested with real data
- [ ] Verified geocoding works
- [ ] Updated tracking status

## 🔗 Helpful Resources:
- @docs/scrapers.md - Scraper implementation guide
- @docs/scraper-patterns.md - Common patterns reference
- @app/scraper/utils.py - Available utilities
- @scripts/feeding-america/README.md - Workflow guide

## 📝 Issue Details:
{'-' * 60}
{issue_body[:1000]}{'...' if len(issue_body) > 1000 else ''}
{'-' * 60}

## 🎲 Why this task?
This food bank was selected from {len(get_pending_tasks(load_tracking_data()))} pending tasks.
Selection criteria: {priority_badge} issue priority, has URL: {'Yes' if url else 'No'}
{f"Population served: Major metropolitan area (5M+ people)" if issue_priority == "CRITICAL" else ""}
{f"Population served: Large city area (1-5M people)" if issue_priority == "HIGH" else ""}
{f"Population served: Mid-size area (500K-1M people)" if issue_priority == "MEDIUM" else ""}
{f"Population served: Rural/small area (<500K people)" if issue_priority == "LOW" else ""}
"""

    return instructions


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Pick a random food bank scraper task and generate instructions"
    )
    parser.add_argument("--priority", choices=["high", "medium", "low"],
                       help="Filter by priority level (legacy - use issue priorities)")
    parser.add_argument("--top-priority", action="store_true",
                       help="Only select from CRITICAL priority issues")
    parser.add_argument("--state", help="Filter by state code (e.g., CA)")
    parser.add_argument("--issue", type=int, help="Pick specific issue number")
    parser.add_argument("--list", action="store_true",
                       help="List available tasks instead of picking one")

    args = parser.parse_args()

    # Load tracking data
    data = load_tracking_data()

    # Get pending tasks
    pending = get_pending_tasks(data, priority=args.priority)

    # Apply state filter if specified
    if args.state:
        pending = [t for t in pending if t["food_bank"].get("state") == args.state.upper()]

    # Get all issue priorities in one batch (much faster!)
    all_priorities = get_all_issue_priorities()

    # Enrich tasks with priorities
    for task in pending:
        task["issue_priority"] = all_priorities.get(task["issue_number"], "")

    # Apply top-priority filter if specified
    if args.top_priority:
        pending = [t for t in pending if t["issue_priority"] == "CRITICAL"]
        if not pending:
            print("No CRITICAL priority tasks found. Try without --top-priority flag.")
            return

    # Sort by priority (CRITICAL > HIGH > MEDIUM > LOW > empty)
    priority_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "": 4}
    pending.sort(key=lambda t: priority_order.get(t["issue_priority"], 4))

    if not pending:
        print("No pending tasks found with the specified criteria.")
        return

    # List mode
    if args.list:
        print(f"\nFound {len(pending)} pending tasks:")
        print("=" * 80)

        # Group by priority
        by_priority = {}
        for task in pending:
            p = task["issue_priority"] or "UNRANKED"
            if p not in by_priority:
                by_priority[p] = []
            by_priority[p].append(task)

        # Show priority distribution
        print("\n📊 Priority Distribution:")
        for priority in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNRANKED"]:
            if priority in by_priority:
                count = len(by_priority[priority])
                print(f"  {priority}: {count} tasks")

        # Show tasks by priority
        print("\n📋 Tasks by Priority:")
        shown = 0
        for priority in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNRANKED"]:
            if priority not in by_priority:
                continue

            print(f"\n{priority}:")
            for task in by_priority[priority][:5]:  # Show first 5 of each
                fb = task["food_bank"]
                url = fb.get("find_food_url") or fb.get("url", "No URL")
                print(f"  #{task['issue_number']}: {fb['name']} ({fb.get('state', 'Unknown')})")
                if url != "No URL":
                    print(f"       URL: {url[:60]}{'...' if len(url) > 60 else ''}")
                shown += 1

            if len(by_priority[priority]) > 5:
                print(f"  ... and {len(by_priority[priority]) - 5} more {priority} tasks")

        return

    # Pick specific issue if requested
    if args.issue:
        selected = None
        for task in pending:
            if task["issue_number"] == args.issue:
                selected = task
                break
        if not selected:
            print(f"Issue #{args.issue} not found in pending tasks.")
            return
    else:
        # Pick task with preference for higher priorities
        # Since pending is sorted by priority, we can use weighted selection
        # Give more weight to tasks at the beginning of the list

        # If we have any CRITICAL tasks, always pick from those
        critical_tasks = [t for t in pending if t["issue_priority"] == "CRITICAL"]
        if critical_tasks:
            selected = random.choice(critical_tasks)
            print(f"\n🎯 Selected a CRITICAL priority task from {len(critical_tasks)} available")
        else:
            # Otherwise use weighted selection favoring higher priorities
            # Weight formula: position 0 gets weight n, position 1 gets n-1, etc.
            weights = [len(pending) - i for i in range(len(pending))]
            selected = random.choices(pending, weights=weights, k=1)[0]

            # Show what priority was selected
            priority = selected["issue_priority"] or "UNRANKED"
            print(f"\n🎯 Selected a {priority} priority task")

    # Generate and print instructions
    instructions = generate_task_instructions(selected)
    print(instructions)

    # Save task to file for reference
    task_file = Path("outputs/current_scraper_task.md")
    task_file.write_text(instructions)
    print(f"\n📄 Task saved to: @{task_file}")


if __name__ == "__main__":
    main()