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


def load_tracking_data() -> Dict[str, Any]:
    """Load tracking data to get food bank information.
    
    Returns:
        Tracking data dictionary
    """
    tracking_file = Path("outputs/scraper_development_tracking.json")
    if not tracking_file.exists():
        print(f"Error: Tracking file not found at {tracking_file}")
        print("Run generate_scraper_tracking.py first.")
        sys.exit(1)
    
    with open(tracking_file) as f:
        return json.load(f)


def find_food_bank_by_issue(data: Dict[str, Any], issue_number: int) -> Optional[Dict[str, Any]]:
    """Find food bank data by issue number.
    
    Args:
        data: Tracking data
        issue_number: GitHub issue number
        
    Returns:
        Food bank data or None
    """
    for fb in data["food_banks"]:
        if fb["issue_number"] == issue_number:
            return fb
    return None


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
    template_path = Path(f"templates/{template_name}")
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


def get_state_coordinates(state: str) -> tuple[float, float]:
    """Get approximate coordinates for a US state.
    
    Args:
        state: Two-letter state code
        
    Returns:
        Tuple of (latitude, longitude)
    """
    # Approximate center coordinates for US states
    state_coords = {
        "AL": (32.806671, -86.791130), "AK": (61.370716, -152.404419),
        "AZ": (33.729759, -111.431221), "AR": (34.969704, -92.373123),
        "CA": (36.116203, -119.681564), "CO": (39.059811, -105.311104),
        "CT": (41.597782, -72.755371), "DE": (39.318523, -75.507141),
        "FL": (27.766279, -81.686783), "GA": (33.040619, -83.643074),
        "HI": (21.094318, -157.498337), "ID": (44.240459, -114.478828),
        "IL": (40.349457, -88.986137), "IN": (39.849426, -86.258278),
        "IA": (42.011539, -93.210526), "KS": (38.526600, -96.726486),
        "KY": (37.668140, -84.670067), "LA": (31.169546, -91.867805),
        "ME": (44.693947, -69.381927), "MD": (39.063946, -76.802101),
        "MA": (42.230171, -71.530106), "MI": (43.326618, -84.536095),
        "MN": (45.694454, -93.900192), "MS": (32.741646, -89.678696),
        "MO": (38.456085, -92.288368), "MT": (46.921925, -110.454353),
        "NE": (41.125370, -98.268082), "NV": (38.313515, -117.055374),
        "NH": (43.452492, -71.563896), "NJ": (40.298904, -74.521011),
        "NM": (34.840515, -106.248482), "NY": (42.165726, -74.948051),
        "NC": (35.630066, -79.806419), "ND": (47.528912, -99.784012),
        "OH": (40.388783, -82.764915), "OK": (35.565342, -96.928917),
        "OR": (44.572021, -122.070938), "PA": (40.590752, -77.209755),
        "RI": (41.680893, -71.511780), "SC": (33.856892, -80.945007),
        "SD": (44.299782, -99.438828), "TN": (35.747845, -86.692345),
        "TX": (31.054487, -97.563461), "UT": (40.150032, -111.862434),
        "VT": (44.045876, -72.710686), "VA": (37.769337, -78.169968),
        "WA": (47.400902, -121.490494), "WV": (38.491226, -80.954456),
        "WI": (44.268543, -89.616508), "WY": (42.755966, -107.302490),
        "DC": (38.897438, -77.026817), "PR": (18.220833, -66.590149),
    }
    
    return state_coords.get(state.upper(), (39.8283, -98.5795))  # Default to US center


def create_scraper_files(food_bank: Dict[str, Any], dry_run: bool = False) -> None:
    """Create scraper and test files from templates.
    
    Args:
        food_bank: Food bank data from tracking
        dry_run: If True, show what would be created without creating files
    """
    # Extract food bank information
    fb_data = food_bank["food_bank"]
    name = fb_data["name"]
    state = fb_data.get("state", "US")
    url = fb_data.get("find_food_url") or fb_data.get("url", "https://example.com")
    
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
    
    # Get state coordinates
    lat, lon = get_state_coordinates(state)
    
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
    
    # Update geocoder coordinates in template
    state_coords_line = f'                "{state}": ({lat:.6f}, {lon:.6f}),'
    
    print(f"\nCreating scraper for: {name}")
    print(f"  Class name: {class_name}")
    print(f"  Module name: {module_name}")
    print(f"  Scraper ID: {scraper_id}")
    print(f"  State: {state}")
    print(f"  URL: {url}")
    print(f"  Coordinates: {lat:.6f}, {lon:.6f}")
    
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
    
    # Update coordinates in scraper
    scraper_content = scraper_content.replace(
        '                "' + state + '": (40.0, -75.0),  # Replace with actual coordinates',
        state_coords_line + '  # ' + name + ' region'
    )
    
    # Create directories if needed
    scraper_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write files
    scraper_path.write_text(scraper_content)
    test_path.write_text(test_content)
    
    print(f"\nFiles created:")
    print(f"  ✓ {scraper_path}")
    print(f"  ✓ {test_path}")
    
    # Update tracking to mark scraper as in progress
    update_cmd = [
        "python3", "scripts/feeding-america/update_scraper_progress.py",
        "--issue", str(food_bank["issue_number"]),
        "--task", "scraper",
        "--status", "in_progress",
        "--file", str(scraper_path)
    ]
    
    try:
        subprocess.run(update_cmd, check=True, capture_output=True)
        print(f"\n✓ Updated tracking: scraper marked as in_progress")
    except subprocess.CalledProcessError as e:
        print(f"\nWarning: Failed to update tracking: {e}")
    
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
    
    # Load tracking data
    data = load_tracking_data()
    
    # Find food bank
    food_bank = find_food_bank_by_issue(data, args.issue)
    if not food_bank:
        print(f"Error: No food bank found for issue #{args.issue}")
        sys.exit(1)
    
    # Create files
    create_scraper_files(food_bank, dry_run=args.dry_run)


if __name__ == "__main__":
    main()