#!/usr/bin/env python3
"""Test script for the new map search endpoint."""

import json
import requests
from typing import Dict, Any, Optional
import time


class MapSearchTester:
    def __init__(self, base_url: str = "https://api.for-the-gg.org"):
        self.base_url = base_url
        self.endpoint = f"{base_url}/api/v1/map/search"
        self.results = []

    def test_search(
        self,
        test_name: str,
        params: Dict[str, Any],
        expected_format: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute a search test."""
        print(f"\n{'='*60}")
        print(f"Test: {test_name}")
        print(f"Params: {params}")

        try:
            start_time = time.time()
            response = requests.get(self.endpoint, params=params, timeout=10)
            elapsed = time.time() - start_time

            result = {
                "test": test_name,
                "status": response.status_code,
                "elapsed": f"{elapsed:.2f}s",
                "success": response.status_code == 200
            }

            if response.status_code == 200:
                data = response.json()
                result["total"] = data.get("total", 0)
                result["returned"] = len(data.get("locations", []))
                result["has_more"] = data.get("has_more", False)

                # Validate format
                if expected_format and data.get("locations"):
                    first_loc = data["locations"][0]
                    if expected_format == "compact":
                        has_compact_fields = all(k in first_loc for k in ["id", "lat", "lng", "name", "confidence"])
                        has_extra_fields = any(k in first_loc for k in ["sources", "address", "services"])
                        result["format_valid"] = has_compact_fields and not has_extra_fields
                    elif expected_format == "geojson":
                        is_collection = isinstance(first_loc, dict) and first_loc.get("type") == "FeatureCollection"
                        result["format_valid"] = is_collection
                    else:  # full
                        has_full_fields = any(k in first_loc for k in ["sources", "address", "services"])
                        result["format_valid"] = has_full_fields

                print(f"✅ Status: {response.status_code}")
                print(f"   Total: {result['total']}, Returned: {result['returned']}, Time: {elapsed:.2f}s")
            else:
                print(f"❌ Status: {response.status_code}")
                if response.text:
                    try:
                        error = response.json()
                        result["error"] = error.get("detail", response.text[:200])
                        print(f"   Error: {result['error']}")
                    except:
                        result["error"] = response.text[:200]

        except Exception as e:
            result = {
                "test": test_name,
                "status": "ERROR",
                "success": False,
                "error": str(e)
            }
            print(f"❌ Error: {e}")

        self.results.append(result)
        return result

    def run_all_tests(self):
        """Run comprehensive test suite."""
        print("\n" + "="*70)
        print("MAP SEARCH ENDPOINT TEST SUITE")
        print("="*70)

        # Test 1: Basic text search
        self.test_search("Basic text search - 'food'", {"q": "food", "per_page": 10})
        self.test_search("Multi-term search - 'food bank'", {"q": "food bank", "per_page": 10})
        self.test_search("Service search - 'emergency'", {"q": "emergency", "per_page": 10})

        # Test 2: Geographic filters
        self.test_search(
            "Bounding box - Manhattan",
            {
                "min_lat": 40.7, "max_lat": 40.8,
                "min_lng": -74.0, "max_lng": -73.9,
                "per_page": 20
            }
        )

        self.test_search(
            "Radius search - 5 miles from NYC",
            {
                "center_lat": 40.7128,
                "center_lng": -74.0060,
                "radius": 5,
                "per_page": 20
            }
        )

        self.test_search(
            "State filter - California",
            {"state": "CA", "per_page": 20}
        )

        # Test 3: Service and language filters
        self.test_search(
            "Service filter - food",
            {"services": "food", "per_page": 10}
        )

        self.test_search(
            "Multiple services - food,clothing",
            {"services": "food,clothing", "per_page": 10}
        )

        self.test_search(
            "Language filter - spanish",
            {"languages": "spanish", "per_page": 10}
        )

        # Test 4: Schedule filters
        self.test_search(
            "Schedule days - monday,wednesday",
            {"schedule_days": "monday,wednesday", "per_page": 10}
        )

        # Test 5: Quality filters
        self.test_search(
            "High confidence only",
            {"confidence_min": 80, "per_page": 10}
        )

        self.test_search(
            "Multiple sources only",
            {"has_multiple_sources": True, "per_page": 10}
        )

        self.test_search(
            "Validated locations",
            {"validation_status": "validated", "per_page": 10}
        )

        # Test 6: Output formats
        self.test_search(
            "Compact format",
            {"q": "food", "format": "compact", "per_page": 5},
            expected_format="compact"
        )

        self.test_search(
            "GeoJSON format",
            {"q": "food", "format": "geojson", "per_page": 5},
            expected_format="geojson"
        )

        self.test_search(
            "Full format (default)",
            {"q": "food", "format": "full", "per_page": 5},
            expected_format="full"
        )

        # Test 7: Combined filters
        self.test_search(
            "Complex query - text + geo + confidence",
            {
                "q": "food",
                "state": "NY",
                "confidence_min": 60,
                "per_page": 10
            }
        )

        self.test_search(
            "Complex query - radius + services + format",
            {
                "center_lat": 40.7128,
                "center_lng": -74.0060,
                "radius": 10,
                "services": "food,pantry",
                "format": "compact",
                "per_page": 20
            }
        )

        # Test 8: Pagination
        self.test_search(
            "Pagination - page 1",
            {"q": "food", "page": 1, "per_page": 5}
        )

        self.test_search(
            "Pagination - page 2",
            {"q": "food", "page": 2, "per_page": 5}
        )

        # Test 9: Edge cases
        self.test_search(
            "Empty search (all results)",
            {"per_page": 10}
        )

        self.test_search(
            "No results expected",
            {"q": "xyzabc123nonexistent", "per_page": 10}
        )

        self.test_search(
            "Special characters in query",
            {"q": "st. mary's", "per_page": 10}
        )

    def print_summary(self):
        """Print test summary."""
        print("\n" + "="*70)
        print("TEST SUMMARY")
        print("="*70)

        total = len(self.results)
        passed = sum(1 for r in self.results if r["success"])
        failed = total - passed

        print(f"\nTotal Tests: {total}")
        print(f"Passed: {passed} ({passed/total*100:.1f}%)")
        print(f"Failed: {failed} ({failed/total*100:.1f}%)")

        if failed > 0:
            print("\nFailed Tests:")
            for r in self.results:
                if not r["success"]:
                    print(f"  - {r['test']}: {r.get('error', 'Unknown error')}")

        # Performance stats
        search_times = [float(r["elapsed"].rstrip("s")) for r in self.results if r.get("elapsed")]
        if search_times:
            print(f"\nPerformance:")
            print(f"  Average response time: {sum(search_times)/len(search_times):.2f}s")
            print(f"  Fastest: {min(search_times):.2f}s")
            print(f"  Slowest: {max(search_times):.2f}s")

        # Save results
        with open("map_search_test_results.json", "w") as f:
            json.dump({
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "endpoint": self.endpoint,
                "summary": {
                    "total": total,
                    "passed": passed,
                    "failed": failed,
                    "success_rate": f"{passed/total*100:.1f}%"
                },
                "results": self.results
            }, f, indent=2)

        print("\nResults saved to map_search_test_results.json")


if __name__ == "__main__":
    tester = MapSearchTester()
    tester.run_all_tests()
    tester.print_summary()