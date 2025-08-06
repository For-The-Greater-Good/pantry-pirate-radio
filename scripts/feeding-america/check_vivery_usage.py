#!/usr/bin/env python3
"""Check which Feeding America food banks actually use Vivery/PantryNet."""

import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, List, Optional
import re
import ssl

# Create SSL context that doesn't verify certificates (for testing)
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE


def check_vivery_indicators(html_content: str, url: str) -> Dict[str, any]:
    """Check if HTML content contains Vivery/PantryNet/AccessFood indicators.

    Args:
        html_content: HTML content to check
        url: URL being checked (for context)

    Returns:
        Dictionary with check results
    """
    results = {
        "url": url,
        "is_vivery": False,
        "indicators": [],
        "iframe_src": None,
        "powered_by": None,
        "script_includes": [],
        "api_calls": [],
        "widget_found": False
    }

    # Check for AccessFood widget (most common current implementation)
    widget_pattern = r'<div[^>]*class=["\'][^"\']*accessfood-widget[^"\']*["\']'
    widget_matches = re.findall(widget_pattern, html_content, re.IGNORECASE)
    if widget_matches:
        results["is_vivery"] = True
        results["widget_found"] = True
        results["indicators"].append("AccessFood widget div found")

        # Look for map ID
        map_id_pattern = r'data-map=["\']([^"\']+)["\']'
        map_id_matches = re.findall(map_id_pattern, html_content)
        if map_id_matches:
            results["indicators"].append(f"Widget map ID: {map_id_matches[0]}")

    # Check for AccessFood CDN resources
    cdn_pattern = r'(?:food-access-widget-cdn\.azureedge\.net|accessfood-widget)'
    cdn_matches = re.findall(cdn_pattern, html_content, re.IGNORECASE)
    if cdn_matches:
        results["is_vivery"] = True
        results["indicators"].append("AccessFood CDN resources detected")

    # Check for iframes
    iframe_pattern = r'<iframe[^>]*src=["\'](https?://[^"\']*(?:pantrynet\.org|vivery\.com|accessfood\.org)[^"\']*)["\']'
    iframe_matches = re.findall(iframe_pattern, html_content, re.IGNORECASE)
    if iframe_matches:
        results["is_vivery"] = True
        results["iframe_src"] = iframe_matches[0]
        results["indicators"].append(f"Iframe from: {iframe_matches[0]}")

    # Check for "Powered by" text
    powered_pattern = r'powered\s+by\s+(?:vivery|pantrynet|accessfood)'
    powered_matches = re.findall(powered_pattern, html_content, re.IGNORECASE)
    if powered_matches:
        results["is_vivery"] = True
        results["powered_by"] = powered_matches[0]
        results["indicators"].append(f"Powered by text: {powered_matches[0]}")

    # Check for script includes
    script_pattern = r'<script[^>]*src=["\'](https?://[^"\']*(?:pantrynet\.org|vivery\.com|accessfood\.org|food-access-widget)[^"\']*)["\']'
    script_matches = re.findall(script_pattern, html_content, re.IGNORECASE)
    if script_matches:
        results["is_vivery"] = True
        results["script_includes"] = script_matches
        results["indicators"].extend([f"Script include: {s}" for s in script_matches])

    # Check for API references in JavaScript
    api_pattern = r'(?:api\.accessfood\.org|pantrynet\.org/api|vivery\.com/api)'
    api_matches = re.findall(api_pattern, html_content, re.IGNORECASE)
    if api_matches:
        results["is_vivery"] = True
        results["api_calls"] = list(set(api_matches))
        results["indicators"].extend([f"API reference: {a}" for a in set(api_matches)])

    # Check for specific Vivery/PantryNet/AccessFood class names or IDs
    vivery_classes = r'(?:class|id)=["\']*[^"\']*(?:vivery|pantrynet|accessfood|pn-|vv-)[^"\']*["\']*'
    class_matches = re.findall(vivery_classes, html_content, re.IGNORECASE)
    if class_matches and not results["widget_found"]:  # Don't duplicate widget detection
        results["is_vivery"] = True
        results["indicators"].extend([f"Vivery-related class/ID: {c}" for c in class_matches[:3]])

    return results


