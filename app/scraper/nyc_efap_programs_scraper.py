"""Scraper for NYC Emergency Food Assistance Program (EFAP) locations."""

import io
import json
import logging
from typing import Any

import pdfplumber
import requests

from app.scraper.utils import GeocoderUtils, ScraperJob, get_scraper_headers

logger = logging.getLogger(__name__)


class Nyc_Efap_ProgramsScraper(ScraperJob):
    """Scraper for NYC Emergency Food Assistance Program (EFAP) locations."""

    def __init__(self, scraper_id: str = "nyc_efap_programs") -> None:
        """Initialize scraper with ID 'nyc_efap_programs' by default.

        Args:
            scraper_id: Optional custom scraper ID, defaults to 'nyc_efap_programs'
        """
        super().__init__(scraper_id=scraper_id)
        self.url = (
            "https://www.nyc.gov/assets/hra/downloads/pdf/services/efap/CFC_ACTIVE.pdf"
        )

        # Initialize geocoder with custom default coordinates for NYC
        self.geocoder = GeocoderUtils(
            default_coordinates={
                "NYC": (40.7128, -74.0060),  # New York City center
                "NY": (
                    40.7128,
                    -74.0060,
                ),  # New York state (using NYC coords as default)
            }
        )

    async def download_pdf(self) -> bytes:
        """Download PDF file from the source URL.

        Returns:
            bytes: Raw PDF content

        Raises:
            requests.RequestException: If download fails
        """
        logger.info(f"Downloading PDF from {self.url}")
        response = requests.get(self.url, headers=get_scraper_headers(), timeout=30)
        response.raise_for_status()
        return response.content

    def extract_text_from_pdf(self, pdf_content: bytes) -> list[dict[str, str]]:
        """Extract text from PDF content.

        Args:
            pdf_content: Raw PDF content

        Returns:
            List of dictionaries containing program information
        """
        logger.info("Extracting text from PDF")
        programs = []

        # Open PDF from bytes
        with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
            # Process each page
            for page_num, page in enumerate(pdf.pages):
                logger.info(f"Processing page {page_num + 1} of {len(pdf.pages)}")

                # Extract tables from the page
                tables = page.extract_tables()

                if not tables:
                    logger.warning(f"No tables found on page {page_num + 1}")
                    continue

                # Process each table
                for table_num, table in enumerate(tables):
                    logger.info(
                        f"Processing table {table_num + 1} on page {page_num + 1}"
                    )

                    # Get header row if this is the first table on the first page
                    header_row = []
                    if page_num == 0 and table_num == 0 and table:
                        header_row = table[0]
                        # Skip header row for processing
                        rows = table[1:]
                    else:
                        # No header, process all rows
                        rows = table

                    # Process each row in the table
                    for row in rows:
                        if not row or all(
                            cell is None or cell.strip() == "" for cell in row
                        ):
                            continue  # Skip empty rows

                        # Extract program information
                        program = self.parse_program_row(row)
                        if program:
                            programs.append(program)

        logger.info(f"Extracted {len(programs)} programs from PDF")
        return programs

    def parse_program_row(self, row: list[str | None]) -> dict[str, str] | None:
        """Parse a row from the PDF table to extract program information.

        Args:
            row: List of cell values from a table row

        Returns:
            Dictionary containing program information, or None if row is invalid
        """
        # Skip rows that don't have enough cells
        if not row or len(row) < 4:
            return None

        # Clean cell values
        cleaned_row = [cell.strip() if isinstance(cell, str) else "" for cell in row]

        # Extract program information based on the table structure
        # The exact structure will depend on the PDF format
        # This is a placeholder implementation that will need to be adjusted
        # based on the actual PDF structure
        program = {}

        # Assuming the table has columns for name, address, borough, zip, phone, etc.
        # Adjust indices based on the actual PDF structure
        if len(cleaned_row) >= 1 and cleaned_row[0]:
            program["name"] = cleaned_row[0]

        if len(cleaned_row) >= 2 and cleaned_row[1]:
            program["address"] = cleaned_row[1]

        if len(cleaned_row) >= 3 and cleaned_row[2]:
            program["borough"] = cleaned_row[2]

        if len(cleaned_row) >= 4 and cleaned_row[3]:
            program["zip_code"] = cleaned_row[3]

        if len(cleaned_row) >= 5 and cleaned_row[4]:
            program["phone"] = cleaned_row[4]

        if len(cleaned_row) >= 6 and cleaned_row[5]:
            program["hours"] = cleaned_row[5]

        # Combine address components
        address_parts = []
        if program.get("address"):
            address_parts.append(program["address"])
        if program.get("borough"):
            address_parts.append(program["borough"])
        if program.get("zip_code"):
            address_parts.append(program["zip_code"])

        if address_parts:
            program["full_address"] = ", ".join(address_parts) + ", NY"

        # Check if we have the minimum required information
        if (
            "name" not in program
            or not program["name"]
            or "full_address" not in program
            or not program["full_address"]
        ):
            return None

        return program

    def transform_to_hsds(self, program: dict[str, Any]) -> dict[str, Any]:
        """Transform program data to HSDS format.

        Args:
            program: Program data from PDF

        Returns:
            Program data in HSDS format
        """
        # Extract basic information
        hsds_data = {
            "name": program.get("name", ""),
            "alternate_name": "",
            "description": f"NYC Emergency Food Assistance Program (EFAP) location in {program.get('borough', 'New York City')}",
            "email": "",
            "url": "",
            "status": "active",
            "address": {
                "address_1": program.get("address", ""),
                "address_2": "",
                "city": "New York",
                "state_province": "NY",
                "postal_code": program.get("zip_code", ""),
                "country": "US",
            },
            "phones": [],
        }

        # Add phone if available
        if program.get("phone"):
            hsds_data["phones"] = [{"number": program["phone"], "type": "voice"}]

        # Add coordinates if available
        if "latitude" in program and "longitude" in program:
            hsds_data["location"] = {
                "latitude": program["latitude"],
                "longitude": program["longitude"],
            }

        # Add hours if available
        if program.get("hours"):
            # Parse hours text to extract schedule
            # This is a placeholder and would need to be adjusted based on the actual format
            hsds_data["regular_schedule"] = [
                {"weekday": "Monday", "opens_at": "09:00", "closes_at": "17:00"}
            ]

        # Add service attributes
        hsds_data["service_attributes"] = [
            {
                "attribute_key": "PROGRAM_TYPE",
                "attribute_value": "Emergency Food Assistance Program (EFAP)",
            }
        ]

        if program.get("borough"):
            hsds_data["service_attributes"].append(
                {"attribute_key": "BOROUGH", "attribute_value": program["borough"]}
            )

        return hsds_data

    async def scrape(self) -> str:
        """Scrape data from NYC EFAP Programs PDF.

        Returns:
            Summary of scraping operation as JSON string
        """
        # 1. Download PDF
        pdf_content = await self.download_pdf()

        # 2. Extract program information from PDF
        programs = self.extract_text_from_pdf(pdf_content)

        # 3. Process programs and submit to queue
        job_count = 0
        failed_programs = []
        geocoder_stats = {"success": 0, "default": 0}

        for program in programs:
            try:
                # Try to geocode address
                try:
                    # Use the geocoder from utils.py
                    latitude, longitude = self.geocoder.geocode_address(
                        program["full_address"], state="NY"
                    )

                    # Add coordinates to program data
                    program["latitude"] = latitude
                    program["longitude"] = longitude
                    geocoder_stats["success"] += 1

                except Exception as geocode_error:
                    # Log the geocoding error
                    logger.warning(
                        f"Geocoding failed for {program['name']}: {geocode_error}"
                    )

                    # Add to failed programs list for later review
                    failed_programs.append(
                        {
                            "name": program["name"],
                            "address": program.get("full_address", ""),
                            "error": str(geocode_error),
                        }
                    )

                    # Use default coordinates for NYC with a small offset
                    latitude, longitude = self.geocoder.get_default_coordinates(
                        location="NYC", with_offset=True
                    )
                    program["latitude"] = latitude
                    program["longitude"] = longitude
                    geocoder_stats["default"] += 1

                    logger.info(
                        f"Using default coordinates with offset for {program['name']}"
                    )

                # Transform to HSDS format
                hsds_data = self.transform_to_hsds(program)

                # Submit to queue
                job_id = self.submit_to_queue(json.dumps(hsds_data))
                job_count += 1
                logger.info(f"Queued job {job_id} for program: {program['name']}")

            except Exception as e:
                logger.error(
                    f"Error processing program {program.get('name', 'Unknown')}: {e}"
                )
                failed_programs.append(
                    {
                        "name": program.get("name", "Unknown"),
                        "address": program.get("full_address", ""),
                        "error": str(e),
                    }
                )
                continue

        # Save failed programs to file for later review
        if failed_programs:
            import datetime
            from pathlib import Path

            # Create outputs directory if it doesn't exist
            output_dir = Path(__file__).parent.parent.parent / "outputs"
            output_dir.mkdir(exist_ok=True)

            # Generate filename with timestamp
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            failed_file = output_dir / f"nyc_efap_programs_failed_{timestamp}.json"

            # Write failed programs to file
            with open(failed_file, "w") as f:
                json.dump(failed_programs, f, indent=2)

            logger.info(
                f"Saved {len(failed_programs)} failed programs to {failed_file}"
            )

        # Create summary
        summary = {
            "total_programs_found": len(programs),
            "total_jobs_created": job_count,
            "failed_processing": len(failed_programs),
            "geocoder_stats": geocoder_stats,
            "source": self.url,
        }

        # Print summary to CLI
        print("\nScraper Summary:")
        print(f"Source: {self.url}")
        print(f"Total programs found: {len(programs)}")
        print(f"Successfully processed: {job_count}")
        print("Geocoder usage:")
        print(f"  - Successful geocoding: {geocoder_stats['success']}")
        print(f"  - Default coordinates: {geocoder_stats['default']}")
        print(f"Failed processing: {len(failed_programs)}")
        if failed_programs:
            print(f"Failed programs saved to: {failed_file}")
        print("Status: Complete\n")

        # Return summary as JSON string
        return json.dumps(summary)
