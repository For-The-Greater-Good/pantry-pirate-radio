"""
Pantry Pirate Radio API Python Client Example

This example demonstrates how to interact with the Pantry Pirate Radio API
using Python. It includes error handling, rate limiting, and common use cases.

Requirements:
    pip install requests
"""

import requests
import time
from typing import Dict, List, Optional, Any
from urllib.parse import urlencode


class PantryPirateClient:
    """
    Python client for the Pantry Pirate Radio API.

    This client provides convenient methods for searching food services,
    retrieving details, and handling API responses.
    """

    def __init__(
        self, base_url: str = "https://api.pantrypirate.org/v1", timeout: int = 30
    ):
        """
        Initialize the API client.

        Args:
            base_url: Base URL for the API
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {"Accept": "application/json", "User-Agent": "PantryPirateClient/1.0"}
        )

    def _make_request(
        self, endpoint: str, params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Make a request to the API with error handling and rate limiting.

        Args:
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            API response as dictionary

        Raises:
            requests.exceptions.RequestException: For API errors
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"

        try:
            response = self.session.get(url, params=params, timeout=self.timeout)

            # Handle rate limiting
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                print(f"Rate limited. Waiting {retry_after} seconds...")
                time.sleep(retry_after)
                response = self.session.get(url, params=params, timeout=self.timeout)

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            print(f"API request failed: {e}")
            if hasattr(e, "response") and e.response is not None:
                try:
                    error_data = e.response.json()
                    print(f"Error details: {error_data}")
                except Exception:
                    print(f"Response content: {e.response.text}")
            raise

    def search_services(
        self,
        latitude: float,
        longitude: float,
        radius: float,
        status: Optional[str] = None,
        service_type: Optional[str] = None,
        languages: Optional[List[str]] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> Dict[str, Any]:
        """
        Search for food services by geographic location.

        Args:
            latitude: Latitude coordinate (25.0 to 49.0)
            longitude: Longitude coordinate (-125.0 to -67.0)
            radius: Search radius in miles (max 80)
            status: Service status filter ('active', 'inactive', etc.)
            service_type: Type of service ('food_pantry', 'hot_meals', etc.)
            languages: List of language codes for language support
            page: Page number for pagination
            per_page: Results per page (max 100)

        Returns:
            Search results with services, pagination, and metadata
        """
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "radius": radius,
            "page": page,
            "per_page": per_page,
        }

        if status:
            params["status"] = status
        if service_type:
            params["service_type"] = service_type
        if languages:
            params["languages"] = ",".join(languages)

        return self._make_request("services", params)

    def search_services_by_bounds(
        self, north: float, south: float, east: float, west: float, **kwargs
    ) -> Dict[str, Any]:
        """
        Search for services within a bounding box.

        Args:
            north: Northern boundary latitude
            south: Southern boundary latitude
            east: Eastern boundary longitude
            west: Western boundary longitude
            **kwargs: Additional filter parameters

        Returns:
            Search results with services, pagination, and metadata
        """
        params = {
            "bounds[north]": north,
            "bounds[south]": south,
            "bounds[east]": east,
            "bounds[west]": west,
        }
        params.update(kwargs)

        return self._make_request("services", params)

    def get_service(self, service_id: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific service.

        Args:
            service_id: Unique service identifier

        Returns:
            Service details including organization, locations, and schedules
        """
        return self._make_request(f"services/{service_id}")

    def get_organization(self, organization_id: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific organization.

        Args:
            organization_id: Unique organization identifier

        Returns:
            Organization details
        """
        return self._make_request(f"organizations/{organization_id}")

    def get_location(self, location_id: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific location.

        Args:
            location_id: Unique location identifier

        Returns:
            Location details including address and coordinates
        """
        return self._make_request(f"locations/{location_id}")

    def list_organizations(
        self, page: int = 1, per_page: int = 20, sort: str = "name", order: str = "asc"
    ) -> Dict[str, Any]:
        """
        List all organizations with pagination.

        Args:
            page: Page number
            per_page: Results per page
            sort: Sort field ('name', 'last_modified')
            order: Sort order ('asc', 'desc')

        Returns:
            List of organizations with pagination info
        """
        params = {"page": page, "per_page": per_page, "sort": sort, "order": order}

        return self._make_request("organizations", params)

    def health_check(self) -> Dict[str, Any]:
        """
        Check API health status.

        Returns:
            Health status information
        """
        return self._make_request("health")


# Example usage and common patterns
def main():
    """
    Example usage of the Pantry Pirate Radio API client.
    """
    # Initialize client
    client = PantryPirateClient()

    # Example 1: Find food pantries near a location
    print("=== Finding Food Pantries Near Manhattan ===")
    try:
        # Search for active food pantries within 5 miles of Manhattan
        results = client.search_services(
            latitude=40.7128,
            longitude=-74.0060,
            radius=5,
            status="active",
            service_type="food_pantry",
        )

        print(f"Found {results['metadata']['total_results']} food pantries")
        for service in results["services"]:
            org = service["organization"]
            location = service["location"]
            schedule = service["schedules"][0] if service["schedules"] else {}

            print(f"\n{org['name']}")
            print(f"  Service: {service['service']['name']}")
            print(
                f"  Address: {location['address']['address_1']}, {location['address']['city']}"
            )
            print(f"  Distance: {location['distance_miles']} miles")
            if schedule:
                print(f"  Hours: {schedule['description']}")
            if service["phones"]:
                print(f"  Phone: {service['phones'][0]['number']}")

    except Exception as e:
        print(f"Error searching for services: {e}")

    # Example 2: Find services with Spanish support
    print("\n=== Finding Services with Spanish Support ===")
    try:
        results = client.search_services(
            latitude=40.7128,
            longitude=-74.0060,
            radius=10,
            languages=["es"],
            status="active",
        )

        print(
            f"Found {results['metadata']['total_results']} services with Spanish support"
        )
        for service in results["services"]:
            org = service["organization"]
            print(f"  {org['name']}: {service['service']['name']}")

    except Exception as e:
        print(f"Error searching for Spanish services: {e}")

    # Example 3: Get detailed information about a service
    print("\n=== Getting Service Details ===")
    try:
        # First, get a service ID from search results
        results = client.search_services(
            latitude=40.7128, longitude=-74.0060, radius=5, per_page=1
        )

        if results["services"]:
            service_id = results["services"][0]["id"]
            service_detail = client.get_service(service_id)

            print(f"Service: {service_detail['name']}")
            print(f"Organization: {service_detail['organization']['name']}")
            print(f"Description: {service_detail['description']}")
            print(f"Eligibility: {service_detail['eligibility_description']}")
            print(f"Application Process: {service_detail['application_process']}")

            # Show all locations for this service
            print("Locations:")
            for sal in service_detail["service_at_location"]:
                loc = sal["location"]
                print(f"  - {loc['name']}")
                print(f"    Address: {loc['address']['address_1']}")
                for sched in sal["schedules"]:
                    print(f"    Schedule: {sched['description']}")

    except Exception as e:
        print(f"Error getting service details: {e}")

    # Example 4: Health check
    print("\n=== API Health Check ===")
    try:
        health = client.health_check()
        print(f"API Status: {health['status']}")
        print(f"Version: {health['version']}")
        print(f"Uptime: {health['uptime']} seconds")

    except Exception as e:
        print(f"Error checking health: {e}")


# Helper functions for common operations
def find_nearest_food_pantry(
    client: PantryPirateClient, latitude: float, longitude: float
) -> Optional[Dict]:
    """
    Find the nearest active food pantry to a given location.

    Args:
        client: API client instance
        latitude: Latitude coordinate
        longitude: Longitude coordinate

    Returns:
        Nearest food pantry service or None if not found
    """
    try:
        results = client.search_services(
            latitude=latitude,
            longitude=longitude,
            radius=20,  # Search within 20 miles
            status="active",
            service_type="food_pantry",
            per_page=1,  # Only need the closest one
        )

        if results["services"]:
            return results["services"][0]
        return None

    except Exception as e:
        print(f"Error finding nearest food pantry: {e}")
        return None


def get_organization_services(
    client: PantryPirateClient, organization_id: str
) -> List[Dict]:
    """
    Get all services provided by a specific organization.

    Args:
        client: API client instance
        organization_id: Organization identifier

    Returns:
        List of services provided by the organization
    """
    try:
        # Get organization details first
        org = client.get_organization(organization_id)

        # Search for services by organization
        results = client.search_services(
            latitude=40.7128,  # Center search somewhere
            longitude=-74.0060,
            radius=80,  # Max radius to catch all services
            per_page=100,  # Get more results
        )

        # Filter services by organization
        org_services = []
        for service in results["services"]:
            if service["organization"]["id"] == organization_id:
                org_services.append(service)

        return org_services

    except Exception as e:
        print(f"Error getting organization services: {e}")
        return []


if __name__ == "__main__":
    main()