def fetch_url(url: str, timeout: int = 10) -> Optional[str]:
    """Fetch content from a URL.

    Args:
        url: URL to fetch
        timeout: Request timeout in seconds

    Returns:
        HTML content or None if error
    """
    if not url:
        return None

    try:
        # Add headers to avoid bot detection
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        request = urllib.request.Request(url, headers=headers)

        with urllib.request.urlopen(request, timeout=timeout, context=ssl_context) as response:
            return response.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None


def main():
    """Main function to check Vivery usage."""
    # Load food bank data
    foodbanks_file = Path("outputs/feeding_america_foodbanks.json")
    with open(foodbanks_file) as f:
        food_banks = json.load(f)

    print(f"Loaded {len(food_banks)} food banks")

    # Track results
    vivery_users = []
    non_vivery = []
    no_url = []
    errors = []

    # Check each food bank
    for i, fb in enumerate(food_banks):
        name = fb.get("name", "Unknown")
        org_id = fb.get("org_id", "")
        find_food_url = fb.get("find_food_url", "")

        print(f"\n[{i+1}/{len(food_banks)}] Checking: {name} (ID: {org_id})")

        if not find_food_url:
            print("  → No find_food_url")
            no_url.append(fb)
            continue

        print(f"  URL: {find_food_url}")

        # Fetch and check the page
        html_content = fetch_url(find_food_url)
        if html_content is None:
            print("  → Error fetching page")
            errors.append(fb)
            continue

        # Check for Vivery indicators
        check_results = check_vivery_indicators(html_content, find_food_url)

        if check_results["is_vivery"]:
            print("  → ✓ VIVERY DETECTED!")
            for indicator in check_results["indicators"]:
                print(f"     - {indicator}")
            vivery_users.append({**fb, "vivery_check": check_results})
        else:
            print("  → Not using Vivery")
            non_vivery.append(fb)

        # Rate limiting
        time.sleep(0.5)

        # Save intermediate results every 10 checks
        if (i + 1) % 10 == 0:
            save_results(vivery_users, non_vivery, no_url, errors)

    # Save final results
    save_results(vivery_users, non_vivery, no_url, errors)

    # Print summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Total food banks checked: {len(food_banks)}")
    print(f"Vivery users detected: {len(vivery_users)}")
    print(f"Not using Vivery: {len(non_vivery)}")
    print(f"No find_food_url: {len(no_url)}")
    print(f"Errors: {len(errors)}")

    if vivery_users:
        print("\nVIVERY USERS:")
        for fb in vivery_users:
            print(f"- {fb['name']} ({fb['org_id']})")
            if 'vivery_check' in fb:
                for indicator in fb['vivery_check']['indicators'][:2]:
                    print(f"  → {indicator}")


def save_results(vivery_users: List[Dict], non_vivery: List[Dict],
                 no_url: List[Dict], errors: List[Dict]) -> None:
    """Save intermediate results to files."""
    output_dir = Path("outputs")

    # Save Vivery users
    with open(output_dir / "vivery_confirmed_users.json", "w") as f:
        json.dump(vivery_users, f, indent=2)

    # Save summary
    summary = {
        "total_checked": len(vivery_users) + len(non_vivery) + len(no_url) + len(errors),
        "vivery_users": len(vivery_users),
        "non_vivery": len(non_vivery),
        "no_url": len(no_url),
        "errors": len(errors),
        "vivery_user_ids": [fb['org_id'] for fb in vivery_users],
        "vivery_user_names": [fb['name'] for fb in vivery_users]
    }

    with open(output_dir / "vivery_check_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nSaved results: {len(vivery_users)} Vivery users found so far")


if __name__ == "__main__":
    main()