#!/usr/bin/env python3
"""Test script optimized for map display endpoint testing."""

import json
import requests
import time


def test_map_endpoint():
    """Test the map search endpoint for geographic queries."""
    base_url = "https://api.for-the-gg.org/api/v1/map/search"
    
    print("MAP SEARCH ENDPOINT TEST - Geographic Focus")
    print("=" * 60)
    
    tests = [
        # Geographic queries (primary use case)
        ("Bounding box - Manhattan", {
            "min_lat": 40.7, "max_lat": 40.8,
            "min_lng": -74.0, "max_lng": -73.9,
            "format": "compact",
            "per_page": 100
        }),
        
        ("Bounding box - California", {
            "min_lat": 32.5, "max_lat": 42.0,
            "min_lng": -124.5, "max_lng": -114.0,
            "format": "compact",
            "per_page": 50
        }),
        
        ("State filter - NY", {
            "state": "NY",
            "format": "compact",
            "per_page": 100
        }),
        
        ("State filter - CA", {
            "state": "CA",
            "format": "compact",
            "per_page": 100
        }),
        
        ("Radius - 5 miles NYC", {
            "center_lat": 40.7128,
            "center_lng": -74.0060,
            "radius": 5,
            "format": "compact",
            "per_page": 100
        }),
        
        ("Radius - 10 miles LA", {
            "center_lat": 34.0522,
            "center_lng": -118.2437,
            "radius": 10,
            "format": "compact",
            "per_page": 100
        }),
        
        # Quality filters with geography
        ("High confidence + State", {
            "state": "NY",
            "confidence_min": 80,
            "format": "compact",
            "per_page": 50
        }),
        
        ("Multiple sources + Bbox", {
            "min_lat": 40.6, "max_lat": 40.9,
            "min_lng": -74.1, "max_lng": -73.8,
            "has_multiple_sources": True,
            "format": "compact",
            "per_page": 50
        }),
        
        # Output format tests
        ("GeoJSON format", {
            "state": "RI",  # Small state for quick response
            "format": "geojson",
            "per_page": 20
        }),
        
        ("Full format (small set)", {
            "min_lat": 40.75, "max_lat": 40.76,
            "min_lng": -73.99, "max_lng": -73.98,
            "format": "full",
            "per_page": 5
        }),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, params in tests:
        try:
            start = time.time()
            response = requests.get(base_url, params=params, timeout=10)
            elapsed = time.time() - start
            
            if response.status_code == 200:
                data = response.json()
                total = data.get("total", 0)
                returned = len(data.get("locations", []))
                
                # Validate format
                format_check = ""
                if "format" in params:
                    fmt = params["format"]
                    if fmt == "compact" and data.get("locations"):
                        loc = data["locations"][0]
                        if all(k in loc for k in ["id", "lat", "lng", "name", "confidence"]):
                            format_check = " ✓"
                    elif fmt == "geojson" and data.get("locations"):
                        loc = data["locations"][0]
                        if isinstance(loc, dict) and loc.get("type") == "FeatureCollection":
                            format_check = " ✓"
                    elif fmt == "full" and data.get("locations"):
                        loc = data["locations"][0]
                        if "sources" in loc:
                            format_check = " ✓"
                
                print(f"✅ {test_name}: {total} total, {returned} returned ({elapsed:.2f}s){format_check}")
                passed += 1
            else:
                print(f"❌ {test_name}: Status {response.status_code} ({elapsed:.2f}s)")
                if response.status_code == 500:
                    error = response.json()
                    print(f"   Error: {error.get('message', '')[:100]}")
                failed += 1
                
        except requests.exceptions.Timeout:
            print(f"❌ {test_name}: Timeout after 10s")
            failed += 1
        except Exception as e:
            print(f"❌ {test_name}: {str(e)[:100]}")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed ({passed}/{passed+failed})")
    
    if passed == len(tests):
        print("🎉 All tests passed! Endpoint ready for map integration.")
    elif passed > len(tests) * 0.8:
        print("✅ Most tests passed. Endpoint functional for map display.")
    else:
        print("⚠️  Multiple failures. Check deployment and indexes.")


if __name__ == "__main__":
    test_map_endpoint()