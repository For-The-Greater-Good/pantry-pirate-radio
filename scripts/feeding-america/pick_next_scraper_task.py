#!/usr/bin/env python3
"""Pick the next scraper task to work on based on priority and randomization.

This script queries GitHub issues directly and helps developers choose
which scraper to implement next using priority-weighted selection.
"""

import argparse
import json
import random
import subprocess
import sys
from typing import Dict, Any, List, Optional


def get_scraper_issues(
    state: Optional[str] = None,
    priority: Optional[str] = None,
    limit: int = 300
) -> List[Dict[str, Any]]:
    """Get all open scraper issues from GitHub.

    Args:
        state: Filter by state code
        priority: Filter by priority (CRITICAL, HIGH, MEDIUM, LOW)
        limit: Maximum number of issues to fetch

    Returns:
        List of issue dictionaries
    """
    cmd = [
        "gh",
        "issue",
        "list",
        "--label",
        "scraper",
        "--state",
        "open",
        "--limit",
        str(limit),
        "--repo",
        "For-The-Greater-Good/pantry-pirate-radio",
        "--json",
        "number,title,body,labels",
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        issues = json.loads(result.stdout)

        # Filter out issues that are already in progress or completed
        pending_issues = []
        for issue in issues:
            labels = [label["name"] for label in issue.get("labels", [])]

            # Skip if already in progress, completed, or covered by Vivery
            if "in-progress" in labels or "completed" in labels or "vivery-covered" in labels:
                continue

            # Extract priority from title
            issue_priority = ""
            title = issue["title"]
            for p in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
                if title.startswith(f"[{p}]"):
                    issue_priority = p
                    break

            # Apply filters
            if priority and issue_priority != priority:
                continue

            if state:
                # Try to extract state from issue body
                body = issue.get("body", "")
                if f"State: {state.upper()}" not in body:
                    continue

            issue["priority"] = issue_priority
            pending_issues.append(issue)

        return pending_issues
    except subprocess.CalledProcessError as e:
        print(f"Error fetching issues: {e}")
        return []


def parse_issue_body(body: str) -> Dict[str, Any]:
    """Parse food bank information from issue body.

    Args:
        body: Issue body text

    Returns:
        Dictionary with food bank information
    """
    info = {
        "name": "",
        "state": "",
        "url": "",
        "find_food_url": "",
        "counties": []
    }

    lines = body.split("\n")
    for line in lines:
        line = line.strip()
        if line.startswith("Name:"):
            info["name"] = line.replace("Name:", "").strip()
        elif line.startswith("State:"):
            info["state"] = line.replace("State:", "").strip()
        elif line.startswith("URL:"):
            url = line.replace("URL:", "").strip()
            if url and url != "None":
                info["url"] = url
        elif line.startswith("Find Food URL:"):
            url = line.replace("Find Food URL:", "").strip()
            if url and url != "None":
                info["find_food_url"] = url
        elif line.startswith("Counties:"):
            counties_str = line.replace("Counties:", "").strip()
            if counties_str and counties_str != "None":
                info["counties"] = [c.strip() for c in counties_str.split(",")]

    return info


def display_implementation_instructions(issue: Dict[str, Any], food_bank: Dict[str, Any]) -> None:
    """Display step-by-step implementation instructions.

    Args:
        issue: GitHub issue dictionary
        food_bank: Parsed food bank information
    """
    issue_num = issue["number"]
    name = food_bank["name"]
    url = food_bank.get("find_food_url") or food_bank.get("url", "No URL available")

    print(f"\n{'='*60}")
    print(f"SELECTED TASK: {name}")
    print(f"{'='*60}")
    print(f"Issue: #{issue_num}")
    print(f"Priority: {issue.get('priority', 'UNRANKED')}")
    print(f"State: {food_bank.get('state', 'Unknown')}")
    print(f"URL: {url}")

    print(f"\n📋 IMPLEMENTATION STEPS:")
    print(f"{'='*60}")

    print("\n1️⃣  CHECK FOR VIVERY (CRITICAL FIRST STEP):")
    print(f"   Visit {url} and check for Vivery/AccessFood integration")
    print(f"   Look for: accessfood-widget, pantrynet.org, vivery.com")
    print(f"   If found, close issue with:")
    print(f"   gh issue close {issue_num} --comment \"Uses Vivery - covered by existing scraper\"")
    print(f"   gh issue edit {issue_num} --add-label \"vivery-covered\"")

    print("\n2️⃣  CREATE BOILERPLATE:")
    print(f"   ./scripts/feeding-america/create_scraper_from_issue.py --issue {issue_num}")

    print("\n3️⃣  IMPLEMENT SCRAPER:")
    print(f"   - Analyze the website structure")
    print(f"   - Choose HTML parsing or API approach")
    print(f"   - NO GEOCODING - validator service handles this")
    print(f"   - Lat/long is optional")

    print("\n4️⃣  TEST YOUR IMPLEMENTATION:")
    print(f"   ./bouy test --pytest tests/test_scraper/test_*_scraper.py")
    print(f"   ./bouy scraper-test <scraper_name>")

    print("\n5️⃣  CREATE PULL REQUEST:")
    print(f"   git add app/scraper/*_scraper.py tests/test_scraper/test_*_scraper.py")
    print(f"   git commit -m \"feat: implement scraper for {name}\"")
    print(f"   gh pr create --title \"Implement scraper for {name}\"")

    print("\n6️⃣  UPDATE ISSUE STATUS:")
    print(f"   gh issue edit {issue_num} --add-label \"completed\"")

    print(f"\n{'='*60}")
    print("⚠️  REMEMBER: No geocoding in scrapers - validator handles it!")
    print(f"{'='*60}\n")


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Pick the next scraper task to work on"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available tasks instead of picking one",
    )
    parser.add_argument(
        "--top-priority",
        action="store_true",
        help="Only select from CRITICAL priority tasks",
    )
    parser.add_argument(
        "--priority",
        choices=["CRITICAL", "HIGH", "MEDIUM", "LOW"],
        help="Filter by specific priority level",
    )
    parser.add_argument(
        "--state",
        help="Filter by state code",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of tasks to show when listing (default: 10)",
    )

    args = parser.parse_args()

    # Get pending issues from GitHub
    issues = get_scraper_issues(state=args.state, priority=args.priority)

    if not issues:
        print("No pending scraper tasks found with the specified criteria.")
        print("\nTry running without filters to see all available tasks.")
        return

    # Sort by priority
    priority_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "": 4}
    issues.sort(key=lambda i: priority_order.get(i.get("priority", ""), 4))

    # Apply top-priority filter if specified
    if args.top_priority:
        issues = [i for i in issues if i.get("priority") == "CRITICAL"]
        if not issues:
            print("No CRITICAL priority tasks found.")
            print("Try without --top-priority flag to see other priorities.")
            return

    if args.list:
        # List available tasks
        print(f"\n{'='*60}")
        print(f"AVAILABLE SCRAPER TASKS ({len(issues)} total)")
        print(f"{'='*60}")

        # Group by priority
        by_priority = {}
        for issue in issues:
            p = issue.get("priority", "UNRANKED")
            if p not in by_priority:
                by_priority[p] = []
            by_priority[p].append(issue)

        # Display by priority
        for priority in ["CRITICAL", "HIGH", "MEDIUM", "LOW", ""]:
            if priority in by_priority:
                priority_label = priority if priority else "UNRANKED"
                priority_badge = {
                    "CRITICAL": "🔴",
                    "HIGH": "🟠",
                    "MEDIUM": "🟡",
                    "LOW": "🟢",
                }.get(priority, "⚪")

                print(f"\n{priority_badge} {priority_label} Priority ({len(by_priority[priority])} tasks):")
                print("-" * 40)

                for issue in by_priority[priority][:args.limit]:
                    fb = parse_issue_body(issue.get("body", ""))
                    print(f"  #{issue['number']}: {fb['name']}")

                if len(by_priority[priority]) > args.limit:
                    print(f"  ... and {len(by_priority[priority]) - args.limit} more")

        print(f"\n{'='*60}")
        print(f"Run without --list to pick a random task")
        print(f"Use --priority or --state to filter tasks")
        print(f"{'='*60}\n")
    else:
        # Pick a random task with priority weighting
        if not issues:
            print("No tasks available to pick from.")
            return

        # Check for CRITICAL tasks
        critical_tasks = [i for i in issues if i.get("priority") == "CRITICAL"]

        if critical_tasks:
            # Always prioritize CRITICAL tasks
            selected = random.choice(critical_tasks)
            print("\n🔴 CRITICAL PRIORITY TASK SELECTED")
        else:
            # Weighted random selection based on position in sorted list
            # Higher priority tasks have more weight
            weights = [len(issues) - i for i in range(len(issues))]
            selected = random.choices(issues, weights=weights, k=1)[0]

            priority = selected.get("priority", "UNRANKED")
            if priority:
                badge = {
                    "HIGH": "🟠 HIGH",
                    "MEDIUM": "🟡 MEDIUM",
                    "LOW": "🟢 LOW",
                }.get(priority, "⚪ UNRANKED")
                print(f"\n{badge} PRIORITY TASK SELECTED")

        # Parse and display the selected task
        food_bank = parse_issue_body(selected.get("body", ""))
        display_implementation_instructions(selected, food_bank)

        # Show how to generate full Claude prompt
        print("\n💡 To get full implementation prompt for Claude:")
        print(f"   python3 scripts/feeding-america/implement_scraper_with_claude.py --issue {selected['number']}")
        print("")


if __name__ == "__main__":
    main()