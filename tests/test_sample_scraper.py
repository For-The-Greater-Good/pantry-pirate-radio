"""Tests for sample scraper."""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.scraper.sample_scraper import SampleScraper


class TestSampleScraper:
    """Test SampleScraper functionality."""

    @pytest.fixture
    def mock_sample_data(self):
        """Create mock GeoJSON data for testing."""
        return [
            {
                "name": "Test Food Pantries",
                "category": "food_assistance",
                "features": [
                    {
                        "properties": {
                            "name": "Test Food Pantry 1",
                            "address": "123 Main St",
                            "phone": "555-1234",
                        }
                    },
                    {
                        "properties": {
                            "name": "Test Food Pantry 2",
                            "address": "456 Oak Ave",
                            "email": "test@example.com",
                        }
                    },
                ],
            }
        ]

    @pytest.fixture
    def temp_test_file(self, mock_sample_data):
        """Create a temporary test file with sample data."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(mock_sample_data, f)
            temp_path = Path(f.name)

        yield temp_path

        # Cleanup
        temp_path.unlink()

    def test_init_default_id(self):
        """Test initialization with default scraper ID."""
        scraper = SampleScraper()
        assert scraper.scraper_id == "sample"

    def test_init_custom_id(self):
        """Test initialization with custom scraper ID."""
        scraper = SampleScraper(scraper_id="custom-sample")
        assert scraper.scraper_id == "custom-sample"

    def test_set_test_file(self, temp_test_file):
        """Test setting test file path."""
        scraper = SampleScraper()
        scraper.set_test_file(temp_test_file)
        assert scraper._test_file == temp_test_file

    @pytest.mark.asyncio
    async def test_run_with_test_file(self, temp_test_file, mock_sample_data):
        """Test run method with test file."""
        scraper = SampleScraper()
        scraper.set_test_file(temp_test_file)

        # Mock the submit_to_queue method
        scraper.submit_to_queue = MagicMock(side_effect=["job-1", "job-2"])

        await scraper.run()

        # Check that submit_to_queue was called for each feature
        assert scraper.submit_to_queue.call_count == 2

        # Check the content of the submitted jobs
        call_args = scraper.submit_to_queue.call_args_list

        # First feature
        first_job_data = json.loads(call_args[0][0][0])
        assert first_job_data["name"] == "Test Food Pantry 1"
        assert first_job_data["address"] == "123 Main St"
        assert first_job_data["phone"] == "555-1234"
        assert first_job_data["collection_name"] == "Test Food Pantries"
        assert first_job_data["collection_category"] == "food_assistance"

        # Second feature
        second_job_data = json.loads(call_args[1][0][0])
        assert second_job_data["name"] == "Test Food Pantry 2"
        assert second_job_data["address"] == "456 Oak Ave"
        assert second_job_data["email"] == "test@example.com"
        assert second_job_data["collection_name"] == "Test Food Pantries"
        assert second_job_data["collection_category"] == "food_assistance"

    @pytest.mark.asyncio
    async def test_run_with_default_file_path(self):
        """Test run method using default file path."""
        scraper = SampleScraper()

        # Mock the file existence and content
        mock_data = [{"features": [{"properties": {"name": "Test Pantry"}}]}]

        with patch("pathlib.Path.exists", return_value=True), patch(
            "builtins.open", mock_open_with_data(json.dumps(mock_data))
        ), patch.object(
            scraper, "submit_to_queue", return_value="job-1"
        ) as mock_submit:

            await scraper.run()

            # Check that submit_to_queue was called
            mock_submit.assert_called_once()

            # Verify the job data
            call_args = mock_submit.call_args[0][0]
            job_data = json.loads(call_args)
            assert job_data["name"] == "Test Pantry"

    @pytest.mark.asyncio
    async def test_run_file_not_found(self):
        """Test run method when file doesn't exist."""
        scraper = SampleScraper()
        scraper.set_test_file(Path("/nonexistent/file.json"))

        with pytest.raises(FileNotFoundError, match="GeoJSON file not found"):
            await scraper.run()

    @pytest.mark.asyncio
    async def test_run_default_file_not_found(self):
        """Test run method when default file doesn't exist."""
        scraper = SampleScraper()

        with patch("pathlib.Path.exists", return_value=False):
            with pytest.raises(FileNotFoundError, match="GeoJSON file not found"):
                await scraper.run()

    @pytest.mark.asyncio
    async def test_run_malformed_json(self, temp_test_file):
        """Test run method with malformed JSON."""
        # Write malformed JSON to temp file
        with open(temp_test_file, "w") as f:
            f.write("invalid json content")

        scraper = SampleScraper()
        scraper.set_test_file(temp_test_file)

        with pytest.raises(json.JSONDecodeError):
            await scraper.run()

    @pytest.mark.asyncio
    async def test_run_no_features(self):
        """Test run method with collection that has no features."""
        scraper = SampleScraper()

        # Mock data without features
        mock_data = [{"name": "Empty Collection"}]

        with patch("pathlib.Path.exists", return_value=True), patch(
            "builtins.open", mock_open_with_data(json.dumps(mock_data))
        ), patch.object(scraper, "submit_to_queue") as mock_submit:

            await scraper.run()

            # Should not submit any jobs
            mock_submit.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_with_missing_collection_metadata(self, temp_test_file):
        """Test run method with collection missing name/category."""
        # Create data without collection metadata
        data = [{"features": [{"properties": {"name": "Test Pantry"}}]}]

        with open(temp_test_file, "w") as f:
            json.dump(data, f)

        scraper = SampleScraper()
        scraper.set_test_file(temp_test_file)
        scraper.submit_to_queue = MagicMock(return_value="job-1")

        await scraper.run()

        # Check that empty strings are used for missing metadata
        call_args = scraper.submit_to_queue.call_args[0][0]
        job_data = json.loads(call_args)
        assert job_data["collection_name"] == ""
        assert job_data["collection_category"] == ""

    @pytest.mark.asyncio
    async def test_scrape_method(self):
        """Test the scrape method returns empty string."""
        scraper = SampleScraper()
        result = await scraper.scrape()
        assert result == ""


def mock_open_with_data(data):
    """Helper to create mock open with specific data."""
    from unittest.mock import mock_open

    return mock_open(read_data=data)
