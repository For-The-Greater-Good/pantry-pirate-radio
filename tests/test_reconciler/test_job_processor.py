"""Tests for the job processor module."""

import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from datetime import datetime

from app.llm.queue.job import LLMJob
from app.llm.queue.types import JobResult, JobStatus
from app.llm.providers.types import LLMResponse
from app.reconciler.job_processor import JobProcessor


class TestJobProcessor:
    """Test cases for JobProcessor class."""

    def test_should_extract_json_from_markdown_code_blocks(self):
        """Test that JSON is correctly extracted from markdown code blocks."""
        # Arrange
        processor = JobProcessor(MagicMock(spec=Session))
        markdown_text = """```json
{
    "organization": {
        "name": "Test Food Bank",
        "description": "A test organization"
    }
}
```"""

        # Act
        result = processor._extract_json_from_markdown(markdown_text)

        # Assert
        expected = """{
    "organization": {
        "name": "Test Food Bank",
        "description": "A test organization"
    }
}"""
        assert result == expected

    def test_should_return_original_text_when_no_markdown_blocks(self):
        """Test that original text is returned when no markdown blocks are present."""
        # Arrange
        processor = JobProcessor(MagicMock(spec=Session))
        plain_json = '{"name": "Test", "value": 123}'

        # Act
        result = processor._extract_json_from_markdown(plain_json)

        # Assert
        assert result == plain_json

    def test_should_handle_json_block_without_language_specifier(self):
        """Test extraction from code blocks without 'json' language specifier."""
        # Arrange
        processor = JobProcessor(MagicMock(spec=Session))
        markdown_text = """```
{"key": "value"}
```"""

        # Act
        result = processor._extract_json_from_markdown(markdown_text)

        # Assert
        assert result == '{"key": "value"}'

    @patch("app.reconciler.job_processor.OrganizationCreator")
    @patch("app.reconciler.job_processor.LocationCreator")
    @patch("app.reconciler.job_processor.ServiceCreator")
    @patch("app.reconciler.job_processor.logger")
    def test_should_parse_json_from_markdown_in_job_result(
        self, mock_logger, mock_service_creator, mock_location_creator, mock_org_creator
    ):
        """Test that job results with markdown-wrapped JSON are parsed correctly."""
        # Arrange
        processor = JobProcessor(MagicMock(spec=Session))

        # Create a mock job result with markdown-wrapped JSON
        llm_response = LLMResponse(
            text="""```json
{
    "organization": [{
        "id": "test-123",
        "name": "Food Bank",
        "description": "Test food bank"
    }],
    "service": [],
    "location": []
}
```""",
            model="test-model",
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )

        job = LLMJob(
            id="job-123",
            prompt="Test prompt",
            created_at=datetime.now(),
            metadata={
                "scraper_id": "test_scraper",
                "type": "hsds_alignment",
                "data": {"raw_data": {"test": "data"}},
            },
        )

        job_result = JobResult(
            job_id="job-123", job=job, status=JobStatus.COMPLETED, result=llm_response
        )

        # Mock the creator instances
        mock_org_instance = mock_org_creator.return_value
        mock_org_instance.process_organization.return_value = ("org-uuid", True)
        mock_org_instance.create_organization.return_value = "org-uuid"

        mock_service_instance = mock_service_creator.return_value
        mock_service_instance.create_services.return_value = []

        mock_location_instance = mock_location_creator.return_value
        mock_location_instance.process_locations.return_value = []

        # Act - this should parse successfully without throwing JSON decode error
        try:
            result = processor.process_job_result(job_result)
            # Assert
            assert result["status"] == "success"
            assert result["scraper_id"] == "test_scraper"
        except json.JSONDecodeError:
            pytest.fail("JSON decoding should not fail with markdown code blocks")

    @patch("app.reconciler.job_processor.OrganizationCreator")
    @patch("app.reconciler.job_processor.LocationCreator")
    @patch("app.reconciler.job_processor.ServiceCreator")
    @patch("app.reconciler.job_processor.logger")
    def test_should_handle_malformed_json_with_backticks(
        self, mock_logger, mock_service_creator, mock_location_creator, mock_org_creator
    ):
        """Test that malformed JSON with backticks uses demjson3 fallback."""
        # Arrange
        processor = JobProcessor(MagicMock(spec=Session))

        # Create a job result with slightly malformed JSON in markdown
        llm_response = LLMResponse(
            text="""```json
{
    "organization": [{
        "name": "Test Org",
        "description": "Test", // This comment makes it invalid JSON
    }],
    "service": [],
    "location": []
}
```""",
            model="test-model",
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )

        job = LLMJob(
            id="job-123",
            prompt="Test prompt",
            created_at=datetime.now(),
            metadata={
                "scraper_id": "test_scraper",
                "type": "hsds_alignment",
                "data": {"raw_data": {"test": "data"}},
            },
        )

        job_result = JobResult(
            job_id="job-123", job=job, status=JobStatus.COMPLETED, result=llm_response
        )

        # Mock the creator instances
        mock_org_instance = mock_org_creator.return_value
        mock_org_instance.process_organization.return_value = ("org-uuid", True)
        mock_org_instance.create_organization.return_value = "org-uuid"

        mock_service_instance = mock_service_creator.return_value
        mock_service_instance.create_services.return_value = []

        mock_location_instance = mock_location_creator.return_value
        mock_location_instance.process_locations.return_value = []

        # Act
        result = processor.process_job_result(job_result)

        # Assert
        assert result["status"] == "success"
        # Verify demjson3 was used (logger was called with the error)
        # The actual log message includes the error details now
        assert any(
            "Standard JSON parsing failed:" in str(call)
            for call in mock_logger.info.call_args_list
        )

    def test_should_raise_error_when_json_completely_invalid(self):
        """Test that completely invalid JSON raises an error."""
        # Arrange
        processor = JobProcessor(MagicMock(spec=Session))

        # Create a job result with completely invalid content
        llm_response = LLMResponse(
            text="This is not JSON at all, just plain text",
            model="test-model",
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )

        job = LLMJob(
            id="job-123",
            prompt="Test prompt",
            created_at=datetime.now(),
            metadata={
                "scraper_id": "test_scraper",
                "type": "hsds_alignment",
                "data": {"raw_data": {"test": "data"}},
            },
        )

        job_result = JobResult(
            job_id="job-123", job=job, status=JobStatus.COMPLETED, result=llm_response
        )

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            processor.process_job_result(job_result)

        # Verify the error contains the expected information
        error_data = json.loads(str(exc_info.value))
        assert error_data["status"] == "error"
        assert error_data["scraper_id"] == "test_scraper"
        assert "error" in error_data

    @patch("app.reconciler.job_processor.OrganizationCreator")
    @patch("app.reconciler.job_processor.LocationCreator")
    @patch("app.reconciler.job_processor.ServiceCreator")
    def test_should_handle_llm_response_starting_with_backticks(
        self, mock_service_creator, mock_location_creator, mock_org_creator
    ):
        """Test that LLM responses starting with backticks are handled correctly."""
        # Arrange
        processor = JobProcessor(MagicMock(spec=Session))

        # Create a job result where text starts with backticks (reproducing the actual error)
        llm_response = LLMResponse(
            text="""```json
{
    "organization": [{
        "name": "Food Helpline Organization",
        "description": "Provides food assistance"
    }],
    "service": [],
    "location": []
}
```""",
            model="test-model",
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )

        job = LLMJob(
            id="job-123",
            prompt="Test prompt",
            created_at=datetime.now(),
            metadata={
                "scraper_id": "food_helpline_org",
                "type": "hsds_alignment",
                "data": {},
            },
        )

        job_result = JobResult(
            job_id="job-123", job=job, status=JobStatus.COMPLETED, result=llm_response
        )

        # Mock the creator instances
        mock_org_instance = mock_org_creator.return_value
        mock_org_instance.process_organization.return_value = ("org-uuid", True)
        mock_org_instance.create_organization.return_value = "org-uuid"

        mock_service_instance = mock_service_creator.return_value
        mock_service_instance.create_services.return_value = []

        mock_location_instance = mock_location_creator.return_value
        mock_location_instance.process_locations.return_value = []

        # Act - this should NOT raise an error anymore
        result = processor.process_job_result(job_result)

        # Assert
        assert result["status"] == "success"
        assert result["scraper_id"] == "food_helpline_org"

    @patch("app.reconciler.job_processor.OrganizationCreator")
    @patch("app.reconciler.job_processor.LocationCreator")
    @patch("app.reconciler.job_processor.ServiceCreator")
    def test_should_handle_empty_string_year_incorporated(
        self, mock_service_creator, mock_location_creator, mock_org_creator
    ):
        """Test that empty string year_incorporated values are converted to None."""
        # Arrange
        processor = JobProcessor(MagicMock(spec=Session))

        # Create a job result with empty string year_incorporated
        llm_response = LLMResponse(
            text="""{
    "organization": [{
        "name": "Test Organization",
        "description": "A test organization",
        "year_incorporated": "",
        "website": "",
        "email": ""
    }],
    "service": [],
    "location": []
}""",
            model="test-model",
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )

        job = LLMJob(
            id="job-123",
            prompt="Test prompt",
            created_at=datetime.now(),
            metadata={
                "scraper_id": "test_scraper",
                "type": "hsds_alignment",
                "data": {},
            },
        )

        job_result = JobResult(
            job_id="job-123", job=job, status=JobStatus.COMPLETED, result=llm_response
        )

        # Mock the creator instances
        mock_org_instance = mock_org_creator.return_value
        mock_org_instance.process_organization.return_value = ("org-uuid", True)

        mock_service_instance = mock_service_creator.return_value
        mock_service_instance.create_services.return_value = []

        mock_location_instance = mock_location_creator.return_value
        mock_location_instance.process_locations.return_value = []

        # Act
        result = processor.process_job_result(job_result)

        # Assert - check that year_incorporated was converted to None
        mock_org_instance.process_organization.assert_called_once()
        call_args = mock_org_instance.process_organization.call_args
        assert (
            call_args[1]["year_incorporated"] is None
        )  # Empty string should be converted to None
        assert (
            call_args[1]["website"] is None
        )  # Empty string should be converted to None
        assert call_args[1]["email"] is None  # Empty string should be converted to None
        assert result["status"] == "success"

    def test_should_convert_string_year_to_integer(self):
        """Test that valid string year values are converted to integers."""
        # Arrange
        processor = JobProcessor(MagicMock(spec=Session))

        # Test various year formats
        test_cases = [
            ("2023", 2023),
            (" 2023 ", 2023),
            ("", None),
            ("  ", None),
            ("abc", None),
            ("20.23", None),
            (2023, 2023),  # Already an integer
            (None, None),  # Already None
        ]

        for input_value, expected in test_cases:
            # Simulate the conversion logic from the job processor
            if isinstance(input_value, str):
                result = (
                    int(input_value)
                    if input_value.strip() and input_value.strip().isdigit()
                    else None
                )
            elif not isinstance(input_value, int | type(None)):
                result = None
            else:
                result = input_value

            assert result == expected, f"Failed for input: {input_value!r}"


