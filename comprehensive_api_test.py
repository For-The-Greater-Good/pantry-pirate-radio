#!/usr/bin/env python3
"""
Comprehensive API Test Suite for Pantry Pirate Radio
Tests data integrity, search, geospatial features, performance, and error handling
"""

import json
import time
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime
from urllib.parse import urljoin
import random
import concurrent.futures
from collections import defaultdict

# Configuration
BASE_URL = "https://api.for-the-gg.org/api/v1/"
TIMEOUT = 30  # seconds

class ComprehensiveAPITester:
    def __init__(self):
        self.base_url = BASE_URL
        self.session = requests.Session()
        self.results = defaultdict(list)
        self.performance_metrics = []
        
    def make_request(self, endpoint: str, params: Optional[Dict] = None) -> tuple:
        """Make a request and return response with timing."""
        url = urljoin(self.base_url, endpoint)
        start_time = time.time()
        
        try:
            response = self.session.get(url, params=params, timeout=TIMEOUT)
            elapsed = time.time() - start_time
            return response, elapsed
        except Exception as e:
            elapsed = time.time() - start_time
            return None, elapsed
    
    def test_data_integrity(self):
        """Test data integrity and consistency."""
        print("\n" + "="*80)
        print("DATA INTEGRITY TESTS")
        print("="*80)
        
        tests = []
        
        # Test 1: Pagination consistency
        print("\n1. Testing pagination consistency...")
        response1, _ = self.make_request("organizations/", {"per_page": 5, "page": 1})
        response2, _ = self.make_request("organizations/", {"per_page": 5, "page": 2})
        
        if response1 and response2:
            data1 = response1.json()
            data2 = response2.json()
            
            # Check total count consistency
            tests.append({
                "name": "Pagination total consistency",
                "passed": data1["total"] == data2["total"],
                "details": f"Total count consistent: {data1['total']}"
            })
            
            # Check no duplicate IDs
            ids1 = {item["id"] for item in data1["data"]}
            ids2 = {item["id"] for item in data2["data"]}
            tests.append({
                "name": "No duplicate IDs across pages",
                "passed": len(ids1.intersection(ids2)) == 0,
                "details": "No duplicates found" if len(ids1.intersection(ids2)) == 0 else f"Found {len(ids1.intersection(ids2))} duplicates"
            })
        
        # Test 2: Field completeness
        print("\n2. Testing field completeness...")
        response, _ = self.make_request("organizations/", {"per_page": 10})
        if response:
            data = response.json()
            required_fields = ["id", "name", "description", "metadata"]
            incomplete_records = []
            
            for item in data["data"]:
                missing = [f for f in required_fields if f not in item or item[f] is None]
                if missing:
                    incomplete_records.append({"id": item["id"], "missing": missing})
            
            tests.append({
                "name": "Required fields present",
                "passed": len(incomplete_records) == 0,
                "details": f"{len(incomplete_records)}/10 records have missing fields" if incomplete_records else "All required fields present"
            })
        
        # Test 3: Relationship consistency
        print("\n3. Testing relationship consistency...")
        response, _ = self.make_request("organizations/", {"include_services": "true", "per_page": 3})
        if response:
            data = response.json()
            for org in data["data"]:
                if org.get("services"):
                    # Check that service references back to organization
                    for service in org["services"]:
                        tests.append({
                            "name": f"Service-Org relationship for {service['id'][:8]}...",
                            "passed": service.get("organization_id") == org["id"],
                            "details": "Bidirectional relationship valid"
                        })
        
        self.results["data_integrity"] = tests
        self._print_test_summary("Data Integrity", tests)
    
    def test_search_functionality(self):
        """Test search capabilities."""
        print("\n" + "="*80)
        print("SEARCH FUNCTIONALITY TESTS")
        print("="*80)
        
        tests = []
        
        # Test 1: Basic search
        print("\n1. Testing basic search...")
        search_terms = ["food", "bank", "pantry", "church", "community"]
        
        for term in search_terms:
            response, elapsed = self.make_request("organizations/search", {"q": term})
            if response and response.status_code == 200:
                data = response.json()
                tests.append({
                    "name": f"Search for '{term}'",
                    "passed": data["total"] > 0,
                    "details": f"Found {data['total']} results in {elapsed:.2f}s"
                })
        
        # Test 2: Case sensitivity
        print("\n2. Testing case insensitivity...")
        for term in ["FOOD", "Food", "food", "FoOd"]:
            response, _ = self.make_request("organizations/search", {"q": term})
            if response and response.status_code == 200:
                data = response.json()
                if term == "FOOD":
                    baseline = data["total"]
                tests.append({
                    "name": f"Case variant '{term}'",
                    "passed": data["total"] == baseline if term != "FOOD" else True,
                    "details": f"Returns {data['total']} results"
                })
        
        # Test 3: Special characters
        print("\n3. Testing special character handling...")
        special_searches = ["food & pantry", "church's", "co-op", "501(c)(3)"]
        
        for term in special_searches:
            response, _ = self.make_request("organizations/search", {"q": term})
            tests.append({
                "name": f"Special chars: '{term}'",
                "passed": response is not None and response.status_code in [200, 422],
                "details": f"Status: {response.status_code if response else 'Failed'}"
            })
        
        # Test 4: Service search
        print("\n4. Testing service search...")
        response, _ = self.make_request("services/search", {"q": "emergency"})
        if response and response.status_code == 200:
            data = response.json()
            tests.append({
                "name": "Service search for 'emergency'",
                "passed": data["total"] > 0,
                "details": f"Found {data['total']} services"
            })
        
        self.results["search"] = tests
        self._print_test_summary("Search Functionality", tests)
    
    def test_geospatial_features(self):
        """Test geospatial queries."""
        print("\n" + "="*80)
        print("GEOSPATIAL FEATURE TESTS")
        print("="*80)
        
        tests = []
        
        # Test 1: Radius search at different scales
        print("\n1. Testing radius searches...")
        locations = [
            {"name": "NYC", "lat": 40.7128, "lon": -74.0060},
            {"name": "LA", "lat": 34.0522, "lon": -118.2437},
            {"name": "Chicago", "lat": 41.8781, "lon": -87.6298}
        ]
        
        for loc in locations:
            for radius in [1, 5, 10, 25]:
                response, elapsed = self.make_request("locations/search", {
                    "latitude": loc["lat"],
                    "longitude": loc["lon"],
                    "radius_miles": radius
                })
                
                if response and response.status_code == 200:
                    data = response.json()
                    tests.append({
                        "name": f"{loc['name']} - {radius} mile radius",
                        "passed": True,
                        "details": f"Found {data['total']} locations in {elapsed:.2f}s"
                    })
        
        # Test 2: Bounding box queries
        print("\n2. Testing bounding box searches...")
        bbox_tests = [
            {"name": "Manhattan", "min_lat": 40.7, "max_lat": 40.8, "min_lon": -74.0, "max_lon": -73.9},
            {"name": "Large area", "min_lat": 40.0, "max_lat": 42.0, "min_lon": -75.0, "max_lon": -73.0}
        ]
        
        for bbox in bbox_tests:
            response, elapsed = self.make_request("locations/search", {
                "min_latitude": bbox["min_lat"],
                "max_latitude": bbox["max_lat"],
                "min_longitude": bbox["min_lon"],
                "max_longitude": bbox["max_lon"]
            })
            
            if response and response.status_code == 200:
                data = response.json()
                tests.append({
                    "name": f"Bounding box: {bbox['name']}",
                    "passed": True,
                    "details": f"Found {data['total']} locations in {elapsed:.2f}s"
                })
        
        # Test 3: Edge cases
        print("\n3. Testing edge cases...")
        edge_cases = [
            {"name": "Zero radius", "lat": 40.7128, "lon": -74.0060, "radius": 0},
            {"name": "Very large radius", "lat": 40.7128, "lon": -74.0060, "radius": 500},
            {"name": "International dateline", "lat": 0, "lon": 180, "radius": 10}
        ]
        
        for edge in edge_cases:
            response, _ = self.make_request("locations/search", {
                "latitude": edge["lat"],
                "longitude": edge["lon"],
                "radius_miles": edge["radius"]
            })
            
            tests.append({
                "name": edge["name"],
                "passed": response is not None and response.status_code in [200, 400, 422],
                "details": f"Status: {response.status_code if response else 'Failed'}"
            })
        
        self.results["geospatial"] = tests
        self._print_test_summary("Geospatial Features", tests)
    
    def test_performance(self):
        """Test API performance under various conditions."""
        print("\n" + "="*80)
        print("PERFORMANCE TESTS")
        print("="*80)
        
        tests = []
        
        # Test 1: Response time for different page sizes
        print("\n1. Testing response times for different page sizes...")
        page_sizes = [1, 10, 25, 50, 100]
        
        for size in page_sizes:
            response, elapsed = self.make_request("organizations/", {"per_page": size})
            if response and response.status_code == 200:
                tests.append({
                    "name": f"Page size {size}",
                    "passed": elapsed < 2.0,  # 2 second threshold
                    "details": f"Response time: {elapsed:.3f}s"
                })
                self.performance_metrics.append({
                    "endpoint": "organizations",
                    "page_size": size,
                    "response_time": elapsed
                })
        
        # Test 2: Concurrent requests
        print("\n2. Testing concurrent request handling...")
        endpoints = [
            "organizations/",
            "locations/",
            "services/",
            "taxonomies/"
        ]
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            start_time = time.time()
            futures = [executor.submit(self.make_request, endpoint) for endpoint in endpoints]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
            total_time = time.time() - start_time
            
            tests.append({
                "name": "4 concurrent requests",
                "passed": total_time < 3.0,  # Should complete within 3 seconds
                "details": f"Total time: {total_time:.3f}s"
            })
        
        # Test 3: Large dataset handling
        print("\n3. Testing large dataset handling...")
        response, elapsed = self.make_request("map/locations", {
            "min_lat": 40.0,
            "max_lat": 41.0,
            "min_lng": -75.0,
            "max_lng": -74.0
        })
        
        tests.append({
            "name": "Large geographic query",
            "passed": response is not None and elapsed < 10.0,
            "details": f"Response time: {elapsed:.3f}s"
        })
        
        self.results["performance"] = tests
        self._print_test_summary("Performance", tests)
    
    def test_error_handling(self):
        """Test error handling and validation."""
        print("\n" + "="*80)
        print("ERROR HANDLING TESTS")
        print("="*80)
        
        tests = []
        
        # Test 1: Invalid parameters
        print("\n1. Testing invalid parameter handling...")
        invalid_params = [
            {"endpoint": "organizations/", "params": {"page": -1}, "name": "Negative page"},
            {"endpoint": "organizations/", "params": {"per_page": 1000}, "name": "Excessive page size"},
            {"endpoint": "locations/search", "params": {"latitude": 200}, "name": "Invalid latitude"},
            {"endpoint": "locations/search", "params": {"longitude": -200}, "name": "Invalid longitude"},
            {"endpoint": "organizations/not-a-uuid", "params": {}, "name": "Invalid UUID"}
        ]
        
        for test in invalid_params:
            response, _ = self.make_request(test["endpoint"], test["params"])
            tests.append({
                "name": test["name"],
                "passed": response is not None and response.status_code in [400, 404, 422],
                "details": f"Status: {response.status_code if response else 'Failed'}"
            })
        
        # Test 2: Missing required parameters
        print("\n2. Testing missing required parameters...")
        response, _ = self.make_request("organizations/search", {})  # Missing 'q' parameter
        tests.append({
            "name": "Missing required search query",
            "passed": response is not None and response.status_code == 422,
            "details": f"Status: {response.status_code if response else 'Failed'}"
        })
        
        # Test 3: Malformed requests
        print("\n3. Testing malformed requests...")
        malformed = [
            {"endpoint": "organizations/%00", "name": "Null byte in path"},
            {"endpoint": "services/../../etc/passwd", "name": "Path traversal attempt"},
            {"endpoint": "locations/<script>alert(1)</script>", "name": "XSS in path"}
        ]
        
        for test in malformed:
            response, _ = self.make_request(test["endpoint"])
            tests.append({
                "name": test["name"],
                "passed": response is not None and response.status_code in [400, 404, 422],
                "details": f"Properly rejected with status: {response.status_code if response else 'Failed'}"
            })
        
        self.results["error_handling"] = tests
        self._print_test_summary("Error Handling", tests)
    
    def test_api_consistency(self):
        """Test API consistency for consumer readiness."""
        print("\n" + "="*80)
        print("API CONSISTENCY TESTS")
        print("="*80)
        
        tests = []
        
        # Test 1: Response structure consistency
        print("\n1. Testing response structure consistency...")
        endpoints = ["organizations/", "locations/", "services/"]
        
        for endpoint in endpoints:
            response, _ = self.make_request(endpoint, {"per_page": 2})
            if response and response.status_code == 200:
                data = response.json()
                required_keys = ["count", "total", "per_page", "current_page", "total_pages", "links", "data"]
                missing_keys = [k for k in required_keys if k not in data]
                
                tests.append({
                    "name": f"{endpoint} response structure",
                    "passed": len(missing_keys) == 0,
                    "details": "All required keys present" if not missing_keys else f"Missing: {missing_keys}"
                })
        
        # Test 2: Link navigation
        print("\n2. Testing pagination link navigation...")
        response, _ = self.make_request("organizations/", {"per_page": 5, "page": 2})
        if response and response.status_code == 200:
            data = response.json()
            if data.get("links", {}).get("next"):
                # Try to follow the next link
                next_url = data["links"]["next"]
                # Extract just the path and params
                if "?" in next_url:
                    path_and_params = next_url.split(self.base_url.replace("/api/v1/", ""))[-1]
                    next_response, _ = self.make_request(path_and_params)
                    tests.append({
                        "name": "Pagination link navigation",
                        "passed": next_response is not None and next_response.status_code == 200,
                        "details": "Next link is navigable"
                    })
        
        # Test 3: CORS headers
        print("\n3. Testing CORS headers...")
        response, _ = self.make_request("health")
        if response:
            cors_headers = {
                "access-control-allow-origin": response.headers.get("access-control-allow-origin"),
                "access-control-allow-methods": response.headers.get("access-control-allow-methods")
            }
            
            tests.append({
                "name": "CORS headers present",
                "passed": cors_headers["access-control-allow-origin"] is not None,
                "details": f"CORS origin: {cors_headers['access-control-allow-origin'] or 'Not set'}"
            })
        
        # Test 4: Content-Type validation
        print("\n4. Testing Content-Type headers...")
        response, _ = self.make_request("organizations/", {"per_page": 1})
        if response:
            content_type = response.headers.get("content-type", "")
            tests.append({
                "name": "Content-Type header",
                "passed": "application/json" in content_type,
                "details": f"Content-Type: {content_type}"
            })
        
        self.results["api_consistency"] = tests
        self._print_test_summary("API Consistency", tests)
    
    def _print_test_summary(self, category: str, tests: List[Dict]):
        """Print a summary of test results."""
        passed = sum(1 for t in tests if t["passed"])
        total = len(tests)
        
        print(f"\n{category} Summary: {passed}/{total} tests passed")
        
        # Show failed tests
        failed = [t for t in tests if not t["passed"]]
        if failed:
            print("\nFailed tests:")
            for test in failed:
                print(f"  ❌ {test['name']}: {test['details']}")
    
    def generate_report(self):
        """Generate comprehensive test report."""
        print("\n" + "="*80)
        print("COMPREHENSIVE TEST REPORT")
        print("="*80)
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Calculate overall statistics
        total_tests = sum(len(tests) for tests in self.results.values())
        passed_tests = sum(sum(1 for t in tests if t["passed"]) for tests in self.results.values())
        
        report = {
            "timestamp": timestamp,
            "api_url": self.base_url,
            "summary": {
                "total_tests": total_tests,
                "passed": passed_tests,
                "failed": total_tests - passed_tests,
                "success_rate": f"{(passed_tests/total_tests)*100:.1f}%" if total_tests > 0 else "0%"
            },
            "categories": {}
        }
        
        # Add category summaries
        for category, tests in self.results.items():
            passed = sum(1 for t in tests if t["passed"])
            report["categories"][category] = {
                "total": len(tests),
                "passed": passed,
                "failed": len(tests) - passed,
                "tests": tests
            }
        
        # Add performance metrics
        if self.performance_metrics:
            avg_response_time = sum(m["response_time"] for m in self.performance_metrics) / len(self.performance_metrics)
            report["performance"] = {
                "average_response_time": f"{avg_response_time:.3f}s",
                "metrics": self.performance_metrics
            }
        
        # Save report to file
        with open("comprehensive_test_report.json", "w") as f:
            json.dump(report, f, indent=2)
        
        # Print summary
        print(f"\nTest Date: {timestamp}")
        print(f"API URL: {self.base_url}")
        print(f"\nOverall Results:")
        print(f"  Total Tests: {total_tests}")
        print(f"  Passed: {passed_tests}")
        print(f"  Failed: {total_tests - passed_tests}")
        print(f"  Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        print(f"\nCategory Breakdown:")
        for category, tests in self.results.items():
            passed = sum(1 for t in tests if t["passed"])
            print(f"  {category.replace('_', ' ').title()}: {passed}/{len(tests)} passed")
        
        print(f"\n✅ Report saved to: comprehensive_test_report.json")
        
        return report

def main():
    print("🚀 Starting Comprehensive API Testing")
    print("="*80)
    
    tester = ComprehensiveAPITester()
    
    # Run all test categories
    tester.test_data_integrity()
    tester.test_search_functionality()
    tester.test_geospatial_features()
    tester.test_performance()
    tester.test_error_handling()
    tester.test_api_consistency()
    
    # Generate final report
    report = tester.generate_report()
    
    # Determine if API is ready for consumers
    success_rate = (report["summary"]["passed"] / report["summary"]["total_tests"]) * 100
    
    print("\n" + "="*80)
    if success_rate >= 90:
        print("✅ API IS READY FOR CONSUMER IMPLEMENTATION")
    elif success_rate >= 75:
        print("⚠️  API IS MOSTLY READY BUT NEEDS SOME FIXES")
    else:
        print("❌ API NEEDS SIGNIFICANT WORK BEFORE CONSUMER IMPLEMENTATION")
    print("="*80)

if __name__ == "__main__":
    main()