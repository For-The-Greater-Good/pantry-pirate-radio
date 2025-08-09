#!/usr/bin/env python
"""
LLM Model Evaluation Script for HSDS Data Processing

This script evaluates multiple LLM models from OpenRouter for their ability
to process data according to the HSDS specification using the production pipeline.
"""

import argparse
import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from statistics import mean, median, stdev
from typing import Any, Dict, List, Optional, TypedDict, cast

# Configure logging early to suppress debug messages by default
# Check for environment variable to enable debug logging
if os.getenv("EVAL_DEBUG"):
    logging.basicConfig(level=logging.DEBUG)
else:
    # Default: suppress debug and info messages from libraries
    logging.basicConfig(level=logging.WARNING, format='%(message)s')
    # Suppress noisy loggers
    for logger_name in ["openai_provider", "app.llm", "app", "root", "httpx", "httpcore"]:
        logging.getLogger(logger_name).setLevel(logging.ERROR)

import demjson3

# Add project root to path to allow imports
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from app.llm.hsds_aligner.schema_converter import SchemaConverter
from app.llm.hsds_aligner.validation import ValidationConfig
from app.llm.providers.openai import OpenAIConfig, OpenAIProvider
from app.llm.providers.types import GenerateConfig


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
    "openai/gpt-5-nano",  # Baseline
    "google/gemini-2.5-flash-lite",  # Same price as baseline
    "meta-llama/llama-3.1-8b-instruct",
    "qwen/qwen3-30b-a3b-instruct-2507",  # Qwen 30B A3B instruct
    "openai/gpt-oss-120b",
    "claude-3-5-haiku-latest",  # Claude Haiku
    "claude-3-5-sonnet-20241022",  # Claude Sonnet
]

# Model pricing per million tokens (in USD)
MODEL_PRICING = {
    "openai/gpt-5-nano": {"input": 0.05, "output": 0.40},
    "google/gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40},
    "google/gemini-2.0-flash-lite-001": {"input": 0.075, "output": 0.30},
    "deepseek/deepseek-chat-v3-0324": {"input": 0.77, "output": 0.77},
    "mistralai/mistral-nemo": {"input": 0.025, "output": 0.05},
    "mistralai/mistral-small-3.2-24b-instruct": {"input": 0.02, "output": 0.08},
    "meta-llama/llama-3.1-8b-instruct": {"input": 0.02, "output": 0.03},
    "qwen/qwen3-14b": {"input": 0.06, "output": 0.24},
    "qwen/qwen3-30b-a3b-instruct-2507": {"input": 0.20, "output": 0.80},  # $0.20/M input, $0.80/M output
    "qwen/qwq-32b": {"input": 0.15, "output": 0.40},
    "openai/gpt-oss-120b": {"input": 0.15, "output": 0.60},
    "openai/gpt-oss-20b": {"input": 0.05, "output": 0.20},
    # Claude models pricing - FREE when using Claude CLI
    "claude-3-5-haiku-latest": {"input": 0.00, "output": 0.00},  # Free via Claude CLI
    "claude-3-5-sonnet-20241022": {"input": 0.00, "output": 0.00},  # Free via Claude CLI
}

# Based on actual usage: 50k records for $25 with gemini-2.5-flash-lite = $0.50 per 1000
# Updated assumption: 10k tokens per location (more realistic for complex prompts and data)
TYPICAL_INPUT_TOKENS = 10000  # Prompt + food pantry data (10k tokens per location)
TYPICAL_OUTPUT_TOKENS = 2500   # HSDS formatted response (proportionally scaled)

def calculate_cost_per_1000(model_name: str) -> float:
    """Calculate estimated cost per 1000 operations based on actual token usage."""
    if model_name not in MODEL_PRICING:
        return 0.0

    pricing = MODEL_PRICING[model_name]
    # Cost for 1000 operations
    input_cost = (TYPICAL_INPUT_TOKENS * 1000 * pricing["input"]) / 1_000_000
    output_cost = (TYPICAL_OUTPUT_TOKENS * 1000 * pricing["output"]) / 1_000_000

    return input_cost + output_cost

# Default timeout in seconds
DEFAULT_TIMEOUT = 90  # 90 seconds


def load_prompt() -> str:
    """Load the system prompt from file."""
    prompt_path = project_root / "app/llm/hsds_aligner/prompts/food_pantry_mapper.prompt"
    return prompt_path.read_text()


def extract_json_from_markdown(text: str) -> str:
    """Extract JSON content from markdown code blocks.

    Args:
        text: Text that may contain markdown code blocks

    Returns:
        str: Extracted JSON content or original text if no code blocks found
    """
    if not text:
        return ""

    # First, check if the entire text is already valid JSON (no markdown)
    text = text.strip()

    # Handle case where response might just be the word "Invalid" or similar
    if len(text) < 10 and not text.startswith('{') and not text.startswith('['):
        # Probably an error message, not JSON
        return ""

    if text.startswith('{') or text.startswith('['):
        # Might already be JSON, clean it up
        # Remove any trailing commas before closing braces/brackets
        text = re.sub(r',\s*([}\]])', r'\1', text)
        return text

    # Look for ```json ... ``` blocks
    json_block_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if json_block_match:
        extracted = json_block_match.group(1).strip()
        # Clean up common LLM mistakes
        extracted = re.sub(r":\s*I\s+don\'t\s+know", ': "Unknown"', extracted)
        extracted = re.sub(r":\s*I\s+am\s+not\s+sure", ': "Unknown"', extracted)
        extracted = re.sub(r":\s*null\s*,", ': null,', extracted)  # Fix null values
        extracted = re.sub(r":\s*undefined", ': null', extracted)  # Fix undefined
        # Remove any trailing commas before closing braces/brackets
        extracted = re.sub(r',\s*([}\]])', r'\1', extracted)
        return extracted

    # If no code blocks found, try to extract JSON if it's embedded in other text
    # Look for JSON-like structure
    json_match = re.search(r'(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})', text, re.DOTALL)
    if json_match:
        extracted = json_match.group(1)
        # Clean up
        extracted = re.sub(r',\s*([}\]])', r'\1', extracted)
        return extracted

    # If still nothing, but text contains curly braces, might be malformed
    if '{' in text and '}' in text:
        # Try to extract between first { and last }
        start = text.find('{')
        end = text.rfind('}')
        if start < end:
            extracted = text[start:end+1]
            # Clean up
            extracted = re.sub(r',\s*([}\]])', r'\1', extracted)
            return extracted

    return text