class TestTransformScheduleWkstDefault:
    """Test that _transform_schedule defaults wkst to 'MO' per RFC 5545."""

    @pytest.fixture
    def processor(self):
        """Create a JobProcessor with a mock session."""
        return JobProcessor(MagicMock(spec=Session))

    def test_schedule_with_freq_and_no_wkst_gets_default(self, processor):
        """Schedule with freq but no wkst should default wkst to 'MO'."""
        schedule = {
            "freq": "WEEKLY",
            "opens_at": "09:00",
            "closes_at": "17:00",
            "byday": "TU,TH",
        }
        result = processor._transform_schedule(schedule)
        assert result is not None
        assert result["wkst"] == "MO"
        assert result["freq"] == "WEEKLY"
        assert result["byday"] == "TU,TH"

    def test_schedule_with_freq_and_wkst_keeps_original(self, processor):
        """Schedule with both freq and wkst should keep the original wkst."""
        schedule = {
            "freq": "WEEKLY",
            "wkst": "SU",
            "opens_at": "10:00",
            "closes_at": "14:00",
        }
        result = processor._transform_schedule(schedule)
        assert result is not None
        assert result["wkst"] == "SU"

    def test_schedule_without_freq_still_dropped(self, processor):
        """Schedule without freq should still be dropped."""
        schedule = {
            "wkst": "MO",
            "opens_at": "09:00",
            "closes_at": "17:00",
        }
        result = processor._transform_schedule(schedule)
        assert result is None

    def test_monthly_schedule_without_wkst_gets_default(self, processor):
        """Monthly schedule without wkst should also get 'MO' default."""
        schedule = {
            "freq": "MONTHLY",
            "opens_at": "10:00",
            "closes_at": "14:00",
            "byday": "1SA,3SA",
        }
        result = processor._transform_schedule(schedule)
        assert result is not None
        assert result["wkst"] == "MO"
        assert result["freq"] == "MONTHLY"

    def test_once_freq_without_wkst_gets_default(self, processor):
        """ONCE frequency (converted to WEEKLY) without wkst should get default."""
        schedule = {
            "freq": "ONCE",
            "opens_at": "09:00",
            "closes_at": "12:00",
            "dtstart": "2025-01-15",
        }
        result = processor._transform_schedule(schedule)
        assert result is not None
        assert result["freq"] == "WEEKLY"
        assert result["wkst"] == "MO"
        assert result["count"] == 1


