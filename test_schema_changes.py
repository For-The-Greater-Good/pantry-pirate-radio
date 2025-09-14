#!/usr/bin/env python3
"""Test script to verify schema changes include required fields."""

import sys
import json
from pathlib import Path

# Add the app directory to the path
sys.path.insert(0, str(Path(__file__).parent))

from app.llm.hsds_aligner.schema_converter import SchemaConverter

def test_schema_required_fields():
    """Test that critical fields are marked as required in the schema."""
    
    # Initialize the schema converter
    schema_path = Path("docs/HSDS/schema/simple/schema.csv")
    converter = SchemaConverter(schema_path)
    
    # Load the core schema
    schema = converter.load_hsds_core_schema()
    
    # Extract the actual schema from the wrapper
    if "json_schema" in schema:
        actual_schema = schema["json_schema"]["schema"]
    else:
        actual_schema = schema
    
    print("Testing Schema Required Fields")
    print("=" * 50)
    
    # Check organization required fields
    if "definitions" in actual_schema:
        definitions = actual_schema["definitions"]
        
        # Check organization
        if "organization" in definitions:
            org_required = definitions["organization"].get("required", [])
            expected_org = ["id", "name", "description", "email", "website"]
            print(f"\nOrganization required fields: {org_required}")
            print(f"Expected: {expected_org}")
            assert all(field in org_required for field in expected_org), f"Missing required organization fields"
            print("✓ Organization fields correct")
        
        # Check service
        if "service" in definitions:
            service_required = definitions["service"].get("required", [])
            expected_service = ["id", "name", "description", "status", "email", "eligibility_description"]
            print(f"\nService required fields: {service_required}")
            print(f"Expected: {expected_service}")
            assert all(field in service_required for field in expected_service), f"Missing required service fields"
            print("✓ Service fields correct")
        
        # Check location
        if "location" in definitions:
            location_required = definitions["location"].get("required", [])
            expected_location = ["id", "name", "description", "latitude", "longitude", "location_type"]
            print(f"\nLocation required fields: {location_required}")
            print(f"Expected: {expected_location}")
            assert all(field in location_required for field in expected_location), f"Missing required location fields"
            print("✓ Location fields correct")
        
        # Check address
        if "address" in definitions:
            address_required = definitions["address"].get("required", [])
            expected_address = ["id", "address_1", "city", "state_province", "postal_code", "country"]
            print(f"\nAddress required fields: {address_required}")
            print(f"Expected: {expected_address}")
            assert all(field in address_required for field in expected_address), f"Missing required address fields"
            print("✓ Address fields correct")
    
    print("\n" + "=" * 50)
    print("✅ All schema tests passed!")
    print("\nThe schema now requires critical fields that were previously optional.")
    print("This will ensure the LLM outputs these fields even when empty/null,")
    print("allowing proper data tracking and potential enrichment downstream.")
    
    # Also check that the prompt file has been updated
    prompt_path = Path("app/llm/hsds_aligner/prompts/food_pantry_mapper.prompt")
    if prompt_path.exists():
        with open(prompt_path) as f:
            prompt_content = f.read()
        
        if "Include ALL schema fields" in prompt_content:
            print("\n✅ Prompt has been updated to include all schema fields")
        else:
            print("\n⚠️ Warning: Prompt may not be updated correctly")
    
    return True

if __name__ == "__main__":
    try:
        test_schema_required_fields()
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)