def transform_llm_output(raw_data: dict[str, Any]) -> dict[str, Any]:
    """Transform LLM output to expected HSDS structure.

    This mimics the production job processor's transformation logic.

    Args:
        raw_data: Raw parsed JSON from LLM

    Returns:
        Transformed HSDS structure with top-level arrays
    """
    # Case 1: Array at top level - extract first element
    if isinstance(raw_data, list) and len(raw_data) > 0:
        raw_data = raw_data[0]

    # Case 2: Single organization object with nested services/locations
    if (
        isinstance(raw_data, dict)
        and "name" in raw_data
        and "organization" not in raw_data
    ):
        # Extract services and locations from the organization object
        services = raw_data.pop("services", [])
        locations = raw_data.pop("locations", [])

        # Create the expected structure
        return {
            "organization": [raw_data],
            "service": services,
            "location": locations,
        }

    # Case 3: Organization is a single object instead of array
    elif (
        isinstance(raw_data, dict)
        and "organization" in raw_data
        and isinstance(raw_data["organization"], dict)
    ):
        raw_data["organization"] = [raw_data["organization"]]

        # Also ensure service and location are arrays
        if "service" in raw_data and isinstance(raw_data["service"], dict):
            raw_data["service"] = [raw_data["service"]]
        if "location" in raw_data and isinstance(raw_data["location"], dict):
            raw_data["location"] = [raw_data["location"]]

        return raw_data

    # Use the data as-is
    return raw_data


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
    total_checks = 0  # Will count actual checks performed

    # Required organizations
    if hsds_data.get("organization") and len(hsds_data["organization"]) > 0:
        total_checks += 1
        score += 1.0
        org = hsds_data["organization"][0]

        # Organization has name
        total_checks += 1
        if org.get("name"):
            score += 1.0

        # Organization has description
        total_checks += 1
        if org.get("description"):
            score += 1.0

        # Organization has services (embedded or referenced)
        total_checks += 1
        if (org.get("services") and len(org["services"]) > 0) or \
           (hsds_data.get("service") and len(hsds_data["service"]) > 0):
            score += 1.0

    # Services if present
    if hsds_data.get("service") and len(hsds_data["service"]) > 0:
        total_checks += 1
        score += 1.0
        service = hsds_data["service"][0]

        # Service has name
        total_checks += 1
        if service.get("name"):
            score += 1.0
    elif hsds_data.get("organization") and hsds_data["organization"]:
        # Check for embedded services
        org = hsds_data["organization"][0]
        if org.get("services") and len(org["services"]) > 0:
            total_checks += 1
            score += 1.0

    # Locations if present
    if hsds_data.get("location") and len(hsds_data["location"]) > 0:
        total_checks += 1
        score += 1.0
        location = hsds_data["location"][0]

        # Location has address or coordinates
        total_checks += 1
        if location.get("physical_addresses") or location.get("addresses") or \
           location.get("address") or \
           (location.get("latitude") and location.get("longitude")):
            score += 1.0
    elif hsds_data.get("organization") and hsds_data["organization"]:
        # Check for embedded locations
        org = hsds_data["organization"][0]
        if org.get("locations") and len(org["locations"]) > 0:
            total_checks += 1
            score += 1.0

    return score / total_checks if total_checks > 0 else 0.0


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

    # Try to find services in either top-level or embedded in organization
    service = None
    if hsds_data.get("service") and hsds_data["service"]:
        service = hsds_data["service"][0]
    elif hsds_data.get("organization") and hsds_data["organization"]:
        org = hsds_data["organization"][0]
        if org.get("services") and org["services"]:
            service = org["services"][0]

    if service:
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


class ClaudeProvider:
    """Provider for Claude models using the CLI."""
    
    def __init__(self, model_name: str):
        self.model_name = model_name
        
    async def generate(self, prompt: str, config: Optional[Any] = None, temperature: float = 0.7, response_format: Optional[dict] = None) -> Any:
        """Generate a response using Claude CLI.
        
        Args:
            prompt: The prompt to send to Claude
            config: Configuration object (for compatibility with OpenAI provider)
            temperature: Temperature parameter (not used for Claude CLI currently)
            response_format: Response format specification (for structured output)
            
        Returns:
            Response object with text attribute
        """
        try:
            # Build the full prompt with JSON instruction
            full_prompt = prompt + "\n\nPlease respond with valid JSON only, no additional text or markdown formatting."
            
            # Prepare the command
            cmd = [
                "claude",
                "--model", self.model_name,
            ]
            
            # Run the command with the prompt as stdin
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Send the prompt and get response
            stdout, stderr = await process.communicate(full_prompt.encode())
            
            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                raise RuntimeError(f"Claude CLI failed: {error_msg}")
            
            # Parse the response
            response_text = stdout.decode().strip()
            
            # Create a response object similar to OpenAI's
            class ClaudeResponse:
                def __init__(self, text, model):
                    self.text = text
                    self.model = model
                    
            return ClaudeResponse(response_text, self.model_name)
            
        except FileNotFoundError:
            raise RuntimeError("Claude CLI not found. Please ensure 'claude' command is available in PATH")
        except Exception as e:
            raise RuntimeError(f"Error calling Claude CLI: {str(e)}")


