#!/usr/bin/env python3
"""Extract Feeding America food bank information from API."""

import json
import re
import sys
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Dict, List, Optional


def fetch_food_banks_from_api() -> List[Dict[str, any]]:
    """Fetch food bank information from Feeding America API."""
    api_url = "https://www.feedingamerica.org/ws-api/GetAllOrganizations"
    api_params = {
        "orgFields": "OrganizationID,FullName,MailAddress,ListPDOs,Drupal,URL,Phone,AgencyURL,VolunteerURL,SocialUrls,ListFipsCounty,LogoUrls,ListPDOs,list_PDO,list_LocalFindings,CountyName"
    }

    # Build URL with parameters
    url = api_url + "?" + urllib.parse.urlencode(api_params)

    print(f"Fetching data from API: {url}")

    try:
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode())
            return data.get("Organization", [])
    except Exception as e:
        print(f"Error fetching from API: {e}")
        sys.exit(1)


def extract_food_bank_info(org_data: Dict[str, any]) -> Dict[str, any]:
    """Extract information from a single food bank organization."""
    try:
        info = {}

        # Basic information
        info["org_id"] = str(org_data.get("OrganizationID", ""))
        info["name"] = org_data.get("FullName", "")

        # Extract address information
        mail_address = org_data.get("MailAddress", {})
        if mail_address:
            address_parts = []
            if mail_address.get("Address1"):
                address_parts.append(mail_address["Address1"])
            if mail_address.get("Address2"):
                address_parts.append(mail_address["Address2"])
            if mail_address.get("City") and mail_address.get("State") and mail_address.get("Zip"):
                address_parts.append(f"{mail_address['City']}, {mail_address['State']} {mail_address['Zip']}")

            info["address"] = ", ".join(address_parts)
            info["state"] = mail_address.get("State", "")
            info["latitude"] = mail_address.get("Latitude")
            info["longitude"] = mail_address.get("Longitude")

        # URLs and contact
        info["phone"] = org_data.get("Phone", "")
        info["website"] = normalize_url(org_data.get("URL", ""))
        info["find_food_url"] = normalize_url(org_data.get("AgencyURL", ""))
        info["volunteer_url"] = normalize_url(org_data.get("VolunteerURL", ""))

        # Extract URL slug from Drupal path if available
        drupal_info = org_data.get("Drupal", {})
        if drupal_info and drupal_info.get("Path"):
            info["feeding_america_path"] = drupal_info.get("Path", "")
            info["url_slug"] = extract_url_slug(drupal_info.get("Path", ""))
        else:
            info["url_slug"] = extract_url_slug(org_data.get("URL", ""))

        # Social URLs
        social_urls = org_data.get("SocialUrls", {})
        if social_urls:
            info["social_facebook"] = social_urls.get("Facebook", "")
            info["social_twitter"] = social_urls.get("Twitter", "")
            info["social_donateurl"] = social_urls.get("DonateUrl", "")
            info["social_weburl"] = social_urls.get("WebUrl", "")

        # Logo URLs
        logo_urls = org_data.get("LogoUrls", {})
        if logo_urls:
            info["logo_url"] = logo_urls.get("LogoUrl", "")
            info["logo_url_alt"] = logo_urls.get("LogoUrlAlt", "")

        # Extract counties from ListFipsCounty
        counties = []
        fips_list = org_data.get("ListFipsCounty", {}).get("LocalFindings", [])
        for fips in fips_list:
            county_name = fips.get("CountyName", "")
            state = fips.get("State", "")
            if county_name and state:
                counties.append(f"{county_name.upper()}, {state}")
        info["counties"] = counties

        # Additional Drupal fields
        if drupal_info:
            info["food_donation_link"] = normalize_url(drupal_info.get("FoodDonationLink", ""))
            info["food_drive_link"] = normalize_url(drupal_info.get("FoodDriveLink", ""))
            info["snap_link"] = normalize_url(drupal_info.get("SnapLink", ""))

        # Mark as main organization (not affiliate)
        info["is_affiliate"] = False
        info["parent_org_id"] = None

        return info

    except Exception as e:
        print(f"Error extracting food bank info: {e}")
        return None


