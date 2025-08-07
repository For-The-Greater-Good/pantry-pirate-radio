# Common Scraper Patterns Quick Reference

This guide provides quick reference patterns for implementing scrapers based on common website architectures. All examples use bouy commands for development and testing to ensure proper container isolation and configuration.

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

### Quick Detection with Bouy
```bash
# Check if site uses known services
./bouy exec scraper curl -s "URL" | grep -E "(vivery|pantrynet|accessfood|food-access-widget)"

# Look for API endpoints
./bouy exec scraper curl -s "URL" | grep -E "(api\.|/api/|\.json|ajax|xhr)"

# Check for store locator plugins
./bouy exec scraper curl -s "URL" | grep -E "(store-locator|storelocator|wp-store-locator)"

# Analyze response headers
./bouy exec scraper curl -I "URL"

# Check JavaScript files for API endpoints
./bouy exec scraper bash -c "curl -s 'URL' | grep -oE 'https?://[^"]+api[^"]*' | sort -u"
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

### Basic Geocoding with Validation
```python
# In scraper - with automatic provider fallback and validation
for location in locations:
    if location.get("address"):
        try:
            lat, lon = self.geocoder.geocode_address(
                address=location["address"],
                state=location.get("state", self.state)
            )
            
            # Validate coordinates (detect 0,0 null island)
            if lat == 0 and lon == 0:
                logger.warning(f"Got null island for {location['name']}")
                lat, lon = self.geocoder.get_default_coordinates(
                    location=self.state,
                    with_offset=True
                )
            
            location["latitude"] = lat
            location["longitude"] = lon
            
        except ValueError as e:
            logger.warning(f"All geocoding providers failed: {e}")
            # Use state default with offset
            lat, lon = self.geocoder.get_default_coordinates(
                location=self.state,
                with_offset=True
            )
            location["latitude"] = lat
            location["longitude"] = lon
```

### Batch Geocoding (Rate Limiting Handled Automatically)
```python
async def geocode_locations(self, locations: List[Dict[str, Any]]) -> None:
    # The unified geocoding service handles rate limiting automatically
    # No need to add manual delays
    for location in locations:
        if location.get("address"):
            try:
                lat, lon = self.geocoder.geocode_address(
                    address=location["address"],
                    state=location.get("state", self.state)
                )
                # Validate and assign as shown above
                if lat == 0 and lon == 0:
                    logger.warning(f"Invalid coordinates for {location['name']}")
                    lat, lon = self.geocoder.get_default_coordinates(
                        location=self.state, with_offset=True
                    )
                location["latitude"] = lat
                location["longitude"] = lon
            except ValueError:
                # Fallback to defaults
                location["latitude"], location["longitude"] = \
                    self.geocoder.get_default_coordinates(
                        location=self.state, with_offset=True
                    )
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
   - Yes → Check if already covered by existing scrapers:
     ```bash
     ./bouy scraper --list | grep -i vivery
     ```
   - No → Continue to 4

4. **Is data loaded by JavaScript?**
   - Yes → Try to find API or data source in:
     - Network tab XHR/Fetch requests
     - JavaScript source files
     - Window/global variables in console
   - No → May need browser automation (last resort)

## Development Workflow with Bouy

### 1. Create New Scraper
```bash
# Create scraper file
vim app/scraper/my_food_bank_scraper.py

# Use existing scraper as template
cp app/scraper/sample_scraper.py app/scraper/my_food_bank_scraper.py
```

### 2. Test Scraper Implementation
```bash
# Test scraper without processing jobs
./bouy scraper-test my_food_bank

# Check logs for errors
./bouy logs scraper --tail 50
```

### 3. Run Scraper
```bash
# Run your scraper
./bouy scraper my_food_bank

# Monitor job processing
./bouy logs worker -f
```

### 4. Debug Issues
```bash
# Interactive debugging
./bouy shell scraper
python -c "from app.scraper.my_food_bank_scraper import *; scraper = MyFoodBankScraper(); print(scraper.test_connection())"

# Check geocoding
./bouy exec scraper python -c "from app.scraper.utils import GeocoderUtils; g = GeocoderUtils(); print(g.geocode_address('123 Main St, Boston, MA'))"
```

