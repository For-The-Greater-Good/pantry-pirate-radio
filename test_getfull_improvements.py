#!/usr/bin/env python3
"""Test script to verify GetFull scraper improvements."""

import asyncio
import json
from app.scraper.getfull_app_browser_scraper import Getfull_App_BrowserScraper


async def test_geo_search():
    """Test the new geo search functionality."""
    print("Testing GetFull.app Geo Search Improvements")
    print("=" * 50)
    
    # Create scraper instance with just 1 worker for testing
    scraper = Getfull_App_BrowserScraper(num_workers=1)
    
    # Initialize browser and get auth token
    playwright, browser, page = await scraper.initialize_browser()
    
    try:
        print("1. Navigating to GetFull.app...")
        await scraper.navigate_to_map(page)
        
        if scraper.auth_token and scraper.auth_token != "anonymous_access_token":
            print(f"   ✓ Successfully obtained auth token")
        else:
            print(f"   ✗ Failed to obtain auth token")
            return
        
        # Test a single location search
        print("\n2. Testing geo search for New York City...")
        nyc_pantries = await scraper.search_pantries_by_location(
            lat=40.7128, lng=-74.0060, radius_miles=30
        )
        print(f"   ✓ Found {len(nyc_pantries)} pantries in NYC area")
        
        if nyc_pantries:
            print(f"   Sample pantry: {nyc_pantries[0].get('name', 'Unknown')}")
        
        # Test another location
        print("\n3. Testing geo search for Los Angeles...")
        la_pantries = await scraper.search_pantries_by_location(
            lat=34.0522, lng=-118.2437, radius_miles=30
        )
        print(f"   ✓ Found {len(la_pantries)} pantries in LA area")
        
        if la_pantries:
            print(f"   Sample pantry: {la_pantries[0].get('name', 'Unknown')}")
        
        # Test rural area
        print("\n4. Testing geo search for rural Montana...")
        mt_pantries = await scraper.search_pantries_by_location(
            lat=46.8772, lng=-113.9961, radius_miles=100
        )
        print(f"   ✓ Found {len(mt_pantries)} pantries in Montana area")
        
        print("\n5. Summary:")
        print(f"   - NYC: {len(nyc_pantries)} pantries")
        print(f"   - LA: {len(la_pantries)} pantries")
        print(f"   - Montana: {len(mt_pantries)} pantries")
        print(f"   - Total unique pantries: {len(set(p['id'] for p in nyc_pantries + la_pantries + mt_pantries if p.get('id')))}")
        
    finally:
        await browser.close()
        await playwright.stop()
    
    print("\n✓ Test completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_geo_search())