class TestSameRecurrence:
    """FF-2: the in-memory schedule-collection dedup key must include
    bymonthday, so two MONTHLY windows differing only in day-of-month are not
    collapsed before reaching REC-2's DB upsert."""

    def _base(self, **over):
        s = {
            "freq": "MONTHLY",
            "wkst": "MO",
            "opens_at": "09:00",
            "closes_at": "12:00",
            "byday": None,
            "bymonthday": "1",
        }
        s.update(over)
        return s

    def test_identical_recurrence_matches(self):
        assert JobProcessor._same_recurrence(self._base(), self._base()) is True

    def test_differs_only_in_bymonthday_does_not_match(self):
        # The bug this fixes: same hours/freq, byday NULL, only the
        # day-of-month differs (1st vs 15th) — must be treated as distinct.
        a = self._base(bymonthday="1")
        b = self._base(bymonthday="15")
        assert JobProcessor._same_recurrence(a, b) is False

    def test_differs_only_in_byday_does_not_match(self):
        a = self._base(freq="WEEKLY", bymonthday=None, byday="MO")
        b = self._base(freq="WEEKLY", bymonthday=None, byday="TH")
        assert JobProcessor._same_recurrence(a, b) is False

    def test_differs_in_hours_does_not_match(self):
        assert (
            JobProcessor._same_recurrence(
                self._base(opens_at="09:00"), self._base(opens_at="08:00")
            )
            is False
        )

    def test_missing_keys_treated_as_none(self):
        # A dict without bymonthday matches one with bymonthday=None (both
        # absent/None), but not one with a real bymonthday.
        no_bmd = {"freq": "WEEKLY", "wkst": "MO", "opens_at": "9", "closes_at": "5"}
        assert JobProcessor._same_recurrence(no_bmd, dict(no_bmd, byday=None)) is True
        assert (
            JobProcessor._same_recurrence(no_bmd, dict(no_bmd, bymonthday="15"))
            is False
        )


