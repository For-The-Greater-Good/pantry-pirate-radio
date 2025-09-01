"""Scraper for Hudson County Community College Food Pantry List PDF."""

import io
import json
import logging
import re
from typing import Any

import pdfplumber
import requests

from app.scraper.utils import ScraperJob, get_scraper_headers

logger = logging.getLogger(__name__)


class Hccc_Food_PantryScraper(ScraperJob):
    """Scraper for Hudson County Community College Food Pantry List PDF."""

    def __init__(self, scraper_id: str = "hccc_food_pantry") -> None:
        """Initialize scraper with ID 'hccc_food_pantry' by default.

        Args:
            scraper_id: Optional custom scraper ID, defaults to 'hccc_food_pantry'
        """
        super().__init__(scraper_id=scraper_id)
        self.url = "https://www.hccc.edu/student-success/resources/documents/food-pantry-list-2021.pdf"

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
            List of dictionaries containing pantry information
        """
        logger.info("Extracting text from PDF")
        pantries = []

        # Open PDF from bytes
        with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
            # Process each page
            for page_num, page in enumerate(pdf.pages):
                logger.info(f"Processing page {page_num + 1} of {len(pdf.pages)}")

                # Extract tables from the page
                tables = page.extract_tables()

                if not tables:
                    logger.warning(f"No tables found on page {page_num + 1}")
                    # Try to extract text if no tables are found
                    text = page.extract_text()
                    if text:
                        logger.info(f"Extracted text from page {page_num + 1}")
                        # Parse text to find pantry information
                        pantries.extend(self.parse_text_for_pantries(text))
                    continue

                # Process each table
                for table_num, table in enumerate(tables):
                    logger.info(
                        f"Processing table {table_num + 1} on page {page_num + 1}"
                    )

                    # Get header row if this is the first table on the first page
                    headers = []
                    start_row = 0

                    if table and len(table) > 0:
                        # Try to identify header row
                        potential_headers = [
                            cell.lower() if cell else "" for cell in table[0]
                        ]
                        if any(
                            h
                            for h in potential_headers
                            if "name" in h or "pantry" in h or "organization" in h
                        ):
                            headers = [cell or "" for cell in table[0]]
                            start_row = 1

                    # If we couldn't identify headers, make a best guess
                    if not headers and table and len(table) > 0:
                        # Make a best guess for headers
                        headers = ["Organization", "Address", "Phone", "Hours", "Notes"]

                    # Process each row in the table
                    for row_idx in range(start_row, len(table)):
                        row = table[row_idx]
                        if not row or all(
                            cell is None
                            or (isinstance(cell, str) and cell.strip() == "")
                            for cell in row
                        ):
                            continue  # Skip empty rows

                        # Extract pantry information
                        pantry = self.parse_pantry_row(row, headers)
                        if pantry:
                            pantries.append(pantry)

        # If we couldn't extract any pantries, try a more aggressive approach
        if not pantries:
            logger.warning(
                "No pantries extracted using table parsing, trying text extraction"
            )
            with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
                full_text = ""
                for page in pdf.pages:
                    full_text += page.extract_text() + "\n"

                pantries = self.parse_text_for_pantries(full_text)

        logger.info(f"Extracted {len(pantries)} pantries from PDF")
        return pantries

    def parse_pantry_row(
        self, row: list[str | None], headers: list[str]
    ) -> dict[str, str] | None:
        """Parse a row from the PDF table to extract pantry information.

        Args:
            row: List of cell values from a table row
            headers: List of column headers

        Returns:
            Dictionary containing pantry information, or None if row is invalid
        """
        # Skip rows that don't have enough cells
        if not row or len(row) < 2:
            return None

        # Clean cell values
        cleaned_row = [cell.strip() if isinstance(cell, str) else "" for cell in row]

        # Create a dictionary with headers as keys
        pantry = {}
        for i, header in enumerate(headers):
            if i < len(cleaned_row):
                # Clean up header name
                header_key = header.lower().strip() if header else f"column_{i}"
                header_key = re.sub(r"[^a-z0-9_]", "_", header_key)
                pantry[header_key] = cleaned_row[i]

        # Extract essential information
        # Try to identify key columns based on content
        name = ""
        address = ""
        phone = ""
        hours = ""
        notes = ""

        # Check if we have expected column names
        if "organization" in pantry or "name" in pantry or "pantry" in pantry:
            # Use the first available name field
            for key in ["organization", "name", "pantry"]:
                if pantry.get(key):
                    name = pantry[key]
                    break

        if "address" in pantry:
            address = pantry["address"]

        if "phone" in pantry or "contact" in pantry or "telephone" in pantry:
            # Use the first available phone field
            for key in ["phone", "contact", "telephone"]:
                if pantry.get(key):
                    phone = pantry[key]
                    break

        if "hours" in pantry or "time" in pantry or "schedule" in pantry:
            # Use the first available hours field
            for key in ["hours", "time", "schedule"]:
                if pantry.get(key):
                    hours = pantry[key]
                    break

        if "notes" in pantry or "additional" in pantry or "information" in pantry:
            # Use the first available notes field
            for key in ["notes", "additional", "information"]:
                if pantry.get(key):
                    notes = pantry[key]
                    break

        # If we couldn't identify columns by name, make a best guess based on position
        if not name and len(cleaned_row) > 0:
            name = cleaned_row[0]

        if not address and len(cleaned_row) > 1:
            address = cleaned_row[1]

        if not phone and len(cleaned_row) > 2:
            # Check if the cell looks like a phone number
            cell = cleaned_row[2]
            if re.search(r"\d{3}[-.\s]?\d{3}[-.\s]?\d{4}", cell):
                phone = cell

        if not hours and len(cleaned_row) > 3:
            hours = cleaned_row[3]

        if not notes and len(cleaned_row) > 4:
            notes = cleaned_row[4]

        # If we don't have at least a name and address, skip this row
        if not name or not address:
            return None

        # Combine into a standard format
        return {
            "name": name,
            "address": address,
            "phone": phone,
            "hours": hours,
            "notes": notes,
            "county": "Hudson",
            "state": "NJ",
            "full_text": " ".join(cleaned_row),
        }

    def parse_text_for_pantries(self, text: str) -> list[dict[str, str]]:
        """Parse text to extract pantry information when tables aren't available.

        Args:
            text: Text extracted from PDF

        Returns:
            List of dictionaries containing pantry information
        """
        pantries = []

        # Split text into sections that might represent pantries
        # Look for patterns like organization names followed by addresses

        # Pattern 1: Sections separated by blank lines
        sections = re.split(r"\n\s*\n", text)

        for section in sections:
            lines = section.strip().split("\n")
            if len(lines) < 2:
                continue  # Skip sections with insufficient data

            name = lines[0].strip()

            # Check if this looks like a pantry name (not a header or footer)
            if re.match(r"page|^\d+$|^food pantry list$|^hudson county", name.lower()):
                continue

            # Try to extract address, phone, and hours
            address = ""
            phone = ""
            hours = ""
            notes = ""

            # Join remaining lines
            remaining_text = "\n".join(lines[1:])

            # Look for address pattern (street, city, state zip)
            address_match = re.search(
                r"\d+\s+[^,\n]+(?:,\s*[^,\n]+){1,2},?\s*NJ\s*\d{5}", remaining_text
            )
            if address_match:
                address = address_match.group(0)
            else:
                # Try simpler address pattern (just street)
                address_match = re.search(
                    r"\d+\s+[A-Za-z\s]+(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Boulevard|Blvd)",
                    remaining_text,
                )
                if address_match:
                    address = address_match.group(0)

            # Look for phone pattern
            phone_match = re.search(
                r"(?<!\d)(\d{3}[-.\s]?\d{3}[-.\s]?\d{4})(?!\d)", remaining_text
            )
            if phone_match:
                phone = phone_match.group(1)

            # Look for hours pattern
            hours_match = re.search(
                r"(?:hours|open|available)[:;]?\s*([^.]*)",
                remaining_text,
                re.IGNORECASE,
            )
            if hours_match:
                hours = hours_match.group(1).strip()

            # If we have a name and either an address or phone, consider it a pantry
            if name and (address or phone):
                pantry = {
                    "name": name,
                    "address": address,
                    "phone": phone,
                    "hours": hours,
                    "notes": notes,
                    "county": "Hudson",
                    "state": "NJ",
                    "full_text": section.strip(),
                }
                pantries.append(pantry)

        return pantries

    def transform_to_hsds(self, pantry: dict[str, str]) -> dict[str, Any]:
        """Transform pantry data to HSDS format.

        Args:
            pantry: Pantry data from PDF

        Returns:
            Pantry data in HSDS format
        """
        # Extract basic information
        hsds_data: dict[str, Any] = {
            "name": pantry.get("name", ""),
            "alternate_name": "",
            "description": f"Food pantry in Hudson County, NJ. {pantry.get('notes', '')}".strip(),
            "email": "",
            "url": "",
            "status": "active",
            "address": {
                "address_1": pantry.get("address", ""),
                "address_2": "",
                "city": "Jersey City",  # Default to Jersey City if not specified
                "state_province": "NJ",
                "postal_code": "",
                "country": "US",
            },
            "phones": [],
        }

        # Try to extract city and zip from address
        address = pantry.get("address", "")
        city_match = re.search(r"([A-Za-z\s]+),\s*NJ", address)
        if city_match:
            hsds_data["address"]["city"] = city_match.group(1).strip()

        zip_match = re.search(r"(\d{5}(?:-\d{4})?)", address)
        if zip_match:
            hsds_data["address"]["postal_code"] = zip_match.group(1)

        # Add phone if available
        if pantry.get("phone"):
            hsds_data["phones"] = [{"number": pantry["phone"], "type": "voice"}]

        # Add coordinates if available
        if "latitude" in pantry and "longitude" in pantry:
            hsds_data["location"] = {
                "latitude": pantry["latitude"],
                "longitude": pantry["longitude"],
            }

        # Add hours if available
        if pantry.get("hours"):
            # Parse hours text to extract schedule
            hours_text = pantry["hours"]

            # Try to identify days and times
            schedule = []

            # Look for day patterns
            days = [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            ]
            day_abbrevs = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

            for i, day in enumerate(days):
                # Check for full day name or abbreviation
                pattern = (
                    r"(%s|%s)[:\s]*([^,;]*\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm)[^,;]*\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm))"
                    % (day, day_abbrevs[i])
                )
                matches = re.findall(pattern, hours_text, re.IGNORECASE)

                for match in matches:
                    time_str = match[1].strip()
                    # Try to extract opening and closing times
                    time_match = re.search(
                        r"(\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm)).*?(\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm))",
                        time_str,
                    )
                    if time_match:
                        opens_at = time_match.group(1).strip()
                        closes_at = time_match.group(2).strip()
                        schedule.append(
                            {
                                "weekday": day,
                                "opens_at": opens_at,
                                "closes_at": closes_at,
                            }
                        )

            # If we couldn't parse specific days/times, add the full hours string
            if not schedule and hours_text:
                hsds_data["hours_notes"] = hours_text

        # Add service attributes
        hsds_data["service_attributes"] = [
            {"attribute_key": "PROGRAM_TYPE", "attribute_value": "Food Pantry"}
        ]

        hsds_data["service_attributes"].append(
            {"attribute_key": "COUNTY", "attribute_value": "Hudson"}
        )

        return hsds_data

    async def scrape(self) -> str:
        """Scrape data from HCCC Food Pantry PDF.

        Returns:
            Summary of scraping operation as JSON string
        """
        # 1. Download PDF
        pdf_content = await self.download_pdf()

        # 2. Extract pantry information from PDF
        pantries = self.extract_text_from_pdf(pdf_content)

        # 3. Process pantries and submit to queue
        job_count = 0
        failed_pantries = []

        for pantry in pantries:
            # Note: Latitude and longitude will be handled by the validator service

            # Add metadata
            pantry["source"] = "hccc_food_pantry"
            pantry["pdf_url"] = self.url

            # Submit to queue
            job_id = self.submit_to_queue(json.dumps(pantry))
            job_count += 1
            logger.debug(
                f"Queued job {job_id} for pantry: {pantry.get('name', 'Unknown')}"
            )

        # Create summary
        summary = {
            "scraper_id": self.scraper_id,
            "total_pantries_found": len(pantries),
            "total_jobs_created": job_count,
            "failed_pantries": len(failed_pantries),
            "source": self.url,
        }

        # Print summary to CLI
        print(f"\n{'='*60}")
        print("SCRAPER SUMMARY: HCCC Food Pantry (Hudson County, NJ)")
        print(f"{'='*60}")
        print(f"PDF URL: {self.url}")
        print(f"Total pantries found: {len(pantries)}")
        print(f"Jobs created: {job_count}")
        print(f"Failed processing: {len(failed_pantries)}")
        print("Status: Complete")
        print(f"{'='*60}\n")

        # Return summary for archiving
        return json.dumps(summary)
