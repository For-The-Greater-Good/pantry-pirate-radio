#!/usr/bin/env python3
"""Create GitHub issues for Feeding America food banks."""

import json
import subprocess
import time
from pathlib import Path
from typing import Dict, List


def create_github_issue(issue_data: Dict[str, any], dry_run: bool = True) -> bool:
    """Create a single GitHub issue using gh CLI.
    
    Args:
        issue_data: Issue data with title, body, labels
        dry_run: If True, only print command without executing
        
    Returns:
        True if successful (or dry_run), False otherwise
    """
    # Filter labels to only include ones we know exist
    existing_labels = ['help wanted', 'scraper', 'food-bank']
    labels = [l for l in issue_data.get('labels', []) if l in existing_labels]
    labels_str = ",".join(labels)
    
    # Build gh command
    cmd = [
        'gh', 'issue', 'create',
        '--title', issue_data['title'],
        '--body', issue_data['body']
    ]
    
    if labels_str:
        cmd.extend(['--label', labels_str])
    
    if dry_run:
        print(f"[DRY RUN] Would create issue: {issue_data['title']}")
        print(f"  Labels: {labels_str}")
        print(f"  First 100 chars of body: {issue_data['body'][:100]}...")
        return True
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ Created issue: {issue_data['title']}")
            print(f"   URL: {result.stdout.strip()}")
            return True
        else:
            print(f"❌ Failed to create issue: {issue_data['title']}")
            print(f"   Error: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Exception creating issue: {issue_data['title']}")
        print(f"   Error: {e}")
        return False


def main():
    """Main function to create GitHub issues."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Create GitHub issues for Feeding America food banks')
    parser.add_argument('--limit', type=int, default=5, help='Number of issues to create (default: 5)')
    parser.add_argument('--start', type=int, default=0, help='Start index (default: 0)')
    parser.add_argument('--dry-run', action='store_true', help='Print commands without executing')
    parser.add_argument('--only-vivery', action='store_true', help='Only create issues for Vivery candidates')
    parser.add_argument('--exclude-vivery', action='store_true', help='Exclude Vivery candidates')
    parser.add_argument('--state', help='Only create issues for a specific state (e.g., NY)')
    parser.add_argument('--delay', type=int, default=2, help='Delay between issues in seconds (default: 2)')
    parser.add_argument('--yes', '-y', action='store_true', help='Skip confirmation prompt')
    
    args = parser.parse_args()
    
    # Load issues data - use relative paths from project root
    issues_file = Path('outputs/feeding_america_issues.json')
    vivery_file = Path('outputs/vivery_candidates.json')
    
    with open(issues_file, 'r') as f:
        all_issues = json.load(f)
    
    with open(vivery_file, 'r') as f:
        vivery_candidates = json.load(f)
    
    # Get Vivery org IDs
    vivery_org_ids = {fb['org_id'] for fb in vivery_candidates}
    
    # Filter issues based on arguments
    filtered_issues = []
    for issue in all_issues:
        fb = issue['food_bank']
        org_id = fb.get('org_id')
        
        # Check Vivery filter
        if args.only_vivery and org_id not in vivery_org_ids:
            continue
        if args.exclude_vivery and org_id in vivery_org_ids:
            continue
        
        # Check state filter
        if args.state and fb.get('state', '').upper() != args.state.upper():
            continue
        
        filtered_issues.append(issue)
    
    # Apply start and limit
    issues_to_create = filtered_issues[args.start:args.start + args.limit]
    
    print(f"Total issues available: {len(all_issues)}")
    print(f"Filtered issues: {len(filtered_issues)}")
    print(f"Will create: {len(issues_to_create)} issues (starting from index {args.start})")
    
    if args.dry_run:
        print("\n🔍 DRY RUN MODE - No issues will be created\n")
    else:
        print(f"\n⚠️  Will create {len(issues_to_create)} real GitHub issues!")
        if not args.yes:
            response = input("Continue? (y/N): ")
            if response.lower() != 'y':
                print("Aborted.")
                return
    
    # Create issues
    success_count = 0
    for i, issue in enumerate(issues_to_create):
        print(f"\n[{i+1}/{len(issues_to_create)}] Processing: {issue['title']}")
        
        if create_github_issue(issue, dry_run=args.dry_run):
            success_count += 1
        
        # Delay between issues (except for last one)
        if i < len(issues_to_create) - 1 and not args.dry_run:
            print(f"Waiting {args.delay} seconds...")
            time.sleep(args.delay)
    
    print(f"\n✅ Successfully created {success_count}/{len(issues_to_create)} issues")
    
    # Show next batch info
    next_start = args.start + len(issues_to_create)
    if next_start < len(filtered_issues):
        print(f"\nTo create the next batch, run:")
        cmd = f"python scripts/create_feeding_america_issues.py --start {next_start} --limit {args.limit}"
        if args.state:
            cmd += f" --state {args.state}"
        if args.exclude_vivery:
            cmd += " --exclude-vivery"
        print(cmd)


if __name__ == '__main__':
    main()