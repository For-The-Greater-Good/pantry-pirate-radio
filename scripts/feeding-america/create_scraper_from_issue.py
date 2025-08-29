#!/usr/bin/env python3
"""Create scraper boilerplate from GitHub issue using templates.

This script generates the initial scraper and test files from templates,
providing a starting point for manual customization.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, Optional


def fetch_issue_details(issue_number: int) -> Optional[Dict[str, Any]]:
    """Fetch issue details from GitHub.
    
    Args:
        issue_number: GitHub issue number
    
    Returns:
        Issue dictionary or None if not found
    """
    cmd = [
        "gh",
        "issue",
        "view",
        str(issue_number),
        "--repo",
        "For-The-Greater-Good/pantry-pirate-radio",
        "--json",
        "number,title,body,labels"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Error fetching issue #{issue_number}: {e}")
        return None


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
    """Sanitize name for use in Python identifiers.
    
    Args:
        name: Original name
    
    Returns:
        Sanitized name
    """
    # Remove special characters and replace with underscores
    name = re.sub(r'[^\w\s]', '', name)
    # Replace spaces with underscores
    name = name.replace(' ', '_')
    # Remove consecutive underscores
    name = re.sub(r'_+', '_', name)
    # Convert to lowercase
    name = name.lower()
    # Remove trailing underscores
    name = name.strip('_')
    return name


def create_class_name(name: str) -> str:
    """Create PascalCase class name from food bank name.
    
    Args:
        name: Food bank name
    
    Returns:
        PascalCase class name
    """
    # Remove special characters
    name = re.sub(r'[^\w\s]', '', name)
    # Split into words and capitalize each
    words = name.split()
    return ''.join(word.capitalize() for word in words)


def load_template(template_name: str) -> str:
    """Load Jinja2 template content.
    
    Args:
        template_name: Template filename
    
    Returns:
        Template content
    """
    # Templates are now in scripts/feeding-america/templates/
    template_path = Path(f"scripts/feeding-america/templates/{template_name}")
    if not template_path.exists():
        print(f"Error: Template not found at {template_path}")
        sys.exit(1)
    
    return template_path.read_text()


def render_template(template_content: str, context: Dict[str, Any]) -> str:
    """Render template with context (simple string replacement).
    
    Args:
        template_content: Template content
        context: Variables to replace
    
    Returns:
        Rendered content
    """
    # Simple template rendering without Jinja2 dependency
    content = template_content
    for key, value in context.items():
        content = content.replace(f"{{{{ {key} }}}}", str(value))
    return content


def create_scraper_files(food_bank_info: Dict[str, Any], issue_number: int, dry_run: bool = False) -> None:
    """Create scraper and test files from templates.
    
    Args:
        food_bank_info: Food bank data parsed from issue
        issue_number: GitHub issue number
        dry_run: If True, show what would be created without creating files
    """
    # Extract food bank information
    name = food_bank_info["name"]
    state = food_bank_info.get("state", "US")
    url = food_bank_info.get("find_food_url") or food_bank_info.get("url", "https://example.com")
    
    # Generate names - include state for uniqueness
    if state and state != "US" and state not in name:
        full_name = f"{name} {state}"
        sanitized_name = sanitize_name(full_name)
        class_name = create_class_name(name) + state
    else:
        sanitized_name = sanitize_name(name)
        class_name = create_class_name(name)
    
    scraper_id = sanitized_name
    module_name = sanitized_name
    
    # Create context for template rendering
    context = {
        "food_bank_name": name,
        "class_name": class_name,
        "scraper_id": scraper_id,
        "module_name": module_name,
        "food_bank_url": url,
        "state": state,
        "state|lower": state.lower() if state else "us",
    }
    
    print(f"\nCreating scraper for: {name}")
    print(f"  Class name: {class_name}")
    print(f"  Module name: {module_name}")
    print(f"  Scraper ID: {scraper_id}")
    print(f"  State: {state}")
    print(f"  URL: {url}")
    
    # Define file paths
    scraper_path = Path(f"app/scraper/{module_name}_scraper.py")
    test_path = Path(f"tests/test_scraper/test_{module_name}_scraper.py")
    
    if dry_run:
        print(f"\n[DRY RUN] Would create:")
        print(f"  - {scraper_path}")
        print(f"  - {test_path}")
        return
    
    # Check if files already exist
    if scraper_path.exists():
        print(f"\nWarning: Scraper already exists at {scraper_path}")
        response = input("Overwrite? (y/N): ")
        if response.lower() != 'y':
            print("Skipping scraper creation.")
            return
    
    # Load and render templates
    scraper_template = load_template("scraper_template.py.jinja2")
    test_template = load_template("test_scraper_template.py.jinja2")
    
    # Render templates
    scraper_content = render_template(scraper_template, context)
    test_content = render_template(test_template, context)
    
    # Create directories if needed
    scraper_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write files
    scraper_path.write_text(scraper_content)
    test_path.write_text(test_content)
    
    print(f"\nFiles created:")
    print(f"  ✓ {scraper_path}")
    print(f"  ✓ {test_path}")
    
    # Update issue status with in-progress label
    update_cmd = [
        "gh", "issue", "edit", str(issue_number),
        "--add-label", "in-progress",
        "--repo", "For-The-Greater-Good/pantry-pirate-radio"
    ]
    
    try:
        subprocess.run(update_cmd, check=True, capture_output=True)
        print(f"\n✓ Added 'in-progress' label to issue #{issue_number}")
    except subprocess.CalledProcessError as e:
        print(f"\nWarning: Failed to update issue label: {e}")
    
    # Provide next steps
    print(f"\nNext steps:")
    print(f"1. Visit {url} to explore the website")
    print(f"2. Identify how location data is presented:")
    print(f"   - Static HTML (tables, lists, divs)")
    print(f"   - JavaScript-rendered content")
    print(f"   - API endpoints (check Network tab)")
    print(f"   - Third-party services (Vivery, etc.)")
    print(f"3. Update {scraper_path} based on findings")
    print(f"4. Run tests: ./bouy test --pytest {test_path}")
    print(f"5. Test scraper: ./bouy scraper-test {scraper_id}")
    print(f"\n⚠️  IMPORTANT: Geocoding is now handled by the validator service")
    print(f"   - Do NOT add geocoding logic to the scraper")
    print(f"   - Lat/long is optional - include if available, otherwise leave as None")


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Create scraper boilerplate from GitHub issue"
    )
    parser.add_argument("--issue", type=int, required=True,
                       help="GitHub issue number")
    parser.add_argument("--dry-run", action="store_true",
                       help="Show what would be created without creating files")
    
    args = parser.parse_args()
    
    # Fetch issue details from GitHub
    print(f"Fetching issue #{args.issue} from GitHub...")
    issue = fetch_issue_details(args.issue)
    
    if not issue:
        print(f"Error: Could not fetch issue #{args.issue}")
        sys.exit(1)
    
    # Check if issue has scraper label
    labels = [label["name"] for label in issue.get("labels", [])]
    if "scraper" not in labels:
        print(f"Warning: Issue #{args.issue} does not have 'scraper' label")
        response = input("Continue anyway? (y/N): ")
        if response.lower() != 'y':
            print("Aborting.")
            sys.exit(0)
    
    # Parse food bank information from issue body
    food_bank_info = parse_issue_body(issue.get("body", ""))
    
    if not food_bank_info["name"]:
        print("Error: Could not extract food bank name from issue body")
        print("Issue body should contain 'Name: <food bank name>'")
        sys.exit(1)
    
    # Create scraper files
    create_scraper_files(food_bank_info, args.issue, dry_run=args.dry_run)


if __name__ == "__main__":
    main()