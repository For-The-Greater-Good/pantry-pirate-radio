#!/usr/bin/env python3
"""Update scraper development progress in the tracking JSON.

This script helps update the status of tasks as you work on scrapers.
"""

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional


def load_tracking_data(file_path: Path) -> Dict[str, Any]:
    """Load tracking data from JSON file.
    
    Args:
        file_path: Path to tracking JSON file
        
    Returns:
        Tracking data dictionary
    """
    if not file_path.exists():
        print(f"Error: Tracking file not found at {file_path}")
        print("Run generate_scraper_tracking.py first to create the tracking file.")
        exit(1)
    
    with open(file_path) as f:
        return json.load(f)


def save_tracking_data(data: Dict[str, Any], file_path: Path) -> None:
    """Save tracking data to JSON file.
    
    Args:
        data: Tracking data
        file_path: Output file path
    """
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=2)


def find_task_by_issue(data: Dict[str, Any], issue_number: int) -> Optional[Dict[str, Any]]:
    """Find task entry by issue number.
    
    Args:
        data: Tracking data
        issue_number: GitHub issue number
        
    Returns:
        Task entry or None if not found
    """
    for task in data["food_banks"]:
        if task["issue_number"] == issue_number:
            return task
    return None


def update_task_status(
    task: Dict[str, Any], 
    subtask: str, 
    status: str,
    file_path: Optional[str] = None,
    pr_number: Optional[int] = None
) -> None:
    """Update the status of a subtask.
    
    Args:
        task: Task entry
        subtask: Subtask name (scraper, tests, pr)
        status: New status (pending, in_progress, completed)
        file_path: Optional file path for scraper/test tasks
        pr_number: Optional PR number for pr task
    """
    if subtask not in task["tasks"]:
        print(f"Error: Invalid subtask '{subtask}'. Valid options: scraper, tests, pr")
        return
    
    old_status = task["tasks"][subtask]["status"]
    task["tasks"][subtask]["status"] = status
    
    if status == "completed":
        task["tasks"][subtask]["completed_at"] = datetime.now().isoformat()
    
    if file_path and subtask in ["scraper", "tests"]:
        task["tasks"][subtask]["file_path"] = file_path
    
    if pr_number and subtask == "pr":
        task["tasks"][subtask]["pr_number"] = pr_number
    
    print(f"Updated {subtask} status: {old_status} → {status}")


def recalculate_metadata(data: Dict[str, Any]) -> None:
    """Recalculate metadata statistics.
    
    Args:
        data: Tracking data to update
    """
    completed = 0
    in_progress = 0
    pending = 0
    
    for task in data["food_banks"]:
        all_completed = all(
            subtask["status"] == "completed" 
            for subtask in task["tasks"].values()
        )
        any_in_progress = any(
            subtask["status"] == "in_progress" 
            for subtask in task["tasks"].values()
        )
        
        if all_completed:
            completed += 1
        elif any_in_progress:
            in_progress += 1
        else:
            pending += 1
    
    data["metadata"]["completed"] = completed
    data["metadata"]["in_progress"] = in_progress
    data["metadata"]["pending"] = pending
    data["metadata"]["last_updated"] = datetime.now().isoformat()


def add_note(task: Dict[str, Any], note: str) -> None:
    """Add a note to a task.
    
    Args:
        task: Task entry
        note: Note to add
    """
    timestamp = datetime.now().isoformat()
    task["notes"].append({
        "timestamp": timestamp,
        "note": note
    })
    print(f"Added note: {note}")


def list_in_progress(data: Dict[str, Any]) -> None:
    """List all tasks currently in progress.
    
    Args:
        data: Tracking data
    """
    in_progress_tasks = []
    
    for task in data["food_banks"]:
        for subtask_name, subtask in task["tasks"].items():
            if subtask["status"] == "in_progress":
                in_progress_tasks.append({
                    "issue": task["issue_number"],
                    "name": task["food_bank"]["name"],
                    "subtask": subtask_name
                })
    
    if not in_progress_tasks:
        print("No tasks currently in progress.")
        return
    
    print("\nTasks In Progress:")
    print("=" * 60)
    for task in in_progress_tasks:
        print(f"Issue #{task['issue']}: {task['name']}")
        print(f"  - Working on: {task['subtask']}")
    print()


def show_next_priorities(data: Dict[str, Any], count: int = 10) -> None:
    """Show next priority tasks.
    
    Args:
        data: Tracking data
        count: Number of tasks to show
    """
    priorities = []
    
    for task in data["food_banks"]:
        if task["priority"] == "high" and task["tasks"]["scraper"]["status"] == "pending":
            priorities.append(task)
    
    print(f"\nNext {count} High Priority Tasks:")
    print("=" * 60)
    
    for i, task in enumerate(priorities[:count]):
        print(f"{i+1}. Issue #{task['issue_number']}: {task['food_bank']['name']}")
        if task["food_bank"].get("find_food_url"):
            print(f"   URL: {task['food_bank']['find_food_url']}")
        elif task["food_bank"].get("url"):
            print(f"   URL: {task['food_bank']['url']}")
    print()


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Update scraper development progress"
    )
    
    # Action arguments
    parser.add_argument("--issue", type=int, help="GitHub issue number")
    parser.add_argument("--task", choices=["scraper", "tests", "pr"], 
                       help="Task to update")
    parser.add_argument("--status", choices=["pending", "in_progress", "completed"],
                       help="New status")
    parser.add_argument("--file", help="File path (for scraper/tests tasks)")
    parser.add_argument("--pr", type=int, help="PR number (for pr task)")
    parser.add_argument("--note", help="Add a note to the task")
    
    # Query arguments
    parser.add_argument("--list-in-progress", action="store_true",
                       help="List all tasks currently in progress")
    parser.add_argument("--next", type=int, metavar="N", default=0,
                       help="Show next N priority tasks")
    
    # File argument
    parser.add_argument("--tracking-file", 
                       default="outputs/scraper_development_tracking.json",
                       help="Path to tracking JSON file")
    
    args = parser.parse_args()
    
    # Load tracking data
    tracking_file = Path(args.tracking_file)
    data = load_tracking_data(tracking_file)
    
    # Handle queries
    if args.list_in_progress:
        list_in_progress(data)
        return
    
    if args.next > 0:
        show_next_priorities(data, args.next)
        return
    
    # Handle updates
    if not args.issue:
        parser.error("--issue is required for updates")
    
    # Find the task
    task = find_task_by_issue(data, args.issue)
    if not task:
        print(f"Error: No task found for issue #{args.issue}")
        return
    
    print(f"Found task: {task['food_bank']['name']}")
    
    # Update status if provided
    if args.task and args.status:
        update_task_status(
            task, 
            args.task, 
            args.status,
            file_path=args.file,
            pr_number=args.pr
        )
    
    # Add note if provided
    if args.note:
        add_note(task, args.note)
    
    # Recalculate metadata
    recalculate_metadata(data)
    
    # Save updated data
    save_tracking_data(data, tracking_file)
    print(f"\nTracking data updated: {tracking_file}")
    
    # Show current task status
    print(f"\nCurrent status for issue #{args.issue}:")
    for subtask_name, subtask in task["tasks"].items():
        status_icon = {
            "pending": "⏳",
            "in_progress": "🔄", 
            "completed": "✅"
        }[subtask["status"]]
        print(f"  {status_icon} {subtask_name}: {subtask['status']}")
        if subtask.get("file_path"):
            print(f"     File: {subtask['file_path']}")
        if subtask.get("pr_number"):
            print(f"     PR: #{subtask['pr_number']}")


if __name__ == "__main__":
    main()