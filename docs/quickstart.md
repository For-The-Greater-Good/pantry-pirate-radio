# Quick Start Guide

Get Pantry Pirate Radio running on your machine in under 10 minutes! This guide provides a complete path from zero to a fully functional system with real food resource data.

## What is Pantry Pirate Radio?

Pantry Pirate Radio is a food security data aggregation system that:
- Collects food resource data from 30+ sources across the US
- Normalizes data using AI to the OpenReferral HSDS standard
- Provides a unified API for accessing food assistance information
- Maintains a complete, searchable database of food pantries, soup kitchens, and mobile food programs

## Prerequisites

### Required Software
- **Docker Desktop** (Mac/Windows) or **Docker Engine** (Linux) - [Install Docker](https://docs.docker.com/get-docker/)
- **Git** - [Install Git](https://git-scm.com/downloads)
- **4GB+ RAM available** for Docker
- **10GB+ disk space** for containers and data

### Optional (for full functionality)
- **GitHub Personal Access Token** - For publishing data to HAARRRvest repository
- **LLM API Key** - Either Claude (Anthropic) or OpenAI key for AI processing

## 🚀 Quick Setup (5 Minutes)

### Step 1: Clone the Repository

```bash
# Clone the repository
git clone https://github.com/For-The-Greater-Good/pantry-pirate-radio.git
cd pantry-pirate-radio
```

✅ **Success Indicator**: You should now be in the `pantry-pirate-radio` directory.

### Step 2: Run the Setup Wizard

```bash
# Run the interactive setup wizard
./bouy setup
```

The setup wizard will:
1. Check for Docker installation
2. Create your `.env` configuration file
3. Guide you through setting up:
   - Database passwords (secure defaults provided)
   - LLM provider selection (Claude or OpenAI)
   - Optional API keys
   - HAARRRvest repository configuration

**💡 Tip**: Press Enter to accept defaults for a quick setup. You can always reconfigure later.

✅ **Success Indicator**: You'll see "✅ Setup complete!" when finished.

### Step 3: Start the System with Data

```bash
# Start all services WITH pre-populated food resource data
./bouy up --with-init
```

This command:
- Downloads ~90 days of food resource data from HAARRRvest
- Starts all required services (database, API, workers)
- Initializes the database with real food pantry data
- Takes 5-15 minutes on first run

**Monitor initialization progress:**
```bash
# In a new terminal, watch the initialization
./bouy logs -f db-init
```

✅ **Success Indicators**:
- You'll see "Database initialization complete" in the logs
- All services show as "running" when you run `./bouy ps`

### Step 4: Verify Everything Works

```bash
# Check service status
./bouy ps

# Test the API
curl http://localhost:8000/health

# Open the interactive API documentation
open http://localhost:8000/docs  # Mac
# OR
xdg-open http://localhost:8000/docs  # Linux
# OR just navigate to http://localhost:8000/docs in your browser
```

✅ **Success Indicators**:
- All services show "Up" status
- API returns `{"status":"healthy"}`
- API documentation page loads successfully

### Step 5: Make Your First API Call

```bash
# Search for food pantries in Manhattan
curl -H "Accept: application/json" \
  "http://localhost:8000/v1/services?latitude=40.7128&longitude=-74.0060&radius=5&status=active"
```

You should see JSON data with food services in the area!

✅ **Success Indicator**: API returns a JSON response with `services` array containing food resource data.

## 🎯 Common Setup Issues & Solutions

### Docker Not Running
```bash
# Check Docker status
docker --version

# If not installed, visit: https://docs.docker.com/get-docker/
# Start Docker Desktop (Mac/Windows) or Docker service (Linux)
```

### Port Conflicts
```bash
# Check if ports are in use
lsof -i :8000  # API port
lsof -i :5432  # Database port
lsof -i :6379  # Redis port

# Solution: Stop conflicting services or change ports in .env
```

### Slow Initialization
- First run downloads ~500MB of data from HAARRRvest
- Subsequent runs use cached data (much faster)
- Use `./bouy up` (without --with-init) for faster startup with empty database

### Memory Issues
```bash
# Increase Docker memory in Docker Desktop settings (Mac/Windows)
# OR reduce worker count:
./bouy up --scale worker=1
```

## 📊 Understanding the System

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

## 🔧 Essential Commands

Once your system is running, here are the most important commands:

### Service Management
```bash
./bouy up                   # Start all services
./bouy down                 # Stop all services
./bouy ps                   # Check service status
./bouy logs app            # View API logs
./bouy logs -f worker      # Follow worker logs (real-time)
./bouy clean               # Stop services and remove data
```

### Running Tests
```bash
./bouy test                # Run all tests and checks
./bouy test --pytest       # Run tests only
./bouy test --black        # Check code formatting
./bouy test --mypy         # Type checking
```

### Data Collection
```bash
./bouy scraper --list      # List available scrapers
./bouy scraper nyc_efap_programs  # Run specific scraper
./bouy scraper --all       # Run all scrapers (30+ sources)
```

### Getting Help
```bash
./bouy --help              # Show all available commands
./bouy scraper --help      # Help for specific command
```

## 🔍 Common API Queries

Once your system is running, try these API calls:

### Find Food Pantries Near You
```bash
# Search within 5 miles of a location
curl -H "Accept: application/json" \
  "http://localhost:8000/v1/services?latitude=40.7128&longitude=-74.0060&radius=5&status=active"
```

### Find Services with Spanish Support
```bash
curl -H "Accept: application/json" \
  "http://localhost:8000/v1/services?latitude=40.7128&longitude=-74.0060&radius=10&languages=es&status=active"
```

### Find Mobile Food Pantries
```bash
curl -H "Accept: application/json" \
  "http://localhost:8000/v1/services?latitude=40.7128&longitude=-74.0060&radius=15&service_type=mobile_pantry&status=active"
```

### Search Within a Bounding Box
```bash
curl -H "Accept: application/json" \
  "http://localhost:8000/v1/services?bounds[north]=40.8&bounds[south]=40.7&bounds[east]=-73.9&bounds[west]=-74.1&status=active"
```

## 🌐 Service URLs

Once running, access these services:

| Service | URL | Description |
|---------|-----|-------------|
| **API Documentation** | http://localhost:8000/docs | Interactive API explorer (Swagger UI) |
| **API Endpoints** | http://localhost:8000/v1/ | REST API base URL |
| **Health Check** | http://localhost:8000/health | System health status |
| **Worker Health** | http://localhost:8080/health | LLM worker status (Claude only) |
| **Queue Monitor** | http://localhost:9181 | RQ Dashboard for job monitoring |
| **Metrics** | http://localhost:8000/metrics | Prometheus metrics |

## 🚦 Understanding the Response Format

The API returns HSDS-compliant JSON with these key sections:

```json
{
  "search_query": {         // Your search parameters
    "latitude": 40.7128,
    "longitude": -74.0060,
    "radius": 5
  },
  "services": [            // Array of matching services
    {
      "organization": {    // Organization providing the service
        "name": "Community Food Bank",
        "email": "info@foodbank.org"
      },
      "service": {         // Service details
        "name": "Emergency Food Pantry",
        "description": "Free groceries..."
      },
      "location": {        // Physical location
        "address": {...},
        "distance_miles": 0.5
      },
      "schedules": [...],  // Operating hours
      "phones": [...]      // Contact information
    }
  ],
  "pagination": {...},     // Pagination info
  "metadata": {...}        // Response metadata
}
```

## 📝 Building a Simple Food Finder App

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

## 💻 Working with Different Programming Languages

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

## ⚙️ Configuration Options

### LLM Provider Setup (Optional)

To enable AI-powered data processing, configure an LLM provider:

#### Option 1: Claude (Recommended)
```bash
# Add to .env file
LLM_PROVIDER=claude
ANTHROPIC_API_KEY=your_api_key_here  # Optional - can use CLI auth

# Or use interactive authentication
./bouy claude-auth
```

#### Option 2: OpenAI
```bash
# Add to .env file
LLM_PROVIDER=openai
OPENROUTER_API_KEY=your_api_key_here
LLM_MODEL_NAME=gpt-4
```

### HAARRRvest Publisher (Optional)

To publish collected data to the HAARRRvest repository:

```bash
# Add to .env file
DATA_REPO_TOKEN=your_github_pat  # GitHub Personal Access Token
DATA_REPO_URL=https://github.com/For-The-Greater-Good/HAARRRvest.git
```

### Geocoding Service (Optional)

Configure geocoding for accurate location data:

```bash
# Add to .env file
GEOCODING_PROVIDER=arcgis  # Free tier available
ARCGIS_API_KEY=your_key    # Optional for higher limits
GEOCODING_ENABLE_FALLBACK=true
```

## 📈 API Limits and Best Practices

### Rate Limiting
- **Limit**: 100 requests per minute per IP address
- **Headers**: Check `X-RateLimit-Remaining` header
- **Retry**: Wait for `Retry-After` header value if rate limited

### Geographic Constraints
- **Coverage**: Continental US (25°N-49°N, -125°W to -67°W)
- **Radius**: Maximum 80 miles for point searches
- **Bounding Box**: No size limit but may paginate results

### Performance Tips
1. Start with smaller radius searches
2. Use filters to reduce response size
3. Implement pagination for large datasets
4. Cache responses when appropriate

## 🎯 Common Use Cases

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

## 🚀 Next Steps

### For API Users
1. **[API Examples](./api-examples.md)** - Comprehensive API usage examples
2. **[API Documentation](./api.md)** - Complete API reference
3. **Interactive API Explorer** - Visit http://localhost:8000/docs

### For Developers
1. **[Docker Development Guide](./docker-development.md)** - Advanced Docker setup
2. **[Architecture Overview](./architecture.md)** - System design details
3. **[Scraper Development](./scrapers.md)** - Add new data sources
4. **[LLM Configuration](./llm.md)** - AI provider setup

### For Contributors
1. **[CLAUDE.md](../CLAUDE.md)** - Development guidelines
2. **[Contributing Guide](../CONTRIBUTING.md)** - How to contribute
3. **[Test Environment Setup](./test-environment-setup.md)** - Testing best practices

## 🆘 Getting Help

### Quick Troubleshooting
```bash
# Check system status
./bouy ps

# View recent logs
./bouy logs app --tail 50

# Restart a service
./bouy down && ./bouy up

# Clean everything and start fresh
./bouy clean
./bouy setup
./bouy up --with-init
```

### Resources
- **[Troubleshooting Guide](./troubleshooting.md)** - Common issues and solutions
- **[GitHub Issues](https://github.com/For-The-Greater-Good/pantry-pirate-radio/issues)** - Report bugs or request features
- **[Documentation Index](./README.md)** - Complete documentation navigation
- **[HAARRRvest Data Explorer](https://for-the-greater-good.github.io/HAARRRvest/)** - Browse collected data

## 🏗️ System Architecture Overview

### Data Flow
```
Scrapers → Content Store → LLM Workers → Database → API
                ↓                           ↓
           Deduplication              HAARRRvest Publisher
```

### Key Components
- **30+ Scrapers**: Collect data from food resource websites
- **Content Store**: Deduplicates data to avoid reprocessing
- **LLM Workers**: AI-powered HSDS normalization
- **Reconciler**: Merges and deduplicates location data
- **Recorder**: Archives all processed data as JSON
- **API**: Serves HSDS-compliant data via REST endpoints
- **HAARRRvest Publisher**: Backs up data to GitHub repository

### Database
- **PostgreSQL 15+** with PostGIS for geographic queries
- **Redis** for job queues and caching
- **HSDS v3.1.1** compliant schema
- **Version tracking** for all records

## 🤝 Contributing

We welcome contributions! Here's how to get involved:

### Quick Contribution Setup
```bash
# Fork and clone the repository
git clone https://github.com/YOUR_USERNAME/pantry-pirate-radio.git
cd pantry-pirate-radio

# Create a feature branch
git checkout -b feat/your-feature

# Run tests before committing
./bouy test

# Make your changes and commit
git add .
git commit -m "feat: your feature description"

# Push and create a pull request
git push origin feat/your-feature
```

### Ways to Contribute
- **Report Bugs**: [Create an issue](https://github.com/For-The-Greater-Good/pantry-pirate-radio/issues)
- **Add Scrapers**: Contribute new data sources
- **Improve Documentation**: Help others get started
- **Fix Issues**: Check our [good first issues](https://github.com/For-The-Greater-Good/pantry-pirate-radio/labels/good%20first%20issue)
- **Enhance Tests**: Improve test coverage

## 📄 License

This project is released under a custom license. See [LICENSE](../LICENSE) for details.

---

**Congratulations!** 🎉 You now have Pantry Pirate Radio running with real food resource data. The system is actively collecting, processing, and serving food security information to help people find assistance in their communities.

*For The Greater Good (FTGG)* | Making public resources truly accessible through intelligent aggregation