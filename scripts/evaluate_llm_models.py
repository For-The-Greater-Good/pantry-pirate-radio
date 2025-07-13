#!/usr/bin/env python
"""
LLM Model Evaluation Script for HSDS Data Processing

This script evaluates multiple LLM models from OpenRouter for their ability
to process data according to the HSDS specification.
"""

import argparse
import asyncio
import builtins
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from statistics import mean, median, stdev
from typing import Any, Dict, List, Optional, TypedDict, cast

from app.llm.hsds_aligner import HSDSAligner
from app.llm.hsds_aligner.type_defs import AlignmentInputDict
from app.llm.hsds_aligner.validation import ValidationConfig
from app.llm.providers.base import BaseLLMProvider
from app.llm.providers.openai import OpenAIConfig, OpenAIProvider

# Add project root to path to allow imports
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))


class InputData(TypedDict):
    """Type for input data."""

    Name: str
    Entity_Id: int
    Category: str
    Subcategory: str
    Organization: str
    More_Information: str
    Counties: List[str]
    Location: str
    Address: str
    City: str
    State: str
    Zip: str
    Phone: str
    Hours_of_Operation: str
    Cost: str
    Accepts: str
    Website: str
    Coalition: int
    CFAN: int
    Latitude: str
    Longitude: str
    Last_Updated: str
    icon: str


class TestResult(TypedDict):
    """Type for test result data."""

    success: bool
    confidence_score: float
    retries: int
    execution_time: float
    error: Optional[str]
    # Enhanced metrics
    test_name: str
    difficulty: str
    source_type: str
    field_mapping_score: float
    data_completeness_score: float
    service_classification_score: float
    hsds_structure_score: float


class ModelResult(TypedDict):
    """Type for model result data."""

    model_name: str
    results: List[TestResult]
    success_rate: float
    avg_confidence: float
    avg_retries: float
    avg_execution_time: float
    std_confidence: float
    std_retries: float
    std_execution_time: float
    # Enhanced metrics
    avg_field_mapping_score: float
    avg_data_completeness_score: float
    avg_service_classification_score: float
    avg_hsds_structure_score: float
    performance_by_difficulty: Dict[str, float]
    performance_by_source_type: Dict[str, float]


# Define the models to evaluate
MODELS = [
    "google/gemini-2.0-flash-001",  # Baseline
    "google/gemini-2.5-flash-lite-preview-06-17",  # Same price as baseline
    "google/gemini-2.0-flash-lite-001",  # 25% cheaper
    "openai/gpt-4.1-nano",  # OpenAI nano model
]

# Default timeout in seconds
DEFAULT_TIMEOUT = 90  # 90 seconds


def calculate_field_mapping_score(input_data: dict[str, Any], hsds_data: Any) -> float:
    """Calculate how well the model mapped input fields to HSDS schema.

    Args:
        input_data: Original input data
        hsds_data: HSDS-aligned output data

    Returns:
        Score from 0.0 to 1.0
    """
    score = 0.0
    total_checks = 0

    # Check if basic organization info was mapped
    if hsds_data.get("organization"):
        org = hsds_data["organization"][0] if hsds_data["organization"] else {}

        # Organization name mapping
        total_checks += 1
        if org.get("name"):
            score += 1.0

        # Contact info mapping
        if any(key in str(input_data).lower() for key in ["phone", "email", "website"]):
            total_checks += 1
            if org.get("contacts") or any(
                key in str(org).lower() for key in ["phone", "email", "url"]
            ):
                score += 1.0

        # Address mapping
        if any(
            key in str(input_data).lower()
            for key in ["address", "location", "city", "state"]
        ):
            total_checks += 1
            if hsds_data.get("location") and hsds_data["location"]:
                score += 1.0

        # Services mapping
        if any(
            key in str(input_data).lower()
            for key in ["service", "program", "pantry", "kitchen"]
        ):
            total_checks += 1
            if hsds_data.get("service") and hsds_data["service"]:
                score += 1.0

    return score / total_checks if total_checks > 0 else 0.0


