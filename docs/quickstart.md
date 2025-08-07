# Quick Start Guide

This guide will help you get started with the Pantry Pirate Radio API in just a few minutes. You'll learn how to make your first API call, understand the response format, and build a simple food finder application.

## What is Pantry Pirate Radio?

Pantry Pirate Radio is a food security data aggregation system that provides access to information about food pantries, soup kitchens, mobile food programs, and other food assistance resources. The API follows the OpenReferral Human Services Data Specification (HSDS) and serves publicly available data to help people find food assistance in their area.

## Prerequisites

- Basic understanding of REST APIs
- Ability to make HTTP requests (using cURL, Postman, or programming languages)
- No API key required - the API is public and free to use

## Making Your First API Call

### Step 1: Check API Health

First, let's verify that the API is running:

```bash
curl -H "Accept: application/json" https://api.pantrypirate.org/v1/health
```

You should see a response like:

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "uptime": 86400,
  "timestamp": "2024-01-15T15:30:00Z"
}
```

### Step 2: Search for Food Services

Now let's search for food services near a specific location. We'll search for services within 5 miles of Manhattan (latitude: 40.7128, longitude: -74.0060):

```bash
curl -H "Accept: application/json" \
  "https://api.pantrypirate.org/v1/services?latitude=40.7128&longitude=-74.0060&radius=5&status=active"
```

This will return a list of active food services within 5 miles of the specified coordinates.

### Step 3: Search for Food Pantries Only

Let's narrow down the search to find only food pantries:

```bash
curl -H "Accept: application/json" \
  "https://api.pantrypirate.org/v1/services?latitude=40.7128&longitude=-74.0060&radius=5&status=active&service_type=food_pantry"
```

## Understanding the Response Format

The API response includes several key sections:

```json
{
  "search_query": {
    "latitude": 40.7128,
    "longitude": -74.0060,
    "radius": 5,
    "filters": {
      "status": "active",
      "service_type": "food_pantry"
    }
  },
  "services": [
    {
      "id": "svc-example-001",
      "organization": {
        "id": "org-example-001",
        "name": "Example Community Food Bank",
        "description": "A full-service food bank...",
        "email": "info@examplefoodbank.org",
        "url": "https://www.examplefoodbank.org"
      },
      "service": {
        "id": "svc-example-001",
        "name": "Emergency Food Pantry",
        "description": "Free groceries and emergency food assistance...",
        "status": "active",
        "eligibility_description": "Open to all residents of Example County..."
      },
      "location": {
        "id": "loc-example-001",
        "name": "Example Community Food Bank - Main Warehouse",
        "latitude": 40.7128,
        "longitude": -74.0060,
        "distance_miles": 0.1,
        "address": {
          "address_1": "123 Main Street",
          "city": "Example City",
          "state_province": "NY",
          "postal_code": "10001",
          "country": "US"
        }
      },
      "schedules": [
        {
          "opens_at": "09:00",
          "closes_at": "17:00",
          "byday": "MO,TU,WE,TH,FR",
          "description": "Food pantry open Monday through Friday, 9 AM to 5 PM"
        }
      ],
      "contacts": [
        {
          "name": "Sarah Johnson",
          "title": "Food Pantry Manager",
          "email": "sarah.johnson@examplefoodbank.org"
        }
      ],
      "phones": [
        {
          "number": "555-123-4567",
          "type": "voice",
          "description": "Main food pantry hotline"
        }
      ]
    }
  ],
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total": 1,
    "total_pages": 1
  },
  "metadata": {
    "timestamp": "2024-01-15T15:30:00Z",
    "query_time": 0.089,
    "total_results": 1
  }
}
```

### Key Response Components

- **search_query**: Shows the parameters used for the search
- **services**: Array of matching services with full details
- **pagination**: Information about result pagination
- **metadata**: Additional information about the response

## Common Search Scenarios

### Find Services with Spanish Support

```bash
curl -H "Accept: application/json" \
  "https://api.pantrypirate.org/v1/services?latitude=40.7128&longitude=-74.0060&radius=10&languages=es&status=active"
```

### Find Mobile Food Pantries

```bash
curl -H "Accept: application/json" \
  "https://api.pantrypirate.org/v1/services?latitude=40.7128&longitude=-74.0060&radius=15&service_type=mobile_pantry&status=active"
```

### Find Hot Meals Programs

```bash
curl -H "Accept: application/json" \
  "https://api.pantrypirate.org/v1/services?latitude=40.7128&longitude=-74.0060&radius=8&service_type=hot_meals&status=active"
```

### Search Within a Bounding Box

```bash
curl -H "Accept: application/json" \
  "https://api.pantrypirate.org/v1/services?bounds[north]=40.8&bounds[south]=40.7&bounds[east]=-73.9&bounds[west]=-74.1&status=active"