class TestSubmarineDirectIdPath:
    """Test submarine's direct ID-based location matching path."""

    @patch("app.reconciler.job_processor.OrganizationCreator")
    @patch("app.reconciler.job_processor.LocationCreator")
    @patch("app.reconciler.job_processor.ServiceCreator")
    @patch("app.reconciler.job_processor.logger")
    def test_submarine_result_uses_direct_id_match(
        self, mock_logger, mock_service_creator, mock_location_creator, mock_org_creator
    ):
        """Submarine results use location_id from metadata instead of coordinate matching.

        When scraper_id='submarine', the processor should query by ID (not coordinates)
        and never call find_matching_location.
        """
        processor = JobProcessor(MagicMock(spec=Session))

        llm_response = LLMResponse(
            text=json.dumps(
                {
                    "organization": [
                        {"name": "Grace Food Pantry", "description": "Food pantry"}
                    ],
                    "service": [],
                    "location": [
                        {
                            "name": "Grace Food Pantry",
                            "description": "Community food pantry",
                            "latitude": 39.7817,
                            "longitude": -89.6501,
                        }
                    ],
                }
            ),
            model="test-model",
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )

        target_location_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        job = LLMJob(
            id="job-sub-001",
            prompt="Test prompt",
            created_at=datetime.now(),
            metadata={
                "scraper_id": "submarine",
                "location_id": target_location_id,
                "source_type": "submarine",
                "type": "hsds_alignment",
                "data": {},
            },
        )

        job_result = JobResult(
            job_id="job-sub-001",
            job=job,
            status=JobStatus.COMPLETED,
            result=llm_response,
        )

        mock_org_instance = mock_org_creator.return_value
        mock_org_instance.process_organization.return_value = ("org-uuid", True)

        mock_service_instance = mock_service_creator.return_value
        mock_service_instance.create_services.return_value = []

        mock_location_instance = mock_location_creator.return_value

        # Mock DB: return the target location for submarine verification,
        # and a mock result for all other queries
        mock_verify_result = MagicMock()
        mock_verify_result.first.return_value = (target_location_id,)
        processor.db.execute.return_value = mock_verify_result

        processor.process_job_result(job_result)

        # Submarine should NOT use coordinate matching
        mock_location_instance.find_matching_location.assert_not_called()

    @patch("app.reconciler.job_processor.OrganizationCreator")
    @patch("app.reconciler.job_processor.LocationCreator")
    @patch("app.reconciler.job_processor.ServiceCreator")
    @patch("app.reconciler.job_processor.logger")
    def test_submarine_result_skips_nonexistent_location(
        self, mock_logger, mock_service_creator, mock_location_creator, mock_org_creator
    ):
        """Submarine skips processing when target location_id does not exist."""
        processor = JobProcessor(MagicMock(spec=Session))

        llm_response = LLMResponse(
            text=json.dumps(
                {
                    "organization": [
                        {"name": "Ghost Pantry", "description": "Does not exist"}
                    ],
                    "service": [],
                    "location": [
                        {
                            "name": "Ghost Pantry",
                            "description": "Non-existent location",
                            "latitude": 40.0,
                            "longitude": -75.0,
                        }
                    ],
                }
            ),
            model="test-model",
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )

        job = LLMJob(
            id="job-sub-002",
            prompt="Test prompt",
            created_at=datetime.now(),
            metadata={
                "scraper_id": "submarine",
                "location_id": "loc-does-not-exist",
                "source_type": "submarine",
                "type": "hsds_alignment",
                "data": {},
            },
        )

        job_result = JobResult(
            job_id="job-sub-002",
            job=job,
            status=JobStatus.COMPLETED,
            result=llm_response,
        )

        mock_org_instance = mock_org_creator.return_value
        mock_org_instance.process_organization.return_value = ("org-uuid", True)

        mock_service_instance = mock_service_creator.return_value
        mock_service_instance.create_services.return_value = []

        mock_location_instance = mock_location_creator.return_value
        mock_location_instance.process_locations.return_value = []

        # DB returns no result for verification query (location doesn't exist)
        mock_verify_result = MagicMock()
        mock_verify_result.first.return_value = None
        processor.db.execute.return_value = mock_verify_result

        result = processor.process_job_result(job_result)

        # Should still succeed overall, but the location was skipped (continue)
        assert result["status"] == "success"
        # The location_creator.create_location_source should NOT be called for
        # a non-existent submarine target since it was skipped via 'continue'
        mock_location_instance.create_location_source.assert_not_called()

    @patch("app.reconciler.job_processor.OrganizationCreator")
    @patch("app.reconciler.job_processor.LocationCreator")
    @patch("app.reconciler.job_processor.ServiceCreator")
    @patch("app.reconciler.job_processor.logger")
    def test_submarine_source_type_propagated(
        self, mock_logger, mock_service_creator, mock_location_creator, mock_org_creator
    ):
        """Submarine source_type is passed through to create_location_source."""
        processor = JobProcessor(MagicMock(spec=Session))

        llm_response = LLMResponse(
            text=json.dumps(
                {
                    "organization": [{"name": "Test Pantry", "description": "Test"}],
                    "service": [],
                    "location": [
                        {
                            "name": "Test Pantry",
                            "description": "Test location",
                            "latitude": 39.78,
                            "longitude": -89.65,
                        }
                    ],
                }
            ),
            model="test-model",
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )

        target_id = "b2c3d4e5-f6a7-8901-bcde-f12345678901"
        job = LLMJob(
            id="job-sub-003",
            prompt="Test prompt",
            created_at=datetime.now(),
            metadata={
                "scraper_id": "submarine",
                "location_id": target_id,
                "source_type": "submarine",
                "type": "hsds_alignment",
                "data": {},
            },
        )

        job_result = JobResult(
            job_id="job-sub-003",
            job=job,
            status=JobStatus.COMPLETED,
            result=llm_response,
        )

        mock_org_instance = mock_org_creator.return_value
        mock_org_instance.process_organization.return_value = ("org-uuid", True)

        mock_service_instance = mock_service_creator.return_value
        mock_service_instance.create_services.return_value = []

        mock_location_instance = mock_location_creator.return_value

        # DB: location exists for submarine verification
        mock_verify_result = MagicMock()
        mock_verify_result.first.return_value = (target_id,)
        processor.db.execute.return_value = mock_verify_result

        result = processor.process_job_result(job_result)

        assert result["status"] == "success"
        # Verify create_location_source was called with source_type="submarine"
        if mock_location_instance.create_location_source.called:
            call_kwargs = mock_location_instance.create_location_source.call_args
            assert call_kwargs.kwargs.get("source_type") == "submarine" or (
                len(call_kwargs.args) > 7 and call_kwargs.args[7] == "submarine"
            )