def extract_affiliate_info(pdo_data: Dict[str, any], parent_org_id: str, parent_org_name: str) -> Dict[str, any]:
    """Extract information from an affiliate (PDO) food bank."""
    try:
        info = {}

        # Basic information
        info["org_id"] = f"{parent_org_id}-{pdo_data.get('Distorgid', '')}"
        info["name"] = pdo_data.get("Title", "")
        info["is_affiliate"] = True
        info["parent_org_id"] = parent_org_id
        info["parent_org_name"] = parent_org_name

        # Address
        address_parts = []
        if pdo_data.get("Address"):
            address_parts.append(pdo_data["Address"])
        if pdo_data.get("City") and pdo_data.get("State") and pdo_data.get("ZipCode"):
            address_parts.append(f"{pdo_data['City']}, {pdo_data['State']} {pdo_data['ZipCode']}")

        info["address"] = ", ".join(address_parts)
        info["state"] = pdo_data.get("State", "")

        # Contact
        info["website"] = normalize_url(pdo_data.get("Website", ""))

        # Director info
        director_name_parts = []
        if pdo_data.get("DirectorFirstName"):
            director_name_parts.append(pdo_data["DirectorFirstName"].strip())
        if pdo_data.get("DirectorMiddleName") and pdo_data["DirectorMiddleName"].strip():
            director_name_parts.append(pdo_data["DirectorMiddleName"].strip())
        if pdo_data.get("DirectorLastName"):
            director_name_parts.append(pdo_data["DirectorLastName"].strip())

        if director_name_parts:
            info["director_name"] = " ".join(director_name_parts)
        info["director_email"] = pdo_data.get("DirectorEmail", "")

        # Extract counties specific to this affiliate
        counties = []
        if "counties" in pdo_data and "LocalFindings" in pdo_data["counties"]:
            fips_list = pdo_data["counties"]["LocalFindings"]
            for fips in fips_list:
                county_name = fips.get("CountyName", "")
                state = fips.get("State", "")
                if county_name and state:
                    counties.append(f"{county_name.title()}, {state}")
        info["counties"] = counties

        return info

    except Exception as e:
        print(f"Error extracting affiliate info: {e}")
        return None


def normalize_url(url: str) -> str:
    """Normalize a URL to ensure it has proper protocol."""
    if not url:
        return ""

    url = url.strip()
    if url.startswith("//"):
        return "https:" + url
    elif not url.startswith("http"):
        return "https://" + url
    return url


def extract_url_slug(url: str) -> str:
    """Extract the URL slug from a Feeding America URL."""
    if not url:
        return ""

    # Look for pattern like /find-your-local-foodbank/food-bank-name
    match = re.search(r'/find-your-local-foodbank/([^/]+)', url)
    if match:
        return match.group(1)

    # Otherwise try to get the last part of the path
    parsed = urllib.parse.urlparse(url)
    path_parts = parsed.path.strip('/').split('/')
    if path_parts:
        return path_parts[-1]

    return ""


def check_for_vivery(food_bank: Dict[str, any]) -> bool:
    """Check if a food bank likely uses Vivery based on URL patterns."""
    vivery_patterns = [
        "pantrynet.org",
        "pantrynetwork.org",
        "findhelp.org",
        "getfood.org",
        "/pantrynet",
        "food-finder",
        "food_finder",
        "foodfinder",
        "pantry-finder",
        "pantry_finder",
        "pantryfinder",
    ]

    # Check find_food_url
    if "find_food_url" in food_bank:
        url = food_bank["find_food_url"].lower()
        for pattern in vivery_patterns:
            if pattern in url:
                return True

    # Check website
    if "website" in food_bank:
        url = food_bank["website"].lower()
        for pattern in vivery_patterns:
            if pattern in url:
                return True

    return False