```

## Building a Simple Food Finder App

Let's create a simple HTML page that uses the API to find nearby food pantries:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Food Finder</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .service { border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 5px; }
        .service h3 { margin: 0 0 10px 0; color: #333; }
        .service p { margin: 5px 0; }
        .distance { font-weight: bold; color: #666; }
        .hours { color: #008000; }
        .phone { color: #0066cc; }
        button { background: #007cba; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; }
        button:hover { background: #005a8a; }
        #results { margin-top: 20px; }
        .loading { display: none; text-align: center; color: #666; }
    </style>
</head>
<body>
    <h1>Food Finder</h1>
    <p>Find food pantries and assistance programs near you.</p>

    <div>
        <input type="number" id="latitude" placeholder="Latitude" step="any" value="40.7128">
        <input type="number" id="longitude" placeholder="Longitude" step="any" value="-74.0060">
        <input type="number" id="radius" placeholder="Radius (miles)" min="1" max="80" value="5">
        <button onclick="findServices()">Find Food Services</button>
        <button onclick="getCurrentLocation()">Use My Location</button>
    </div>

    <div id="loading" class="loading">Searching for services...</div>
    <div id="results"></div>

    <script>
        const API_BASE_URL = 'https://api.pantrypirate.org/v1';

        async function findServices() {
            const latitude = document.getElementById('latitude').value;
            const longitude = document.getElementById('longitude').value;
            const radius = document.getElementById('radius').value;

            if (!latitude || !longitude || !radius) {
                alert('Please fill in all fields');
                return;
            }

            document.getElementById('loading').style.display = 'block';
            document.getElementById('results').innerHTML = '';

            try {
                const response = await fetch(
                    `${API_BASE_URL}/services?latitude=${latitude}&longitude=${longitude}&radius=${radius}&status=active`
                );

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }

                const data = await response.json();
                displayResults(data);
            } catch (error) {
                console.error('Error:', error);
                document.getElementById('results').innerHTML =
                    `<p style="color: red;">Error: ${error.message}</p>`;
            } finally {
                document.getElementById('loading').style.display = 'none';
            }
        }

        function displayResults(data) {
            const resultsDiv = document.getElementById('results');

            if (data.services.length === 0) {
                resultsDiv.innerHTML = '<p>No food services found in the specified area.</p>';
                return;
            }

            let html = `<h2>Found ${data.services.length} Food Services</h2>`;

            data.services.forEach(service => {
                const org = service.organization;
                const svc = service.service;
                const location = service.location;
                const schedule = service.schedules[0] || {};
                const phone = service.phones[0] || {};

                html += `
                    <div class="service">
                        <h3>${org.name}</h3>
                        <p><strong>Service:</strong> ${svc.name}</p>
                        <p><strong>Description:</strong> ${svc.description}</p>
                        <p><strong>Address:</strong> ${location.address.address_1}, ${location.address.city}, ${location.address.state_province} ${location.address.postal_code}</p>
                        <p class="distance"><strong>Distance:</strong> ${location.distance_miles} miles</p>
                        ${schedule.description ? `<p class="hours"><strong>Hours:</strong> ${schedule.description}</p>` : ''}
                        ${phone.number ? `<p class="phone"><strong>Phone:</strong> ${phone.number}</p>` : ''}
                        ${svc.eligibility_description ? `<p><strong>Eligibility:</strong> ${svc.eligibility_description}</p>` : ''}
                        ${svc.application_process ? `<p><strong>How to Apply:</strong> ${svc.application_process}</p>` : ''}
                    </div>
                `;
            });

            resultsDiv.innerHTML = html;
        }

        function getCurrentLocation() {
            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(
                    position => {
                        document.getElementById('latitude').value = position.coords.latitude;
                        document.getElementById('longitude').value = position.coords.longitude;
                    },
                    error => {
                        alert('Error getting location: ' + error.message);
                    }
                );
            } else {
                alert('Geolocation is not supported by this browser');
            }
        }
    </script>
</body>
</html>
```

## Working with Different Programming Languages

### Python Example

```python
import requests

def find_food_pantries(latitude, longitude, radius=5):
    url = "https://api.pantrypirate.org/v1/services"
    params = {
        'latitude': latitude,
        'longitude': longitude,
        'radius': radius,
        'status': 'active',
        'service_type': 'food_pantry'
    }

    response = requests.get(url, params=params)
    response.raise_for_status()

    data = response.json()

    print(f"Found {len(data['services'])} food pantries:")
    for service in data['services']:
        org = service['organization']
        location = service['location']
        print(f"- {org['name']}: {location['address']['address_1']}")
        print(f"  Distance: {location['distance_miles']} miles")
        if service['phones']:
            print(f"  Phone: {service['phones'][0]['number']}")
        print()

# Example usage
find_food_pantries(40.7128, -74.0060, 5)
```

### JavaScript/Node.js Example