### 5. Monitor Performance
```bash
# Check scraper metrics
./bouy exec scraper python -c "from app.scraper.utils import SCRAPER_JOBS; print(SCRAPER_JOBS._metrics)"

# View content store stats
./bouy content-store status
```

## Real-World Scraper Examples

### Example 1: API with Grid Search (Vivery Pattern)
Used by multiple food banks with Vivery/PantryNet integration:

```python
class ViveryStyleScraper(ScraperJob):
    def __init__(self):
        super().__init__(scraper_id="vivery_style")
        self.api_url = "https://api.example.com/v2/locations"
        self.search_radius = 50  # miles
    
    async def scrape(self) -> str:
        # Get grid points for coverage area
        grid_points = self.utils.get_state_grid_points("ca")
        
        all_locations = []
        seen_ids = set()
        
        for point in grid_points:
            # Search around each grid point
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.api_url,
                    params={
                        "latitude": point.lat,
                        "longitude": point.lng,
                        "radius": self.search_radius,
                        "limit": 1000
                    },
                    headers=get_scraper_headers()
                )
                
                data = response.json()
                
                # Deduplicate by ID
                for location in data.get("locations", []):
                    if location["id"] not in seen_ids:
                        seen_ids.add(location["id"])
                        all_locations.append(location)
            
            # Be nice to the API
            await asyncio.sleep(1)
        
        # Submit each location for processing
        for location in all_locations:
            self.submit_to_queue(json.dumps(location))
        
        return json.dumps({"total": len(all_locations)})
```

### Example 2: WordPress Store Locator Pattern
Common pattern for WordPress sites with store locator plugins:

```python
class WordPressLocatorScraper(ScraperJob):
    def __init__(self):
        super().__init__(scraper_id="wp_locator")
        self.ajax_url = "https://example.org/wp-admin/admin-ajax.php"
    
    async def scrape(self) -> str:
        # WordPress AJAX typically uses POST
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.ajax_url,
                data={
                    "action": "store_locator",
                    "lat": "40.7128",
                    "lng": "-74.0060",
                    "radius": "100",
                    "filter": "food_pantry"
                },
                headers=get_scraper_headers()
            )
            
            data = response.json()
            
            # Process and geocode if needed
            for location in data.get("stores", []):
                # Add geocoding if coordinates missing
                if not location.get("lat"):
                    try:
                        lat, lon = self.geocoder.geocode_address(
                            address=location["address"],
                            state=location.get("state", "NY")
                        )
                        location["lat"] = lat
                        location["lng"] = lon
                    except ValueError:
                        # Use defaults with offset
                        lat, lon = self.geocoder.get_default_coordinates(
                            "NY", with_offset=True
                        )
                        location["lat"] = lat
                        location["lng"] = lon
                
                self.submit_to_queue(json.dumps(location))
            
            return json.dumps({"total": len(data.get("stores", []))})
```

### Example 3: HTML Table Scraping Pattern
For static HTML pages with tabular data:

```python
class TableScraper(ScraperJob):
    def __init__(self):
        super().__init__(scraper_id="table_scraper")
        self.url = "https://example.org/pantries"
    
    async def scrape(self) -> str:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.url,
                headers=get_scraper_headers()
            )
        
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(response.text, "html.parser")
        
        locations = []
        table = soup.find("table", {"class": "pantry-list"})
        
        if table:
            rows = table.find_all("tr")[1:]  # Skip header
            for row in rows:
                cells = row.find_all("td")
                if len(cells) >= 3:
                    location = {
                        "name": cells[0].get_text(strip=True),
                        "address": cells[1].get_text(strip=True),
                        "phone": cells[2].get_text(strip=True),
                        "hours": cells[3].get_text(strip=True) if len(cells) > 3 else ""
                    }
                    
                    # Geocode the address
                    try:
                        lat, lon = self.geocoder.geocode_address(
                            address=location["address"]
                        )
                        # Validate coordinates
                        if lat == 0 and lon == 0:
                            raise ValueError("Invalid coordinates")
                        location["latitude"] = lat
                        location["longitude"] = lon
                    except ValueError:
                        # Fallback to defaults
                        lat, lon = self.geocoder.get_default_coordinates(
                            "US", with_offset=True
                        )
                        location["latitude"] = lat
                        location["longitude"] = lon
                    
                    locations.append(location)
                    self.submit_to_queue(json.dumps(location))
        
        return json.dumps({"total": len(locations)})
```