def generate_github_issue(food_bank: Dict[str, any]) -> Dict[str, any]:
    """Generate GitHub issue content for a food bank."""
    title = f"Implement scraper for {food_bank['name']}"

    body = f"""## Food Bank Information

**Name:** {food_bank['name']}
**State:** {food_bank.get('state', 'Unknown')}
**Website:** {food_bank.get('website', 'N/A')}
**Find Food URL:** {food_bank.get('find_food_url', 'N/A')}
**Address:** {food_bank.get('address', 'N/A')}
**Phone:** {food_bank.get('phone', 'N/A')}

### Service Area
**Counties Served:** {', '.join(food_bank.get('counties', ['Unknown']))}

## ⚠️ IMPORTANT: Check for Vivery First

Before implementing a custom scraper, check if this food bank uses Vivery:

1. Visit the Find Food URL above
2. Look for these Vivery indicators:
   - Embedded iframes from `pantrynet.org`, `vivery.com`, or similar domains
   - "Powered by Vivery" or "Powered by PantryNet" branding
   - Map interface with pins showing food locations
   - Search interface with filters for food types, days, etc.
   - URLs containing patterns like `pantry-finder`, `food-finder`, `pantrynet`

**If Vivery is detected:**
- Close this issue with comment: "Covered by vivery_api_scraper.py"
- Add the food bank name to the Vivery users list

## Implementation Guide

If this food bank does NOT use Vivery, implement a custom scraper:

### 1. Create Scraper File
Create `app/scraper/{food_bank.get('url_slug', 'foodbank').replace('-', '_')}_scraper.py`

### 2. Basic Structure
```python
from app.scraper.utils import ScraperJob, get_scraper_headers

class {food_bank['name'].replace(' ', '').replace(',', '').replace('.', '')}Scraper(ScraperJob):
    def __init__(self):
        super().__init__(scraper_id="{food_bank.get('url_slug', 'foodbank')}")

    async def scrape(self) -> str:
        # Your implementation here
        pass
```

### 3. Key Implementation Steps

1. **Analyze the food finder page** at the Find Food URL
2. **Determine the data source type**:
   - Static HTML with listings
   - JavaScript-rendered content (may need Selenium)
   - API endpoints (check Network tab in browser)
   - Map-based interface with data endpoints
   - PDF downloads

3. **Extract food resource data** including:
   - Organization/pantry name
   - Complete address
   - Phone number (if available)
   - Hours of operation
   - Services offered (food pantry, meal site, etc.)
   - Eligibility requirements
   - Additional notes or special instructions

4. **Use provided utilities**:
   - `GeocoderUtils` for converting addresses to coordinates
   - `get_scraper_headers()` for HTTP requests
   - Grid search if needed: `self.utils.get_state_grid_points("{food_bank.get('state', 'US')}")`

5. **Submit data to processing queue**:
   ```python
   for location in locations:
       json_data = json.dumps(location)
       self.submit_to_queue(json_data)
   ```

### 4. Testing
```bash
# Run the scraper
python -m app.scraper {food_bank.get('url_slug', 'foodbank').replace('-', '_')}

# Run in test mode
python -m app.scraper.test_scrapers {food_bank.get('url_slug', 'foodbank').replace('-', '_')}
```

## Essential Documentation

### Scraper Development
- **Implementation Guide**: `docs/scrapers.md` - Comprehensive guide with examples
- **Base Classes**: `app/scraper/utils.py` - ScraperJob, GeocoderUtils, ScraperUtils
- **Example Scrapers**:
  - `app/scraper/nyc_efap_programs_scraper.py` - HTML table scraping
  - `app/scraper/food_helpline_org_scraper.py` - ZIP code search example
  - `app/scraper/vivery_api_scraper.py` - API integration example

### Utilities Available
- **ScraperJob**: Base class providing scraper lifecycle management
- **GeocoderUtils**: Convert addresses to lat/lon coordinates
- **get_scraper_headers()**: Standard headers for HTTP requests
- **Grid Search**: For map-based searches use `get_state_grid_points()`

### Data Format
Scraped data should be formatted as JSON with these fields (when available):
```json
{{
    "name": "Food Pantry Name",
    "address": "123 Main St, City, State ZIP",
    "phone": "555-123-4567",
    "hours": "Mon-Fri 9am-5pm",
    "services": ["food pantry", "hot meals"],
    "eligibility": "Must live in county",
    "notes": "Bring ID and proof of address",
    "latitude": 40.7128,
    "longitude": -74.0060
}}
```

## Notes
- Some food banks may have multiple locations/programs
- Check if the food bank has a separate mobile food schedule
- Look for seasonal or temporary distribution sites
- Consider accessibility information if available
"""

    return {
        "title": title,
        "body": body,
        "labels": [
            "scraper",
            "food-bank",
            food_bank.get("state", "unknown").lower(),
            "help wanted",
        ],
        "food_bank": food_bank,
    }


