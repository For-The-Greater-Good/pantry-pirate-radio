#!/usr/bin/env python3
"""Extract Feeding America food bank information from HTML file."""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional
from bs4 import BeautifulSoup
import urllib.parse


def extract_food_banks(html_file: Path) -> List[Dict[str, any]]:
    """Extract food bank information from the HTML file."""
    with open(html_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    soup = BeautifulSoup(content, 'html.parser')
    
    # Find all food bank entries
    food_banks = []
    results_boxes = soup.find_all('div', class_='results-box')
    
    for box in results_boxes:
        if box.get('data-orgid'):
            food_bank = extract_food_bank_info(box)
            if food_bank:
                food_banks.append(food_bank)
    
    return food_banks


def extract_food_bank_info(box) -> Optional[Dict[str, any]]:
    """Extract information from a single food bank box."""
    try:
        info = {}
        
        # Organization ID
        info['org_id'] = box.get('data-orgid')
        
        # Name
        name_elem = box.find('h3', class_='name')
        if name_elem:
            info['name'] = name_elem.text.strip()
        
        # URL slug from the link
        link_elem = box.find('a', href=re.compile(r'/find-your-local-foodbank/'))
        if link_elem:
            info['url_slug'] = link_elem['href'].split('/')[-1]
        
        # Address and phone
        p_tags = box.find_all('p')
        for p in p_tags:
            text = p.text.strip()
            if p.find('a', class_='mobile-link'):
                phone_link = p.find('a', class_='mobile-link')
                info['phone'] = phone_link.text.strip()
                # Extract address from the same paragraph
                address_text = p.get_text(separator='\n').strip()
                address_lines = [line.strip() for line in address_text.split('\n') if line.strip() and not line.strip().startswith(info['phone'])]
                if address_lines:
                    info['address'] = ', '.join(address_lines)
        
        # Website URL
        url_p = box.find('p', class_='url')
        if url_p:
            url_link = url_p.find('a')
            if url_link:
                href = url_link['href']
                # Normalize the URL
                if href.startswith('//'):
                    href = 'https:' + href
                elif not href.startswith('http'):
                    href = 'https://' + href
                info['website'] = href.rstrip('/')
        
        # Extract button links
        buttons = box.find_all('a', class_='button')
        for button in buttons:
            button_text = button.text.strip().lower()
            if 'find food' in button_text:
                info['find_food_url'] = button['href']
            elif 'volunteer' in button_text:
                info['volunteer_url'] = button['href']
            elif 'give locally' in button_text:
                info['donate_url'] = button['href']
        
        # Counties served
        counties_p = box.find('p', class_='counties')
        if counties_p:
            counties_text = counties_p.text
            if 'Counties Served:' in counties_text:
                counties = counties_text.split('Counties Served:')[1].strip()
                info['counties'] = [c.strip() for c in counties.split(',')]
        
        # State (inferred from address)
        if 'address' in info:
            # Extract state code from address
            state_match = re.search(r',\s*([A-Z]{2})\s+\d{5}', info['address'])
            if state_match:
                info['state'] = state_match.group(1)
        
        return info
    
    except Exception as e:
        print(f"Error extracting food bank info: {e}")
        return None


def check_for_vivery(food_bank: Dict[str, any]) -> bool:
    """Check if a food bank likely uses Vivery based on URL patterns."""
    vivery_patterns = [
        'pantrynet.org',
        'pantrynetwork.org',
        'findhelp.org',
        'getfood.org',
        '/pantrynet',
        'food-finder',
        'food_finder',
        'foodfinder',
        'pantry-finder',
        'pantry_finder',
        'pantryfinder'
    ]
    
    # Check find_food_url
    if 'find_food_url' in food_bank:
        url = food_bank['find_food_url'].lower()
        for pattern in vivery_patterns:
            if pattern in url:
                return True
    
    # Check website
    if 'website' in food_bank:
        url = food_bank['website'].lower()
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
        'title': title,
        'body': body,
        'labels': ['scraper', 'food-bank', food_bank.get('state', 'unknown').lower(), 'help wanted'],
        'food_bank': food_bank
    }


def main():
    """Main function to extract food banks and prepare issues."""
    # Get the HTML file from command line argument or default location
    import sys
    if len(sys.argv) > 1:
        html_file = Path(sys.argv[1])
    else:
        # Default to current directory
        html_file = Path('feeding-america-foodbanks.html')
    
    if not html_file.exists():
        print(f"Error: HTML file not found at {html_file}")
        print("Please download the HTML from: https://www.feedingamerica.org/find-your-local-foodbank/all-food-banks")
        print("Usage: python extract_feeding_america_foodbanks.py <path-to-html-file>")
        sys.exit(1)
    
    print("Extracting food banks from HTML...")
    all_food_banks = extract_food_banks(html_file)
    print(f"Found {len(all_food_banks)} total entries")
    
    # Deduplicate by org_id
    unique_food_banks = {}
    for fb in all_food_banks:
        org_id = fb.get('org_id')
        if org_id and org_id not in unique_food_banks:
            unique_food_banks[org_id] = fb
    
    food_banks = list(unique_food_banks.values())
    print(f"Found {len(food_banks)} unique food banks")
    
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
    output_dir = Path('outputs')
    output_dir.mkdir(exist_ok=True)
    
    # Save food banks data
    with open(output_dir / 'feeding_america_foodbanks.json', 'w') as f:
        json.dump(food_banks, f, indent=2)
    
    # Save issues data
    with open(output_dir / 'feeding_america_issues.json', 'w') as f:
        json.dump(issues, f, indent=2)
    
    # Save Vivery candidates
    with open(output_dir / 'vivery_candidates.json', 'w') as f:
        json.dump(vivery_food_banks, f, indent=2)
    
    # Create summary report
    summary = f"""# Feeding America Food Banks Analysis

## Summary
- Total food banks: {len(food_banks)}
- Potential Vivery integrations: {len(vivery_food_banks)}
- Need individual scrapers: {len(non_vivery_food_banks)}

## States Covered
"""
    
    # Group by state
    states = {}
    for fb in food_banks:
        state = fb.get('state', 'Unknown')
        if state not in states:
            states[state] = []
        states[state].append(fb['name'])
    
    for state in sorted(states.keys()):
        summary += f"\n### {state} ({len(states[state])} food banks)\n"
        for name in sorted(states[state]):
            summary += f"- {name}\n"
    
    with open(output_dir / 'feeding_america_summary.md', 'w') as f:
        f.write(summary)
    
    print(f"\nResults saved to {output_dir}")
    print("- feeding_america_foodbanks.json: All food bank data")
    print("- feeding_america_issues.json: GitHub issue templates")
    print("- vivery_candidates.json: Food banks potentially using Vivery")
    print("- feeding_america_summary.md: Summary report")


if __name__ == '__main__':
    main()