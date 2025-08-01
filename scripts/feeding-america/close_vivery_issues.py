#!/usr/bin/env python3
"""Close GitHub issues for food banks that use Vivery."""

import json
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional


def find_issue_for_foodbank(org_id: str, name: str) -> Optional[str]:
    """Find GitHub issue number for a food bank.
    
    Args:
        org_id: Organization ID
        name: Food bank name
        
    Returns:
        Issue number if found, None otherwise
    """
    # Search for issues with the food bank name
    search_query = f'repo:For-The-Greater-Good/pantry-pirate-radio is:issue is:open "{name}"'
    
    cmd = [
        "gh", "issue", "list",
        "--repo", "For-The-Greater-Good/pantry-pirate-radio",
        "--search", search_query,
        "--json", "number,title",
        "--limit", "100"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        issues = json.loads(result.stdout)
        
        # Look for exact match in title
        for issue in issues:
            if name in issue.get("title", ""):
                return str(issue["number"])
                
        return None
    except Exception as e:
        print(f"Error searching for issue: {e}")
        return None


def close_issue_with_comment(issue_number: str, dry_run: bool = True) -> bool:
    """Close an issue with a comment about Vivery coverage.
    
    Args:
        issue_number: GitHub issue number
        dry_run: If True, only print what would be done
        
    Returns:
        True if successful, False otherwise
    """
    comment = "Covered by vivery_api_scraper.py"
    
    if dry_run:
        print(f"[DRY RUN] Would close issue #{issue_number} with comment: '{comment}'")
        return True
    
    try:
        # Add comment
        comment_cmd = [
            "gh", "issue", "comment", issue_number,
            "--repo", "For-The-Greater-Good/pantry-pirate-radio",
            "--body", comment
        ]
        subprocess.run(comment_cmd, check=True, capture_output=True)
        print(f"  ✓ Added comment to issue #{issue_number}")
        
        # Close issue
        close_cmd = [
            "gh", "issue", "close", issue_number,
            "--repo", "For-The-Greater-Good/pantry-pirate-radio"
        ]
        subprocess.run(close_cmd, check=True, capture_output=True)
        print(f"  ✓ Closed issue #{issue_number}")
        
        return True
        
    except Exception as e:
        print(f"  ✗ Error with issue #{issue_number}: {e}")
        return False


def main():
    """Main function to close Vivery-covered issues."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Close GitHub issues for Vivery-covered food banks")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    parser.add_argument("--delay", type=int, default=1, help="Delay between operations in seconds")
    args = parser.parse_args()
    
    # Load Vivery users
    vivery_file = Path("outputs/vivery_confirmed_users.json")
    if not vivery_file.exists():
        print("Error: vivery_confirmed_users.json not found. Run check_vivery_usage.py first.")
        return
    
    with open(vivery_file) as f:
        vivery_users = json.load(f)
    
    print(f"Found {len(vivery_users)} confirmed Vivery users")
    
    # Track results
    found_issues = []
    not_found = []
    closed_count = 0
    
    # Process each Vivery user
    for i, fb in enumerate(vivery_users):
        org_id = fb.get("org_id", "")
        name = fb.get("name", "")
        state = fb.get("state", "")
        
        print(f"\n[{i+1}/{len(vivery_users)}] {name} (ID: {org_id}, State: {state})")
        
        # Find corresponding issue
        issue_number = find_issue_for_foodbank(org_id, name)
        
        if issue_number:
            print(f"  → Found issue #{issue_number}")
            found_issues.append({
                "org_id": org_id,
                "name": name,
                "issue_number": issue_number
            })
            
            # Close the issue
            if close_issue_with_comment(issue_number, dry_run=args.dry_run):
                closed_count += 1
            
            # Rate limiting
            if not args.dry_run and i < len(vivery_users) - 1:
                time.sleep(args.delay)
        else:
            print(f"  → No issue found")
            not_found.append({
                "org_id": org_id,
                "name": name
            })
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Total Vivery users: {len(vivery_users)}")
    print(f"Issues found: {len(found_issues)}")
    print(f"Issues not found: {len(not_found)}")
    if not args.dry_run:
        print(f"Issues closed: {closed_count}")
    
    # Save results
    results = {
        "vivery_users_count": len(vivery_users),
        "issues_found": found_issues,
        "issues_not_found": not_found,
        "closed_count": closed_count if not args.dry_run else 0,
        "dry_run": args.dry_run
    }
    
    output_file = Path("outputs/vivery_issues_closed.json")
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\nResults saved to: {output_file}")
    
    if found_issues:
        print("\nISSUES TO CLOSE:")
        for item in found_issues:
            print(f"- #{item['issue_number']}: {item['name']}")
    
    if not_found:
        print("\nNO ISSUES FOUND FOR:")
        for item in not_found:
            print(f"- {item['name']} (ID: {item['org_id']})")
    
    if args.dry_run:
        print("\n⚠️  This was a dry run. Use without --dry-run to actually close issues.")


if __name__ == "__main__":
    main()