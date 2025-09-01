#!/usr/bin/env python3
"""Update scraper progress using GitHub issue labels and comments.

This script manages scraper development status directly through GitHub,
using labels to track progress and comments to add notes.
"""

import argparse
import json
import subprocess
import sys
from typing import List, Optional


def add_label(issue_number: int, label: str) -> bool:
    """Add a label to a GitHub issue.

    Args:
        issue_number: GitHub issue number
        label: Label to add

    Returns:
        True if successful, False otherwise
    """
    cmd = [
        "gh", "issue", "edit", str(issue_number),
        "--add-label", label,
        "--repo", "For-The-Greater-Good/pantry-pirate-radio"
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"✓ Added label '{label}' to issue #{issue_number}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to add label: {e}")
        return False


def remove_label(issue_number: int, label: str) -> bool:
    """Remove a label from a GitHub issue.

    Args:
        issue_number: GitHub issue number
        label: Label to remove

    Returns:
        True if successful, False otherwise
    """
    cmd = [
        "gh", "issue", "edit", str(issue_number),
        "--remove-label", label,
        "--repo", "For-The-Greater-Good/pantry-pirate-radio"
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"✓ Removed label '{label}' from issue #{issue_number}")
        return True
    except subprocess.CalledProcessError:
        # Label might not exist, that's ok
        return True


def add_comment(issue_number: int, comment: str) -> bool:
    """Add a comment to a GitHub issue.

    Args:
        issue_number: GitHub issue number
        comment: Comment text to add

    Returns:
        True if successful, False otherwise
    """
    cmd = [
        "gh", "issue", "comment", str(issue_number),
        "--body", comment,
        "--repo", "For-The-Greater-Good/pantry-pirate-radio"
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"✓ Added comment to issue #{issue_number}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to add comment: {e}")
        return False


def update_status(issue_number: int, status: str) -> bool:
    """Update the status of a scraper task.

    Args:
        issue_number: GitHub issue number
        status: New status (pending, in-progress, completed, vivery-covered)

    Returns:
        True if successful, False otherwise
    """
    # Remove old status labels
    for old_status in ["pending", "in-progress", "completed", "vivery-covered"]:
        if old_status != status:
            remove_label(issue_number, old_status)

    # Add new status label
    if status != "pending":  # pending is the default (no label)
        return add_label(issue_number, status)
    return True


