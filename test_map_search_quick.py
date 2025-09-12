#!/usr/bin/env python3
"""Quick test script for the new map search endpoint."""

import json
import requests
import time


def test_endpoint():
    """Run quick tests on the map search endpoint."""
    base_url = "https://api.for-the-gg.org/api/v1/map/search"
    tests_passed = 0
    tests_failed = 0
    
    tests = [
        ("Basic text search", {"q": "food", "per_page": 5}),
        ("State filter", {"state": "CA", "per_page": 5}),
        ("Bounding box", {
            "min_lat": 40.7, "max_lat": 40.8,
            "min_lng": -74.0, "max_lng": -73.9,
            "per_page": 5
        }),
        ("Radius search", {
            "center_lat": 40.7128,
            "center_lng": -74.0060,
            "radius": 5,
            "per_page": 5
        }),
        ("Service filter", {"services": "food,pantry", "per_page": 5}),
        ("High confidence", {"confidence_min": 80, "per_page": 5}),
        ("Compact format", {"q": "food", "format": "compact", "per_page": 3}),
        ("GeoJSON format", {"q": "food", "format": "geojson", "per_page": 3}),
        ("Pagination", {"q": "food", "page": 2, "per_page": 5}),
        ("Complex query", {
            "q": "food",
            "state": "NY", 
            "confidence_min": 60,
            "per_page": 5
        }),
    ]
    
    print("MAP SEARCH ENDPOINT QUICK TEST")
    print("=" * 60)
    
    for test_name, params in tests:
        try:
            start = time.time()
            response = requests.get(base_url, params=params, timeout=5)
            elapsed = time.time() - start
            
            if response.status_code == 200:
                data = response.json()
                total = data.get("total", 0)
                returned = len(data.get("locations", []))
                
                # Validate format for specific tests
                format_check = ""
                if "format" in params:
                    if params["format"] == "compact" and data.get("locations"):
                        loc = data["locations"][0]
                        if "id" in loc and "lat" in loc and "sources" not in loc:
                            format_check = " ✓ Format OK"
                        else:
                            format_check = " ✗ Format Issue"
                    elif params["format"] == "geojson" and data.get("locations"):
                        loc = data["locations"][0]
                        if isinstance(loc, dict) and loc.get("type") == "FeatureCollection":
                            format_check = " ✓ Format OK"
                        else:
                            format_check = " ✗ Format Issue"
                
                print(f"✅ {test_name}: {total} total, {returned} returned ({elapsed:.2f}s){format_check}")
                tests_passed += 1
            else:
                print(f"❌ {test_name}: Status {response.status_code}")
                tests_failed += 1
                
        except Exception as e:
            print(f"❌ {test_name}: {str(e)}")
            tests_failed += 1
    
    print("\n" + "=" * 60)
    print(f"SUMMARY: {tests_passed} passed, {tests_failed} failed")
    print(f"Success rate: {tests_passed}/{tests_passed+tests_failed} ({tests_passed/(tests_passed+tests_failed)*100:.0f}%)")
    
    return tests_passed, tests_failed


if __name__ == "__main__":
    test_endpoint()