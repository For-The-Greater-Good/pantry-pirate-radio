#!/usr/bin/env python3
"""Prioritize food bank scraper issues based on population served.

This script analyzes GitHub issues and assigns priority levels based on
the population of the areas served by each food bank.
"""

import argparse
import json
import subprocess
import sys
from typing import Dict, List, Tuple


# Priority definitions based on metropolitan area populations
CRITICAL_METROS = {
    # Major metros with 5M+ population
    "New York": ["162", "192", "229"],  # NYC metro ~20M
    "Los Angeles": ["35", "36", "37", "45", "52"],  # LA/Inland Empire ~18M
    "Chicago": ["91"],  # Chicago metro ~10M
    "Dallas": ["292"],  # DFW metro ~8M (Tarrant Area)
    "Houston": ["293"],  # Houston metro ~7M
    "Washington DC": ["65", "113"],  # DC metro ~6M (Capital Area, Maryland)
    "Miami": ["71"],  # South Florida ~6M
    "Philadelphia": ["272", "273", "275"],  # Philly metro ~6M
    "Atlanta": ["75"],  # Atlanta metro ~6M
    "Phoenix": ["32"],  # Phoenix metro ~5M (St. Marys)
    "Boston": ["112"],  # Boston metro ~5M (Western Mass)
    "San Francisco": ["54", "55"],  # Bay Area ~8M
    "Seattle": ["315"],  # Seattle metro ~4M
}

HIGH_PRIORITY_METROS = {
    # Large cities with 1-5M population
    "San Antonio": ["302"],
    "San Diego": ["45", "46"],  # FIND, Imperial Valley
    "Tampa": ["73"],
    "St. Louis": ["128"],
    "Pittsburgh": ["264"],
    "Sacramento": ["40"],
    "Cleveland": ["197", "234"],
    "Milwaukee": ["318"],  # Eastern Wisconsin
    "New Orleans": ["109"],
    "Orlando": ["70"],  # Central Florida
    "Jacksonville": ["69"],  # Northeast Florida
    "Cincinnati": ["102"],  # Kentucky's Heartland
    "Kansas City": ["130"],  # Harvesters
    "Las Vegas": [],  # Need to find
    "Columbus": ["129"],  # Central & Northeast Missouri
    "Charlotte": ["279"],  # Harvest Hope
    "Indianapolis": ["96"],  # Gleaners
    "Nashville": ["285"],  # Middle Tennessee
    "Virginia Beach": ["309"],  # Southeastern VA
    "Providence": ["277"],  # Rhode Island
    "Memphis": ["81"],  # Second Harvest South Georgia (covers parts)
    "Louisville": ["105"],  # Dare to Care
    "Richmond": ["310"],  # Feed More
    "Buffalo": ["157", "187", "224"],  # FeedMore Western NY
    "Hartford": ["64"],  # Connecticut
    "Birmingham": ["17"],  # Central Alabama
    "Rochester": ["194", "231"],  # Central NY
    "Tucson": ["33"],  # Southern Arizona
    "Fresno": ["41"],  # Central California
    "Tulsa": ["132"],  # Ozarks (covers parts)
    "Honolulu": ["82"],  # Hawaii
    "Spokane": ["316"],  # Second Harvest Inland Northwest
    "Madison": ["317"],  # Southern Wisconsin
    "Des Moines": ["86"],  # Iowa
    "Albuquerque": [],  # Need to find
    "Omaha": ["145", "175", "212"],  # Siouxland
    "Raleigh": [],  # Need to find  
    "Baton Rouge": ["107"],
    "Akron": ["197", "234"],  # Part of Cleveland area
    "Toledo": ["269"],  # Northwest PA (covers parts)
    "Knoxville": ["283"],  # East Tennessee
    "Worcester": ["112"],  # Part of Western Mass
    "Charleston": ["278"],  # Lowcountry
    "Grand Rapids": ["119"],  # West Michigan
    "Newport News": ["308"],  # Virginia Peninsula
}