```javascript
const axios = require('axios');

async function findFoodPantries(latitude, longitude, radius = 5) {
    try {
        const response = await axios.get('https://api.pantrypirate.org/v1/services', {
            params: {
                latitude,
                longitude,
                radius,
                status: 'active',
                service_type: 'food_pantry'
            }
        });

        const data = response.data;

        console.log(`Found ${data.services.length} food pantries:`);
        data.services.forEach(service => {
            const org = service.organization;
            const location = service.location;
            console.log(`- ${org.name}: ${location.address.address_1}`);
            console.log(`  Distance: ${location.distance_miles} miles`);
            if (service.phones.length > 0) {
                console.log(`  Phone: ${service.phones[0].number}`);
            }
            console.log();
        });
    } catch (error) {
        console.error('Error:', error.response?.data || error.message);
    }
}

// Example usage
findFoodPantries(40.7128, -74.0060, 5);
```

## API Limits and Best Practices

### Rate Limiting
- **Limit**: 100 requests per minute per IP address
- **Headers**: Check `X-RateLimit-Remaining` to see remaining requests
- **Retry**: Wait for the time specified in `Retry-After` header if rate limited

### Geographic Constraints
- **Latitude**: Must be between 25.0 and 49.0 (Continental US)
- **Longitude**: Must be between -125.0 and -67.0 (Continental US)
- **Radius**: Maximum 80 miles for point-based searches

### Performance Tips
1. Use the smallest radius that meets your needs
2. Apply filters to reduce response size
3. Use pagination for large result sets
4. Cache responses when possible

## Common Use Cases

### 1. Food Pantry Locator
Search for food pantries within a specific radius of a user's location.

### 2. Mobile Food Finder
Find mobile food pantries that serve different locations on different days.

### 3. Multilingual Service Directory
Find services that offer support in specific languages.

### 4. Emergency Food Assistance
Quick lookup of immediate food assistance options.

### 5. Community Resource Mapping
Display food resources on a map for community planning.

## Next Steps

Now that you've learned the basics, explore these advanced topics:

1. **[API Examples](./api-examples.md)** - Comprehensive API documentation with examples
2. **[Integration Examples](../examples/integrations/)** - Complete code examples in multiple languages
3. **[Sample Data](../examples/sample_data/)** - Explore the HSDS data structure
4. **[Error Handling](../examples/api_responses/error_responses.json)** - Learn how to handle API errors

## Getting Help

- **Documentation**: Visit the [API documentation](./api.md) for detailed information
- **Examples**: Check the [examples directory](../examples/) for code samples
- **Issues**: Report bugs or request features on [GitHub](https://github.com/example/pantry-pirate-radio/issues)
- **Community**: Join discussions about food security data and the OpenReferral specification

## Understanding the Data Pipeline (For Contributors)

### Data Flow Overview
The system processes food resource data through several stages:

1. **Scrapers** collect data from various sources
2. **Workers** process the data using LLM providers
3. **Reconciler** ensures data consistency and HSDS compliance
4. **Recorder** archives all processed data
5. **HAARRRvest Publisher** publishes data to the public repository
6. **API** serves the processed data

### Running the Full System Locally

```bash
# 1. Clone and setup
git clone https://github.com/For-The-Greater-Good/pantry-pirate-radio.git
cd pantry-pirate-radio
cp .env.example .env

# 2. Configure essential services in .env

## HAARRRvest Publisher Configuration
DATA_REPO_URL=https://github.com/For-The-Greater-Good/HAARRRvest.git
DATA_REPO_TOKEN=your_github_token

## Geocoding Service Configuration (Optional but Recommended)
# The system uses a unified geocoding service with caching and fallback
GEOCODING_PROVIDER=arcgis  # Primary provider (free tier available)
GEOCODING_CACHE_TTL=2592000  # Cache for 30 days to reduce API calls
GEOCODING_RATE_LIMIT=0.5  # Respects provider rate limits

# Optional: Get free ArcGIS API key for higher limits (1M/month vs 20K/month)
# Create account at: https://developers.arcgis.com
ARCGIS_API_KEY=your_api_key_here  # Optional, provides 50x more geocoding capacity

# The system automatically falls back to Nominatim if ArcGIS fails
GEOCODING_ENABLE_FALLBACK=true  # Automatic provider fallback
NOMINATIM_USER_AGENT=pantry-pirate-radio  # Required for Nominatim

# 3. Start all services
docker-compose up -d

# 4. Run a scraper to generate data
./bouy scraper nyc_efap_programs

# 5. Monitor processing
./bouy logs worker
./bouy logs recorder
./bouy logs haarrrvest-publisher

# Follow logs continuously
./bouy logs -f worker

# 6. Check published data
# Visit https://github.com/For-The-Greater-Good/HAARRRvest
```

### HAARRRvest Publisher
The publisher service automatically:
- Monitors for new recorder outputs every 5 minutes
- Creates date-based branches for safety
- Exports PostgreSQL data to SQLite for visualization
- Pushes updates to the HAARRRvest repository
- Maintains a complete audit trail

To manually trigger publishing:
```bash
docker-compose restart haarrrvest-publisher
```

## Contributing

The Pantry Pirate Radio project is open source. You can contribute by:
- Reporting bugs or suggesting features
- Improving documentation
- Adding new scrapers for additional data sources
- Helping with translations
- Enhancing the data processing pipeline

Visit our [GitHub repository](https://github.com/For-The-Greater-Good/pantry-pirate-radio) to get started!