def get_pending_issues(state: Optional[str] = None) -> List[dict]:
    """Get all pending scraper issues from GitHub.

    Args:
        state: Optional state filter

    Returns:
        List of pending issues
    """
    cmd = [
        "gh", "issue", "list",
        "--label", "scraper",
        "--state", "open",
        "--limit", "300",
        "--repo", "For-The-Greater-Good/pantry-pirate-radio",
        "--json", "number,title,body,labels"
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        issues = json.loads(result.stdout)

        # Filter for pending (no status label)
        pending = []
        for issue in issues:
            labels = [label["name"] for label in issue.get("labels", [])]

            # Skip if has any status label
            if any(status in labels for status in ["in-progress", "completed", "vivery-covered"]):
                continue

            # Apply state filter if provided
            if state:
                body = issue.get("body", "")
                if f"State: {state.upper()}" not in body:
                    continue

            pending.append(issue)

        return pending
    except subprocess.CalledProcessError:
        return []


def get_in_progress_issues() -> List[dict]:
    """Get all in-progress scraper issues from GitHub.

    Returns:
        List of in-progress issues
    """
    cmd = [
        "gh", "issue", "list",
        "--label", "scraper",
        "--label", "in-progress",
        "--state", "open",
        "--limit", "100",
        "--repo", "For-The-Greater-Good/pantry-pirate-radio",
        "--json", "number,title,body"
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    except subprocess.CalledProcessError:
        return []


def show_summary() -> None:
    """Show a summary of scraper development progress."""
    cmd = [
        "gh", "issue", "list",
        "--label", "scraper",
        "--state", "all",
        "--limit", "500",
        "--repo", "For-The-Greater-Good/pantry-pirate-radio",
        "--json", "number,title,state,labels"
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        issues = json.loads(result.stdout)

        # Count by status
        stats = {
            "pending": 0,
            "in-progress": 0,
            "completed": 0,
            "vivery-covered": 0,
            "closed": 0,
            "total": len(issues)
        }

        for issue in issues:
            if issue["state"] == "CLOSED":
                stats["closed"] += 1
                continue

            labels = [label["name"] for label in issue.get("labels", [])]

            if "completed" in labels:
                stats["completed"] += 1
            elif "in-progress" in labels:
                stats["in-progress"] += 1
            elif "vivery-covered" in labels:
                stats["vivery-covered"] += 1
            else:
                stats["pending"] += 1

        # Display summary
        print(f"\n{'='*60}")
        print("SCRAPER DEVELOPMENT SUMMARY")
        print(f"{'='*60}")
        print(f"Total Issues:        {stats['total']}")
        print(f"Closed:              {stats['closed']}")
        print(f"Completed:           {stats['completed']}")
        print(f"In Progress:         {stats['in-progress']}")
        print(f"Pending:             {stats['pending']}")
        print(f"Vivery Covered:      {stats['vivery-covered']}")
        print(f"{'='*60}")

        # Calculate percentage
        open_issues = stats['total'] - stats['closed']
        if open_issues > 0:
            completion_pct = ((stats['completed'] + stats['vivery-covered']) / open_issues) * 100
            print(f"Completion Rate:     {completion_pct:.1f}%")
        print(f"{'='*60}\n")

    except subprocess.CalledProcessError as e:
        print(f"Error fetching summary: {e}")


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Update scraper progress using GitHub labels"
    )

    # Issue selection
    parser.add_argument("--issue", type=int, help="GitHub issue number to update")

    # Status update
    parser.add_argument(
        "--status",
        choices=["pending", "in-progress", "completed", "vivery-covered"],
        help="New status for the issue"
    )

    # Add notes
    parser.add_argument("--note", help="Add a comment to the issue")
    parser.add_argument("--file", help="Note the file path (added as comment)")
    parser.add_argument("--pr", type=int, help="Note the PR number (added as comment)")

    # List and summary options
    parser.add_argument(
        "--next",
        type=int,
        metavar="N",
        help="Show next N pending tasks"
    )
    parser.add_argument(
        "--list-in-progress",
        action="store_true",
        help="List all in-progress tasks"
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Show summary statistics"
    )

    args = parser.parse_args()

    # Handle summary
    if args.summary:
        show_summary()
        return

    # Handle listing next tasks
    if args.next:
        pending = get_pending_issues()
        print(f"\nNext {args.next} pending tasks:")
        print("-" * 40)
        for i, issue in enumerate(pending[:args.next], 1):
            print(f"{i}. #{issue['number']}: {issue['title']}")

        if len(pending) > args.next:
            print(f"\n... and {len(pending) - args.next} more pending tasks")
        return

    # Handle listing in-progress
    if args.list_in_progress:
        in_progress = get_in_progress_issues()
        if not in_progress:
            print("No tasks currently in progress")
        else:
            print(f"\nIn-progress tasks ({len(in_progress)}):")
            print("-" * 40)
            for issue in in_progress:
                print(f"#{issue['number']}: {issue['title']}")
        return

    # Handle issue updates
    if args.issue:
        success = True

        # Update status if provided
        if args.status:
            success = update_status(args.issue, args.status) and success

        # Add comments for additional information
        comments = []

        if args.file:
            comments.append(f"📁 File: `{args.file}`")

        if args.pr:
            comments.append(f"🔗 Pull Request: #{args.pr}")

        if args.note:
            comments.append(f"📝 Note: {args.note}")

        if comments:
            comment_text = "\n".join(comments)
            success = add_comment(args.issue, comment_text) and success

        if success:
            print(f"\n✅ Successfully updated issue #{args.issue}")
        else:
            print(f"\n⚠️  Some updates may have failed for issue #{args.issue}")
    else:
        # Show help if no action specified
        parser.print_help()


if __name__ == "__main__":
    main()