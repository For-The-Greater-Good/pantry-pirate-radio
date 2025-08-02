#!/usr/bin/env python3
"""Generate a Claude prompt to implement a food bank scraper.

This script picks a random pending scraper task and generates a complete
prompt for Claude to implement it, including all necessary context.
"""

import argparse
import json
import random
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List


def load_tracking_data() -> Dict[str, Any]:
    """Load tracking data to get food bank information."""
    tracking_file = Path("outputs/scraper_development_tracking.json")
    if not tracking_file.exists():
        print(f"Error: Tracking file not found at {tracking_file}")
        print("Run generate_scraper_tracking.py first.")
        sys.exit(1)

    with open(tracking_file) as f:
        return json.load(f)


def get_pending_tasks(
    data: Dict[str, Any], priority: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Get all pending scraper tasks."""
    pending = []

    for fb in data["food_banks"]:
        if fb["tasks"]["scraper"]["status"] == "pending":
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
        "gh",
        "issue",
        "list",
        "--label",
        "scraper",
        "--limit",
        "300",
        "--repo",
        "For-The-Greater-Good/pantry-pirate-radio",
        "--json",
        "number,title",
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


def fetch_issue_body(issue_number: int) -> str:
    """Fetch the body content of a GitHub issue."""
    cmd = [
        "gh",
        "issue",
        "view",
        str(issue_number),
        "--repo",
        "For-The-Greater-Good/pantry-pirate-radio",
        "--json",
        "body",
        "--jq",
        ".body",
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return "Unable to fetch issue body"


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


def read_file_content(filepath: str, max_lines: int = 200) -> str:
    """Read file content for context."""
    path = Path(filepath)
    if not path.exists():
        return f"File not found: {filepath}"

    lines = path.read_text().splitlines()
    if len(lines) > max_lines:
        return (
            "\n".join(lines[:max_lines])
            + f"\n... (truncated, {len(lines) - max_lines} more lines)"
        )
    return "\n".join(lines)


def generate_claude_prompt(task: Dict[str, Any]) -> str:
    """Generate a complete prompt for Claude to implement a scraper."""
    fb = task["food_bank"]
    issue_num = task["issue_number"]

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

    # Get issue body
    issue_body = fetch_issue_body(issue_num)

    # Extract URL
    url = fb.get("find_food_url") or fb.get("url", "")
    if not url and "http" in issue_body:
        import re

        url_match = re.search(r'https?://[^\s<>"]+', issue_body)
        if url_match:
            url = url_match.group(0)

    # Read key reference files
    scraper_utils = read_file_content("app/scraper/utils.py", 100)
    scraper_patterns = read_file_content("docs/scraper-patterns.md", 150)
    example_scraper = read_file_content(
        "app/scraper/mercer_food_finder_scraper.py", 150
    )

    prompt = f"""I need you to implement a scraper for {name} in {state}.

## Task Details:
- GitHub Issue: #{issue_num}
- State: {fb.get('state', 'Unknown')}
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
- Update tracking to mark as not needed:
```bash
./scripts/feeding-america/update_scraper_progress.py --issue {issue_num} --task scraper --status not_needed --notes "Uses Vivery - covered by existing scraper"
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
- Add geocoding for addresses

5. Update the tests in {test_path}:
- Add realistic mock data based on actual website
- Test all methods including error cases
- Ensure geocoding fallbacks work

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
- Geocoding handles failures gracefully"

# After PR is merged, the issue will automatically close
```

8. Update tracking:
```bash
./scripts/feeding-america/update_scraper_progress.py --issue {issue_num} --task scraper --status completed --file {scraper_path}
./scripts/feeding-america/update_scraper_progress.py --issue {issue_num} --task tests --status completed --file {test_path}
./scripts/feeding-america/update_scraper_progress.py --issue {issue_num} --task pr --status completed --pr <PR_NUMBER>
```

## Context from GitHub Issue:
{issue_body[:500]}

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
- Use the geocoder utility for address coordinates
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
        choices=["high", "medium", "low"],
        help="Filter by priority level (legacy - use issue priorities)",
    )
    parser.add_argument(
        "--top-priority",
        action="store_true",
        help="Only select from CRITICAL priority issues",
    )
    parser.add_argument("--state", help="Filter by state code")
    parser.add_argument("--issue", type=int, help="Use specific issue number")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute Claude with the generated prompt",
    )
    parser.add_argument(
        "--save", action="store_true", help="Save prompt to file instead of printing"
    )

    args = parser.parse_args()

    # Load tracking data
    data = load_tracking_data()

    # Get pending tasks
    pending = get_pending_tasks(data, priority=args.priority)

    # Apply state filter
    if args.state:
        pending = [
            t for t in pending if t["food_bank"].get("state") == args.state.upper()
        ]

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

    # Select task
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
        # If we have any CRITICAL tasks, always pick from those
        critical_tasks = [t for t in pending if t["issue_priority"] == "CRITICAL"]
        if critical_tasks:
            selected = random.choice(critical_tasks)
            priority = selected["issue_priority"]
            print(
                f"\n🎯 Selected a {priority} priority task from {len(critical_tasks)} available"
            )
        else:
            # Otherwise use weighted selection favoring higher priorities
            weights = [len(pending) - i for i in range(len(pending))]
            selected = random.choices(pending, weights=weights, k=1)[0]
            priority = selected["issue_priority"] or "UNRANKED"
            print(f"\n🎯 Selected a {priority} priority task")

    # Generate prompt
    prompt = generate_claude_prompt(selected)

    # Handle output
    if args.save:
        output_file = Path("outputs/claude_scraper_prompt.txt")
        output_file.write_text(prompt)
        print(f"Prompt saved to: {output_file}")
        priority_badge = {
            "CRITICAL": "🔴 CRITICAL",
            "HIGH": "🟠 HIGH",
            "MEDIUM": "🟡 MEDIUM",
            "LOW": "🟢 LOW",
        }.get(selected.get("issue_priority", ""), "⚪ UNRANKED")
        print(
            f"\nSelected: {selected['food_bank']['name']} (Issue #{selected['issue_number']})"
        )
        print(f"Priority: {priority_badge}")
    elif args.execute:
        # Execute Claude with the prompt
        fb = selected["food_bank"]
        priority_badge = {
            "CRITICAL": "🔴 CRITICAL",
            "HIGH": "🟠 HIGH",
            "MEDIUM": "🟡 MEDIUM",
            "LOW": "🟢 LOW",
        }.get(selected.get("issue_priority", ""), "⚪ UNRANKED")

        print(
            f"Implementing scraper for: {fb['name']} (Issue #{selected['issue_number']})"
        )
        print(f"Priority: {priority_badge}")
        print("Launching Claude...\n")

        # Create a more focused prompt with permission mode
        state = fb.get("state", "")
        focused_prompt = f"""Implement a scraper for {fb['name']} in {state} (GitHub issue #{selected['issue_number']}).

CRITICAL FIRST STEP: Check if this site uses Vivery/AccessFood!

1. Use Playwright to explore {fb.get('find_food_url') or fb.get('url', '')}:
- Navigate with mcp_playwright_browser_navigate
- Take snapshot with mcp_playwright_browser_snapshot
- Check for Vivery: mcp_playwright_browser_evaluate --function "() => {{ return document.body.innerHTML.includes('accessfood-widget') || document.body.innerHTML.includes('food-access-widget-cdn') || document.body.innerHTML.includes('pantrynet'); }}"

IF VIVERY IS DETECTED:
- DO NOT implement a scraper
- Close the issue: gh issue close {selected['issue_number']} --comment "This food bank uses Vivery/AccessFood and is already covered by vivery_api_scraper.py. No additional scraper is needed."
- Update tracking: ./scripts/feeding-america/update_scraper_progress.py --issue {selected['issue_number']} --task scraper --status not_needed --notes "Uses Vivery"
- STOP - no further action needed

IF VIVERY IS NOT DETECTED:
2. Create boilerplate: ./scripts/feeding-america/create_scraper_from_issue.py --issue {selected['issue_number']}

3. Implement the scraper:
- Include state in scraper name for uniqueness
- Parse location data (HTML or API)
- Geocode addresses
- Submit each location to queue

4. Test the scraper:
- Run tests: ./bouy test --pytest tests/test_scraper/test_*_scraper.py
- Test scraper in container: ./bouy exec app python3 -m app.scraper <scraper_name>
- The app container has bind-mounted code, so changes are immediate

5. Create PR: gh pr create (include "Closes #{selected['issue_number']}" in commit)

6. Update tracking with all tasks marked complete"""

        # Use Claude with appropriate flags
        cmd = ["claude", "--permission-mode", "default", focused_prompt]

        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error running Claude: {e}")
        except FileNotFoundError:
            print(
                "Claude CLI not found. Make sure 'claude' is installed and in your PATH."
            )
    else:
        # Print prompt
        print(prompt)
        print(f"\n{'='*60}")
        priority_badge = {
            "CRITICAL": "🔴 CRITICAL",
            "HIGH": "🟠 HIGH",
            "MEDIUM": "🟡 MEDIUM",
            "LOW": "🟢 LOW",
        }.get(selected.get("issue_priority", ""), "⚪ UNRANKED")
        print(
            f"Selected: {selected['food_bank']['name']} (Issue #{selected['issue_number']})"
        )
        print(f"Priority: {priority_badge}")
        print(f"To execute with Claude, run with --execute flag")


if __name__ == "__main__":
    main()
