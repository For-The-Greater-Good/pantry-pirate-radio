#!/bin/bash

# Pantry Pirate Radio API cURL Examples
#
# This script demonstrates how to interact with the Pantry Pirate Radio API
# using cURL commands. It includes examples for all major API endpoints and
# common use cases.
#
# Usage:
#   chmod +x curl_examples.sh
#   ./curl_examples.sh
#
# Or run individual commands by copying and pasting them.

# API Configuration
API_BASE_URL="https://api.pantrypirate.org/v1"
# For local development, use:
# API_BASE_URL="http://localhost:8000/api/v1"

# Common headers
HEADERS=(
    -H "Accept: application/json"
    -H "User-Agent: PantryPirateAPI-Examples/1.0"
)

echo "=== Pantry Pirate Radio API cURL Examples ==="
echo "Base URL: $API_BASE_URL"
echo ""

# Function to make API calls with error handling
make_api_call() {
    local description="$1"
    local url="$2"
    local extra_args=("${@:3}")

    echo "=== $description ==="
    echo "URL: $url"
    echo ""

    # Make the API call
    response=$(curl -s -w "\n%{http_code}" "${HEADERS[@]}" "${extra_args[@]}" "$url")

    # Extract HTTP status code
    http_code=$(echo "$response" | tail -n1)
    response_body=$(echo "$response" | head -n -1)

    echo "HTTP Status: $http_code"

    if [ "$http_code" -eq 200 ]; then
        echo "Response:"
        echo "$response_body" | python3 -m json.tool 2>/dev/null || echo "$response_body"
    else
        echo "Error Response:"
        echo "$response_body" | python3 -m json.tool 2>/dev/null || echo "$response_body"
    fi

    echo ""
    echo "---"
    echo ""
}

# Example 1: Health Check
make_api_call "Health Check" "$API_BASE_URL/health"

# Example 2: Search for food pantries near Manhattan
make_api_call "Search Food Pantries Near Manhattan" \
    "$API_BASE_URL/services?latitude=40.7128&longitude=-74.0060&radius=5&status=active&service_type=food_pantry"

# Example 3: Search with multiple filters
make_api_call "Search with Multiple Filters" \
    "$API_BASE_URL/services?latitude=40.7128&longitude=-74.0060&radius=10&status=active&languages=es&per_page=5"

# Example 4: Bounding box search
make_api_call "Bounding Box Search" \
    "$API_BASE_URL/services?bounds[north]=40.8&bounds[south]=40.7&bounds[east]=-73.9&bounds[west]=-74.1&status=active"

# Example 5: List organizations with pagination
make_api_call "List Organizations" \
    "$API_BASE_URL/organizations?page=1&per_page=3&sort=name&order=asc"

# Example 6: List all services
make_api_call "List Services" \
    "$API_BASE_URL/services?page=1&per_page=3&status=active"

# Example 7: Get specific organization (using a known ID from sample data)
make_api_call "Get Organization Details" \
    "$API_BASE_URL/organizations/org-example-001"

# Example 8: Get specific service (using a known ID from sample data)
make_api_call "Get Service Details" \
    "$API_BASE_URL/services/svc-example-001"

# Example 9: Get specific location (using a known ID from sample data)
make_api_call "Get Location Details" \
    "$API_BASE_URL/locations/loc-example-001"

# Example 10: Search for mobile food pantries
make_api_call "Search Mobile Food Pantries" \
    "$API_BASE_URL/services?latitude=40.7128&longitude=-74.0060&radius=15&service_type=mobile_pantry&status=active"

# Example 11: Search for hot meals programs
make_api_call "Search Hot Meals Programs" \
    "$API_BASE_URL/services?latitude=40.7128&longitude=-74.0060&radius=8&service_type=hot_meals&status=active"

# Example 12: Error handling - Invalid coordinates
make_api_call "Error Example - Invalid Coordinates" \
    "$API_BASE_URL/services?latitude=91.0&longitude=-74.0060&radius=5"

# Example 13: Error handling - Resource not found
make_api_call "Error Example - Resource Not Found" \
    "$API_BASE_URL/services/svc-nonexistent-123"

echo "=== Advanced cURL Examples ==="
echo ""

# Example 14: Using jq to parse JSON responses (if jq is available)
echo "=== Using jq to Parse Responses ==="
if command -v jq &> /dev/null; then
    echo "Extracting organization names from search results:"
    curl -s "${HEADERS[@]}" \
        "$API_BASE_URL/services?latitude=40.7128&longitude=-74.0060&radius=5&per_page=3" \
        | jq -r '.services[].organization.name'
    echo ""

    echo "Extracting service names and phone numbers:"
    curl -s "${HEADERS[@]}" \
        "$API_BASE_URL/services?latitude=40.7128&longitude=-74.0060&radius=5&per_page=3" \
        | jq -r '.services[] | "\(.service.name): \(.phones[0].number // "No phone")"'
    echo ""
else
    echo "jq not available. Install jq for advanced JSON parsing."
    echo "Example jq commands:"
    echo "  # Extract organization names"
    echo "  curl -s \"$API_BASE_URL/services?latitude=40.7128&longitude=-74.0060&radius=5\" | jq -r '.services[].organization.name'"
    echo "  # Extract service names and phones"
    echo "  curl -s \"$API_BASE_URL/services?latitude=40.7128&longitude=-74.0060&radius=5\" | jq -r '.services[] | \"\\(.service.name): \\(.phones[0].number // \"No phone\")\"'"
