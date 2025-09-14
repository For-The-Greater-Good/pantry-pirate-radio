#!/usr/bin/env python3
"""
Comprehensive API Test Script for Pantry Pirate Radio
Tests ALL endpoints systematically to identify issues
"""

import requests
import json
import time
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from urllib.parse import urljoin
import sys
import uuid
import traceback

# Configuration
API_BASE_URL = "https://api.for-the-gg.org"
TIMEOUT = 30  # seconds

# ANSI color codes
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

class EndpointTester:
    def __init__(self, base_url: str = API_BASE_URL):
        self.base_url = base_url
        self.session = requests.Session()
        self.results = []
        self.passed = 0
        self.failed = 0
        self.total = 0
        
    def test(self, method: str, endpoint: str, name: str, 
             params: Optional[Dict] = None, 
             json_data: Optional[Dict] = None,
             expected_status: Optional[List[int]] = None,
             check_response: bool = True) -> Dict:
        """Test a single endpoint."""
        self.total += 1
        
        url = urljoin(self.base_url, endpoint)
        print(f"\n{Colors.CYAN}[{self.total}] Testing: {name}{Colors.RESET}")
        print(f"    {method} {endpoint}")
        if params:
            print(f"    Params: {json.dumps(params, indent=2)}")
        if json_data:
            print(f"    Body: {json.dumps(json_data, indent=2)}")
        
        start_time = time.time()
        
        try:
            if method == "GET":
                response = self.session.get(url, params=params, timeout=TIMEOUT)
            elif method == "POST":
                response = self.session.post(url, json=json_data, params=params, timeout=TIMEOUT)
            elif method == "PUT":
                response = self.session.put(url, json=json_data, params=params, timeout=TIMEOUT)
            elif method == "PATCH":
                response = self.session.patch(url, json=json_data, params=params, timeout=TIMEOUT)
            elif method == "DELETE":
                response = self.session.delete(url, params=params, timeout=TIMEOUT)
            else:
                raise ValueError(f"Unsupported method: {method}")
                
            elapsed = time.time() - start_time
            
            # Expected status codes
            if expected_status is None:
                expected_status = [200, 201] if method == "POST" else [200]
            
            # Parse response
            response_data = None
            if response.text:
                try:
                    response_data = response.json()
                except:
                    response_data = response.text[:500]  # First 500 chars if not JSON
            
            # Check status
            success = response.status_code in expected_status
            
            # Additional response checks
            issues = []
            if success and check_response and response_data:
                # Check for common issues
                if isinstance(response_data, dict):
                    if "detail" in response_data and "error" in str(response_data["detail"]).lower():
                        issues.append(f"Error in response: {response_data['detail']}")
                        success = False
                    if "error" in response_data:
                        issues.append(f"Error field present: {response_data['error']}")
                        success = False
                    
                    # Check pagination structure
                    if endpoint.endswith("/") and "data" in response_data:
                        if not isinstance(response_data.get("data"), list):
                            issues.append("Data field is not a list")
                        if "total" not in response_data:
                            issues.append("Missing 'total' field in paginated response")
                        if "page" not in response_data:
                            issues.append("Missing 'page' field in paginated response")
            
            # Print result
            if success and not issues:
                self.passed += 1
                print(f"    {Colors.GREEN}✓ PASSED{Colors.RESET} - Status: {response.status_code}, Time: {elapsed:.2f}s")
                if response_data and isinstance(response_data, dict):
                    if "total" in response_data:
                        print(f"    Results: {response_data.get('total', 0)} total items")
                    elif "data" in response_data and isinstance(response_data["data"], list):
                        print(f"    Results: {len(response_data['data'])} items")
            else:
                self.failed += 1
                print(f"    {Colors.RED}✗ FAILED{Colors.RESET} - Status: {response.status_code} (expected {expected_status}), Time: {elapsed:.2f}s")
                if issues:
                    for issue in issues:
                        print(f"    {Colors.YELLOW}Issue: {issue}{Colors.RESET}")
                if response_data:
                    if isinstance(response_data, dict) and "detail" in response_data:
                        print(f"    Detail: {str(response_data['detail'])[:200]}")
                    elif isinstance(response_data, str):
                        print(f"    Response: {response_data[:200]}")
            
            result = {
                "name": name,
                "method": method,
                "endpoint": endpoint,
                "status": response.status_code,
                "success": success and not issues,
                "elapsed": elapsed,
                "issues": issues,
                "response_sample": str(response_data)[:200] if response_data else None
            }
            
        except requests.exceptions.RequestException as e:
            self.failed += 1
            elapsed = time.time() - start_time
            print(f"    {Colors.RED}✗ ERROR{Colors.RESET} - {str(e)[:100]}")
            result = {
                "name": name,
                "method": method,
                "endpoint": endpoint,
                "status": None,
                "success": False,
                "elapsed": elapsed,
                "issues": [str(e)],
                "response_sample": None
            }
        
        self.results.append(result)
        return result
    
    def run_all_tests(self):
        """Run tests for all endpoints."""
        print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 80}")
        print(f"PANTRY PIRATE RADIO - COMPLETE API TEST")
        print(f"Target: {self.base_url}")
        print(f"Time: {datetime.now().isoformat()}")
        print(f"{'=' * 80}{Colors.RESET}")
        
        # Test data
        sample_uuid = str(uuid.uuid4())
        valid_lat = 40.7128
        valid_lng = -74.0060
        
        # ============ HEALTH & MONITORING ============
        print(f"\n{Colors.BOLD}{Colors.MAGENTA}━━━ HEALTH & MONITORING ENDPOINTS ━━━{Colors.RESET}")
        
        self.test("GET", "/api/v1/", "API Root Metadata")
        self.test("GET", "/api/v1/health", "Health Check")
        self.test("GET", "/api/v1/health/db", "Database Health")
        self.test("GET", "/api/v1/health/redis", "Redis Health")
        self.test("GET", "/api/v1/health/llm", "LLM Health")
        self.test("GET", "/api/v1/metrics", "Prometheus Metrics")
        
        # ============ ORGANIZATIONS ============
        print(f"\n{Colors.BOLD}{Colors.MAGENTA}━━━ ORGANIZATION ENDPOINTS ━━━{Colors.RESET}")
        
        self.test("GET", "/api/v1/organizations/", "List Organizations")
        self.test("GET", "/api/v1/organizations/", "List Organizations (Paginated)", 
                  params={"page": 1, "per_page": 5})
        self.test("GET", "/api/v1/organizations/", "List Organizations (With Services)", 
                  params={"include_services": True})
        self.test("GET", "/api/v1/organizations/", "Filter Organizations by Name", 
                  params={"name": "food"})
        self.test("GET", "/api/v1/organizations/search", "Search Organizations", 
                  params={"q": "pantry"})
        self.test("GET", f"/api/v1/organizations/{sample_uuid}", "Get Organization by ID", 
                  expected_status=[404])  # Expect 404 for random UUID
        
        # ============ LOCATIONS ============
        print(f"\n{Colors.BOLD}{Colors.MAGENTA}━━━ LOCATION ENDPOINTS ━━━{Colors.RESET}")
        
        self.test("GET", "/api/v1/locations/", "List Locations")
        self.test("GET", "/api/v1/locations/", "List Locations (Paginated)", 
                  params={"page": 1, "per_page": 10})
        self.test("GET", "/api/v1/locations/", "List Locations (Include Schedule)", 
                  params={"include_schedule": True})
        self.test("GET", "/api/v1/locations/", "Filter Locations by Organization", 
                  params={"organization_id": sample_uuid})
        
        # Location search endpoints
        self.test("GET", "/api/v1/locations/search", "Search Locations (Radius)", 
                  params={"latitude": valid_lat, "longitude": valid_lng, "radius_miles": 10})
        self.test("GET", "/api/v1/locations/search", "Search Locations (Bounding Box)", 
                  params={
                      "min_latitude": valid_lat - 0.5,
                      "max_latitude": valid_lat + 0.5,
                      "min_longitude": valid_lng - 0.5,
                      "max_longitude": valid_lng + 0.5
                  })
        self.test("GET", "/api/v1/locations/search", "Search Locations (Text)", 
                  params={"q": "church"})
        
        # Export endpoints
        # Note: /export endpoint was removed as deprecated
        self.test("GET", "/api/v1/locations/export-simple", "Export Simple Format")
        
        self.test("GET", f"/api/v1/locations/{sample_uuid}", "Get Location by ID", 
                  expected_status=[404])
        
        # ============ SERVICES ============
        print(f"\n{Colors.BOLD}{Colors.MAGENTA}━━━ SERVICE ENDPOINTS ━━━{Colors.RESET}")
        
        self.test("GET", "/api/v1/services/", "List Services")
        self.test("GET", "/api/v1/services/", "List Services (Paginated)", 
                  params={"page": 1, "per_page": 10})
        self.test("GET", "/api/v1/services/active", "List Active Services")
        self.test("GET", "/api/v1/services/search", "Search Services", 
                  params={"q": "meal"})
        self.test("GET", f"/api/v1/services/{sample_uuid}", "Get Service by ID", 
                  expected_status=[404])
        
        # ============ SERVICE-AT-LOCATION ============
        print(f"\n{Colors.BOLD}{Colors.MAGENTA}━━━ SERVICE-AT-LOCATION ENDPOINTS ━━━{Colors.RESET}")
        
        self.test("GET", "/api/v1/service-at-location/", "List Service-at-Location")
        self.test("GET", f"/api/v1/service-at-location/{sample_uuid}", "Get Service-at-Location by ID", 
                  expected_status=[404])
        self.test("GET", f"/api/v1/service-at-location/location/{sample_uuid}/services", 
                  "Get Services at Location")
        self.test("GET", f"/api/v1/service-at-location/service/{sample_uuid}/locations", 
                  "Get Locations for Service")
        
        # ============ MAP ENDPOINTS ============
        print(f"\n{Colors.BOLD}{Colors.MAGENTA}━━━ MAP ENDPOINTS ━━━{Colors.RESET}")
        
        self.test("GET", "/api/v1/map/metadata", "Map Metadata")
        self.test("GET", "/api/v1/map/states", "States Coverage")
        self.test("GET", "/api/v1/map/locations", "Map Locations")
        self.test("GET", "/api/v1/map/locations", "Map Locations (Filtered)", 
                  params={
                      "min_lat": valid_lat - 1,
                      "max_lat": valid_lat + 1,
                      "min_lng": valid_lng - 1,
                      "max_lng": valid_lng + 1
                  })
        self.test("GET", "/api/v1/map/clusters", "Map Clusters", 
                  params={
                      "min_lat": valid_lat - 1,
                      "max_lat": valid_lat + 1,
                      "min_lng": valid_lng - 1,
                      "max_lng": valid_lng + 1,
                      "zoom": 10
                  })
        self.test("GET", f"/api/v1/map/locations/{sample_uuid}", "Map Location Detail", 
                  expected_status=[404])
        self.test("GET", "/api/v1/map/search", "Map Search", 
                  params={"q": "food pantry"})
        self.test("GET", "/api/v1/map/geolocate", "Geolocate IP Address",
                  params={"ip": "8.8.8.8"})
        
        # ============ TAXONOMY ENDPOINTS ============
        print(f"\n{Colors.BOLD}{Colors.MAGENTA}━━━ TAXONOMY ENDPOINTS ━━━{Colors.RESET}")
        
        self.test("GET", "/api/v1/taxonomies/", "List Taxonomies")
        self.test("GET", f"/api/v1/taxonomies/{sample_uuid}", "Get Taxonomy by ID", 
                  expected_status=[404])
        self.test("GET", "/api/v1/taxonomy-terms/", "List Taxonomy Terms")
        self.test("GET", f"/api/v1/taxonomy-terms/{sample_uuid}", "Get Taxonomy Term by ID", 
                  expected_status=[404])
        
        # ============ EDGE CASES & ERROR HANDLING ============
        print(f"\n{Colors.BOLD}{Colors.MAGENTA}━━━ EDGE CASES & ERROR HANDLING ━━━{Colors.RESET}")
        
        # Invalid pagination
        self.test("GET", "/api/v1/organizations/", "Invalid Page Number", 
                  params={"page": -1}, expected_status=[422, 400])
        self.test("GET", "/api/v1/organizations/", "Invalid Per Page", 
                  params={"per_page": 1000}, expected_status=[422, 400, 200])  # Might be clamped
        
        # Invalid coordinates
        self.test("GET", "/api/v1/locations/search", "Invalid Coordinates", 
                  params={"latitude": 999, "longitude": 999}, expected_status=[422, 400, 200])
        
        # SQL injection attempts (should be safely handled)
        self.test("GET", "/api/v1/organizations/search", "SQL Injection Test", 
                  params={"q": "'; DROP TABLE organizations; --"})
        
        # XSS attempt (should be safely handled)
        self.test("GET", "/api/v1/organizations/search", "XSS Test", 
                  params={"q": "<script>alert('xss')</script>"})
        
        # Large radius search (within our 1000 mile limit)
        self.test("GET", "/api/v1/locations/search", "Very Large Radius",
                  params={"latitude": valid_lat, "longitude": valid_lng, "radius_miles": 999})
        
        # Empty search
        self.test("GET", "/api/v1/organizations/search", "Empty Search", 
                  params={"q": ""})
        
        # Unicode search
        self.test("GET", "/api/v1/organizations/search", "Unicode Search", 
                  params={"q": "食物銀行 🍔"})
        
        self.print_summary()
    
    def print_summary(self):
        """Print test summary and generate reports."""
        print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 80}")
        print(f"TEST SUMMARY")
        print(f"{'=' * 80}{Colors.RESET}")
        
        print(f"\nTotal Tests: {self.total}")
        print(f"{Colors.GREEN}Passed: {self.passed}{Colors.RESET}")
        print(f"{Colors.RED}Failed: {self.failed}{Colors.RESET}")
        
        if self.total > 0:
            success_rate = (self.passed / self.total) * 100
            color = Colors.GREEN if success_rate >= 80 else Colors.YELLOW if success_rate >= 50 else Colors.RED
            print(f"\n{color}Success Rate: {success_rate:.1f}%{Colors.RESET}")
        
        # Failed endpoints
        if self.failed > 0:
            print(f"\n{Colors.RED}FAILED ENDPOINTS:{Colors.RESET}")
            for result in self.results:
                if not result["success"]:
                    print(f"\n  • {result['name']}")
                    print(f"    {result['method']} {result['endpoint']}")
                    if result["issues"]:
                        for issue in result["issues"]:
                            print(f"    - {issue}")
        
        # Performance stats
        print(f"\n{Colors.CYAN}PERFORMANCE:{Colors.RESET}")
        response_times = [r["elapsed"] for r in self.results if r["elapsed"]]
        if response_times:
            print(f"  Average: {sum(response_times)/len(response_times):.2f}s")
            print(f"  Fastest: {min(response_times):.2f}s")
            print(f"  Slowest: {max(response_times):.2f}s")
        
        # Generate JSON report
        self.generate_json_report()
    
    def generate_json_report(self):
        """Generate detailed JSON report."""
        report = {
            "timestamp": datetime.now().isoformat(),
            "base_url": self.base_url,
            "summary": {
                "total": self.total,
                "passed": self.passed,
                "failed": self.failed,
                "success_rate": (self.passed / self.total * 100) if self.total > 0 else 0
            },
            "results": self.results
        }
        
        filename = f"api_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, "w") as f:
            json.dump(report, f, indent=2, default=str)
        
        print(f"\n{Colors.GREEN}JSON report saved: {filename}{Colors.RESET}")
        
        # Also create a summary of issues
        issues_summary = {}
        for result in self.results:
            if not result["success"]:
                endpoint = f"{result['method']} {result['endpoint']}"
                issues_summary[endpoint] = {
                    "name": result["name"],
                    "status": result["status"],
                    "issues": result["issues"],
                    "response_sample": result["response_sample"]
                }
        
        if issues_summary:
            with open("api_issues_current.json", "w") as f:
                json.dump(issues_summary, f, indent=2, default=str)
            print(f"{Colors.YELLOW}Issues summary saved: api_issues_current.json{Colors.RESET}")

def main():
    """Main entry point."""
    print(f"{Colors.BOLD}{Colors.CYAN}Starting Comprehensive API Test...{Colors.RESET}\n")
    
    tester = EndpointTester()
    
    try:
        tester.run_all_tests()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Tests interrupted by user{Colors.RESET}")
        tester.print_summary()
    except Exception as e:
        print(f"\n{Colors.RED}Unexpected error: {e}{Colors.RESET}")
        traceback.print_exc()
        tester.print_summary()
    
    # Exit code based on results
    sys.exit(0 if tester.failed == 0 else 1)

if __name__ == "__main__":
    main()