def get_all_scraper_issues() -> List[Dict]:
    """Fetch all GitHub issues with the scraper label."""
    cmd = [
        "gh", "issue", "list",
        "--label", "scraper",
        "--limit", "300",
        "--json", "number,title,body",
        "--repo", "For-The-Greater-Good/pantry-pirate-radio"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Error fetching issues: {e}")
        sys.exit(1)


def extract_state_and_name(issue: Dict) -> Tuple[str, str]:
    """Extract state code and food bank name from issue."""
    body_lines = issue["body"].split("\n")
    state = ""
    name = ""
    
    for line in body_lines:
        if "**State:**" in line:
            state = line.replace("**State:**", "").strip()
        if "**Name:**" in line:
            name = line.replace("**Name:**", "").strip()
    
    # Also try to get name from title
    if not name and "Implement scraper for" in issue["title"]:
        name = issue["title"].replace("Implement scraper for", "").strip()
    
    return state, name


def determine_priority(issue_num: str, state: str, name: str) -> str:
    """Determine priority level for an issue."""
    # Check if it's in critical metros
    for metro, issues in CRITICAL_METROS.items():
        if issue_num in issues:
            return "CRITICAL"
    
    # Check if it's in high priority metros
    for metro, issues in HIGH_PRIORITY_METROS.items():
        if issue_num in issues:
            return "HIGH"
    
    # State-based heuristics for remaining issues
    high_pop_states = ["CA", "TX", "FL", "NY", "PA", "IL", "OH", "GA", "NC", "MI", "NJ", "VA", "WA", "AZ", "MA", "TN", "IN", "MD", "MO", "WI", "CO", "MN", "SC", "AL", "LA", "KY", "OR", "OK", "CT", "UT", "IA", "NV", "AR", "MS", "KS", "NM", "NE", "ID", "WV", "HI", "NH", "ME", "RI", "MT", "DE", "SD", "ND", "AK", "VT", "WY"]
    
    # Major metropolitan areas by state
    if state == "CA":
        if any(metro in name.lower() for metro in ["los angeles", "san diego", "san jose", "oakland", "long beach", "anaheim", "riverside", "san bernardino"]):
            return "HIGH"
    elif state == "TX":
        if any(metro in name.lower() for metro in ["dallas", "austin", "fort worth", "el paso", "arlington", "corpus christi", "plano", "laredo", "lubbock", "irving"]):
            return "HIGH"
    elif state == "FL":
        if any(metro in name.lower() for metro in ["miami", "orlando", "tampa", "st. petersburg", "hialeah", "tallahassee", "fort lauderdale", "pembroke pines", "hollywood", "gainesville"]):
            return "HIGH"
    elif state == "NY":
        if any(metro in name.lower() for metro in ["buffalo", "rochester", "yonkers", "syracuse", "albany"]):
            return "HIGH"
    
    # Check if it mentions "regional" or covers multiple counties
    if "regional" in name.lower() or "area" in name.lower() or "community" in name.lower():
        if state in high_pop_states[:15]:  # Top 15 states by population
            return "HIGH"
        else:
            return "MEDIUM"
    
    # Default based on state population ranking
    if state in high_pop_states[:10]:  # Top 10 states
        return "MEDIUM"
    elif state in high_pop_states[:30]:  # Top 30 states
        return "MEDIUM"
    else:
        return "LOW"


def update_issue_title(issue_num: int, new_title: str, dry_run: bool = False):
    """Update a GitHub issue title."""
    if dry_run:
        print(f"[DRY RUN] Would update issue #{issue_num} to: {new_title}")
        return
    
    cmd = [
        "gh", "issue", "edit", str(issue_num),
        "--title", new_title,
        "--repo", "For-The-Greater-Good/pantry-pirate-radio"
    ]
    
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"✓ Updated issue #{issue_num}: {new_title}")
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to update issue #{issue_num}: {e}")


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Prioritize food bank scraper issues based on population served"
    )
    parser.add_argument("--dry-run", action="store_true",
                       help="Show what would be updated without making changes")
    parser.add_argument("--stats-only", action="store_true",
                       help="Only show statistics, don't update anything")
    
    args = parser.parse_args()
    
    # Fetch all issues
    print("Fetching scraper issues...")
    issues = get_all_scraper_issues()
    print(f"Found {len(issues)} scraper issues")
    
    # Analyze and categorize
    priorities = {"CRITICAL": [], "HIGH": [], "MEDIUM": [], "LOW": []}
    updates_needed = []
    
    for issue in issues:
        issue_num = str(issue["number"])
        current_title = issue["title"]
        state, name = extract_state_and_name(issue)
        
        # Skip if already has a priority prefix
        if any(current_title.startswith(f"[{p}]") for p in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]):
            priority = None
            for p in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
                if current_title.startswith(f"[{p}]"):
                    priority = p
                    break
            if priority:
                priorities[priority].append((issue_num, name, state))
            continue
        
        # Determine priority
        priority = determine_priority(issue_num, state, name)
        priorities[priority].append((issue_num, name, state))
        
        # Prepare update
        new_title = f"[{priority}] {current_title}"
        updates_needed.append((issue_num, new_title, current_title))
    
    # Show statistics
    print("\n📊 Priority Distribution:")
    print(f"  CRITICAL: {len(priorities['CRITICAL'])} issues (major metros, 5M+ people)")
    print(f"  HIGH:     {len(priorities['HIGH'])} issues (large cities, 1-5M people)")
    print(f"  MEDIUM:   {len(priorities['MEDIUM'])} issues (mid-size areas, 500K-1M)")
    print(f"  LOW:      {len(priorities['LOW'])} issues (rural/small areas)")
    print(f"  Total:    {len(issues)} issues")
    
    if args.stats_only:
        # Show some examples from each category
        print("\n📍 Example Issues by Priority:")
        for priority in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            print(f"\n{priority}:")
            for issue_num, name, state in priorities[priority][:5]:
                print(f"  #{issue_num}: {name} ({state})")
            if len(priorities[priority]) > 5:
                print(f"  ... and {len(priorities[priority]) - 5} more")
        return
    
    # Show updates needed
    print(f"\n🔄 Updates needed: {len(updates_needed)} issues")
    
    if not updates_needed:
        print("All issues already have priority prefixes!")
        return
    
    # Show what will be updated
    print("\n📝 Planned updates:")
    for issue_num, new_title, old_title in updates_needed[:10]:
        print(f"  #{issue_num}: {old_title}")
        print(f"         → {new_title}")
    
    if len(updates_needed) > 10:
        print(f"  ... and {len(updates_needed) - 10} more")
    
    if args.dry_run:
        print("\n[DRY RUN] No changes made. Remove --dry-run to apply updates.")
        return
    
    # Confirm before proceeding
    response = input(f"\nProceed with updating {len(updates_needed)} issues? [y/N] ")
    if response.lower() != 'y':
        print("Cancelled.")
        return
    
    # Apply updates
    print("\n🚀 Updating issues...")
    for issue_num, new_title, _ in updates_needed:
        update_issue_title(int(issue_num), new_title)
    
    print("\n✅ Done!")


if __name__ == "__main__":
    main()