def main():
    """Main function to extract food banks and prepare issues."""
    print("Fetching food banks from Feeding America API...")
    organizations = fetch_food_banks_from_api()
    print(f"Found {len(organizations)} organizations from API")

    # Process all food banks (main and affiliates)
    all_food_banks = []

    for org in organizations:
        # Extract main food bank
        main_fb = extract_food_bank_info(org)
        if main_fb:
            all_food_banks.append(main_fb)

            # Extract affiliate food banks (PDOs)
            pdos = org.get("ListPDOs", {}).get("PDO", [])
            if isinstance(pdos, dict):
                pdos = [pdos]  # Convert single PDO to list

            for pdo in pdos:
                affiliate = extract_affiliate_info(
                    pdo,
                    main_fb["org_id"],
                    main_fb["name"]
                )
                if affiliate:
                    all_food_banks.append(affiliate)

    print(f"Total food banks extracted: {len(all_food_banks)}")
    print(f"  - Main food banks: {len([fb for fb in all_food_banks if not fb.get('is_affiliate', False)])}")
    print(f"  - Affiliate food banks: {len([fb for fb in all_food_banks if fb.get('is_affiliate', False)])}")

    food_banks = all_food_banks

    # Categorize food banks
    vivery_food_banks = []
    non_vivery_food_banks = []

    for fb in food_banks:
        if check_for_vivery(fb):
            vivery_food_banks.append(fb)
        else:
            non_vivery_food_banks.append(fb)

    print(f"\nPotential Vivery integrations: {len(vivery_food_banks)}")
    print(f"Non-Vivery food banks: {len(non_vivery_food_banks)}")

    # Generate issues
    issues = []
    for fb in food_banks:
        issue = generate_github_issue(fb)
        issues.append(issue)

    # Save results - use relative path from project root
    output_dir = Path("outputs")
    output_dir.mkdir(exist_ok=True)

    # Save food banks data
    with open(output_dir / "feeding_america_foodbanks.json", "w") as f:
        json.dump(food_banks, f, indent=2)

    # Save issues data
    with open(output_dir / "feeding_america_issues.json", "w") as f:
        json.dump(issues, f, indent=2)

    # Save Vivery candidates
    with open(output_dir / "vivery_candidates.json", "w") as f:
        json.dump(vivery_food_banks, f, indent=2)

    # Create summary report
    main_food_banks = [fb for fb in food_banks if not fb.get('is_affiliate', False)]
    affiliate_food_banks = [fb for fb in food_banks if fb.get('is_affiliate', False)]

    summary = f"""# Feeding America Food Banks Analysis

## Summary
- Total food banks: {len(food_banks)}
  - Main food banks: {len(main_food_banks)}
  - Affiliate food banks: {len(affiliate_food_banks)}
- Potential Vivery integrations: {len(vivery_food_banks)}
- Need individual scrapers: {len(non_vivery_food_banks)}

## States Covered
"""

    # Group by state
    states = {}
    for fb in food_banks:
        state = fb.get("state", "Unknown")
        if state not in states:
            states[state] = []
        states[state].append(fb["name"])

    for state in sorted(states.keys()):
        summary += f"\n### {state} ({len(states[state])} food banks)\n"
        for name in sorted(states[state]):
            summary += f"- {name}\n"

    with open(output_dir / "feeding_america_summary.md", "w") as f:
        f.write(summary)

    print(f"\nResults saved to {output_dir}")
    print("- feeding_america_foodbanks.json: All food bank data")
    print("- feeding_america_issues.json: GitHub issue templates")
    print("- vivery_candidates.json: Food banks potentially using Vivery")
    print("- feeding_america_summary.md: Summary report")


if __name__ == "__main__":
    main()