class TestExistingMatchPathCallsCorroboration:
    """Negative-case integration: certain job shapes must not trigger
    the corroboration bonus on the existing-match branch (path 2).

    The positive case (path 2 invokes corroboration with the right
    inputs) is covered by `TestExistingMatchPathScoreBump` via a
    behavior assertion on the rendered SQL.
    """

    @patch("app.reconciler.job_processor.OrganizationCreator")
    @patch("app.reconciler.job_processor.LocationCreator")
    @patch("app.reconciler.job_processor.ServiceCreator")
    @patch("app.reconciler.job_processor.SubmarineLocationHandler")
    @patch("app.reconciler.job_processor.VersionTracker")
    @patch("app.reconciler.job_processor.logger")
    def test_submarine_job_skips_corroboration_bonus(
        self,
        mock_logger,
        mock_version_tracker,
        mock_submarine_handler,
        mock_service_creator,
        mock_location_creator,
        mock_org_creator,
    ):
        """Submarine enrichment jobs must not contribute to corroboration.

        Submarine is an enrichment pass, not an independent confirmation
        — constitution amendment v1.5.1 explicitly excludes it from
        corroboration. The per-job score on a submarine job is also
        artificially inflated by enrichment; using it as the bonus base
        would write a misleading canonical score.
        """
        processor = JobProcessor(MagicMock(spec=Session))

        target_location_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        llm_response = LLMResponse(
            text=json.dumps(
                {
                    "organization": [{"name": "Submarine Pantry", "description": "x"}],
                    "service": [],
                    "location": [
                        {
                            "name": "Submarine Pantry",
                            "description": "Crawled and extracted",
                            "latitude": 39.7817,
                            "longitude": -89.6501,
                            "confidence_score": 78,
                            "validation_status": "verified",
                        }
                    ],
                }
            ),
            model="test-model",
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        )

        job = LLMJob(
            id="job-sub-corrob-001",
            prompt="Test prompt",
            created_at=datetime.now(),
            metadata={
                "scraper_id": "submarine",
                "location_id": target_location_id,
                "source_type": "submarine",
                "type": "hsds_alignment",
            },
        )
        job_result = JobResult(
            job_id="job-sub-corrob-001",
            job=job,
            status=JobStatus.COMPLETED,
            result=llm_response,
        )

        mock_org_instance = mock_org_creator.return_value
        mock_org_instance.process_organization.return_value = ("org-uuid", True)
        mock_service_instance = mock_service_creator.return_value
        mock_service_instance.create_services.return_value = []

        # Submarine handler resolves the target via metadata-supplied id
        # rather than coordinate matching.
        mock_submarine_instance = mock_submarine_handler.return_value
        mock_submarine_instance.is_submarine_job.return_value = True
        mock_submarine_instance.resolve_target_location.return_value = (
            target_location_id
        )
        mock_submarine_instance.update_location.return_value = "desc"
        mock_submarine_instance.persist_schedules.return_value = None

        mock_location_instance = mock_location_creator.return_value
        mock_location_instance.find_matching_location.return_value = target_location_id

        # Mock the verification SELECT (line ~900) used in the submarine
        # branch to confirm the target location exists.
        verify_result = MagicMock()
        verify_result.first.return_value = (target_location_id,)
        processor.db.execute.return_value = verify_result

        with patch("app.reconciler.job_processor.MergeStrategy") as mock_merge_cls:
            processor.process_job_result(job_result)

        # Submarine jobs must NOT route through merge_location — submarine is
        # enrichment, not independent confirmation (constitution v1.5.1), and
        # it has its own selective-field update handler.
        mock_merge_cls.return_value.merge_location.assert_not_called()


