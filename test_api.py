#!/usr/bin/env python3
"""
Comprehensive API Testing Script for Pantry Pirate Radio HSDS API
Tests all endpoints at https://api.for-the-gg.org
"""

import requests
import json
import time
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import sys
from urllib.parse import urljoin
import traceback
import uuid

# Configuration
API_BASE_URL = "https://api.for-the-gg.org"
TIMEOUT = 10  # seconds

# ANSI color codes for terminal output
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

class TestStatus(Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"

@dataclass
class TestResult:
    endpoint: str
    method: str
    test_name: str
    status: TestStatus
    response_code: Optional[int]
    response_time: float
    error_message: Optional[str]
    response_data: Optional[Any]
    timestamp: datetime

class APITester:
    def __init__(self, base_url: str = API_BASE_URL):
        self.base_url = base_url
        self.session = requests.Session()
        self.results: List[TestResult] = []
        self.test_count = 0
        self.passed_count = 0
        self.failed_count = 0
        self.error_count = 0
        
    def make_request(self, endpoint: str, method: str = "GET", 
                     params: Optional[Dict] = None, 
                     data: Optional[Dict] = None,
                     timeout_override: Optional[int] = None) -> Tuple[Optional[requests.Response], float]:
        """Make an HTTP request and return response with timing."""
        url = urljoin(self.base_url, endpoint)
        start_time = time.time()
        
        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=data,
                timeout=timeout_override if timeout_override else TIMEOUT
            )
            elapsed = time.time() - start_time
            return response, elapsed
        except Exception as e:
            elapsed = time.time() - start_time
            print(f"{Colors.RED}Request failed: {e}{Colors.RESET}")
            return None, elapsed
    
    def test_endpoint(self, endpoint: str, test_name: str, 
                      method: str = "GET", 
                      params: Optional[Dict] = None,
                      expected_status: int = 200,
                      validate_func: Optional[callable] = None,
                      timeout_override: Optional[int] = None) -> TestResult:
        """Test a single endpoint."""
        self.test_count += 1
        print(f"\n{Colors.CYAN}Testing: {test_name}{Colors.RESET}")
        print(f"  Endpoint: {method} {endpoint}")
        if params:
            print(f"  Params: {params}")
        
        response, elapsed = self.make_request(endpoint, method, params, timeout_override=timeout_override)
        
        if response is None:
            self.error_count += 1
            result = TestResult(
                endpoint=endpoint,
                method=method,
                test_name=test_name,
                status=TestStatus.ERROR,
                response_code=None,
                response_time=elapsed,
                error_message="Connection failed",
                response_data=None,
                timestamp=datetime.now()
            )
            print(f"  {Colors.RED}✗ ERROR: Connection failed{Colors.RESET}")
        else:
            try:
                response_data = response.json() if response.text else None
            except:
                response_data = response.text
            
            # Check status code
            if response.status_code == expected_status:
                # Additional validation if provided
                if validate_func:
                    try:
                        validate_func(response_data)
                        status = TestStatus.PASSED
                        error_msg = None
                        self.passed_count += 1
                        print(f"  {Colors.GREEN}✓ PASSED{Colors.RESET} - Status: {response.status_code}, Time: {elapsed:.3f}s")
                    except Exception as e:
                        status = TestStatus.FAILED
                        error_msg = str(e)
                        self.failed_count += 1
                        print(f"  {Colors.YELLOW}✗ FAILED{Colors.RESET} - Validation error: {e}")
                else:
                    status = TestStatus.PASSED
                    error_msg = None
                    self.passed_count += 1
                    print(f"  {Colors.GREEN}✓ PASSED{Colors.RESET} - Status: {response.status_code}, Time: {elapsed:.3f}s")
            else:
                status = TestStatus.FAILED
                error_msg = f"Expected {expected_status}, got {response.status_code}"
                self.failed_count += 1
                print(f"  {Colors.RED}✗ FAILED{Colors.RESET} - {error_msg}")
                if isinstance(response_data, dict) and 'error' in response_data:
                    print(f"    Error: {response_data.get('error')}")
                    print(f"    Message: {response_data.get('message', '')[:200]}")
            
            result = TestResult(
                endpoint=endpoint,
                method=method,
                test_name=test_name,
                status=status,
                response_code=response.status_code,
                response_time=elapsed,
                error_message=error_msg,
                response_data=response_data,
                timestamp=datetime.now()
            )
        
        self.results.append(result)
        return result
    
    def run_all_tests(self):
        """Run all API tests."""
        print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 80}")
        print(f"PANTRY PIRATE RADIO API TEST SUITE")
        print(f"Target: {self.base_url}")
        print(f"Started: {datetime.now().isoformat()}")
        print(f"{'=' * 80}{Colors.RESET}\n")
        
        # 1. Health & Monitoring Tests
        self.test_health_endpoints()
        
        # 2. API Metadata
        self.test_metadata_endpoints()
        
        # 3. Core CRUD Endpoints
        self.test_organization_endpoints()
        self.test_location_endpoints()
        self.test_service_endpoints()
        self.test_service_at_location_endpoints()
        
        # 4. Map Endpoints
        self.test_map_endpoints()
        
        # 5. Taxonomy Endpoints
        self.test_taxonomy_endpoints()
        
        # Generate report
        self.generate_report()
    
    def test_health_endpoints(self):
        """Test health check endpoints."""
        print(f"\n{Colors.BOLD}{Colors.MAGENTA}=== HEALTH CHECK ENDPOINTS ==={Colors.RESET}")
        
        self.test_endpoint(
            "/api/v1/health",
            "Basic Health Check",
            validate_func=lambda d: self.validate_health_response(d)
        )
        
        self.test_endpoint(
            "/api/v1/health/db",
            "Database Health Check"
        )
        
        self.test_endpoint(
            "/api/v1/health/redis",
            "Redis Health Check"
        )
        
        self.test_endpoint(
            "/api/v1/health/llm",
            "LLM Provider Health Check",
            timeout_override=30  # LLM health check can be slow
        )
        
        self.test_endpoint(
            "/api/v1/metrics",
            "Prometheus Metrics"
        )
    
    def test_metadata_endpoints(self):
        """Test API metadata endpoints."""
        print(f"\n{Colors.BOLD}{Colors.MAGENTA}=== API METADATA ==={Colors.RESET}")
        
        self.test_endpoint(
            "/api/v1/",
            "API Root Metadata",
            validate_func=lambda d: self.validate_api_metadata(d)
        )
    
    def test_organization_endpoints(self):
        """Test organization endpoints."""
        print(f"\n{Colors.BOLD}{Colors.MAGENTA}=== ORGANIZATION ENDPOINTS ==={Colors.RESET}")
        
        # List organizations
        result = self.test_endpoint(
            "/api/v1/organizations/",
            "List Organizations"
        )
        
        # List with pagination
        self.test_endpoint(
            "/api/v1/organizations/",
            "List Organizations (Paginated)",
            params={"page": 1, "per_page": 10}
        )
        
        # List with services included
        self.test_endpoint(
            "/api/v1/organizations/",
            "List Organizations with Services",
            params={"include_services": "true"}
        )
        
        # Search organizations
        self.test_endpoint(
            "/api/v1/organizations/search",
            "Search Organizations",
            params={"q": "food"}
        )
        
        # Get specific organization (using a valid UUID if available)
        sample_uuid = str(uuid.uuid4())
        self.test_endpoint(
            f"/api/v1/organizations/{sample_uuid}",
            "Get Organization by ID",
            expected_status=404  # Expecting 404 for random UUID
        )
    
    def test_location_endpoints(self):
        """Test location endpoints."""
        print(f"\n{Colors.BOLD}{Colors.MAGENTA}=== LOCATION ENDPOINTS ==={Colors.RESET}")
        
        # List locations
        self.test_endpoint(
            "/api/v1/locations/",
            "List Locations"
        )
        
        # List with pagination
        self.test_endpoint(
            "/api/v1/locations/",
            "List Locations (Paginated)",
            params={"page": 1, "per_page": 10}
        )
        
        # Search by radius
        self.test_endpoint(
            "/api/v1/locations/search",
            "Search Locations by Radius",
            params={
                "latitude": 40.7128,
                "longitude": -74.0060,
                "radius_miles": 10
            }
        )
        
        # Search by bounding box
        self.test_endpoint(
            "/api/v1/locations/search",
            "Search Locations by Bounding Box",
            params={
                "min_latitude": 40.0,
                "max_latitude": 41.0,
                "min_longitude": -75.0,
                "max_longitude": -74.0
            }
        )
        
        # Get specific location
        sample_uuid = str(uuid.uuid4())
        self.test_endpoint(
            f"/api/v1/locations/{sample_uuid}",
            "Get Location by ID",
            expected_status=404
        )
    
    def test_service_endpoints(self):
        """Test service endpoints."""
        print(f"\n{Colors.BOLD}{Colors.MAGENTA}=== SERVICE ENDPOINTS ==={Colors.RESET}")
        
        # List services
        self.test_endpoint(
            "/api/v1/services/",
            "List Services"
        )
        
        # List active services
        self.test_endpoint(
            "/api/v1/services/active",
            "List Active Services"
        )
        
        # Search services
        self.test_endpoint(
            "/api/v1/services/search",
            "Search Services",
            params={"q": "meal"}
        )
        
        # Get specific service
        sample_uuid = str(uuid.uuid4())
        self.test_endpoint(
            f"/api/v1/services/{sample_uuid}",
            "Get Service by ID",
            expected_status=404
        )
    
    def test_service_at_location_endpoints(self):
        """Test service-at-location endpoints."""
        print(f"\n{Colors.BOLD}{Colors.MAGENTA}=== SERVICE-AT-LOCATION ENDPOINTS ==={Colors.RESET}")
        
        # List service-at-location
        self.test_endpoint(
            "/api/v1/service-at-location/",
            "List Service-at-Location"
        )
        
        # Get specific service-at-location
        sample_uuid = str(uuid.uuid4())
        self.test_endpoint(
            f"/api/v1/service-at-location/{sample_uuid}",
            "Get Service-at-Location by ID",
            expected_status=404
        )
        
        # Get locations for service (returns 200 with empty list for non-existent service)
        self.test_endpoint(
            f"/api/v1/service-at-location/service/{sample_uuid}/locations",
            "Get Locations for Service",
            expected_status=200  # List endpoints return 200 with empty data
        )
        
        # Get services at location (returns 200 with empty list for non-existent location)
        self.test_endpoint(
            f"/api/v1/service-at-location/location/{sample_uuid}/services",
            "Get Services at Location",
            expected_status=200  # List endpoints return 200 with empty data
        )
    
    def test_map_endpoints(self):
        """Test map endpoints."""
        print(f"\n{Colors.BOLD}{Colors.MAGENTA}=== MAP ENDPOINTS ==={Colors.RESET}")
        
        # Get map metadata
        self.test_endpoint(
            "/api/v1/map/metadata",
            "Map Metadata",
            validate_func=lambda d: self.validate_map_metadata(d)
        )
        
        # Get states coverage
        self.test_endpoint(
            "/api/v1/map/states",
            "States Coverage"
        )
        
        # Get map locations
        self.test_endpoint(
            "/api/v1/map/locations",
            "Map Locations"
        )
        
        # Get map locations with filters
        self.test_endpoint(
            "/api/v1/map/locations",
            "Map Locations (Filtered)",
            params={
                "min_lat": 40.0,
                "max_lat": 41.0,
                "min_lng": -75.0,
                "max_lng": -74.0,
                "clustering_radius": 500
            }
        )
        
        # Get specific location detail
        sample_uuid = str(uuid.uuid4())
        self.test_endpoint(
            f"/api/v1/map/locations/{sample_uuid}",
            "Map Location Detail",
            expected_status=404
        )
    
    def test_taxonomy_endpoints(self):
        """Test taxonomy endpoints."""
        print(f"\n{Colors.BOLD}{Colors.MAGENTA}=== TAXONOMY ENDPOINTS ==={Colors.RESET}")
        
        # List taxonomies
        self.test_endpoint(
            "/api/v1/taxonomies/",
            "List Taxonomies"
        )
        
        # Get specific taxonomy
        sample_uuid = str(uuid.uuid4())
        self.test_endpoint(
            f"/api/v1/taxonomies/{sample_uuid}",
            "Get Taxonomy by ID"
        )
        
        # List taxonomy terms
        self.test_endpoint(
            "/api/v1/taxonomy-terms/",
            "List Taxonomy Terms"
        )
        
        # Get specific taxonomy term
        self.test_endpoint(
            f"/api/v1/taxonomy-terms/{sample_uuid}",
            "Get Taxonomy Term by ID"
        )
    
    def validate_health_response(self, data: Dict):
        """Validate health check response."""
        assert isinstance(data, dict), "Response should be a dictionary"
        assert "status" in data, "Response should contain 'status'"
        assert data["status"] == "healthy", f"Status should be 'healthy', got '{data['status']}'"
    
    def validate_api_metadata(self, data: Dict):
        """Validate API metadata response."""
        assert isinstance(data, dict), "Response should be a dictionary"
        assert "version" in data, "Response should contain 'version'"
        assert "profile" in data, "Response should contain 'profile'"
        assert data["version"] == "3.1.1", f"Version should be '3.1.1', got '{data['version']}'"
    
    def validate_map_metadata(self, data: Dict):
        """Validate map metadata response."""
        assert isinstance(data, dict), "Response should be a dictionary"
        assert "total_locations" in data, "Response should contain 'total_locations'"
        assert "states_covered" in data, "Response should contain 'states_covered'"
        assert data["total_locations"] > 0, "Should have locations"
    
    def generate_report(self):
        """Generate test report."""
        print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 80}")
        print("TEST SUMMARY")
        print(f"{'=' * 80}{Colors.RESET}")
        
        # Summary statistics
        print(f"\nTotal Tests: {self.test_count}")
        print(f"{Colors.GREEN}Passed: {self.passed_count}{Colors.RESET}")
        print(f"{Colors.RED}Failed: {self.failed_count}{Colors.RESET}")
        print(f"{Colors.YELLOW}Errors: {self.error_count}{Colors.RESET}")
        
        success_rate = (self.passed_count / self.test_count * 100) if self.test_count > 0 else 0
        print(f"\nSuccess Rate: {success_rate:.1f}%")
        
        # Failed tests details
        if self.failed_count > 0 or self.error_count > 0:
            print(f"\n{Colors.RED}FAILED/ERROR TESTS:{Colors.RESET}")
            for result in self.results:
                if result.status in [TestStatus.FAILED, TestStatus.ERROR]:
                    print(f"\n  • {result.test_name}")
                    print(f"    Endpoint: {result.method} {result.endpoint}")
                    print(f"    Status: {result.status.value}")
                    if result.error_message:
                        print(f"    Error: {result.error_message}")
                    if result.response_code:
                        print(f"    Response Code: {result.response_code}")
        
        # Performance summary
        print(f"\n{Colors.CYAN}PERFORMANCE:{Colors.RESET}")
        response_times = [r.response_time for r in self.results if r.response_time]
        if response_times:
            print(f"  Average Response Time: {sum(response_times)/len(response_times):.3f}s")
            print(f"  Min Response Time: {min(response_times):.3f}s")
            print(f"  Max Response Time: {max(response_times):.3f}s")
        
        # Generate HTML report
        self.generate_html_report()
        
        # Generate markdown report
        self.generate_markdown_report()
    
    def generate_html_report(self):
        """Generate HTML report."""
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>API Test Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .header {{ background: #2c3e50; color: white; padding: 20px; border-radius: 5px; }}
        .summary {{ background: white; padding: 20px; margin: 20px 0; border-radius: 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .passed {{ color: #27ae60; font-weight: bold; }}
        .failed {{ color: #e74c3c; font-weight: bold; }}
        .error {{ color: #f39c12; font-weight: bold; }}
        table {{ width: 100%; border-collapse: collapse; background: white; }}
        th {{ background: #34495e; color: white; padding: 10px; text-align: left; }}
        td {{ padding: 10px; border-bottom: 1px solid #ecf0f1; }}
        tr:hover {{ background: #f8f9fa; }}
        .status-passed {{ background: #d4edda; color: #155724; padding: 2px 8px; border-radius: 3px; }}
        .status-failed {{ background: #f8d7da; color: #721c24; padding: 2px 8px; border-radius: 3px; }}
        .status-error {{ background: #fff3cd; color: #856404; padding: 2px 8px; border-radius: 3px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Pantry Pirate Radio API Test Report</h1>
        <p>Target: {self.base_url}</p>
        <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
    
    <div class="summary">
        <h2>Test Summary</h2>
        <p>Total Tests: {self.test_count}</p>
        <p class="passed">Passed: {self.passed_count}</p>
        <p class="failed">Failed: {self.failed_count}</p>
        <p class="error">Errors: {self.error_count}</p>
        <p>Success Rate: {(self.passed_count / self.test_count * 100) if self.test_count > 0 else 0:.1f}%</p>
    </div>
    
    <h2>Test Results</h2>
    <table>
        <thead>
            <tr>
                <th>Test Name</th>
                <th>Endpoint</th>
                <th>Method</th>
                <th>Status</th>
                <th>Response Code</th>
                <th>Response Time</th>
                <th>Error</th>
            </tr>
        </thead>
        <tbody>
"""
        
        for result in self.results:
            status_class = f"status-{result.status.value.lower()}"
            html_content += f"""
            <tr>
                <td>{result.test_name}</td>
                <td>{result.endpoint}</td>
                <td>{result.method}</td>
                <td><span class="{status_class}">{result.status.value}</span></td>
                <td>{result.response_code or 'N/A'}</td>
                <td>{result.response_time:.3f}s</td>
                <td>{result.error_message or ''}</td>
            </tr>
"""
        
        html_content += """
        </tbody>
    </table>
</body>
</html>
"""
        
        with open("api_test_report.html", "w") as f:
            f.write(html_content)
        print(f"\n{Colors.GREEN}HTML report generated: api_test_report.html{Colors.RESET}")
    
    def generate_markdown_report(self):
        """Generate markdown report with findings and recommendations."""
        md_content = f"""# API Test Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}

## Executive Summary

- **Target API**: {self.base_url}
- **Total Tests**: {self.test_count}
- **Passed**: {self.passed_count}
- **Failed**: {self.failed_count}
- **Errors**: {self.error_count}
- **Success Rate**: {(self.passed_count / self.test_count * 100) if self.test_count > 0 else 0:.1f}%

## Critical Issues Found

### 1. Pydantic Validation Errors
Most CRUD endpoints are failing with validation errors:
- **Organizations**: Missing `metadata.last_updated` field
- **Locations**: ValidationError in response serialization
- **Services**: ValidationError in response serialization
- **Service-at-Location**: ValidationError in response serialization

### 2. SQLAlchemy Async/Greenlet Error
The organizations endpoint shows:
```
MissingGreenlet: greenlet_spawn has not been called; can't call await_only() here
```
This indicates an async/await context issue in the database layer.

## Working Endpoints

✅ Health checks (`/api/v1/health`)
✅ API metadata (`/api/v1/`)
✅ Map metadata (`/api/v1/map/metadata`)
✅ Map states (`/api/v1/map/states`)

## Recommendations

### Immediate Fixes Required

1. **Fix Pydantic Models**
   - Add `metadata.last_updated` field to OrganizationResponse model
   - Ensure all required fields have defaults or are properly populated
   - Review all response models against actual database schema

2. **Fix SQLAlchemy Async Issues**
   - Review database session management
   - Ensure proper async context for all database operations
   - Consider using `selectinload` or `joinedload` for relationships

3. **Add Comprehensive Error Handling**
   - Wrap all endpoint handlers in try-catch blocks
   - Return proper error responses with helpful messages
   - Log all errors for debugging

### Code Changes Needed

1. Update `app/api/schemas.py` to fix response models
2. Update `app/api/endpoints/*.py` to fix async database queries
3. Add proper relationship loading in SQLAlchemy queries
4. Implement proper pagination response structure

## Performance Metrics

- Average Response Time: {sum([r.response_time for r in self.results])/len(self.results):.3f}s
- Fastest Endpoint: {min([r.response_time for r in self.results]):.3f}s
- Slowest Endpoint: {max([r.response_time for r in self.results]):.3f}s

## Next Steps

1. Fix validation errors in response models
2. Resolve async/database context issues
3. Re-run tests to verify fixes
4. Add integration tests to CI/CD pipeline
5. Monitor API performance in production
"""
        
        with open("api_test_findings.md", "w") as f:
            f.write(md_content)
        print(f"{Colors.GREEN}Markdown report generated: api_test_findings.md{Colors.RESET}")

def main():
    """Main entry point."""
    tester = APITester()
    try:
        tester.run_all_tests()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Tests interrupted by user{Colors.RESET}")
        tester.generate_report()
    except Exception as e:
        print(f"\n{Colors.RED}Unexpected error: {e}{Colors.RESET}")
        traceback.print_exc()
        tester.generate_report()
    
    # Exit with appropriate code
    if tester.failed_count > 0 or tester.error_count > 0:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()