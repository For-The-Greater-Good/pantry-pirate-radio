"""Utilities for scraper job submission."""

import os
import random
import re
from pathlib import Path
from typing import Any, NotRequired, TypedDict

from geopy.exc import GeocoderServiceError, GeocoderTimedOut, GeocoderUnavailable
from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import ArcGIS, Nominatim
from prometheus_client import Counter
from redis import Redis

# Job import removed - not used
from app.core.grid import GridGenerator
from app.llm.hsds_aligner.schema_converter import SchemaConverter
from app.llm.hsds_aligner.validation import ValidationConfig
from app.llm.queue.queues import llm_queue
from app.models.geographic import BoundingBox, GridPoint


def get_scraper_headers() -> dict[str, str]:
    """Get standard headers for scraper requests.

    Returns:
        Dict with headers including a browser-like User-Agent
    """
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }


# Prometheus metrics
SCRAPER_JOBS = Counter(
    "scraper_jobs_total", "Total number of jobs submitted", ["scraper_id"]
)


class JobMetadata(TypedDict):
    """Metadata for scraper jobs."""

    scraper_id: str
    source_type: NotRequired[str]
    priority: NotRequired[str]


class ScraperUtils:
    """Utilities for scrapers to queue jobs and generate grid points."""

    @staticmethod
    def get_us_grid_points() -> list[GridPoint]:
        """Get grid points covering continental US.

        Returns:
            List[GridPoint]: List of grid points with overlapping coverage
        """
        generator = GridGenerator()
        points: list[GridPoint] = generator.generate_grid()
        return points

    @staticmethod
    def get_grid_points(bounds: BoundingBox | None = None) -> list[GridPoint]:
        """Get grid points for specified area or US if none provided.

        Args:
            bounds: Optional bounding box, defaults to continental US

        Returns:
            List[GridPoint]: List of grid points with overlapping coverage
        """
        generator = GridGenerator(bounds)
        points: list[GridPoint] = generator.generate_grid()
        return points

    @staticmethod
    def get_grid_points_from_geojson(geojson_path: str | Path) -> list[GridPoint]:
        """Generate grid points from GeoJSON file.

        Args:
            geojson_path: Path to GeoJSON file

        Returns:
            List[GridPoint]: List of grid points with overlapping coverage

        Raises:
            ValueError: If GeoJSON file is invalid or missing
        """
        path = Path(geojson_path) if isinstance(geojson_path, str) else geojson_path
        bounds = BoundingBox.from_geojson(path)
        return ScraperUtils.get_grid_points(bounds)

    @staticmethod
    def get_state_grid_points(state_code: str) -> list[GridPoint]:
        """Get grid points for a US state.

        Args:
            state_code: Two-letter state code (case insensitive)

        Returns:
            List[GridPoint]: List of grid points covering the state

        Raises:
            ValueError: If state code is invalid
        """
        # Normalize state code
        state_code = state_code.lower()

        # Construct path to state GeoJSON
        base_path = Path(__file__).parent.parent.parent
        # Find state file matching pattern: {state_code}_{state_name}_zip_codes_geo.min.json
        geojson_path = (
            base_path / "docs/GeoJson/States" / f"{state_code}_*_zip_codes_geo.min.json"
        )

        # Get list of matching files (should be exactly one)
        matches = list(geojson_path.parent.glob(geojson_path.name))
        if not matches:
            raise ValueError(f"No GeoJSON file found for state code: {state_code}")

        # Use first match (should be only one)
        geojson_path = matches[0]

        if not geojson_path.exists():
            raise ValueError(f"No GeoJSON file found for state code: {state_code}")

        return ScraperUtils.get_grid_points_from_geojson(geojson_path)

    def __init__(
        self,
        scraper_id: str,
    ) -> None:
        """Initialize scraper utilities.

        Args:
            scraper_id: Identifier for this scraper

        Raises:
            KeyError: If required environment variables are missing
            FileNotFoundError: If required files are missing
            ConnectionError: If Redis connection fails
        """
        # Check for required environment variables
        if not os.getenv("REDIS_URL"):
            raise KeyError("REDIS_URL environment variable is required")

        # Test Redis connection
        try:
            Redis.from_url(os.environ["REDIS_URL"]).ping()
        except Exception as e:
            raise ConnectionError(f"Failed to connect to Redis: {e}")

        self.scraper_id = scraper_id

        # Initialize paths
        base_path = Path(__file__).parent.parent.parent
        schema_path = base_path / "docs/HSDS/schema/simple/schema.csv"
        prompt_path = (
            base_path / "app/llm/hsds_aligner/prompts/food_pantry_mapper.prompt"
        )
        if not prompt_path.exists():
            # Try alternate location
            prompt_path = base_path / "docs/HSDS/prompts/food_pantry_mapper.prompt"
            if not prompt_path.exists():
                raise FileNotFoundError(
                    "Could not find food_pantry_mapper.prompt in expected locations"
                )

        # Load schema and prompt
        self.schema_converter = SchemaConverter(schema_path)
        self.system_prompt = prompt_path.read_text()

        # Configure validation with high confidence thresholds
        self.validation_config = ValidationConfig(
            min_confidence=0.90,  # Set 90% confidence threshold
            retry_threshold=0.75,  # Higher retry threshold for better quality
        )

        # Convert schema for structured output
        self.hsds_schema = self.schema_converter.convert_to_llm_schema("organization")

    def queue_for_processing(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Queue raw content for processing.

        Args:
            content: Raw content to process
            metadata: Optional additional metadata

        Returns:
            Job ID for tracking
        """
        # Combine scraper ID with any additional metadata
        job_metadata: JobMetadata = {
            "scraper_id": self.scraper_id,
            **(metadata or {}),  # type: ignore
        }

        # Prepare input with system prompt
        full_prompt = f"{self.system_prompt}\n\nInput Data:\n{content}"

        # Create LLMJob
        from datetime import datetime

        from app.llm.queue.job import LLMJob

        job = LLMJob(
            id=str(datetime.now().timestamp()),
            prompt=full_prompt,
            format={
                "type": "json_schema",
                "schema": self.hsds_schema["json_schema"],
                "strict": True,
                "validation": {
                    "min_confidence": self.validation_config.min_confidence,
                    "retry_threshold": self.validation_config.retry_threshold,
                },
            },
            metadata=job_metadata,
            provider_config={},
            created_at=datetime.now(),
        )

        # Submit job using RQ
        from typing import cast
        from app.core.events import get_setting
        from app.llm.providers.base import BaseLLMProvider
        from app.llm.providers.openai import OpenAIConfig, OpenAIProvider
        from app.llm.providers.claude import ClaudeConfig, ClaudeProvider

        # Create provider based on configuration
        llm_provider = get_setting("llm_provider", str, required=True)
        llm_model = get_setting("llm_model_name", str, required=True)
        llm_temperature = get_setting("llm_temperature", float, required=True)
        llm_max_tokens = get_setting("llm_max_tokens", int, None, required=False)

        if llm_provider == "openai":
            openai_config = OpenAIConfig(
                model_name=llm_model,
                temperature=llm_temperature,
                max_tokens=llm_max_tokens,
            )
            provider = cast(BaseLLMProvider[Any, Any], OpenAIProvider(openai_config))
        elif llm_provider == "claude":
            claude_config = ClaudeConfig(
                model_name=llm_model,
                temperature=llm_temperature,
                max_tokens=llm_max_tokens,
            )
            provider = cast(BaseLLMProvider[Any, Any], ClaudeProvider(claude_config))
        else:
            raise ValueError(
                f"Unsupported LLM provider: {llm_provider}. "
                f"Supported providers: openai, claude"
            )

        result = llm_queue.enqueue_call(
            func="app.llm.queue.processor.process_llm_job",
            args=(job, provider),
            job_id=job.id,
            meta={"job": job.model_dump()},
            result_ttl=86400,  # Keep results for 24 hours
            failure_ttl=86400,  # Keep failed jobs for 24 hours
        )
        if result is None:
            raise RuntimeError("Failed to enqueue job")

        # Increment counter
        SCRAPER_JOBS.labels(scraper_id=self.scraper_id).inc()
        return str(result.id)


class GeocoderUtils:
    """Utilities for geocoding addresses."""

    def __init__(
        self,
        timeout: int = 10,
        min_delay_seconds: int = 2,
        max_retries: int = 3,
        default_coordinates: dict[str, tuple[float, float]] | None = None,
    ):
        """Initialize geocoder utilities.

        Args:
            timeout: Timeout for geocoding requests in seconds
            min_delay_seconds: Minimum delay between geocoding requests
            max_retries: Maximum number of retries for geocoding requests
            default_coordinates: Optional dictionary of default coordinates by location name
        """
        # Initialize multiple geocoders with rate limiting
        self.nominatim = Nominatim(user_agent="pantry-pirate-radio", timeout=timeout)
        self.nominatim_geocode = RateLimiter(
            self.nominatim.geocode,
            min_delay_seconds=min_delay_seconds,
            max_retries=max_retries,
        )

        self.arcgis = ArcGIS(timeout=timeout)
        self.arcgis_geocode = RateLimiter(
            self.arcgis.geocode,
            min_delay_seconds=min_delay_seconds,
            max_retries=max_retries,
        )

        # Default coordinates - can be overridden by the caller
        self.default_coordinates = default_coordinates or {
            # Geographic center of the United States
            "US": (39.8283, -98.5795),
        }

    def geocode_address(
        self, address: str, county: str | None = None, state: str | None = None
    ) -> tuple[float, float]:
        """Geocode address to get latitude and longitude using multiple geocoders.

        Args:
            address: Address to geocode
            county: Optional county name
            state: Optional state code

        Returns:
            Tuple of (latitude, longitude)

        Raises:
            ValueError: If all geocoding attempts fail
        """
        # Prepare address variations to try
        address_variations = []

        # Full address with county and state
        if (
            county
            and state
            and county.lower() not in address.lower()
            and state.lower() not in address.lower()
        ):
            address_variations.append(f"{address}, {county} County, {state}")

        # Address with just state
        if state and state.lower() not in address.lower():
            address_variations.append(f"{address}, {state}")

        # Original address as fallback
        address_variations.append(address)

        # Add specific variations for addresses with landmarks or special formats
        if "parking lot" in address.lower() or "across from" in address.lower():
            # Extract street address if it contains a street number
            street_match = re.search(
                r"\d+\s+[A-Za-z\s]+(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Boulevard|Blvd)",
                address,
            )
            if street_match:
                street_address = street_match.group(0)
                if county and state:
                    address_variations.append(
                        f"{street_address}, {county} County, {state}"
                    )
                if state:
                    address_variations.append(f"{street_address}, {state}")

        # Try each geocoder with each address variation
        errors = []

        # 1. Try Nominatim first
        for addr in address_variations:
            try:
                location = self.nominatim_geocode(addr)
                if location:
                    return location.latitude, location.longitude
            except (GeocoderTimedOut, GeocoderUnavailable, GeocoderServiceError) as e:
                errors.append(f"Nominatim error for '{addr}': {e!s}")
                continue

        # 2. Try ArcGIS next
        for addr in address_variations:
            try:
                location = self.arcgis_geocode(addr)
                if location:
                    return location.latitude, location.longitude
            except (GeocoderTimedOut, GeocoderUnavailable, GeocoderServiceError) as e:
                errors.append(f"ArcGIS error for '{addr}': {e!s}")
                continue

        # If we get here, all geocoding attempts failed
        error_msg = "; ".join(errors) if errors else "Unknown geocoding error"
        raise ValueError(f"Could not geocode address: {address}. Errors: {error_msg}")

    def get_default_coordinates(
        self, location: str = "US", with_offset: bool = True, offset_range: float = 0.01
    ) -> tuple[float, float]:
        """Get default coordinates for a location with optional random offset.

        Args:
            location: Location name (US, state code, or county name)
            with_offset: Whether to add a random offset
            offset_range: Range for random offset

        Returns:
            Tuple of (latitude, longitude)
        """
        # Get base coordinates
        if location in self.default_coordinates:
            lat, lon = self.default_coordinates[location]
        else:
            # Default to US if location not found
            lat, lon = self.default_coordinates["US"]

        # Add random offset if requested
        if with_offset:
            lat_offset = random.uniform(-offset_range, offset_range)  # nosec B311
            lon_offset = random.uniform(-offset_range, offset_range)  # nosec B311
            lat += lat_offset
            lon += lon_offset

        return lat, lon


class ScraperJob:
    """Base class for implementing scrapers."""

    def __init__(
        self,
        scraper_id: str,
    ) -> None:
        """Initialize scraper job.

        Args:
            scraper_id: Unique identifier for this scraper
        """
        self.scraper_id = scraper_id
        self.utils = ScraperUtils(scraper_id=scraper_id)
        self.geocoder = GeocoderUtils()

    async def scrape(self) -> str:
        """Scrape data from source.

        This method must be implemented by subclasses to define
        scraper-specific logic for data collection.

        Returns:
            Raw scraped content as string

        Raises:
            NotImplementedError: If subclass doesn't implement
        """
        raise NotImplementedError("Subclasses must implement scrape()")

    def submit_to_queue(self, content: str) -> str:
        """Submit scraped content to processing queue.

        Args:
            content: Raw scraped content

        Returns:
            Job ID for tracking
        """
        return self.utils.queue_for_processing(
            content, metadata={"source": self.scraper_id}
        )

    async def run(self) -> None:
        """Execute scraper lifecycle.

        This orchestrates the scraping process:
        1. Scrape data (implemented by subclass)
        2. Submit to queue

        Raises:
            Exception: If any step fails
        """
        try:
            # 1. Scrape data
            content = await self.scrape()

            # 2. Submit to queue
            self.submit_to_queue(content)

        except Exception:
            raise
