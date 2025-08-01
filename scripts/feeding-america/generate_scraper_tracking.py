#!/usr/bin/env python3
"""Generate comprehensive tracking JSON for Feeding America scraper development.

This script:
1. Fetches all open GitHub issues for food banks
2. Cross-references with Feeding America data for metadata
3. Creates a structured to-do list with subtasks for each food bank
4. Supports filtering, reporting, and various export formats
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def fetch_open_issues() -> List[Dict[str, Any]]:
    """Fetch all open GitHub issues.
    
    Returns:
        List of issue dictionaries with number and title
    """
    cmd = [
        "gh", "issue", "list",
        "--repo", "For-The-Greater-Good/pantry-pirate-radio",
        "--state", "open",
        "--json", "number,title,labels,body",
        "--limit", "1000"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Error fetching issues: {e}")
        print(f"stderr: {e.stderr}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
        sys.exit(1)


def load_feeding_america_data() -> Dict[str, Dict[str, Any]]:
    """Load Feeding America food bank data for metadata enrichment.
    
    Returns:
        Dictionary mapping org_id to food bank data
    """
    fa_file = Path("outputs/feeding_america_foodbanks.json")
    if not fa_file.exists():
        print(f"Warning: {fa_file} not found. Metadata will be limited.")
        return {}
    
    with open(fa_file) as f:
        food_banks = json.load(f)
    
    # Create lookup by name and org_id
    lookup = {}
    for fb in food_banks:
        # Store by org_id
        if "org_id" in fb:
            lookup[fb["org_id"]] = fb
        # Also store by name for fallback matching
        if "name" in fb:
            lookup[fb["name"]] = fb
    
    return lookup


def parse_issue_title(title: str) -> Dict[str, str]:
    """Parse food bank information from issue title.
    
    Expected formats: 
    - "Implement scraper for Food Bank Name"
    - "Feeding America Scraper: Food Bank Name"
    
    Args:
        title: Issue title
        
    Returns:
        Dictionary with parsed information
    """
    info = {
        "name": "",
        "state": "",
        "raw_title": title
    }
    
    # Extract food bank name
    if "Implement scraper for " in title:
        name_part = title.split("Implement scraper for ", 1)[1].strip()
        info["name"] = name_part
    elif "Feeding America Scraper:" in title:
        name_part = title.split("Feeding America Scraper:", 1)[1].strip()
        info["name"] = name_part
    elif ":" in title:
        # Fallback for other formats
        name_part = title.split(":", 1)[1].strip()
        info["name"] = name_part
    else:
        info["name"] = title.strip()
    
    # Try to extract state from parentheses or end of name
    # e.g., "Food Bank (CA)" or "Food Bank California"
    import re
    state_match = re.search(r'\(([A-Z]{2})\)$', info["name"])
    if state_match:
        info["state"] = state_match.group(1)
        info["name"] = info["name"].replace(state_match.group(0), "").strip()
    
    return info


def create_task_entry(issue: Dict[str, Any], fa_data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a task entry for a food bank.
    
    Args:
        issue: GitHub issue data
        fa_data: Feeding America metadata lookup
        
    Returns:
        Task entry dictionary
    """
    parsed = parse_issue_title(issue["title"])
    
    # Try to find matching FA data
    food_bank_data = {}
    if parsed["name"] in fa_data:
        food_bank_data = fa_data[parsed["name"]]
    else:
        # Try partial matching
        for name, data in fa_data.items():
            if parsed["name"].lower() in name.lower() or name.lower() in parsed["name"].lower():
                food_bank_data = data
                break
    
    # Build food bank info
    food_bank = {
        "name": parsed["name"],
        "org_id": food_bank_data.get("org_id", ""),
        "state": food_bank_data.get("state", parsed["state"]),
        "url": food_bank_data.get("url", ""),
        "find_food_url": food_bank_data.get("find_food_url", ""),
        "counties": food_bank_data.get("counties", [])
    }
    
    # Create task structure
    entry = {
        "issue_number": issue["number"],
        "issue_title": issue["title"],
        "issue_url": f"https://github.com/For-The-Greater-Good/pantry-pirate-radio/issues/{issue['number']}",
        "food_bank": food_bank,
        "tasks": {
            "scraper": {
                "status": "pending",
                "file_path": None,
                "completed_at": None
            },
            "tests": {
                "status": "pending", 
                "file_path": None,
                "completed_at": None
            },
            "pr": {
                "status": "pending",
                "pr_number": None,
                "completed_at": None
            }
        },
        "priority": determine_priority(food_bank),
        "assigned_to": None,
        "notes": [],
        "labels": [label["name"] for label in issue.get("labels", [])]
    }
    
    return entry