### Example 4: ArcGIS REST API Pattern
For organizations using ESRI ArcGIS services:

```python
class ArcGISScraper(ScraperJob):
    def __init__(self):
        super().__init__(scraper_id="arcgis_scraper")
        self.service_url = "https://services.arcgis.com/xxx/arcgis/rest/services/FoodPantries/FeatureServer/0"
    
    async def scrape(self) -> str:
        # Query all features
        params = {
            "where": "1=1",  # Get all records
            "outFields": "*",  # All fields
            "f": "json",  # JSON format
            "resultRecordCount": 1000  # Max records per request
        }
        
        all_features = []
        offset = 0
        
        async with httpx.AsyncClient() as client:
            while True:
                params["resultOffset"] = offset
                
                response = await client.get(
                    f"{self.service_url}/query",
                    params=params,
                    headers=get_scraper_headers()
                )
                
                data = response.json()
                features = data.get("features", [])
                
                if not features:
                    break
                
                all_features.extend(features)
                offset += len(features)
                
                # Check if more records exist
                if not data.get("exceededTransferLimit", False):
                    break
                
                await asyncio.sleep(1)  # Rate limiting
        
        # Process features
        for feature in all_features:
            attrs = feature.get("attributes", {})
            geom = feature.get("geometry", {})
            
            location = {
                "name": attrs.get("NAME"),
                "address": attrs.get("ADDRESS"),
                "city": attrs.get("CITY"),
                "state": attrs.get("STATE"),
                "zip": attrs.get("ZIP"),
                "phone": attrs.get("PHONE"),
                "latitude": geom.get("y"),
                "longitude": geom.get("x"),
                "hours": attrs.get("HOURS"),
                "services": attrs.get("SERVICES", "").split(";")
            }
            
            self.submit_to_queue(json.dumps(location))
        
        return json.dumps({"total": len(all_features)})
```

## Common Gotchas and Solutions

1. **Rate Limiting** - The unified geocoding service handles this automatically
2. **Dynamic Class Names** - Look for partial matches or data attributes
3. **Missing Data** - Always handle None/empty gracefully
4. **Coordinate Formats** - Some sites use [lng, lat] instead of [lat, lng]
   ```python
   # Check and swap if needed
   if abs(lon) > 90 and abs(lat) <= 180:
       lat, lon = lon, lat  # Swap if likely reversed
   ```
5. **Invalid Coordinates** - Watch for 0,0 (null island) and projected coordinates
   ```python
   # The reconciler will automatically detect and correct these:
   # - Web Mercator coordinates (very large numbers)
   # - State Plane coordinates
   # - Zero coordinates
   ```
6. **Time Zones** - Food bank hours may not specify timezone
7. **Duplicate Locations** - Use sets or dict keys for deduplication
   ```python
   seen_locations = set()
   unique_locations = []
   for loc in locations:
       key = (loc['name'], loc['address'])
       if key not in seen_locations:
           seen_locations.add(key)
           unique_locations.append(loc)
   ```
8. **Address Formats** - May need parsing
   ```python
   # Parse combined address
   parts = address.split(', ')
   if len(parts) >= 3:
       street = parts[0]
       city = parts[1]
       state_zip = parts[2].split(' ')
       state = state_zip[0] if state_zip else ''
       zip_code = state_zip[1] if len(state_zip) > 1 else ''
   ```