# Common Scraper Patterns Quick Reference

This guide provides quick reference patterns for implementing scrapers based on common website architectures.

## Table of Contents
- [Website Analysis](#website-analysis)
- [HTML Scraping Patterns](#html-scraping-patterns)
- [API Scraping Patterns](#api-scraping-patterns)
- [JavaScript-Rendered Sites](#javascript-rendered-sites)
- [Common Third-Party Services](#common-third-party-services)
- [Geocoding Patterns](#geocoding-patterns)
- [Testing Patterns](#testing-patterns)

## Website Analysis

### Initial Exploration Checklist
1. **Visit the find food URL** in browser
2. **View Page Source** - Check if data is in initial HTML
3. **Open DevTools Network Tab** - Look for API calls
4. **Check for JavaScript frameworks** - React, Vue, Angular indicators
5. **Look for third-party widgets** - Vivery, Store Locator Plus, etc.
6. **Test search functionality** - Note parameters and responses

### Quick Detection Commands
```bash
# Check if site uses known services
curl -s "URL" | grep -E "(vivery|pantrynet|accessfood|food-access-widget)"

# Look for API endpoints
curl -s "URL" | grep -E "(api\.|/api/|\.json|ajax|xhr)"

# Check for store locator plugins
curl -s "URL" | grep -E "(store-locator|storelocator|wp-store-locator)"
```

## HTML Scraping Patterns

### Table-Based Locations
```python
def parse_html(self, html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    locations = []
    
    # Find table
    table = soup.find("table", class_="locations")  # or id="pantries"
    if not table:
        return locations
    
    # Parse rows
    rows = table.find_all("tr")[1:]  # Skip header
    for row in rows:
        cells = row.find_all("td")
        if len(cells) >= 3:
            location = {
                "name": cells[0].get_text(strip=True),
                "address": cells[1].get_text(strip=True),
                "phone": cells[2].get_text(strip=True),
                # Extract more fields as needed
            }
            locations.append(location)
    
    return locations
```

### Card/Div-Based Locations
```python
def parse_html(self, html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    locations = []
    
    # Find location cards
    cards = soup.find_all("div", class_="location-card")
    for card in cards:
        location = {
            "name": card.find("h3", class_="name").get_text(strip=True),
            "address": card.find("p", class_="address").get_text(strip=True),
            "phone": card.find("span", class_="phone").get_text(strip=True),
            # Handle missing elements gracefully
            "hours": card.find("div", class_="hours").get_text(strip=True) if card.find("div", class_="hours") else "",
        }
        locations.append(location)
    
    return locations
```

### List-Based Locations
```python
def parse_html(self, html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    locations = []
    
    # Find list container
    list_container = soup.find("ul", class_="pantry-list")
    if list_container:
        for item in list_container.find_all("li"):
            # Parse structured data within list item
            name_elem = item.find("strong") or item.find("b")
            location = {
                "name": name_elem.get_text(strip=True) if name_elem else "",
                "details": item.get_text(strip=True),
            }
            # Extract address, phone from details text
            locations.append(location)
    
    return locations
```

## API Scraping Patterns

### Direct API Endpoint
```python
async def scrape(self) -> str:
    # Fetch from API
    response = await self.fetch_api_data("locations", params={"type": "food_pantry"})
    locations = self.process_api_response(response)
    
    # Process and submit...
```

### Paginated API
```python
async def fetch_all_pages(self) -> List[Dict[str, Any]]:
    all_locations = []
    page = 1
    
    while True:
        response = await self.fetch_api_data(
            "search",
            params={"page": page, "per_page": 100}
        )
        
        locations = response.get("results", [])
        if not locations:
            break
            
        all_locations.extend(locations)
        
        # Check for more pages
        if len(locations) < 100 or page >= response.get("total_pages", 1):
            break
            
        page += 1
        await asyncio.sleep(self.request_delay)
    
    return all_locations
```

### Geographic Grid Search
```python
async def scrape(self) -> str:
    # Get grid points for state
    grid_points = self.utils.get_state_grid_points(self.state.lower())
    
    if self.test_mode:
        grid_points = grid_points[:3]
    
    all_locations = []
    
    for i, point in enumerate(grid_points):
        if i > 0:
            await asyncio.sleep(self.request_delay)
        
        # Search around grid point
        response = await self.fetch_api_data(
            "search",
            params={
                "lat": point.lat,
                "lng": point.lng,
                "radius": 50,  # miles
                "type": "food_pantry"
            }
        )
        
        locations = self.process_api_response(response)
        all_locations.extend(locations)
    
    # Deduplicate...
```

### WordPress/WP Store Locator
```python
# Common WordPress store locator endpoint
self.url = "https://example.com/wp-admin/admin-ajax.php"

async def fetch_locations(self) -> List[Dict[str, Any]]:
    # WordPress AJAX parameters
    params = {
        "action": "store_locator",  # or "wpsl_store_search"
        "lat": 40.0,
        "lng": -75.0,
        "radius": 100
    }
    
    # May need to be POST instead of GET
    async with httpx.AsyncClient() as client:
        response = await client.post(self.url, data=params)
        return response.json()
```

## JavaScript-Rendered Sites

### Detection Signs
- View source shows minimal HTML
- Data appears after page load
- React/Vue/Angular indicators in HTML
- API calls in Network tab after page load

### Handling Options
1. **Find the API** - Check Network tab for XHR/Fetch requests
2. **Use browser automation** - Last resort, much slower
3. **Check for static data** - Sometimes embedded in script tags

### Extracting from Script Tags
```python
def extract_json_from_scripts(self, html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    
    # Look for JSON data in script tags
    for script in soup.find_all("script"):
        text = script.string or ""
        
        # Common patterns
        patterns = [
            r'window\.__INITIAL_STATE__\s*=\s*({.*?});',
            r'var\s+locations\s*=\s*(\[.*?\]);',
            r'data:\s*({.*?}),',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(1))
                    # Extract locations from data structure
                    return self.extract_locations_from_data(data)
                except:
                    continue
    
    return []
```

## Common Third-Party Services

### Vivery/AccessFood (Already covered by vivery_api_scraper.py)
Detection:
```python
# Check HTML for indicators
if any(x in html for x in ["accessfood-widget", "food-access-widget-cdn", "pantrynet.org"]):
    print("This food bank uses Vivery - already covered by vivery_api_scraper.py")
```

### Store Locator Plus
```python
# Common endpoint
url = "https://example.com/wp-admin/admin-ajax.php"
params = {
    "action": "csl_ajax_onload",
    "address": "",
    "formdata": "addressInput=",
    "lat": 40.0,
    "lng": -75.0,
    "radius": 100
}
```

### Google Maps Embed
```python
# Look for embedded map data
map_data_pattern = r'maps\.google\.com/maps\?.*?!3d([-\d.]+)!4d([-\d.]+)'
# Extract coordinates from Google Maps URLs
```

## Geocoding Patterns

### Basic Geocoding with Fallback
```python
# In scraper
for location in locations:
    if location.get("address"):
        try:
            lat, lon = self.geocoder.geocode_address(
                address=location["address"],
                state=location.get("state", self.state)
            )
            location["latitude"] = lat
            location["longitude"] = lon
        except ValueError as e:
            logger.warning(f"Geocoding failed: {e}")
            # Use state default with offset
            lat, lon = self.geocoder.get_default_coordinates(
                location=self.state,
                with_offset=True
            )
            location["latitude"] = lat
            location["longitude"] = lon
```

### Batch Geocoding with Rate Limiting
```python
async def geocode_locations(self, locations: List[Dict[str, Any]]) -> None:
    for i, location in enumerate(locations):
        if i > 0 and i % 10 == 0:
            # Rate limit after every 10 geocodes
            await asyncio.sleep(2)
        
        # Geocode as above...
```

## Testing Patterns

### Mock HTML Response
```python
@pytest.fixture
def mock_html_response() -> str:
    # Use actual HTML snippet from target website
    return """
    <table class="locations">
        <tr>
            <td>Test Pantry</td>
            <td>123 Main St</td>
            <td>(555) 123-4567</td>
        </tr>
    </table>
    """
```

### Mock API Response
```python
@pytest.fixture
def mock_api_response() -> Dict[str, Any]:
    return {
        "success": True,
        "locations": [
            {
                "id": 1,
                "name": "Test Pantry",
                "address": "123 Main St",
                "lat": 40.0,
                "lon": -75.0
            }
        ]
    }
```

### Testing Grid Search
```python
@pytest.mark.asyncio
async def test_grid_search(scraper):
    # Mock grid points
    mock_points = [
        GridPoint(lat=40.0, lng=-75.0),
        GridPoint(lat=40.5, lng=-75.5),
    ]
    scraper.utils.get_state_grid_points = Mock(return_value=mock_points)
    
    # Mock API responses for each point
    scraper.fetch_api_data = AsyncMock(side_effect=[
        {"locations": [{"name": "Pantry 1"}]},
        {"locations": [{"name": "Pantry 2"}]},
    ])
    
    # Run and verify
    await scraper.scrape()
    assert scraper.fetch_api_data.call_count == 2
```

## Quick Decision Tree

1. **Is data in HTML source?**
   - Yes → Use HTML scraping patterns
   - No → Continue to 2

2. **Are there API calls in Network tab?**
   - Yes → Use API scraping patterns
   - No → Continue to 3

3. **Is it a known service (Vivery, etc.)?**
   - Yes → Check if already covered
   - No → Continue to 4

4. **Is data loaded by JavaScript?**
   - Yes → Try to find API or data source
   - No → May need browser automation

## Common Gotchas

1. **Rate Limiting** - Always add delays between requests
2. **Dynamic Class Names** - Look for partial matches or data attributes
3. **Missing Data** - Always handle None/empty gracefully
4. **Coordinate Formats** - Some sites use [lng, lat] instead of [lat, lng]
5. **Time Zones** - Food bank hours may not specify timezone
6. **Duplicate Locations** - Same location may appear multiple times
7. **Address Formats** - May need parsing (e.g., "123 Main St, City, ST 12345")