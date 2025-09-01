#!/usr/bin/env python3
"""Generate a Claude prompt to implement a food bank scraper.

This script picks a random pending scraper task from GitHub issues
and generates a complete prompt for Claude to implement it.
"""

import argparse
import json
import random
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List


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

            # Skip if already in progress or completed
            if "in-progress" in labels or "completed" in labels:
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

    # If no URL found in structured format, try to find any URL in the body
    if not info["url"] and not info["find_food_url"]:
        import re
        url_match = re.search(r'https?://[^\s<>"]+', body)
        if url_match:
            info["url"] = url_match.group(0)

    return info


def sanitize_name(name: str) -> str:
    """Sanitize name for use in Python identifiers."""
    import re

    name = re.sub(r"[^\w\s]", "", name)
    name = name.replace(" ", "_")
    name = re.sub(r"_+", "_", name)
    name = name.lower()
    name = name.strip("_")
    return name


def create_class_name(name: str) -> str:
    """Create PascalCase class name from food bank name."""
    import re

    name = re.sub(r"[^\w\s]", "", name)
    words = name.split()
    return "".join(word.capitalize() for word in words)


def generate_claude_prompt(issue: Dict[str, Any]) -> str:
    """Generate a complete prompt for Claude to implement a scraper.

    Args:
        issue: GitHub issue dictionary

    Returns:
        Formatted prompt string
    """
    issue_num = issue["number"]
    body = issue.get("body", "")
    priority = issue.get("priority", "")

    # Parse food bank info from issue body
    fb = parse_issue_body(body)

    # Generate names - include state in the name for uniqueness
    name = fb["name"]
    state = fb.get("state", "")

    # Create unique scraper name including state
    if state and state not in name:
        full_name = f"{name} {state}"
        sanitized = sanitize_name(full_name)
    else:
        sanitized = sanitize_name(name)

    class_name = create_class_name(name)
    if state and state not in class_name:
        class_name = f"{class_name}{state}"

    # File paths
    scraper_path = f"app/scraper/{sanitized}_scraper.py"
    test_path = f"tests/test_scraper/test_{sanitized}_scraper.py"

    # Get URL
    url = fb.get("find_food_url") or fb.get("url", "")

    prompt = f"""I need you to implement a scraper for {name} in {state}.

## Task Details:
- GitHub Issue: #{issue_num}
- Priority: {priority or "UNRANKED"}
- State: {state}
- URL to scrape: {url}
- Scraper ID: {sanitized}
- Class name: {class_name}

## CRITICAL FIRST STEP - Check for Vivery/AccessFood:

1. Use Playwright to check if the site uses Vivery:
```bash
# Navigate to the website
mcp_playwright_browser_navigate --url "{url}"

# Take a screenshot to see the page
mcp_playwright_browser_snapshot

# Check if it uses Vivery/AccessFood - THIS IS CRITICAL
mcp_playwright_browser_evaluate --function "() => {{ return document.body.innerHTML.includes('accessfood-widget') || document.body.innerHTML.includes('food-access-widget-cdn') || document.body.innerHTML.includes('pantrynet'); }}"
```

**IF VIVERY IS DETECTED:**
- DO NOT implement a scraper
- Close the GitHub issue with this comment:
```bash
gh issue close {issue_num} --comment "This food bank uses Vivery/AccessFood and is already covered by vivery_api_scraper.py. No additional scraper is needed."
```
- Add label to indicate it's covered:
```bash
gh issue edit {issue_num} --add-label "vivery-covered"
```
- STOP HERE - do not proceed with implementation

## IF VIVERY IS NOT DETECTED, continue with implementation:

2. Create the boilerplate files:
```bash
./scripts/feeding-america/create_scraper_from_issue.py --issue {issue_num}
```

3. Analyze the website:
- Check if data is in HTML source or loaded dynamically
- Look for API endpoints in Network tab
- Identify the data structure (table, divs, API JSON)
- Note any pagination or search requirements

4. Implement the scraper in {scraper_path}:
- IMPORTANT: Name the scraper uniquely including state (e.g., "{sanitized}_scraper.py")
- Choose the appropriate method (HTML parsing or API)
- Use existing patterns from similar scrapers
- Include proper error handling and logging
- **DO NOT include geocoding** - the validator service handles this
- Lat/long is optional - include if available from the source, otherwise leave as None

5. Update the tests in {test_path}:
- Add realistic mock data based on actual website
- Test all methods including error cases
- Remove any geocoding-related test expectations

6. Test the implementation:
```bash
# Run tests using bouy (inside the app container)
./bouy test --pytest {test_path}

# Test the scraper directly in the app container
# The app container has bind-mounted code so changes are immediately available
./bouy exec app python3 -m app.scraper {sanitized}

# Or use the scraper-test command for dry run
./bouy scraper-test {sanitized}
```

7. Create PR and close issue:
```bash
# Create a new branch
git checkout -b scraper/{sanitized}

# Add files and commit
git add {scraper_path} {test_path}
git commit -m "feat: implement scraper for {name} ({state})

Closes #{issue_num}"

# Push and create PR
git push -u origin scraper/{sanitized}
gh pr create --title "Implement scraper for {name} ({state})" --body "Implements scraper for {name} food bank.

Closes #{issue_num}

## Changes
- Add scraper implementation
- Add comprehensive tests
- Follow existing patterns

## Testing
- Tests pass with 100% coverage
- Scraper successfully extracts location data
- No geocoding in scraper (handled by validator service)"

# After PR is merged, the issue will automatically close
```

8. Update issue status:
```bash
# Add in-progress label when starting
gh issue edit {issue_num} --add-label "in-progress"

# Add completed label when done
gh issue edit {issue_num} --add-label "completed"
```

## Key Patterns to Follow:

### For HTML Scraping:
- Use BeautifulSoup to parse HTML
- Look for tables, lists, or div containers with location data
- Handle missing elements gracefully (use .find() with None checks)
- Example pattern from existing scrapers

### For API Scraping:
- Use httpx for async requests
- Handle pagination if needed
- Add appropriate delays between requests
- Check for geographic grid search patterns

### Important Changes from Previous System:
- **NO GEOCODING in scrapers** - validator service handles this
- **Lat/long is OPTIONAL** - include if available, otherwise None
- **No local tracking JSON** - use GitHub issues and labels only
- **Templates are in scripts/feeding-america/templates/**

### Running Scrapers During Development:
- Use `./bouy exec app python3 -m app.scraper <scraper_name>` to run scrapers
- The app container has bind-mounted code, so changes are immediate
- Use `./bouy scraper-test <scraper_name>` for dry runs without queue submission
- Always test inside the container to ensure proper environment

## Important Guidelines:
- ALWAYS check for Vivery first - if found, close issue and stop
- Follow the existing scraper patterns
- Use test_mode parameter for limiting data during development
- Add comprehensive logging
- Handle missing data gracefully
- DO NOT add geocoding logic
- Submit each location as a separate job to the queue

Please start by checking if this site uses Vivery. If it does, close the issue. Otherwise, implement the scraper following the patterns in existing scrapers."""

    return prompt


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Generate Claude prompt to implement a food bank scraper"
    )
    parser.add_argument(
        "--priority",
        choices=["CRITICAL", "HIGH", "MEDIUM", "LOW"],
        help="Filter by priority level",
    )
    parser.add_argument("--state", help="Filter by state code")
    parser.add_argument("--issue", type=int, help="Use specific issue number")
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available issues instead of generating prompt",
    )

    args = parser.parse_args()

    # Get pending issues from GitHub
    issues = get_scraper_issues(state=args.state, priority=args.priority)

    if not issues:
        print("No pending scraper issues found with the specified criteria.")
        return

    # Sort by priority
    priority_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "": 4}
    issues.sort(key=lambda i: priority_order.get(i.get("priority", ""), 4))

    if args.list:
        # List available issues
        print(f"\nFound {len(issues)} pending scraper issues:\n")
        for issue in issues[:20]:  # Show first 20
            priority = issue.get("priority", "")
            priority_badge = {
                "CRITICAL": "🔴",
                "HIGH": "🟠",
                "MEDIUM": "🟡",
                "LOW": "🟢",
            }.get(priority, "⚪")

            print(f"{priority_badge} #{issue['number']}: {issue['title']}")

        if len(issues) > 20:
            print(f"\n... and {len(issues) - 20} more")
        return

    # Select issue
    if args.issue:
        selected = None
        for issue in issues:
            if issue["number"] == args.issue:
                selected = issue
                break
        if not selected:
            print(f"Issue #{args.issue} not found in pending tasks.")
            return
    else:
        # Pick task with preference for higher priorities
        # If we have any CRITICAL tasks, always pick from those
        critical_tasks = [i for i in issues if i.get("priority") == "CRITICAL"]
        if critical_tasks:
            selected = random.choice(critical_tasks)
        else:
            # Otherwise use weighted selection favoring higher priorities
            weights = [len(issues) - i for i in range(len(issues))]
            selected = random.choices(issues, weights=weights, k=1)[0]

    # Generate prompt
    prompt = generate_claude_prompt(selected)

    # Output
    print(prompt)
    print(f"\n{'='*60}")

    priority = selected.get("priority", "UNRANKED")
    priority_badge = {
        "CRITICAL": "🔴 CRITICAL",
        "HIGH": "🟠 HIGH",
        "MEDIUM": "🟡 MEDIUM",
        "LOW": "🟢 LOW",
    }.get(priority, "⚪ UNRANKED")

    fb = parse_issue_body(selected.get("body", ""))
    print(f"Selected: {fb['name']} (Issue #{selected['number']})")
    print(f"Priority: {priority_badge}")
    print(f"\nTo copy to clipboard: python3 scripts/feeding-america/implement_scraper_with_claude.py --issue {selected['number']} | pbcopy")


if __name__ == "__main__":
    main()