fi

echo ""
echo "=== Useful cURL Command Patterns ==="
echo ""

# Show individual command examples
echo "1. Basic search with pretty-printed JSON:"
echo "curl -s -H 'Accept: application/json' '$API_BASE_URL/services?latitude=40.7128&longitude=-74.0060&radius=5' | python3 -m json.tool"
echo ""

echo "2. Save response to file:"
echo "curl -s -H 'Accept: application/json' '$API_BASE_URL/services?latitude=40.7128&longitude=-74.0060&radius=5' > services.json"
echo ""

echo "3. Include response headers:"
echo "curl -i -H 'Accept: application/json' '$API_BASE_URL/health'"
echo ""

echo "4. Follow redirects and show timing:"
echo "curl -L -w 'Total time: %{time_total}s\n' -H 'Accept: application/json' '$API_BASE_URL/health'"
echo ""

echo "5. Set custom timeout:"
echo "curl --connect-timeout 10 --max-time 30 -H 'Accept: application/json' '$API_BASE_URL/health'"
echo ""

echo "6. Use environment variables:"
echo "export API_KEY='your-api-key-if-needed'"
echo "curl -H 'Accept: application/json' -H 'Authorization: Bearer \$API_KEY' '$API_BASE_URL/health'"
echo ""

echo "=== Common Search Patterns ==="
echo ""

# Common search patterns as separate functions
search_nearby_pantries() {
    local lat="$1"
    local lng="$2"
    local radius="${3:-5}"

    echo "Searching for food pantries near coordinates ($lat, $lng) within $radius miles:"
    curl -s "${HEADERS[@]}" \
        "$API_BASE_URL/services?latitude=$lat&longitude=$lng&radius=$radius&status=active&service_type=food_pantry" \
        | python3 -m json.tool
}

search_services_with_language() {
    local lat="$1"
    local lng="$2"
    local language="$3"
    local radius="${4:-10}"

    echo "Searching for services with $language support near ($lat, $lng) within $radius miles:"
    curl -s "${HEADERS[@]}" \
        "$API_BASE_URL/services?latitude=$lat&longitude=$lng&radius=$radius&languages=$language&status=active" \
        | python3 -m json.tool
}

get_organization_info() {
    local org_id="$1"

    echo "Getting information for organization: $org_id"
    curl -s "${HEADERS[@]}" \
        "$API_BASE_URL/organizations/$org_id" \
        | python3 -m json.tool
}

echo "Available functions:"
echo "  search_nearby_pantries <lat> <lng> [radius]"
echo "  search_services_with_language <lat> <lng> <language> [radius]"
echo "  get_organization_info <org_id>"
echo ""

echo "Example usage:"
echo "  search_nearby_pantries 40.7128 -74.0060 5"
echo "  search_services_with_language 40.7128 -74.0060 es 10"
echo "  get_organization_info org-example-001"
echo ""

echo "=== Rate Limiting and Error Handling ==="
echo ""

# Function to handle rate limiting
handle_rate_limit() {
    local url="$1"
    local max_retries="${2:-3}"
    local retry_count=0

    while [ $retry_count -lt $max_retries ]; do
        response=$(curl -s -w "\n%{http_code}" "${HEADERS[@]}" "$url")
        http_code=$(echo "$response" | tail -n1)

        if [ "$http_code" -eq 429 ]; then
            echo "Rate limited. Waiting 60 seconds before retry..."
            sleep 60
            ((retry_count++))
        else
            echo "$response" | head -n -1
            break
        fi
    done

    if [ $retry_count -eq $max_retries ]; then
        echo "Max retries reached. Request failed."
    fi
}

echo "Rate limiting example:"
echo "handle_rate_limit '$API_BASE_URL/services?latitude=40.7128&longitude=-74.0060&radius=5'"
echo ""

echo "=== Batch Operations ==="
echo ""

# Example of batch operations
echo "Batch search for multiple locations:"
locations=(
    "40.7128,-74.0060"  # Manhattan
    "40.7831,-73.9712"  # Bronx
    "40.6892,-73.9442"  # Brooklyn
    "40.7282,-73.7949"  # Queens
    "40.5795,-74.1502"  # Staten Island
)

for location in "${locations[@]}"; do
    IFS=',' read -r lat lng <<< "$location"
    echo "Searching near $lat, $lng:"
    curl -s "${HEADERS[@]}" \
        "$API_BASE_URL/services?latitude=$lat&longitude=$lng&radius=2&status=active&per_page=1" \
        | python3 -c "
import json, sys
data = json.load(sys.stdin)
if data['services']:
    service = data['services'][0]
    print(f\"  Found: {service['organization']['name']} - {service['service']['name']}\")
else:
    print('  No services found')
"
done

echo ""
echo "=== Performance Testing ==="
echo ""

# Simple performance test
echo "Testing API response time:"
for i in {1..5}; do
    echo "Request $i:"
    curl -w "Time: %{time_total}s, Size: %{size_download} bytes\n" \
         -o /dev/null -s "${HEADERS[@]}" \
         "$API_BASE_URL/health"
done

echo ""
echo "=== End of Examples ==="
echo ""
echo "For more information, visit the API documentation at:"
echo "https://api.pantrypirate.org/docs"