def calculate_data_completeness_score(hsds_data: Any) -> float:
    """Calculate how complete the HSDS data is.

    Args:
        hsds_data: HSDS-aligned output data

    Returns:
        Score from 0.0 to 1.0
    """
    score = 0.0
    total_checks = 8  # Number of completeness checks

    # Required organizations
    if hsds_data.get("organization") and len(hsds_data["organization"]) > 0:
        score += 1.0
        org = hsds_data["organization"][0]

        # Organization has name
        if org.get("name"):
            score += 1.0

        # Organization has description
        if org.get("description"):
            score += 1.0

        # Organization has services
        if org.get("services") and len(org["services"]) > 0:
            score += 1.0

    # Required services
    if hsds_data.get("service") and len(hsds_data["service"]) > 0:
        score += 1.0
        service = hsds_data["service"][0]

        # Service has name
        if service.get("name"):
            score += 1.0

    # Required locations
    if hsds_data.get("location") and len(hsds_data["location"]) > 0:
        score += 1.0
        location = hsds_data["location"][0]

        # Location has address or coordinates
        if location.get("physical_addresses") or (
            location.get("latitude") and location.get("longitude")
        ):
            score += 1.0

    return score / total_checks


def calculate_service_classification_score(
    input_data: dict[str, Any], hsds_data: Any
) -> float:
    """Calculate how well the model classified services.

    Args:
        input_data: Original input data
        hsds_data: HSDS-aligned output data

    Returns:
        Score from 0.0 to 1.0
    """
    score = 0.0
    total_checks = 0

    if hsds_data.get("service") and hsds_data["service"]:
        service = hsds_data["service"][0]
        input_str = str(input_data).lower()

        # Check service type classification
        total_checks += 1
        service_name = service.get("name", "").lower()

        # Food pantry classification
        if any(
            word in input_str for word in ["pantry", "food bank", "food distribution"]
        ):
            if any(word in service_name for word in ["pantry", "food", "distribution"]):
                score += 1.0
        # Soup kitchen classification
        elif any(word in input_str for word in ["soup kitchen", "hot meal", "meals"]):
            if any(word in service_name for word in ["meal", "kitchen", "food"]):
                score += 1.0
        # Mobile service classification
        elif any(word in input_str for word in ["mobile", "truck", "various location"]):
            if any(word in service_name for word in ["mobile", "outreach", "delivery"]):
                score += 1.0
        # Government program classification
        elif any(
            word in input_str
            for word in ["wic", "snap", "government", "health department"]
        ):
            if any(
                word in service_name for word in ["assistance", "program", "benefit"]
            ):
                score += 1.0
        else:
            # Generic food assistance
            if any(word in service_name for word in ["food", "assistance", "support"]):
                score += 1.0

        # Check if eligibility requirements were captured
        if any(
            word in input_str
            for word in ["eligibility", "requirement", "income", "documentation"]
        ):
            total_checks += 1
            if service.get("eligibility") or service.get("application_process"):
                score += 1.0

        # Check if hours were captured
        if any(word in input_str for word in ["hours", "schedule", "time", "open"]):
            total_checks += 1
            if service.get("schedule") or any(
                sched.get("opens_at") for sched in service.get("schedule", [])
            ):
                score += 1.0

    return score / total_checks if total_checks > 0 else 0.0


def calculate_hsds_structure_score(hsds_data: Any) -> float:
    """Calculate how well the data follows HSDS structure.

    Args:
        hsds_data: HSDS-aligned output data

    Returns:
        Score from 0.0 to 1.0
    """
    score = 0.0
    total_checks = 5

    # Has required top-level entities
    if hsds_data.get("organization"):
        score += 1.0

    if hsds_data.get("service"):
        score += 1.0

    if hsds_data.get("location"):
        score += 1.0

    # Check relationships are properly formed
    if hsds_data.get("organization") and hsds_data.get("service"):
        org = hsds_data["organization"][0] if hsds_data["organization"] else {}
        if org.get("services") and len(org["services"]) > 0:
            score += 1.0

    # Check for proper IDs and references
    if hsds_data.get("service"):
        service = hsds_data["service"][0] if hsds_data["service"] else {}
        if service.get("id") and service.get("organization_id"):
            score += 1.0

    return score / total_checks