def create_provider(model_name: str) -> Any:
    """Create a provider with the specified model.

    Args:
        model_name: The name of the model to use

    Returns:
        Provider: The configured provider (OpenAIProvider or ClaudeProvider)
    """
    # Check if it's a Claude model
    if model_name.startswith("claude-"):
        return ClaudeProvider(model_name)
    
    # Otherwise, use OpenAI provider for OpenRouter models
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
    """Get test data from real scraper outputs.

    These are actual examples from production scrapers to ensure realistic testing.

    Returns:
        List of test data dictionaries with varying complexity levels
    """
    return [
        # REAL EXAMPLE 1: feeding_the_gulf_coast_al - Complete with all fields
        {
            "test_name": "gulf_coast_complete",
            "difficulty": "easy",
            "source_type": "structured",
            "data": {
                "name": "Atmore Area Christian Care",
                "zip": "36502",
                "state": "AL",
                "address": "923 West Nashville Avenue",
                "city": "Atmore",
                "phone": "(251) 446-3476",
                "distance": "0.0 miles",
                "notes": "Tuesday - Thursday 9:00 AM - 12:00 PM",
                "latitude": 30.69367872652979,
                "longitude": -88.05062482583588,
                "source": "feeding_the_gulf_coast_al",
                "food_bank": "Feeding the Gulf Coast"
            },
        },
        # REAL EXAMPLE 2: the_food_pantries_org - Complex hours format
        {
            "test_name": "food_pantries_org_complex",
            "difficulty": "easy",
            "source_type": "structured",
            "data": {
                "Name": "Penates Inc.",
                "Entity_Id": 1802,
                "Category": "Food Pantry",
                "Subcategory": "All Other - NYS Food Pantries",
                "Organization": "Penates Inc.",
                "More_Information": "Call to verify hours of operation and to see if an appointment is required",
                "Counties": ["Suffolk"],
                "Location": "",
                "Address": "1356 5th Ave.",
                "City": "Bay Shore",
                "State": "NY",
                "Zip": "11706",
                "Phone": "631-665-2866",
                "Hours_of_Operation": "Every Wednesday  9:00 AM 1:00 PM \n Every Friday  9:00 AM 1:00 PM \n Every Wednesday  9:00AM 1:00 PM \n Every Friday  9:00AM 1:00 PM",
                "Cost": "",
                "Accepts": "",
                "Website": "",
                "Coalition": None,
                "CFAN": 0,
                "Latitude": "40.738795",
                "Longitude": "-73.263671",
                "Last_Updated": "02-21-2023",
                "icon": "marker-C53E2A",
            },
        },
        # REAL EXAMPLE 3: mercer_food_finder - Government/nutrition program
        {
            "test_name": "mercer_county_nutrition",
            "difficulty": "medium",
            "source_type": "government",
            "data": {
                "name": "Mercer County Nutrition Program for Older Adults (Hamilton site - John O. Wilson Hamilton Neighborhood Service Center)",
                "address": "169 Wilfred Avenue Hamilton, NJ 08610",
                "phone": "609-989-6650",
                "description": "Open to anyone 60 years old or older and their spouses (regardless of age), any county resident with a disability whose primary caregiver is a program participant, anyone volunteering in the program, and the personal care aides of program participants (when they accompany a participant to the site where meals are provided). This program encourages participants to make a suggested donation of $1 for their daily meal.\n\nParticipants must register for the program by calling 609-989-6650. Transportation can be made available, anyone interested can contact the program for details.",
                "county": "Mercer",
                "state": "NJ",
                "latitude": 40.203370391486,
                "longitude": -74.7283017052,
                "geocoder": "nominatim"
            },
        },
        # REAL EXAMPLE 4: food_helpline_org - Complex schedule format
        {
            "test_name": "food_helpline_schedule",
            "difficulty": "medium",
            "source_type": "structured",
            "data": {
                "name": "Temple Community 2",
                "alternate_name": "",
                "description": "Katrina\tWatkins\t9088204220\nStarts: 07/07/2025\t08/15/2025",
                "email": "",
                "url": None,
                "status": "active",
                "address": {
                    "address_1": "630 South Street",
                    "address_2": None,
                    "city": "Elizabeth",
                    "state_province": "NJ",
                    "postal_code": "07202",
                    "country": "US"
                },
                "location": {
                    "latitude": 40.657862,
                    "longitude": -74.2123896
                },
                "phones": [
                    {
                        "number": "(908) 820-4220",
                        "type": "voice"
                    }
                ],
                "regular_schedule": [
                    {"weekday": "Monday", "opens_at": "15:30", "closes_at": "16:30"},
                    {"weekday": "Tuesday", "opens_at": "15:30", "closes_at": "16:30"},
                    {"weekday": "Wednesday", "opens_at": "15:30", "closes_at": "16:30"},
                    {"weekday": "Thursday", "opens_at": "15:30", "closes_at": "16:30"},
                    {"weekday": "Friday", "opens_at": "15:30", "closes_at": "16:30"},
                ],
                "service_attributes": [
                    {"attribute_key": "REQUIREMENT", "attribute_value": "Students & staff only"},
                    {"attribute_key": "INFO", "attribute_value": "Summer Meal Program"}
                ]
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
    quiet: bool = False,
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

    # Load schema and prompt
    schema_path = project_root / "docs/HSDS/schema/simple/schema.csv"
    prompt_path = project_root / "app/llm/hsds_aligner/prompts/food_pantry_mapper.prompt"

    schema_converter = SchemaConverter(schema_path)
    system_prompt = prompt_path.read_text()

    # Convert schema for structured output
    hsds_schema = schema_converter.convert_to_llm_schema("organization")

    # Extract test data
    input_data = test_case["data"]
    test_name = test_case["test_name"]
    difficulty = test_case["difficulty"]
    source_type = test_case["source_type"]

    # Prepare prompt
    full_prompt = f"{system_prompt}\n\nInput Data:\n{input_data}"

    # Track metrics
    start_time = time.time()
    success = False
    confidence_score = 0.0
    error: Optional[str] = None
    retries = 0

    # Initialize enhanced metrics
    field_mapping_score = 0.0
    data_completeness_score = 0.0
    service_classification_score = 0.0
    hsds_structure_score = 0.0

    if debug and not quiet:
        print(f"Starting test {test_name} with {model_name}, timeout: {timeout_seconds}s")

    try:
        # Configure generation
        config = GenerateConfig(
            temperature=0.7,
            max_tokens=64768,
            format={
                "type": "json_schema",
                "schema": cast(dict[str, Any], hsds_schema["json_schema"]),
                "strict": True,
            },
        )

        # Generate response with timeout
        response = await asyncio.wait_for(
            provider.generate(full_prompt, config=config),
            timeout=timeout_seconds
        )

        if not quiet and debug:
            print(f"Response received for {test_name}")
            print(f"Raw response text length: {len(response.text) if response.text else 0}")
            if debug and not quiet and response.text:
                print(f"Raw response preview: {response.text[:200]}..." if len(response.text) > 200 else f"Raw response: {response.text}")

        # Check if response is empty
        if not response.text or response.text.strip() == "":
            raise ValueError("Empty response from LLM - no text returned")

        # Parse response
        json_text = extract_json_from_markdown(response.text)

        # Debug: Show what we're trying to parse
        if debug and not quiet:
            print(f"Extracted JSON text length: {len(json_text)}")
            if not quiet:
                if len(json_text) < 100:
                    print(f"Short JSON text: '{json_text}'")
                else:
                    print(f"JSON text starts with: {json_text[:100]}...")

        # Check if we have empty JSON after extraction
        if not json_text or json_text.strip() == "":
            raise ValueError(f"Empty JSON after extraction from response: {response.text[:500]}")

        # Try standard JSON parsing first
        try:
            raw_data = json.loads(json_text)
        except json.JSONDecodeError as e:
            # If standard parsing fails, use demjson3 which is more tolerant
            if debug and not quiet:
                print(f"Standard JSON parsing failed: {e}, trying demjson3")
                # Show the problematic part of JSON
                error_pos = e.pos if hasattr(e, 'pos') else 0
                if error_pos < len(json_text):
                    context_start = max(0, error_pos-50)
                    context_end = min(len(json_text), error_pos+50)
                    if not quiet:
                        print(f"Error at position {error_pos}:")
                        print(f"  Context: ...{json_text[context_start:context_end]}...")
                        print(f"  Error char: '{json_text[error_pos]}'" if error_pos < len(json_text) else "EOF")
            try:
                import demjson3
                raw_data = demjson3.decode(json_text, strict=False)
            except Exception as demjson_error:
                # If both fail, show more context
                if debug and not quiet:
                    print(f"demjson3 also failed: {demjson_error}")
                    print(f"JSON text that failed: {json_text[:500]}")
                    print(f"Original response: {response.text[:500]}")

                # Try one more thing - see if it's an identifier issue
                if "Invalid" in str(demjson_error) or "Unknown identifier" in str(demjson_error):
                    # Sometimes the response is literally "Invalid" or contains unquoted strings
                    if debug and not quiet:
                        print(f"Response appears to be an error message, not JSON: {json_text[:100]}")
                    raise ValueError(f"LLM returned an error message instead of JSON: {json_text[:200]}")

                raise ValueError(f"Failed to parse JSON: {demjson_error}. Response may be incomplete or malformed.")

        # Transform to HSDS structure (mimicking production)
        hsds_data = transform_llm_output(raw_data)

        # Debug output to see what we got
        if debug and not quiet:
            print(f"Raw data keys: {raw_data.keys() if isinstance(raw_data, dict) else 'Not a dict'}")
            print(f"Transformed data keys: {hsds_data.keys() if isinstance(hsds_data, dict) else 'Not a dict'}")

        # Verify basic HSDS structure - but handle various formats
        # Some LLMs might not include all three top-level keys
        has_org = hsds_data.get("organization") and len(hsds_data.get("organization", [])) > 0
        has_service = hsds_data.get("service") and len(hsds_data.get("service", [])) > 0
        has_location = hsds_data.get("location") and len(hsds_data.get("location", [])) > 0

        # At minimum we need an organization
        if not has_org:
            # Try to extract organization data from other structures
            if "name" in hsds_data and "organization" not in hsds_data:
                # The entire response might be an organization object
                hsds_data = {
                    "organization": [hsds_data],
                    "service": hsds_data.get("services", []),
                    "location": hsds_data.get("locations", [])
                }
                has_org = True
                has_service = len(hsds_data.get("service", [])) > 0
                has_location = len(hsds_data.get("location", [])) > 0

        assert has_org, f"No organizations found in data: {list(hsds_data.keys()) if isinstance(hsds_data, dict) else hsds_data}"

        # Services and locations might be embedded in organization
        if not has_service and has_org:
            org = hsds_data["organization"][0]
            if "services" in org:
                hsds_data["service"] = org["services"]
                has_service = True

        if not has_location and has_org:
            org = hsds_data["organization"][0]
            if "locations" in org:
                hsds_data["location"] = org["locations"]
                has_location = True

        # Default empty arrays if still missing
        if "service" not in hsds_data:
            hsds_data["service"] = []
        if "location" not in hsds_data:
            hsds_data["location"] = []

        # For scoring purposes, we'll be more lenient - just need organization
        # Services and locations can be empty for minimal data cases

        # Calculate enhanced metrics
        field_mapping_score = calculate_field_mapping_score(input_data, hsds_data)
        data_completeness_score = calculate_data_completeness_score(hsds_data)
        service_classification_score = calculate_service_classification_score(
            input_data, hsds_data
        )
        hsds_structure_score = calculate_hsds_structure_score(hsds_data)

        # Simple confidence score based on metrics
        confidence_score = mean([
            field_mapping_score,
            data_completeness_score,
            service_classification_score,
            hsds_structure_score
        ])

        success = True

    except asyncio.TimeoutError:
        error = f"Timeout after {timeout_seconds} seconds"
        if not quiet and debug:
            print(f"Error: {error}")

    except Exception as e:
        error = str(e)
        if not quiet and debug:
            print(f"Error: {error}")
            if debug:
                import traceback
                traceback.print_exc()

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
    quiet: bool = False,
    parallel_tests: bool = True,
    max_concurrent_tests: int = 20,
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
    if not quiet:
        print(f"\nEvaluating model: {model_name}")
    results: List[TestResult] = []
    test_cases = get_test_data()

    # Calculate total number of tests: iterations x number of test cases
    total_tests = iterations * len(test_cases)

    if parallel_tests:
        # Run all tests in parallel with semaphore to limit concurrency
        if not quiet:
            print(f"  Running {total_tests} tests in parallel (max {max_concurrent_tests} concurrent)...")

        semaphore = asyncio.Semaphore(max_concurrent_tests)

        async def run_test_with_semaphore(test_index: int) -> TestResult:
            async with semaphore:
                test_case = test_cases[test_index % len(test_cases)]
                iteration_num = (test_index // len(test_cases)) + 1
                case_num = (test_index % len(test_cases)) + 1

                try:
                    result = await run_single_test(
                        model_name, test_case, verbose, timeout_seconds, debug, quiet
                    )
                    if not quiet:
                        status = "✓" if result["success"] else "✗"
                        print(f"  Test {test_index+1}/{total_tests} [{test_case['test_name']}]: {status}")
                    return result
                except Exception as e:
                    if not quiet:
                        print(f"  Test {test_index+1}/{total_tests} [{test_case['test_name']}]: ✗ (Error: {str(e)})")
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
                    return error_result

        # Create tasks for all tests
        tasks = [run_test_with_semaphore(i) for i in range(total_tests)]

        # Run all tasks and gather results
        results = await asyncio.gather(*tasks)

        if not quiet:
            successful = sum(1 for r in results if r["success"])
            print(f"  Completed: {successful}/{total_tests} tests succeeded")
    else:
        # Sequential execution (original behavior)
        for i in range(total_tests):
            # Cycle through test cases
            test_case = test_cases[i % len(test_cases)]
            iteration_num = (i // len(test_cases)) + 1
            case_num = (i % len(test_cases)) + 1
            if not quiet:
                print(
                    f"  Running test {i+1}/{total_tests} [iteration {iteration_num}, case {case_num}: {test_case['test_name']}]...",
                    end="",
                    flush=True,
                )

            try:
                result = await run_single_test(
                    model_name, test_case, verbose, timeout_seconds, debug, quiet
                )
                results.append(result)
                if not quiet:
                    status = "✓" if result["success"] else "✗"
                    print(
                        f" {status} ({result['execution_time']:.1f}s, retries: {result['retries']})"
                    )
            except Exception as e:
                if not quiet:
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
    for source_type in ["structured", "scraped", "government"]:  # Removed CSV - no test cases
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
    """Print the result for a single model with enhanced formatting.

    Args:
        result: The model result to print
    """
    print(f"\n{'='*80}")
    print(f"Model: {result['model_name']}")
    print(f"{'='*80}")

    # Basic Metrics
    print("\n📊 Basic Performance Metrics:")
    print(f"  ✅ Success Rate: {result['success_rate']:.1%} ({sum(1 for r in result['results'] if r['success'])}/{len(result['results'])} tests passed)")
    print(f"  🎯 Avg Confidence: {result['avg_confidence']:.3f} ± {result['std_confidence']:.3f}")
    print(f"  🔄 Avg Retries: {result['avg_retries']:.2f} ± {result['std_retries']:.2f}")
    print(f"  ⏱️  Execution Time: {result['avg_execution_time']:.2f}s ± {result['std_execution_time']:.2f}s")

    # Enhanced Quality Metrics
    print("\n📈 Quality Metrics (0.0 - 1.0 scale):")
    print(f"  📍 Field Mapping Score: {result['avg_field_mapping_score']:.3f}")
    print(f"  ✨ Data Completeness: {result['avg_data_completeness_score']:.3f}")
    print(f"  🏷️  Service Classification: {result['avg_service_classification_score']:.3f}")
    print(f"  🏗️  HSDS Structure Compliance: {result['avg_hsds_structure_score']:.3f}")

    # Overall quality score
    quality_scores = [
        result['avg_field_mapping_score'],
        result['avg_data_completeness_score'],
        result['avg_service_classification_score'],
        result['avg_hsds_structure_score']
    ]
    overall_quality = mean(quality_scores)
    print(f"  ⭐ Overall Quality Score: {overall_quality:.3f}")

    # Performance by difficulty
    print("\n🎚️  Performance by Difficulty Level:")
    for difficulty in ["easy", "medium", "hard"]:
        rate = result["performance_by_difficulty"].get(difficulty, 0)
        bar_length = int(rate * 20)
        bar = "█" * bar_length + "░" * (20 - bar_length)
        print(f"  {difficulty.capitalize():8s}: [{bar}] {rate:.1%}")

    # Performance by source type
    print("\n📂 Performance by Data Source Type:")
    for source_type in ["structured", "scraped", "government"]:  # Removed CSV - no test cases
        rate = result["performance_by_source_type"].get(source_type, 0)
        bar_length = int(rate * 20)
        bar = "█" * bar_length + "░" * (20 - bar_length)
        print(f"  {source_type.capitalize():12s}: [{bar}] {rate:.1%}")

    # Test case details
    print("\n📋 Individual Test Results:")
    for i, test_result in enumerate(result['results'], 1):
        status = "✅" if test_result['success'] else "❌"
        print(f"  {status} Test {i}: {test_result['test_name']:25s} - Confidence: {test_result['confidence_score']:.3f}, Time: {test_result['execution_time']:.2f}s")


def print_summary(all_results: List[ModelResult], quiet: bool = False) -> None:
    """Print a comprehensive summary and comparison of all model results.

    Args:
        all_results: The list of all model results
        quiet: If True, only print minimal summary
    """
    if not all_results:
        if not quiet:
            print("\nNo results to summarize.")
        return

    # Calculate combined scores for all models first
    for result in all_results:
        # Overall quality is the average of all quality metrics
        result['overall_quality'] = mean([
            result['avg_field_mapping_score'],
            result['avg_data_completeness_score'],
            result['avg_service_classification_score'],
            result['avg_hsds_structure_score']
        ])

        # Combined score weighted: 40% success rate, 30% quality, 20% speed, 10% confidence
        speed_factor = 1.0 - min(result['avg_execution_time'] / 10.0, 1.0)  # Normalize to 0-1
        result['combined_score'] = (
            result['success_rate'] * 0.4 +
            result['overall_quality'] * 0.3 +
            speed_factor * 0.2 +
            result['avg_confidence'] * 0.1
        )

        # Calculate cost (informational only, not used in scoring)
        result['cost_per_1000'] = calculate_cost_per_1000(result['model_name'])
        # Value score is now based purely on performance, not cost
        result['value_score'] = result['overall_quality'] * result['success_rate']

    if quiet:
        # In quiet mode, just print the winner
        by_combined = sorted(all_results, key=lambda x: x["combined_score"], reverse=True)
        winner = by_combined[0]
        print(f"\nBest model: {winner['model_name']} (score: {winner['combined_score']:.3f})")
        return

    print("\n" + "="*80)
    print("🏆 FINAL EVALUATION SUMMARY")
    print("="*80)

    # Explain scoring methodology
    print("\n📊 SCORING METHODOLOGY (Cost not factored into rankings):")
    print("   Quality Score = Average of:")
    print("     • Field Mapping: How well input fields are mapped to HSDS schema")
    print("     • Data Completeness: How many required HSDS fields are populated")
    print("     • Service Classification: Accuracy of service type categorization")
    print("     • HSDS Structure: Compliance with HSDS 3.1.1 format requirements")
    print("\n   Combined Score = Weighted average (performance metrics only):")
    print("     • 40% Success Rate (tests passed)")
    print("     • 30% Quality Score (HSDS compliance)")
    print("     • 20% Speed (faster is better)")
    print("     • 10% Confidence (model's self-reported confidence)")
    print("\n   Note: Cost is shown for information but does NOT affect rankings")
    print("-" * 80)

    # Scores already calculated at the beginning of this function

    # Sort by different metrics
    by_combined = sorted(all_results, key=lambda r: r["combined_score"], reverse=True)
    by_success_rate = sorted(all_results, key=lambda r: r["success_rate"], reverse=True)
    by_quality = sorted(all_results, key=lambda r: r["overall_quality"], reverse=True)
    by_confidence = sorted(all_results, key=lambda r: r["avg_confidence"], reverse=True)
    by_execution_time = sorted(all_results, key=lambda r: r["avg_execution_time"])
    by_retries = sorted(all_results, key=lambda r: r["avg_retries"])
    by_cost = sorted(all_results, key=lambda r: r["cost_per_1000"])
    by_value = sorted(all_results, key=lambda r: r["value_score"], reverse=True)

    # Overall Winner
    print("\n🥇 OVERALL BEST MODEL:")
    winner = by_combined[0]
    print(f"   {winner['model_name']}")
    print(f"   Combined Score: {winner['combined_score']:.3f} out of 1.000")
    print(f"   • Success Rate: {winner['success_rate']:.1%} ({sum(1 for r in winner['results'] if r['success'])}/{len(winner['results'])} tests passed)")
    print(f"   • Quality Score: {winner['overall_quality']:.3f} (Field:{winner['avg_field_mapping_score']:.2f} Complete:{winner['avg_data_completeness_score']:.2f} Service:{winner['avg_service_classification_score']:.2f} Structure:{winner['avg_hsds_structure_score']:.2f})")
    print(f"   • Speed: {winner['avg_execution_time']:.2f}s average per test")
    print(f"   • Confidence: {winner['avg_confidence']:.3f} average self-reported")

    # Top 3 Models
    print("\n🏅 TOP 3 MODELS BY COMBINED PERFORMANCE:")
    for i, model in enumerate(by_combined[:3], 1):
        medal = ["🥇", "🥈", "🥉"][i-1]
        print(f"\n   {medal} #{i}. {model['model_name']}")
        print(f"      Combined Score: {model['combined_score']:.3f}")
        print(f"      Success: {model['success_rate']:.1%} | Quality: {model['overall_quality']:.3f} | Time: {model['avg_execution_time']:.2f}s")

    # Category Winners
    print("\n📊 CATEGORY LEADERS:")
    print(f"\n   🎯 Best Success Rate: {by_success_rate[0]['model_name']}")
    print(f"      {by_success_rate[0]['success_rate']:.1%} success ({sum(1 for r in by_success_rate[0]['results'] if r['success'])}/{len(by_success_rate[0]['results'])} tests)")

    print(f"\n   ⭐ Best Quality Score: {by_quality[0]['model_name']}")
    print(f"      Overall Quality: {by_quality[0]['overall_quality']:.3f}")
    print(f"      Field Mapping: {by_quality[0]['avg_field_mapping_score']:.3f} | Completeness: {by_quality[0]['avg_data_completeness_score']:.3f}")

    print(f"\n   ⚡ Fastest Model: {by_execution_time[0]['model_name']}")
    print(f"      Avg Time: {by_execution_time[0]['avg_execution_time']:.2f}s ± {by_execution_time[0]['std_execution_time']:.2f}s")

    print(f"\n   🔧 Most Reliable (Fewest Retries): {by_retries[0]['model_name']}")
    print(f"      Avg Retries: {by_retries[0]['avg_retries']:.2f} ± {by_retries[0]['std_retries']:.2f}")

    print(f"\n   💯 Highest Confidence: {by_confidence[0]['model_name']}")
    print(f"      Avg Confidence: {by_confidence[0]['avg_confidence']:.3f} ± {by_confidence[0]['std_confidence']:.3f}")

    # Comparative Table
    print("\n📈 DETAILED PERFORMANCE COMPARISON:")
    print("   Success: % of tests that returned valid HSDS data")
    print("   Quality: Average of field mapping, completeness, service classification, and structure scores (0-1)")
    print("   $/1K: Cost per 1000 operations (informational only, not used in rankings)")
    print("   Perf Score: Performance score (quality × success rate)")
    print("   Combined: Weighted score (40% success, 30% quality, 20% speed, 10% confidence)")
    print("-" * 140)
    print(f"{'Model':30s} | {'Success':>8s} | {'Quality':>8s} | {'$/1K':>8s} | {'Perf':>8s} | {'Time(s)':>8s} | {'Combined':>8s} | {'Rank':>5s}")
    print("-" * 140)

    for i, model in enumerate(by_combined, 1):
        print(f"{model['model_name']:30s} | "
              f"{model['success_rate']:>7.1%} | "
              f"{model['overall_quality']:>8.3f} | "
              f"${model['cost_per_1000']:>7.2f} | "
              f"{model['value_score']:>8.2f} | "
              f"{model['avg_execution_time']:>8.2f} | "
              f"{model['combined_score']:>8.3f} | "
              f"{i:>5d}")
    print("-" * 140)

    # Performance by Test Difficulty
    print("\n🎚️  PERFORMANCE BY DIFFICULTY (All Models):")
    for difficulty in ["easy", "medium", "hard"]:
        print(f"\n   {difficulty.capitalize()} Tests:")
        for model in by_combined[:5]:  # Top 5 models
            rate = model["performance_by_difficulty"].get(difficulty, 0)
            bar_length = int(rate * 15)
            bar = "█" * bar_length + "░" * (15 - bar_length)
            print(f"      {model['model_name']:30s} [{bar}] {rate:.1%}")

    # Performance by Source Type
    print("\n📂 PERFORMANCE BY SOURCE TYPE (All Models):")
    for source_type in ["structured", "scraped", "government"]:  # Removed CSV - no test cases
        print(f"\n   {source_type.capitalize()} Data:")
        for model in by_combined[:5]:  # Top 5 models
            rate = model["performance_by_source_type"].get(source_type, 0)
            bar_length = int(rate * 15)
            bar = "█" * bar_length + "░" * (15 - bar_length)
            print(f"      {model['model_name']:30s} [{bar}] {rate:.1%}")

    # Recommendations based on performance metrics only
    print("\n🏆 RECOMMENDATIONS BY USE CASE:")
    print(f"\n   🥇 Best Overall Performance: {by_combined[0]['model_name']}")
    print(f"      → Best balance of accuracy, quality, and speed")
    print(f"      → Combined score: {by_combined[0]['combined_score']:.3f}/1.000")
    print(f"      → Success: {by_combined[0]['success_rate']:.1%}, Quality: {by_combined[0]['overall_quality']:.3f}, Speed: {by_combined[0]['avg_execution_time']:.1f}s")
    print(f"      → Cost info: ${by_combined[0]['cost_per_1000']:.2f} per 1000 operations")

    print(f"\n   ⭐ Best Data Quality: {by_quality[0]['model_name']}")
    print(f"      → Highest quality score: {by_quality[0]['overall_quality']:.3f}/1.000")
    print(f"      → Field mapping: {by_quality[0]['avg_field_mapping_score']:.3f}, Completeness: {by_quality[0]['avg_data_completeness_score']:.3f}")
    print(f"      → Cost info: ${by_quality[0]['cost_per_1000']:.2f} per 1000 operations")

    print(f"\n   🎯 Most Reliable: {by_success_rate[0]['model_name']}")
    print(f"      → Highest success rate: {by_success_rate[0]['success_rate']:.1%}")
    total_tests = len(by_success_rate[0]['results'])
    total_failures = sum(1 for r in by_success_rate[0]['results'] if not r['success'])
    print(f"      → Failures: {total_failures}/{total_tests} tests")
    print(f"      → Cost info: ${by_success_rate[0]['cost_per_1000']:.2f} per 1000 operations")

    print(f"\n   ⚡ Fastest Processing: {by_execution_time[0]['model_name']}")
    print(f"      → Speed: {by_execution_time[0]['avg_execution_time']:.2f}s per test")
    print(f"      → Success rate: {by_execution_time[0]['success_rate']:.1%}, Quality: {by_execution_time[0]['overall_quality']:.3f}")
    print(f"      → Cost info: ${by_execution_time[0]['cost_per_1000']:.2f} per 1000 operations")

    print(f"\n   💎 Best Performance Score: {by_value[0]['model_name']}")
    print(f"      → Performance score: {by_value[0]['value_score']:.3f} (quality × success rate)")
    print(f"      → Success: {by_value[0]['success_rate']:.1%}, Quality: {by_value[0]['overall_quality']:.3f}")
    print(f"      → Cost info: ${by_value[0]['cost_per_1000']:.2f} per 1000 operations")

    # Cost information section (informational only)
    print(f"\n   💰 Cost Information (not factored into rankings):")
    print(f"      → Lowest cost: {by_cost[0]['model_name']} at ${by_cost[0]['cost_per_1000']:.2f}/1000 ops")
    print(f"      → Highest cost: {by_cost[-1]['model_name']} at ${by_cost[-1]['cost_per_1000']:.2f}/1000 ops")

    # Score interpretation guide
    print("\n📖 SCORE INTERPRETATION GUIDE:")
    print("   • Combined Score > 0.7: Excellent - Production ready")
    print("   • Combined Score 0.5-0.7: Good - Suitable for most use cases")
    print("   • Combined Score 0.3-0.5: Fair - May need fallback options")
    print("   • Combined Score < 0.3: Poor - Not recommended for production")

    print("\n" + "="*80)


async def main() -> None:
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Evaluate LLM models for HSDS data processing using production pipeline"
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
        "--quiet", "-q",
        action="store_true",
        help="Quiet mode - only show essential output and errors"
    )
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
    parser.add_argument(
        "--parallel-tests",
        action="store_true",
        default=True,
        help="Run individual tests within each model evaluation in parallel (default: True)",
    )
    parser.add_argument(
        "--sequential-tests",
        action="store_true",
        help="Run tests sequentially instead of in parallel",
    )
    parser.add_argument(
        "--max-concurrent-tests",
        type=int,
        default=20,
        help="Maximum number of concurrent test requests per model (default: 20)",
    )
    args = parser.parse_args()

    # Configure logging based on quiet flag
    if args.quiet:
        # Suppress all logging except critical errors
        logging.basicConfig(level=logging.CRITICAL, format='')
        # Suppress all loggers
        logging.getLogger().setLevel(logging.CRITICAL)
        # Also suppress specific noisy loggers
        for logger_name in ["openai_provider", "app.llm", "app", "root"]:
            logging.getLogger(logger_name).setLevel(logging.CRITICAL)
    elif args.debug:
        # Show all logging in debug mode
        logging.basicConfig(level=logging.DEBUG)
    else:
        # Default: suppress debug messages but show warnings and errors
        logging.basicConfig(level=logging.WARNING, format='%(message)s')
        # Suppress noisy loggers by default
        for logger_name in ["openai_provider", "app.llm", "app", "root"]:
            logging.getLogger(logger_name).setLevel(logging.ERROR)

    # Select models to evaluate first
    if args.quick_test:
        # Use specified model or default to baseline
        if args.models:
            models_to_evaluate = args.models[:1]  # Just use first specified model
        else:
            models_to_evaluate = ["google/gemini-2.0-flash-001"]  # Default baseline
        args.iterations = 1  # Just one iteration
        if not (hasattr(args, 'quiet') and args.quiet):
            print(f"Running in quick test mode with {models_to_evaluate[0]} and one iteration")
    else:
        models_to_evaluate = args.models if args.models else MODELS

    # Check for API key (only needed for non-Claude models)
    needs_openrouter = any(not model.startswith("claude-") for model in models_to_evaluate)
    
    if needs_openrouter and not os.getenv("OPENROUTER_API_KEY"):
        print("Error: OPENROUTER_API_KEY environment variable not set (required for OpenRouter models)")
        print("Note: Claude models can be run without an API key using the Claude CLI")
        sys.exit(1)

    # Print header (unless in quiet mode)
    if not (hasattr(args, 'quiet') and args.quiet):
        print("===== LLM Model Evaluation for HSDS Data Processing (Production Pipeline) =====")
        print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Iterations per model: {args.iterations}")
        print(f"Models to evaluate: {', '.join(models_to_evaluate)}")
        if hasattr(args, 'sequential_tests') and not args.sequential_tests:
            print(f"Test execution: Sequential")
        else:
            max_concurrent = args.max_concurrent_tests if hasattr(args, 'max_concurrent_tests') else 20
            print(f"Test execution: Parallel (max {max_concurrent} concurrent per model)")

    # Evaluate models
    all_results: List[ModelResult] = []

    if args.parallel:
        if not (hasattr(args, 'quiet') and args.quiet):
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
                        args.quiet if hasattr(args, 'quiet') else False,
                        parallel_tests=not args.sequential_tests if hasattr(args, 'sequential_tests') else True,
                        max_concurrent_tests=args.max_concurrent_tests if hasattr(args, 'max_concurrent_tests') else 20,
                    )
                    return result
                except Exception as e:
                    if not (hasattr(args, 'quiet') and args.quiet):
                        print(f"Error evaluating model {model_name}: {str(e)}")
                    if args.debug and not (hasattr(args, 'quiet') and args.quiet):
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
                if not (hasattr(args, 'quiet') and args.quiet):
                    print(f"Error evaluating model {models_to_evaluate[i]}: {str(result)}")
                if args.debug and not (hasattr(args, 'quiet') and args.quiet):
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
                    model_name,
                    args.iterations,
                    args.verbose,
                    args.timeout,
                    args.debug,
                    args.quiet if hasattr(args, 'quiet') else False,
                    parallel_tests=not args.sequential_tests if hasattr(args, 'sequential_tests') else True,
                    max_concurrent_tests=args.max_concurrent_tests if hasattr(args, 'max_concurrent_tests') else 20,
                )
                all_results.append(result)
                print_model_result(result)
            except Exception as e:
                if not (hasattr(args, 'quiet') and args.quiet):
                    print(f"Error evaluating model {model_name}: {str(e)}")
                if args.debug and not (hasattr(args, 'quiet') and args.quiet):
                    import traceback

                    traceback.print_exc()

    # Print summary if we have results
    if all_results:
        print_summary(all_results, quiet=args.quiet if hasattr(args, 'quiet') else False)
    else:
        if not (hasattr(args, 'quiet') and args.quiet):
            print("\nNo results to summarize.")


if __name__ == "__main__":
    asyncio.run(main())