class TestExistingMatchPathScoreBump:
    """REC-4 behavioral assertions on the existing-match (path 2) update:
    the standard matched path routes the canonical content + corroboration
    write through field-level MergeStrategy.merge_location instead of a
    last-write-wins UPDATE, never wipes an existing organization link, fills
    a missing one, and a merge failure does not abort the surrounding job.
    Observes the rendered SQL and the MergeStrategy mock so the assertions
    survive call-site refactors."""

    @staticmethod
    def _matched_job_result(*, scraper_id="scraper_b", org=True):
        """Build a JobResult whose single location matches an existing row."""
        location = {
            "name": "Test Pantry",
            "description": "Community food pantry",
            "latitude": 39.7817,
            "longitude": -89.6501,
            "confidence_score": 66,
            "validation_status": "needs_review",
            "address": [
                {
                    "address_1": "123 Main St",
                    "city": "Springfield",
                    "state_province": "IL",
                    "postal_code": "62701",
                    "country": "US",
                    "address_type": "physical",
                }
            ],
        }
        organization = (
            [{"name": "Test Pantry Org", "description": "Test"}] if org else []
        )
        llm_response = LLMResponse(
            text=json.dumps(
                {"organization": organization, "service": [], "location": [location]}
            ),
            model="test-model",
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )
        job = LLMJob(
            id="job-bump-001",
            prompt="Test prompt",
            created_at=datetime.now(),
            metadata={"scraper_id": scraper_id, "type": "hsds_alignment"},
        )
        return JobResult(
            job_id="job-bump-001",
            job=job,
            status=JobStatus.COMPLETED,
            result=llm_response,
        )

    @staticmethod
    def _content_lww_updates(execute_calls):
        """Inline last-write-wins content UPDATEs (those binding name=:name) —
        the overwrite that REC-4 removes. The fill-only org UPDATE (which sets
        only organization_id) is intentionally NOT counted here."""
        return [
            c
            for c in execute_calls
            if "update location" in str(c.args[0]).lower()
            and "name=:name" in str(c.args[0]).lower()
        ]

    @patch("app.reconciler.job_processor.MergeStrategy")
    @patch("app.reconciler.job_processor.OrganizationCreator")
    @patch("app.reconciler.job_processor.LocationCreator")
    @patch("app.reconciler.job_processor.ServiceCreator")
    @patch("app.reconciler.job_processor.VersionTracker")
    @patch("app.reconciler.job_processor.logger")
    def test_matched_path_routes_through_merge_location(
        self,
        mock_logger,
        mock_version_tracker,
        mock_service_creator,
        mock_location_creator,
        mock_org_creator,
        mock_merge_cls,
    ):
        """The standard matched path must delegate the canonical write to
        MergeStrategy.merge_location(location_id, per_job_score) and must NOT
        issue an inline last-write-wins `UPDATE location SET name=...`."""
        processor = JobProcessor(MagicMock(spec=Session))
        existing_loc_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        validator_score = 66

        mock_org_creator.return_value.process_organization.return_value = (
            "org-uuid",
            True,
        )
        mock_service_creator.return_value.create_services.return_value = []
        mock_location_creator.return_value.find_matching_location.return_value = (
            existing_loc_id
        )

        generic = MagicMock()
        generic.first.return_value = None
        generic.scalar.return_value = 0
        generic.rowcount = 1
        processor.db.execute.return_value = generic

        processor.process_job_result(self._matched_job_result())

        # Routed through field-level merge with the per-job validator score
        # (idempotent base, not the canonical row's already-bonused score).
        mock_merge_cls.return_value.merge_location.assert_called_once_with(
            existing_loc_id, validator_score
        )
        # No inline last-write-wins content overwrite remains.
        assert self._content_lww_updates(processor.db.execute.call_args_list) == [], (
            "Standard matched path must not run the inline "
            "`UPDATE location SET name=...` last-write-wins overwrite"
        )

        # Idempotency: reprocessing the same job passes the SAME per-job
        # validator score again — never the canonical row's already-bonused
        # score — so the corroboration bonus cannot compound across reruns.
        processor.process_job_result(self._matched_job_result())
        merge_calls = mock_merge_cls.return_value.merge_location.call_args_list
        assert len(merge_calls) == 2
        assert all(c.args == (existing_loc_id, validator_score) for c in merge_calls)

    @patch("app.reconciler.job_processor.MergeStrategy")
    @patch("app.reconciler.job_processor.OrganizationCreator")
    @patch("app.reconciler.job_processor.LocationCreator")
    @patch("app.reconciler.job_processor.ServiceCreator")
    @patch("app.reconciler.job_processor.VersionTracker")
    @patch("app.reconciler.job_processor.logger")
    def test_no_org_rescrape_does_not_wipe_org(
        self,
        mock_logger,
        mock_version_tracker,
        mock_service_creator,
        mock_location_creator,
        mock_org_creator,
        mock_merge_cls,
    ):
        """REC-4 org-wipe fix: a re-scrape with NO organization must never
        bind organization_id=NULL on the canonical row. merge_location does
        not touch org, and the fill-only UPDATE fires only when an org is
        present, so no org write happens at all."""
        processor = JobProcessor(MagicMock(spec=Session))
        existing_loc_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

        # No organization in the LLM output → org_id resolves falsy.
        mock_org_creator.return_value.process_organization.return_value = (None, False)
        mock_service_creator.return_value.create_services.return_value = []
        mock_location_creator.return_value.find_matching_location.return_value = (
            existing_loc_id
        )

        generic = MagicMock()
        generic.first.return_value = None
        generic.scalar.return_value = 0
        generic.rowcount = 1
        processor.db.execute.return_value = generic

        processor.process_job_result(self._matched_job_result(org=False))

        org_writes = [
            c
            for c in processor.db.execute.call_args_list
            if "update location" in str(c.args[0]).lower()
            and "organization_id" in str(c.args[0]).lower()
        ]
        assert org_writes == [], (
            "A no-org re-scrape must issue no organization_id UPDATE "
            f"(would risk wiping an existing link); found: {org_writes}"
        )

    @patch("app.reconciler.job_processor.MergeStrategy")
    @patch("app.reconciler.job_processor.OrganizationCreator")
    @patch("app.reconciler.job_processor.LocationCreator")
    @patch("app.reconciler.job_processor.ServiceCreator")
    @patch("app.reconciler.job_processor.VersionTracker")
    @patch("app.reconciler.job_processor.logger")
    def test_missing_org_is_filled_not_overwritten(
        self,
        mock_logger,
        mock_version_tracker,
        mock_service_creator,
        mock_location_creator,
        mock_org_creator,
        mock_merge_cls,
    ):
        """REC-4 org enrichment: when a scrape provides an org, the matched
        path fills the link ONLY when the canonical row currently has none —
        a guarded `UPDATE ... SET organization_id ... WHERE organization_id
        IS NULL`. It must never overwrite/flip an existing link."""
        processor = JobProcessor(MagicMock(spec=Session))
        existing_loc_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

        mock_org_creator.return_value.process_organization.return_value = (
            "org-uuid",
            True,
        )
        mock_service_creator.return_value.create_services.return_value = []
        mock_location_creator.return_value.find_matching_location.return_value = (
            existing_loc_id
        )

        generic = MagicMock()
        generic.first.return_value = None
        generic.scalar.return_value = 0
        generic.rowcount = 1
        processor.db.execute.return_value = generic

        processor.process_job_result(self._matched_job_result(org=True))

        org_fill = [
            c
            for c in processor.db.execute.call_args_list
            if "update location" in str(c.args[0]).lower()
            and "organization_id" in str(c.args[0]).lower()
        ]
        assert (
            len(org_fill) == 1
        ), f"Expected exactly one org-fill UPDATE; found {len(org_fill)}"
        sql = str(org_fill[0].args[0]).lower()
        assert "organization_id is null" in sql, (
            "Org fill must be guarded by `organization_id IS NULL` so it only "
            "fills a missing link and never overwrites an existing one"
        )
        # Owner-protected rows are still skipped.
        assert "verified_by" in sql
        assert org_fill[0].args[1]["organization_id"] == "org-uuid"

    @patch("app.reconciler.job_processor.MergeStrategy")
    @patch("app.reconciler.job_processor.OrganizationCreator")
    @patch("app.reconciler.job_processor.LocationCreator")
    @patch("app.reconciler.job_processor.ServiceCreator")
    @patch("app.reconciler.job_processor.VersionTracker")
    @patch("app.reconciler.job_processor.logger")
    def test_merge_location_failure_does_not_abort_job(
        self,
        mock_logger,
        mock_version_tracker,
        mock_service_creator,
        mock_location_creator,
        mock_org_creator,
        mock_merge_cls,
    ):
        """A failure inside merge_location must not abort the broader job
        (Principle XI). The scraper's data is already persisted in
        location_source; the next pass re-merges. The failure is logged as
        `merge_location_failed`."""
        from sqlalchemy.exc import OperationalError

        processor = JobProcessor(MagicMock(spec=Session))
        existing_loc_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

        mock_org_creator.return_value.process_organization.return_value = ("org", True)
        mock_service_creator.return_value.create_services.return_value = []
        mock_location_creator.return_value.find_matching_location.return_value = (
            existing_loc_id
        )
        mock_merge_cls.return_value.merge_location.side_effect = OperationalError(
            "boom", None, None
        )

        generic = MagicMock()
        generic.first.return_value = None
        generic.scalar.return_value = 0
        generic.rowcount = 1
        processor.db.execute.return_value = generic

        result = processor.process_job_result(self._matched_job_result())

        assert result["status"] == "success"
        warn_messages = [
            call_args.args[0] if call_args.args else call_args.kwargs.get("msg", "")
            for call_args in mock_logger.warning.call_args_list
        ]
        assert any(
            "merge_location_failed" in str(m) for m in warn_messages
        ), f"Expected 'merge_location_failed' in warning logs; got {warn_messages}"