def determine_priority(food_bank: Dict[str, Any]) -> str:
    """Determine priority based on food bank characteristics.
    
    Args:
        food_bank: Food bank data
        
    Returns:
        Priority level (high, medium, low)
    """
    # High priority for food banks with URLs (easier to scrape)
    if food_bank.get("find_food_url") or food_bank.get("url"):
        return "high"
    
    # Medium priority for food banks with state info
    if food_bank.get("state"):
        return "medium"
    
    # Low priority for others
    return "low"


def calculate_statistics(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate statistics from task list.
    
    Args:
        tasks: List of task entries
        
    Returns:
        Statistics dictionary
    """
    stats = {
        "by_state": {},
        "by_priority": {"high": 0, "medium": 0, "low": 0},
        "by_status": {
            "pending": 0,
            "in_progress": 0,
            "completed": 0
        },
        "completion_rate": {
            "scrapers": 0,
            "tests": 0,
            "prs": 0,
            "overall": 0
        }
    }
    
    total_tasks = len(tasks) * 3  # 3 subtasks per food bank
    completed_tasks = 0
    scraper_completed = 0
    tests_completed = 0
    prs_completed = 0
    
    for task in tasks:
        # State statistics
        state = task["food_bank"].get("state", "Unknown")
        stats["by_state"][state] = stats["by_state"].get(state, 0) + 1
        
        # Priority statistics
        priority = task.get("priority", "medium")
        stats["by_priority"][priority] += 1
        
        # Status statistics
        all_completed = True
        any_in_progress = False
        
        for subtask_name, subtask in task["tasks"].items():
            if subtask["status"] == "completed":
                completed_tasks += 1
                if subtask_name == "scraper":
                    scraper_completed += 1
                elif subtask_name == "tests":
                    tests_completed += 1
                elif subtask_name == "pr":
                    prs_completed += 1
            elif subtask["status"] == "in_progress":
                any_in_progress = True
                all_completed = False
            else:
                all_completed = False
        
        if all_completed:
            stats["by_status"]["completed"] += 1
        elif any_in_progress:
            stats["by_status"]["in_progress"] += 1
        else:
            stats["by_status"]["pending"] += 1
    
    # Calculate completion rates
    if len(tasks) > 0:
        stats["completion_rate"]["scrapers"] = round(scraper_completed / len(tasks) * 100, 2)
        stats["completion_rate"]["tests"] = round(tests_completed / len(tasks) * 100, 2)
        stats["completion_rate"]["prs"] = round(prs_completed / len(tasks) * 100, 2)
        stats["completion_rate"]["overall"] = round(completed_tasks / total_tasks * 100, 2)
    
    return stats


def generate_report(data: Dict[str, Any]) -> str:
    """Generate a text report from tracking data.
    
    Args:
        data: Tracking data dictionary
        
    Returns:
        Formatted report string
    """
    report = []
    report.append("=" * 60)
    report.append("FEEDING AMERICA SCRAPER DEVELOPMENT TRACKING REPORT")
    report.append("=" * 60)
    report.append(f"Generated: {data['metadata']['generated_at']}")
    report.append("")
    
    # Overall statistics
    meta = data["metadata"]
    report.append("OVERALL PROGRESS:")
    report.append(f"  Total Food Banks: {meta['total_food_banks']}")
    report.append(f"  Completed: {meta['completed']}")
    report.append(f"  In Progress: {meta['in_progress']}")
    report.append(f"  Pending: {meta['pending']}")
    report.append("")
    
    # Completion rates
    stats = data["statistics"]
    report.append("COMPLETION RATES:")
    report.append(f"  Scrapers: {stats['completion_rate']['scrapers']}%")
    report.append(f"  Tests: {stats['completion_rate']['tests']}%")
    report.append(f"  Pull Requests: {stats['completion_rate']['prs']}%")
    report.append(f"  Overall: {stats['completion_rate']['overall']}%")
    report.append("")
    
    # By priority
    report.append("BY PRIORITY:")
    for priority, count in stats["by_priority"].items():
        report.append(f"  {priority.capitalize()}: {count}")
    report.append("")
    
    # By state (top 10)
    report.append("TOP 10 STATES BY FOOD BANK COUNT:")
    sorted_states = sorted(stats["by_state"].items(), key=lambda x: x[1], reverse=True)[:10]
    for state, count in sorted_states:
        report.append(f"  {state}: {count}")
    report.append("")
    
    # Next priorities (high priority, pending items)
    report.append("NEXT PRIORITIES (High priority, pending):")
    count = 0
    for task in data["food_banks"]:
        if task["priority"] == "high" and task["tasks"]["scraper"]["status"] == "pending":
            report.append(f"  - Issue #{task['issue_number']}: {task['food_bank']['name']}")
            if task["food_bank"].get("find_food_url"):
                report.append(f"    URL: {task['food_bank']['find_food_url']}")
            count += 1
            if count >= 10:
                break
    
    return "\n".join(report)


def export_to_csv(data: Dict[str, Any], output_file: Path) -> None:
    """Export tracking data to CSV format.
    
    Args:
        data: Tracking data
        output_file: Output CSV file path
    """
    import csv
    
    with open(output_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'issue_number', 'food_bank_name', 'state', 'url', 'find_food_url',
            'scraper_status', 'tests_status', 'pr_status', 'priority'
        ])
        writer.writeheader()
        
        for task in data["food_banks"]:
            writer.writerow({
                'issue_number': task['issue_number'],
                'food_bank_name': task['food_bank']['name'],
                'state': task['food_bank'].get('state', ''),
                'url': task['food_bank'].get('url', ''),
                'find_food_url': task['food_bank'].get('find_food_url', ''),
                'scraper_status': task['tasks']['scraper']['status'],
                'tests_status': task['tasks']['tests']['status'],
                'pr_status': task['tasks']['pr']['status'],
                'priority': task['priority']
            })


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Generate comprehensive tracking JSON for Feeding America scraper development"
    )
    parser.add_argument("--state", help="Filter by state code (e.g., CA)")
    parser.add_argument("--priority", choices=["high", "medium", "low"], 
                       help="Filter by priority level")
    parser.add_argument("--report", action="store_true", 
                       help="Generate and print a summary report")
    parser.add_argument("--output", default="outputs/scraper_development_tracking.json",
                       help="Output file path (default: outputs/scraper_development_tracking.json)")
    parser.add_argument("--format", choices=["json", "csv"], default="json",
                       help="Output format (default: json)")
    parser.add_argument("--update", action="store_true",
                       help="Update existing tracking file, preserving status")
    
    args = parser.parse_args()
    
    # Load existing data if updating
    existing_data = {}
    if args.update and Path(args.output).exists():
        with open(args.output) as f:
            existing_data = json.load(f)
    
    # Fetch data
    print("Fetching open GitHub issues...")
    issues = fetch_open_issues()
    
    print("Loading Feeding America data...")
    fa_data = load_feeding_america_data()
    
    # Filter to only Feeding America issues
    fa_issues = [
        issue for issue in issues 
        if ("Implement scraper for" in issue.get("title", "") or 
            "Feeding America Scraper" in issue.get("title", ""))
    ]
    
    print(f"Found {len(fa_issues)} Feeding America scraper issues")
    
    # Create task entries
    tasks = []
    for issue in fa_issues:
        task = create_task_entry(issue, fa_data)
        
        # Preserve existing status if updating
        if args.update and existing_data:
            for existing_task in existing_data.get("food_banks", []):
                if existing_task["issue_number"] == task["issue_number"]:
                    task["tasks"] = existing_task["tasks"]
                    task["assigned_to"] = existing_task.get("assigned_to")
                    task["notes"] = existing_task.get("notes", [])
                    break
        
        # Apply filters
        if args.state and task["food_bank"].get("state") != args.state:
            continue
        if args.priority and task["priority"] != args.priority:
            continue
            
        tasks.append(task)
    
    # Sort by priority and issue number
    priority_order = {"high": 0, "medium": 1, "low": 2}
    tasks.sort(key=lambda x: (priority_order[x["priority"]], x["issue_number"]))
    
    # Calculate statistics
    stats = calculate_statistics(tasks)
    
    # Build output data
    data = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "total_food_banks": len(tasks),
            "completed": stats["by_status"]["completed"],
            "in_progress": stats["by_status"]["in_progress"],
            "pending": stats["by_status"]["pending"]
        },
        "food_banks": tasks,
        "statistics": stats
    }
    
    # Generate report if requested
    if args.report:
        print("\n" + generate_report(data))
    
    # Export data
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    if args.format == "csv":
        export_to_csv(data, output_path.with_suffix('.csv'))
        print(f"\nCSV data exported to: {output_path.with_suffix('.csv')}")
    else:
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"\nTracking data saved to: {output_path}")
    
    # Print summary
    print(f"\nSummary:")
    print(f"  Total food banks: {len(tasks)}")
    print(f"  High priority: {stats['by_priority']['high']}")
    print(f"  Medium priority: {stats['by_priority']['medium']}")
    print(f"  Low priority: {stats['by_priority']['low']}")


if __name__ == "__main__":
    main()