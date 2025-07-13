"""Scraper for HFC Partner Data CSV file."""

import csv
import json
import logging
from pathlib import Path
from typing import Any

from app.scraper.utils import GeocoderUtils, ScraperJob

logger = logging.getLogger(__name__)


class Hfc_Partner_DataScraper(ScraperJob):
    """Scraper for HFC Partner Data CSV file.

    This scraper processes the CSV file containing HFC Partner Data,
    transforms it to HSDS format, and submits each entry to the processing queue.
    """

    def __init__(self, scraper_id: str = "hfc_partner_data") -> None:
        """Initialize scraper with ID 'hfc_partner_data' by default.

        Args:
            scraper_id: Optional custom scraper ID, defaults to 'hfc_partner_data'
        """
        super().__init__(scraper_id=scraper_id)
        self.csv_path = (
            Path(__file__).parent.parent.parent / "docs/HFCData/HFC_Partner_Data.csv"
        )

        # Initialize geocoder with default coordinates (used only if lat/long are missing)
        self.geocoder = GeocoderUtils(
            default_coordinates={
                "US": (39.8283, -98.5795),  # Geographic center of the United States
            }
        )

    def parse_hours(
        self, days: str, hours: str, exact_hours: str, agency_hours: str
    ) -> list[dict[str, str]]:
        """Parse hours information into HSDS regular_schedule format.

        Args:
            days: Days of food pantry operation
            hours: Hours of operation
            exact_hours: Exact hours of operation
            agency_hours: Agency hours of operation

        Returns:
            List of dictionaries in HSDS regular_schedule format
        """
        schedule = []

        # Use exact_hours if available, otherwise try to parse days and hours
        if exact_hours:
            # Try to parse exact hours which might be in format like:
            # "Monday: 9am-12pm, Tuesday: 1pm-4pm"
            parts = [p.strip() for p in exact_hours.split(",")]
            for part in parts:
                if ":" in part:
                    day_part, time_part = part.split(":", 1)
                    day = day_part.strip()
                    time_range = time_part.strip()

                    # Skip if day or time_range is empty
                    if not day or not time_range:
                        continue

                    # Handle day names
                    day_mapping = {
                        "mon": "Monday",
                        "tue": "Tuesday",
                        "wed": "Wednesday",
                        "thu": "Thursday",
                        "fri": "Friday",
                        "sat": "Saturday",
                        "sun": "Sunday",
                    }

                    day_lower = day.lower()
                    for abbr, full_day in day_mapping.items():
                        if abbr in day_lower:
                            day = full_day
                            break

                    # Parse time range
                    if "-" in time_range:
                        opens, closes = time_range.split("-", 1)
                        schedule.append(
                            {
                                "weekday": day,
                                "opens_at": opens.strip(),
                                "closes_at": closes.strip(),
                            }
                        )
        elif days and hours:
            # Try to parse days and hours separately
            day_list = [d.strip() for d in days.split(",")]

            # If hours is a single time range, apply to all days
            if "-" in hours and "," not in hours:
                opens, closes = hours.split("-", 1)
                for day in day_list:
                    if day:
                        # Map day abbreviations to full names
                        day_mapping = {
                            "mon": "Monday",
                            "tue": "Tuesday",
                            "wed": "Wednesday",
                            "thu": "Thursday",
                            "fri": "Friday",
                            "sat": "Saturday",
                            "sun": "Sunday",
                        }

                        day_lower = day.lower()
                        for abbr, full_day in day_mapping.items():
                            if abbr in day_lower:
                                day = full_day
                                break

                        schedule.append(
                            {
                                "weekday": day,
                                "opens_at": opens.strip(),
                                "closes_at": closes.strip(),
                            }
                        )

        # If we couldn't parse structured hours, add a note with the raw values
        if not schedule and (days or hours or exact_hours or agency_hours):
            hours_note = ""
            if days:
                hours_note += f"Days: {days}. "
            if hours:
                hours_note += f"Hours: {hours}. "
            if exact_hours:
                hours_note += f"Exact hours: {exact_hours}. "
            if agency_hours:
                hours_note += f"Agency hours: {agency_hours}."

            # Return a special format to indicate this is a note, not structured hours
            return [{"hours_note": hours_note.strip()}]

        return schedule

    def transform_to_hsds(self, row: dict[str, str]) -> dict[str, Any]:
        """Transform CSV row to HSDS format.

        Args:
            row: Dictionary containing CSV row data

        Returns:
            Dictionary in HSDS format
        """
        # Extract basic information
        name = row.get("Account Name", "")
        email = row.get("Account Email", "")
        phone = row.get("Phone", "")
        program_phone = row.get("Program Phone Number", "")
        website = row.get("Website", "")

        # Extract address information
        address1 = row.get("Billing Address Line 1", "")
        address2 = row.get("Billing Address Line 2", "")
        city = row.get("Billing City", "")
        state = row.get("Billing State/Province", "")
        postal_code = row.get("Billing Zip/Postal Code", "")

        # Extract latitude and longitude
        try:
            latitude = float(row.get("MALatitude", "0"))
            longitude = float(row.get("MALongitude", "0"))
        except (ValueError, TypeError):
            # If lat/long are invalid, use default coordinates
            latitude, longitude = self.geocoder.get_default_coordinates(
                with_offset=True
            )

        # Extract service information
        type_code = row.get("Type Code", "")
        is_food_pantry = row.get("Is this a food pantry?", "")
        food_type = row.get("Food Type", "")
        services_provided = row.get("Services Provided", "")

        # Extract hours information
        days = row.get("Days of Food Pantry Operation", "")
        hours = row.get("Hours of Operation", "")
        agency_hours = row.get("Agency Hours of Operation", "")
        exact_hours = row.get("Exact Hours of Operation", "")

        # Extract requirements and restrictions
        docs_required = row.get("Documents Required", "")
        access_requirements = row.get("Access Requirements", "")
        languages = row.get("Languages Spoken", "")
        population_served = row.get("Population Served", "")

        # Extract service area information
        areas_served = row.get("Areas Served", "")
        zip_codes_served = row.get("Zip Codes Served By Delivery", "")
        counties_served = row.get("Counties Served By Deliver", "")
        miles_served = row.get("Miles from Org Served By Delivery", "")

        # Create description
        description_parts = []
        if is_food_pantry:
            description_parts.append(f"Food pantry: {is_food_pantry}")
        if food_type:
            description_parts.append(f"Food type: {food_type}")
        if services_provided:
            description_parts.append(f"Services provided: {services_provided}")
        if areas_served:
            description_parts.append(f"Areas served: {areas_served}")
        if zip_codes_served:
            description_parts.append(
                f"Zip codes served by delivery: {zip_codes_served}"
            )
        if counties_served:
            description_parts.append(f"Counties served by delivery: {counties_served}")
        if miles_served:
            description_parts.append(
                f"Miles from organization served by delivery: {miles_served}"
            )

        description = ". ".join(description_parts)

        # Create service attributes
        service_attributes = []

        if type_code:
            service_attributes.append(
                {"attribute_key": "TYPE_CODE", "attribute_value": type_code}
            )

        if is_food_pantry:
            service_attributes.append(
                {"attribute_key": "IS_FOOD_PANTRY", "attribute_value": is_food_pantry}
            )

        if food_type:
            service_attributes.append(
                {"attribute_key": "FOOD_TYPE", "attribute_value": food_type}
            )

        if docs_required:
            service_attributes.append(
                {
                    "attribute_key": "DOCUMENTS_REQUIRED",
                    "attribute_value": docs_required,
                }
            )

        if access_requirements:
            service_attributes.append(
                {
                    "attribute_key": "ACCESS_REQUIREMENTS",
                    "attribute_value": access_requirements,
                }
            )

        if languages:
            service_attributes.append(
                {"attribute_key": "LANGUAGES_SPOKEN", "attribute_value": languages}
            )

        if population_served:
            service_attributes.append(
                {
                    "attribute_key": "POPULATION_SERVED",
                    "attribute_value": population_served,
                }
            )

        # Parse hours
        regular_schedule = self.parse_hours(days, hours, exact_hours, agency_hours)

        # Create HSDS data structure
        hsds_data: dict[str, Any] = {
            "name": name,
            "alternate_name": "",
            "description": description,
            "email": email,
            "url": website,
            "status": "active",
            "address": {
                "address_1": address1,
                "address_2": address2,
                "city": city,
                "state_province": state,
                "postal_code": postal_code,
                "country": "US",
            },
            "phones": [],
        }

        # Add phones
        if phone:
            hsds_data["phones"].append({"number": phone, "type": "voice"})

        if program_phone and program_phone != phone:
            hsds_data["phones"].append(
                {
                    "number": program_phone,
                    "type": "voice",
                    "description": "Program phone",
                }
            )

        # Add location if valid coordinates
        if latitude != 0 and longitude != 0:
            hsds_data["location"] = {"latitude": latitude, "longitude": longitude}

        # Add service attributes if any
        if service_attributes:
            hsds_data["service_attributes"] = service_attributes

        # Add regular schedule if any
        if regular_schedule:
            # Check if we have a hours_note instead of structured hours
            if "hours_note" in regular_schedule[0]:
                hsds_data["hours_notes"] = regular_schedule[0]["hours_note"]
            else:
                hsds_data["regular_schedule"] = regular_schedule

        return hsds_data

    async def scrape(self) -> str:
        """Scrape data from HFC Partner Data CSV file.

        Returns:
            Summary of scraping operation as JSON string
        """
        if not self.csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {self.csv_path}")

        logger.info(f"Processing CSV file: {self.csv_path}")

        # Track statistics
        total_rows = 0
        processed_rows = 0
        skipped_rows = 0
        job_count = 0

        # Process CSV file
        with open(self.csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row in reader:
                total_rows += 1

                # Check if this row should be included (Show on Map)
                show_on_map = row.get("Show on Map", "").lower()
                if show_on_map in ("no", "false", "0", "n"):
                    skipped_rows += 1
                    continue

                # Check if we have a name (required field)
                if not row.get("Account Name"):
                    logger.warning(f"Skipping row {total_rows}: Missing Account Name")
                    skipped_rows += 1
                    continue

                try:
                    # Transform to HSDS format
                    hsds_data = self.transform_to_hsds(row)

                    # Submit to queue
                    job_id = self.submit_to_queue(json.dumps(hsds_data))
                    job_count += 1

                    # Log progress periodically
                    if job_count % 10 == 0:
                        logger.info(f"Processed {job_count} entries")

                    processed_rows += 1

                except Exception as e:
                    logger.error(f"Error processing row {total_rows}: {e}")
                    skipped_rows += 1
                    continue

        # Create summary
        summary = {
            "total_rows": total_rows,
            "processed_rows": processed_rows,
            "skipped_rows": skipped_rows,
            "jobs_created": job_count,
            "source": str(self.csv_path),
        }

        # Print summary to CLI
        print("\nScraper Summary:")
        print(f"Source: {self.csv_path}")
        print(f"Total rows: {total_rows}")
        print(f"Processed rows: {processed_rows}")
        print(f"Skipped rows: {skipped_rows}")
        print(f"Jobs created: {job_count}")
        print("Status: Complete\n")

        # Return summary as JSON string
        return json.dumps(summary)