def create_provider(model_name: str) -> OpenAIProvider:
    """Create an OpenAI provider with the specified model.

    Args:
        model_name: The name of the model to use

    Returns:
        OpenAIProvider: The configured provider
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY environment variable not set")

    return OpenAIProvider(
        OpenAIConfig(model_name=model_name),
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        headers={
            "HTTP-Referer": "https://github.com/openrouter-ai/openrouter-python",
            "X-Title": "Pantry Pirate Radio",
        },
    )


def get_test_data() -> list[dict[str, Any]]:
    """Get diverse test data for alignment based on real scraper output formats.

    Returns:
        List of test data dictionaries with varying complexity levels
    """
    return [
        # EASY CASE 1: Clean, complete data (original baseline)
        {
            "test_name": "clean_complete_data",
            "difficulty": "easy",
            "source_type": "structured",
            "data": {
                "Name": '"The Pantry" at St. Patrick\'s',
                "Entity_Id": 97,
                "Category": "Food Pantry",
                "Subcategory": "Food Pantries within the Capital District",
                "Organization": "St. Patrick",
                "More_Information": "Can visit once a month unless they are in need. walk in no appt necessary. If a client is in need of food they will open to accommodate them",
                "Counties": ["Albany"],
                "Location": "Ravena",
                "Address": "21 Main St.",
                "City": "Ravena",
                "State": "NY",
                "Zip": "12143",
                "Phone": "(518) 756-3145",
                "Hours_of_Operation": "Tues 10:00-11:00am, Wed 6:00-7:00pm, Fri 10:00-11:00am",
                "Cost": "",
                "Accepts": "",
                "Website": "https://churchofsaintpatrick.wixsite.com/church-ravena",
                "Coalition": 1,
                "CFAN": 0,
                "Latitude": "42.4733363",
                "Longitude": "-73.8023108",
                "Last_Updated": "03-21-2024",
                "icon": "marker-F42000",
            },
        },
        # EASY CASE 2: HFC Partner Data format
        {
            "test_name": "hfc_partner_format",
            "difficulty": "easy",
            "source_type": "csv",
            "data": {
                "Account Name": "Example Community Food Bank",
                "Account Email": "info@examplefoodbank.org",
                "Phone": "555-123-4567",
                "Website": "https://www.examplefoodbank.org",
                "MALatitude": "39.7392",
                "MALongitude": "-104.9903",
                "Billing Address Line 1": "123 Main Street",
                "Billing City": "Denver",
                "Billing State/Province": "CO",
                "Billing Zip/Postal Code": "80202",
                "Type Code": "Pantry",
                "Is this a food pantry?": "1",
                "Food Type": "This program provides boxes of perishable and non-perishable food; canned, bread, meats, produce.",
                "Services Provided": "Pantry",
                "Days of Food Pantry Operation": "Tuesday; Thursday",
                "Hours of Operation": "Morning; Afternoon",
                "Exact Hours of Operation": "Tuesday 9am-12pm; Thursday 2pm-5pm",
                "Documents Required": "ID Required",
                "Access Requirements": "Walk-in",
                "Languages Spoken": "English; Spanish",
                "Areas Served": "Denver Metro Area",
                "Population Served": "All",
            },
        },
        # MEDIUM CASE 1: Scraped web data with inconsistent fields
        {
            "test_name": "scraped_web_data",
            "difficulty": "medium",
            "source_type": "scraped",
            "data": {
                "org_name": "Community Kitchen & Pantry",
                "location": "456 Hope Ave, Example City, NY 10002",
                "phone": "555-234-5678",
                "email": "meals@communitykitchen.org",
                "website": "https://communitykitchen.org",
                "hours": "Hot meals: Daily 12pm-2pm, Pantry: Mon/Wed/Fri 10am-1pm",
                "services": "Hot meals, food pantry, holiday meal programs",
                "description": "Volunteer-run kitchen serving anyone in need. No questions asked policy.",
                "eligibility": "Open to all",
                "languages": "English, Spanish, French",
                "contact_person": "Maria Santos, Volunteer Coordinator",
                "last_verified": "2024-01-08",
            },
        },
        # MEDIUM CASE 2: Missing fields and inconsistent formatting
        {
            "test_name": "missing_fields_inconsistent",
            "difficulty": "medium",
            "source_type": "scraped",
            "data": {
                "name": "Westside Food Pantry",
                "address": "741 Westside Avenue, Denver, CO 80204",
                "phone": "555-012-3456",
                "hours": "Tuesday 9am-12pm; Friday 2pm-5pm",
                "services": "Emergency food assistance for families in need",
                "requirements": "ID Required, Walk-in",
                "languages": "English, Spanish",
                "service_area": "West Denver",
                "website": "https://www.westsidefoodpantry.org",
                "zip_codes": "80204, 80212, 80214",
            },
        },
        # HARD CASE 1: Mobile/Multi-location service
        {
            "test_name": "mobile_service",
            "difficulty": "hard",
            "source_type": "scraped",
            "data": {
                "org_name": "Mobile Food Truck",
                "location": "Various locations - see schedule",
                "phone": "(555) 345-6789",
                "email": "mobile@foodtruck.org",
                "website": "foodtruck.org/schedule",
                "hours": "Tues: Community Center 2-4pm, Thurs: Elementary School 3-5pm",
                "services": "Mobile food pantry, fresh produce distribution",
                "description": "Brings food directly to underserved neighborhoods. Free groceries including fresh fruits and vegetables.",
                "eligibility": "No restrictions",
                "languages": "English, Spanish",
                "contact_person": "Mike Rodriguez, Mobile Coordinator",
                "last_verified": "2024-01-12",
            },
        },
        # HARD CASE 2: Faith-based with complex eligibility
        {
            "test_name": "faith_based_complex",
            "difficulty": "hard",
            "source_type": "scraped",
            "data": {
                "name": "St. Mary's Community Kitchen",
                "address": "147 Faith Avenue, Denver, CO 80222",
                "phone": "555-789-0123",
                "website": "https://www.stmarysexample.org/kitchen",
                "description": "A faith-based organization providing hot meals, food pantry services, and emergency assistance to individuals and families facing food insecurity.",
                "services": "Hot meals (Mon-Fri 12pm-1pm), Food pantry (Wed 10am-2pm), Holiday food baskets (Thanksgiving and Christmas), Emergency assistance",
                "eligibility": "Income below 200% federal poverty level, Documentation required for pantry services",
                "languages": "English",
                "contact": "kitchen@stmarysexample.org",
                "notes": "Faith-based organization, Religious Organization status, Volunteer-run",
            },
        },
        # HARD CASE 3: Government/Health Department data
        {
            "test_name": "government_health_dept",
            "difficulty": "hard",
            "source_type": "government",
            "data": {
                "agency_name": "Example Health Department Nutrition Services",
                "program_name": "WIC and SNAP Outreach Program",
                "address": "258 Government Boulevard, Denver, CO 80207",
                "phone": "555-890-1234",
                "website": "https://www.examplehealth.gov/nutrition",
                "programs": "WIC enrollment and certification, SNAP application assistance, Nutrition education services, Farmers market vouchers",
                "hours": "Monday-Friday 8am-5pm, Evening appointments available",
                "eligibility": "WIC: Pregnant women, new mothers, infants and children up to age 5 who are at nutritional risk and meet income guidelines. SNAP: Income at or below 130% of federal poverty level",
                "languages": "English, Spanish, interpretation services available",
                "services": "Nutrition counseling, Breastfeeding support, Referrals to food assistance programs",
                "documentation": "ID, proof of income, proof of residency required",
                "contact_email": "nutrition@examplehealth.gov",
            },
        },
        # HARD CASE 4: Minimal/incomplete data
        {
            "test_name": "minimal_incomplete",
            "difficulty": "hard",
            "source_type": "scraped",
            "data": {
                "name": "Neighborhood Food Co-op",
                "phone": "555-567-8901",
                "info": "Community-owned cooperative with sliding-scale food pantry for members",
                "location": "somewhere in downtown area",
                "hours": "varies",
            },
        },
    ]


async def run_single_test(
    model_name: str,
    test_case: dict[str, Any],
    verbose: bool = False,
    timeout_seconds: int = DEFAULT_TIMEOUT,
    debug: bool = False,
) -> TestResult:
    """Run a single test for the specified model with a specific test case.

    Args:
        model_name: The name of the model to test
        test_case: The test case data with metadata
        verbose: Whether to print verbose output
        timeout_seconds: Timeout in seconds
        debug: Whether to enable debug mode

    Returns:
        TestResult: The test result with enhanced metrics
    """
    provider = create_provider(model_name)
    schema_path = project_root / "docs/HSDS/schema/simple/schema.csv"

    validation_config = ValidationConfig(
        min_confidence=0.90,  # Set 90% confidence threshold
        retry_threshold=0.5,  # Higher retry threshold for better quality
        max_retries=5,  # Limit to 3 retries maximum
    )

    # Cast provider to correct type for HSDSAligner
    typed_provider = cast(BaseLLMProvider[Any, OpenAIConfig], provider)

    # Create aligner with validation
    aligner = HSDSAligner[Any, OpenAIConfig](
        provider=typed_provider,
        schema_path=schema_path,
        validation_config=validation_config,
        validation_provider=typed_provider,
    )

    # Extract test data
    input_data = test_case["data"]
    test_name = test_case["test_name"]
    difficulty = test_case["difficulty"]
    source_type = test_case["source_type"]

    # Create alignment input
    alignment_input: AlignmentInputDict = {
        "raw_data": str(input_data),
        "source_format": "python_dict",
    }

    # Track metrics
    start_time = time.time()
    success = False
    confidence_score = 0.0
    error: Optional[str] = None

    # Initialize enhanced metrics
    field_mapping_score = 0.0
    data_completeness_score = 0.0
    service_classification_score = 0.0
    hsds_structure_score = 0.0

    # Create a simple retry counter
    retries = 0

    # Create a custom print function to track retries
    original_print = print

    def count_retries_print(*args: Any, **kwargs: Any) -> None:
        nonlocal retries
        message = " ".join(str(arg) for arg in args)
        if "Retrying..." in message:
            retries += 1
            if debug:
                original_print(f"Retry #{retries} detected")
        if verbose or debug:
            original_print(*args, **kwargs)

    try:
        # Temporarily replace the print function to count retries
        builtins.print = count_retries_print

        if debug:
            print(
                f"Starting alignment with {model_name} for {test_name}, timeout: {timeout_seconds}s"
            )

        # Perform alignment with validation and timeout
        try:
            result = await asyncio.wait_for(
                aligner.align(alignment_input["raw_data"]), timeout=timeout_seconds
            )

            if debug:
                print(f"Alignment completed with {retries} retries")
        finally:
            # Restore the original print function
            builtins.print = original_print

        # Extract metrics
        confidence_score = result["confidence_score"]
        hsds_data = result["hsds_data"]

        # Verify basic HSDS structure
        assert len(hsds_data["organization"]) > 0, "No organizations found"
        assert len(hsds_data["service"]) > 0, "No services found"
        assert len(hsds_data["location"]) > 0, "No locations found"

        # Verify organization has services
        org = hsds_data["organization"][0]
        assert len(org["services"]) > 0, "Organization missing services"

        # Calculate enhanced metrics
        field_mapping_score = calculate_field_mapping_score(input_data, hsds_data)
        data_completeness_score = calculate_data_completeness_score(hsds_data)
        service_classification_score = calculate_service_classification_score(
            input_data, hsds_data
        )
        hsds_structure_score = calculate_hsds_structure_score(hsds_data)

        success = True

    except asyncio.TimeoutError:
        # Restore the original print function
        builtins.print = original_print

        error = f"Timeout after {timeout_seconds} seconds"
        if verbose or debug:
            print(f"Error: {error}")

    except Exception as e:
        # Restore the original print function
        builtins.print = original_print

        error = str(e)
        if verbose or debug:
            print(f"Error: {error}")

    execution_time = time.time() - start_time

    return {
        "success": success,
        "confidence_score": confidence_score,
        "retries": retries,
        "execution_time": execution_time,
        "error": error,
        "test_name": test_name,
        "difficulty": difficulty,
        "source_type": source_type,
        "field_mapping_score": field_mapping_score,
        "data_completeness_score": data_completeness_score,
        "service_classification_score": service_classification_score,
        "hsds_structure_score": hsds_structure_score,
    }


def calculate_summary(results: List[TestResult]) -> Dict[str, Any]:
    """Calculate summary statistics for test results.

    Args:
        results: The list of test results

    Returns:
        Dict[str, Any]: The summary statistics
    """
    successful_results = [r for r in results if r["success"]]
    success_rate = len(successful_results) / len(results) if results else 0

    if successful_results:
        confidence_scores = [r["confidence_score"] for r in successful_results]
        retry_counts = [r["retries"] for r in successful_results]
        execution_times = [r["execution_time"] for r in successful_results]

        return {
            "success_rate": success_rate,
            "avg_confidence": mean(confidence_scores) if confidence_scores else 0,
            "avg_retries": mean(retry_counts) if retry_counts else 0,
            "avg_execution_time": mean(execution_times) if execution_times else 0,
            "std_confidence": (
                stdev(confidence_scores) if len(confidence_scores) > 1 else 0
            ),
            "std_retries": stdev(retry_counts) if len(retry_counts) > 1 else 0,
            "std_execution_time": (
                stdev(execution_times) if len(execution_times) > 1 else 0
            ),
            "median_confidence": median(confidence_scores) if confidence_scores else 0,
            "median_retries": median(retry_counts) if retry_counts else 0,
            "median_execution_time": median(execution_times) if execution_times else 0,
        }
    else:
        return {
            "success_rate": 0,
            "avg_confidence": 0,
            "avg_retries": 0,
            "avg_execution_time": 0,
            "std_confidence": 0,
            "std_retries": 0,
            "std_execution_time": 0,
            "median_confidence": 0,
            "median_retries": 0,
            "median_execution_time": 0,
        }


async def evaluate_model(
    model_name: str,
    iterations: int = 1,
    verbose: bool = False,
    timeout_seconds: int = DEFAULT_TIMEOUT,
    debug: bool = False,
) -> ModelResult:
    """Evaluate a model by running multiple tests across different test cases.

    Args:
        model_name: The name of the model to evaluate
        iterations: The number of times to run through all test cases
        verbose: Whether to print verbose output
        timeout_seconds: Timeout in seconds
        debug: Whether to enable debug mode

    Returns:
        ModelResult: The model evaluation result with enhanced metrics
    """
    print(f"\nEvaluating model: {model_name}")
    results: List[TestResult] = []
    test_cases = get_test_data()

    # Calculate total number of tests: iterations x number of test cases
    total_tests = iterations * len(test_cases)

    for i in range(total_tests):
        # Cycle through test cases
        test_case = test_cases[i % len(test_cases)]
        iteration_num = (i // len(test_cases)) + 1
        case_num = (i % len(test_cases)) + 1
        print(
            f"  Running test {i+1}/{total_tests} [iteration {iteration_num}, case {case_num}: {test_case['test_name']}]...",
            end="",
            flush=True,
        )

        try:
            result = await run_single_test(
                model_name, test_case, verbose, timeout_seconds, debug
            )
            results.append(result)
            status = "✓" if result["success"] else "✗"
            print(
                f" {status} ({result['execution_time']:.1f}s, retries: {result['retries']})"
            )
        except Exception as e:
            print(f" ✗ (Error: {str(e)})")
            # Create a proper TestResult with all required fields
            error_result: TestResult = {
                "success": False,
                "confidence_score": 0.0,
                "retries": 0,
                "execution_time": 0.0,
                "error": str(e),
                "test_name": test_case["test_name"],
                "difficulty": test_case["difficulty"],
                "source_type": test_case["source_type"],
                "field_mapping_score": 0.0,
                "data_completeness_score": 0.0,
                "service_classification_score": 0.0,
                "hsds_structure_score": 0.0,
            }
            results.append(error_result)

    # Calculate basic summary
    summary = calculate_summary(results)

    # Calculate enhanced metrics
    successful_results = [r for r in results if r["success"]]

    # Enhanced metric averages
    avg_field_mapping_score = (
        mean([r["field_mapping_score"] for r in successful_results])
        if successful_results
        else 0.0
    )
    avg_data_completeness_score = (
        mean([r["data_completeness_score"] for r in successful_results])
        if successful_results
        else 0.0
    )
    avg_service_classification_score = (
        mean([r["service_classification_score"] for r in successful_results])
        if successful_results
        else 0.0
    )
    avg_hsds_structure_score = (
        mean([r["hsds_structure_score"] for r in successful_results])
        if successful_results
        else 0.0
    )

    # Performance by difficulty
    performance_by_difficulty: Dict[str, float] = {}
    for difficulty in ["easy", "medium", "hard"]:
        difficulty_results = [r for r in results if r["difficulty"] == difficulty]
        if difficulty_results:
            performance_by_difficulty[difficulty] = len(
                [r for r in difficulty_results if r["success"]]
            ) / len(difficulty_results)
        else:
            performance_by_difficulty[difficulty] = 0.0

    # Performance by source type
    performance_by_source_type: Dict[str, float] = {}
    for source_type in ["structured", "csv", "scraped", "government"]:
        source_results = [r for r in results if r["source_type"] == source_type]
        if source_results:
            performance_by_source_type[source_type] = len(
                [r for r in source_results if r["success"]]
            ) / len(source_results)
        else:
            performance_by_source_type[source_type] = 0.0

    return {
        "model_name": model_name,
        "results": results,
        "success_rate": summary["success_rate"],
        "avg_confidence": summary["avg_confidence"],
        "avg_retries": summary["avg_retries"],
        "avg_execution_time": summary["avg_execution_time"],
        "std_confidence": summary["std_confidence"],
        "std_retries": summary["std_retries"],
        "std_execution_time": summary["std_execution_time"],
        "avg_field_mapping_score": avg_field_mapping_score,
        "avg_data_completeness_score": avg_data_completeness_score,
        "avg_service_classification_score": avg_service_classification_score,
        "avg_hsds_structure_score": avg_hsds_structure_score,
        "performance_by_difficulty": performance_by_difficulty,
        "performance_by_source_type": performance_by_source_type,
    }


def print_model_result(result: ModelResult) -> None:
    """Print the result for a single model.

    Args:
        result: The model result to print
    """
    print(f"\nModel: {result['model_name']}")
    print(
        f"  Success Rate: {result['success_rate']:.0%} ({sum(1 for r in result['results'] if r['success'])}/{len(result['results'])})"
    )
    print(
        f"  Avg Confidence: {result['avg_confidence']:.2f} ± {result['std_confidence']:.2f}"
    )
    print(f"  Avg Retries: {result['avg_retries']:.1f} ± {result['std_retries']:.1f}")
    print(
        f"  Execution Time: {result['avg_execution_time']:.1f}s ± {result['std_execution_time']:.1f}s"
    )

    # Enhanced metrics
    print("  Enhanced Metrics:")
    print(f"    Field Mapping: {result['avg_field_mapping_score']:.2f}")
    print(f"    Data Completeness: {result['avg_data_completeness_score']:.2f}")
    print(
        f"    Service Classification: {result['avg_service_classification_score']:.2f}"
    )
    print(f"    HSDS Structure: {result['avg_hsds_structure_score']:.2f}")

    # Performance by difficulty
    print("  Performance by Difficulty:")
    for difficulty, rate in result["performance_by_difficulty"].items():
        print(f"    {difficulty.capitalize()}: {rate:.0%}")

    # Performance by source type
    print("  Performance by Source Type:")
    for source_type, rate in result["performance_by_source_type"].items():
        print(f"    {source_type.capitalize()}: {rate:.0%}")


def print_summary(all_results: List[ModelResult]) -> None:
    """Print a summary of all model results.

    Args:
        all_results: The list of all model results
    """
    print("\n===== Summary =====")

    # Sort by different metrics
    by_success_rate = sorted(all_results, key=lambda r: r["success_rate"], reverse=True)
    by_confidence = sorted(all_results, key=lambda r: r["avg_confidence"], reverse=True)
    by_execution_time = sorted(all_results, key=lambda r: r["avg_execution_time"])
    by_retries = sorted(all_results, key=lambda r: r["avg_retries"])

    print(
        f"Best Success Rate: {by_success_rate[0]['model_name']} ({by_success_rate[0]['success_rate']:.0%})"
    )
    print(
        f"Best Confidence: {by_confidence[0]['model_name']} ({by_confidence[0]['avg_confidence']:.2f})"
    )
    print(
        f"Fastest Model: {by_execution_time[0]['model_name']} ({by_execution_time[0]['avg_execution_time']:.1f}s)"
    )
    print(
        f"Fewest Retries: {by_retries[0]['model_name']} ({by_retries[0]['avg_retries']:.1f})"
    )


async def main() -> None:
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Evaluate LLM models for HSDS data processing"
    )
    parser.add_argument("--models", nargs="+", help="Models to evaluate (default: all)")
    parser.add_argument(
        "--iterations",
        type=int,
        default=1,
        help="Number of times to run through all test cases per model (default: 1)",
    )
    parser.add_argument("--verbose", action="store_true", help="Print verbose output")
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Timeout in seconds for each test (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--debug", action="store_true", help="Enable debug mode with additional logging"
    )
    parser.add_argument(
        "--quick-test",
        action="store_true",
        help="Run a quick test with just one model and one iteration",
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Run model evaluations in parallel (faster but uses more resources)",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=3,
        help="Maximum number of parallel model evaluations (default: 3)",
    )
    args = parser.parse_args()

    # Check for API key
    if not os.getenv("OPENROUTER_API_KEY"):
        print("Error: OPENROUTER_API_KEY environment variable not set")
        sys.exit(1)

    # Select models to evaluate
    if args.quick_test:
        # Just use the baseline model
        models_to_evaluate = ["google/gemini-2.0-flash-001"]
        args.iterations = 1  # Just one iteration
        print("Running in quick test mode with one model and one iteration")
    else:
        models_to_evaluate = args.models if args.models else MODELS

    # Print header
    print("===== LLM Model Evaluation for HSDS Data Processing =====")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Iterations per model: {args.iterations}")
    print(f"Models to evaluate: {', '.join(models_to_evaluate)}")

    # Evaluate models
    all_results: List[ModelResult] = []

    if args.parallel:
        print(f"Running evaluations in parallel with max {args.max_workers} workers")

        # Create semaphore to limit concurrent evaluations
        semaphore = asyncio.Semaphore(args.max_workers)

        async def evaluate_model_with_semaphore(
            model_name: str,
        ) -> Optional[ModelResult]:
            async with semaphore:
                try:
                    result = await evaluate_model(
                        model_name,
                        args.iterations,
                        args.verbose,
                        args.timeout,
                        args.debug,
                    )
                    return result
                except Exception as e:
                    print(f"Error evaluating model {model_name}: {str(e)}")
                    if args.debug:
                        import traceback

                        traceback.print_exc()
                    return None

        # Run evaluations in parallel
        tasks = [
            evaluate_model_with_semaphore(model_name)
            for model_name in models_to_evaluate
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"Error evaluating model {models_to_evaluate[i]}: {str(result)}")
                if args.debug:
                    import traceback

                    traceback.print_exception(
                        type(result), result, result.__traceback__
                    )
            elif result is not None:
                # Type cast to ensure ModelResult type
                model_result = cast(ModelResult, result)
                all_results.append(model_result)
                print_model_result(model_result)
    else:
        # Sequential evaluation (original behavior)
        for model_name in models_to_evaluate:
            try:
                result = await evaluate_model(
                    model_name, args.iterations, args.verbose, args.timeout, args.debug
                )
                all_results.append(result)
                print_model_result(result)
            except Exception as e:
                print(f"Error evaluating model {model_name}: {str(e)}")
                if args.debug:
                    import traceback

                    traceback.print_exc()

    # Print summary if we have results
    if all_results:
        print_summary(all_results)
    else:
        print("\nNo results to summarize.")


if __name__ == "__main__":
    asyncio.run(main())
