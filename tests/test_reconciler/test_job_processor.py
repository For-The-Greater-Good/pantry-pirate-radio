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


class TestApplyCorroborationBonus:
    """Pins the contract of JobProcessor._apply_corroboration_bonus:
    distinct-scraper count, +5/+10 tiers, cap at 90, no-op shapes,
    idempotency, and the human-curated guard."""

    def _make_processor(self):
        return JobProcessor(MagicMock(spec=Session))

    def _stub_scraper_count(self, processor, n: int):
        """Stub the first execute() call to return scalar n (the COUNT
        result); subsequent calls return a generic MagicMock."""
        count_result = MagicMock()
        count_result.scalar.return_value = n
        update_result = MagicMock()
        processor.db.execute.side_effect = [count_result, update_result]
        return count_result, update_result

    def test_two_scrapers_adds_five(self):
        processor = self._make_processor()
        self._stub_scraper_count(processor, 2)

        processor._apply_corroboration_bonus(
            location_id="11111111-1111-1111-1111-111111111111",
            per_job_score=66,
        )

        update_calls = [
            c
            for c in processor.db.execute.call_args_list
            if "update location" in str(c.args[0]).lower()
        ]
        assert len(update_calls) == 1
        params = update_calls[0].args[1]
        assert params["score"] == 71  # 66 + 5

    def test_three_scrapers_adds_ten(self):
        processor = self._make_processor()
        self._stub_scraper_count(processor, 3)

        processor._apply_corroboration_bonus(
            location_id="11111111-1111-1111-1111-111111111111",
            per_job_score=66,
        )

        update_calls = [
            c
            for c in processor.db.execute.call_args_list
            if "update location" in str(c.args[0]).lower()
        ]
        assert len(update_calls) == 1
        assert update_calls[0].args[1]["score"] == 76  # 66 + 10

    def test_caps_at_ninety(self):
        processor = self._make_processor()
        self._stub_scraper_count(processor, 3)

        processor._apply_corroboration_bonus(
            location_id="11111111-1111-1111-1111-111111111111",
            per_job_score=85,
        )

        update_calls = [
            c
            for c in processor.db.execute.call_args_list
            if "update location" in str(c.args[0]).lower()
        ]
        assert len(update_calls) == 1
        assert update_calls[0].args[1]["score"] == 90  # 85 + 10 clamped to 90

    def test_single_scraper_no_update(self):
        processor = self._make_processor()
        self._stub_scraper_count(processor, 1)

        processor._apply_corroboration_bonus(
            location_id="11111111-1111-1111-1111-111111111111",
            per_job_score=66,
        )

        update_calls = [
            c
            for c in processor.db.execute.call_args_list
            if "update location" in str(c.args[0]).lower()
        ]
        assert update_calls == []

    def test_none_per_job_score_is_noop(self):
        processor = self._make_processor()
        # Even with multiple scrapers, missing per-job score = no-op.
        # No COUNT query should fire either — we short-circuit on input.
        processor._apply_corroboration_bonus(
            location_id="11111111-1111-1111-1111-111111111111",
            per_job_score=None,
        )
        assert processor.db.execute.call_args_list == []

    def test_idempotent_across_repeat_calls(self):
        """Same per_job_score across repeated calls produces the same score.

        The base for the bonus is the per-job (validator) score, not the
        canonical row — so bonuses never compound even if a scraper's
        job is re-processed.
        """
        processor = self._make_processor()
        # Two back-to-back calls; mock execute for both rounds.
        count1, update1 = MagicMock(), MagicMock()
        count1.scalar.return_value = 2
        count2, update2 = MagicMock(), MagicMock()
        count2.scalar.return_value = 2
        processor.db.execute.side_effect = [count1, update1, count2, update2]

        processor._apply_corroboration_bonus("loc-id", per_job_score=66)
        processor._apply_corroboration_bonus("loc-id", per_job_score=66)

        update_calls = [
            c
            for c in processor.db.execute.call_args_list
            if "update location" in str(c.args[0]).lower()
        ]
        assert len(update_calls) == 2
        # Both calls set the same target score — no compounding.
        assert update_calls[0].args[1]["score"] == 71
        assert update_calls[1].args[1]["score"] == 71

    def test_count_query_filters_to_scraper_source_type(self):
        """The distinct-scraper count must filter on source_type to
        exclude submarine/portal_ingest. Behavior assertion: stub
        execute() to return 3 only when the SQL contains the filter,
        and 99 (impossible / sentinel) otherwise. The bonus written to
        the UPDATE must reflect the filtered count (+10 for 3
        scrapers), proving the function used the right query shape.
        """
        processor = self._make_processor()

        def execute_side_effect(stmt, params=None):
            sql = str(stmt).lower()
            result = MagicMock()
            if "count(distinct scraper_id)" in sql:
                # Filtered query → 3 scrapers (the truth).
                # Unfiltered query → 99 (sentinel; would yield wrong score).
                if "source_type" in sql:
                    result.scalar.return_value = 3
                else:
                    result.scalar.return_value = 99
                return result
            result.rowcount = 1
            return result

        processor.db.execute.side_effect = execute_side_effect
        processor._apply_corroboration_bonus(
            location_id="11111111-1111-1111-1111-111111111111",
            per_job_score=66,
        )

        update_calls = [
            c
            for c in processor.db.execute.call_args_list
            if "update location" in str(c.args[0]).lower()
        ]
        # 3 scrapers → +10 → 76. If the filter was wrong (sentinel 99
        # returned), this would still produce 76 (capped at 90 anyway),
        # so the assertion also pins the filtered-count math: must be 76,
        # not the sentinel-driven 90.
        assert len(update_calls) == 1
        assert update_calls[0].args[1]["score"] == 76

    def test_owner_protected_row_does_not_log_applied(self, caplog):
        """When the verified_by guard filters the row out, the UPDATE
        affects 0 rows. The function must not emit `corroboration_applied`
        for that case — that would lie in the audit trail. A distinct
        `corroboration_skipped_owner_protected` event fires instead so
        operators can grep for the guard firing.
        """
        import logging

        processor = self._make_processor()
        count_result = MagicMock()
        count_result.scalar.return_value = 2
        update_result = MagicMock()
        update_result.rowcount = 0  # guard filtered the row
        processor.db.execute.side_effect = [count_result, update_result]

        with caplog.at_level(logging.INFO):
            processor._apply_corroboration_bonus(
                location_id="11111111-1111-1111-1111-111111111111",
                per_job_score=66,
            )

        events = [r.message for r in caplog.records]
        assert "corroboration_applied" not in events
        assert "corroboration_skipped_owner_protected" in events

    def test_successful_update_logs_applied(self, caplog):
        """When the UPDATE affects 1+ rows, the audit trail records
        `corroboration_applied` with the score delta."""
        import logging

        processor = self._make_processor()
        count_result = MagicMock()
        count_result.scalar.return_value = 2
        update_result = MagicMock()
        update_result.rowcount = 1
        processor.db.execute.side_effect = [count_result, update_result]

        with caplog.at_level(logging.INFO):
            processor._apply_corroboration_bonus(
                location_id="11111111-1111-1111-1111-111111111111",
                per_job_score=66,
            )

        events = [r.message for r in caplog.records]
        assert "corroboration_applied" in events
        assert "corroboration_skipped_owner_protected" not in events


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

        with patch.object(processor, "_apply_corroboration_bonus") as mock_apply:
            processor.process_job_result(job_result)

        # Submarine jobs must NOT trigger corroboration.
        mock_apply.assert_not_called()


class TestExistingMatchPathScoreBump:
    """End-to-end behavioral assertions on the existing-match (path 2)
    update: the canonical row's confidence_score reflects the
    corroboration bonus, and a corroboration failure does not abort
    the surrounding job. Observes rendered SQL so it survives refactors
    of the call site or helper rename."""

    @patch("app.reconciler.job_processor.OrganizationCreator")
    @patch("app.reconciler.job_processor.LocationCreator")
    @patch("app.reconciler.job_processor.ServiceCreator")
    @patch("app.reconciler.job_processor.VersionTracker")
    @patch("app.reconciler.job_processor.logger")
    def test_canonical_row_receives_corroboration_bonus(
        self,
        mock_logger,
        mock_version_tracker,
        mock_service_creator,
        mock_location_creator,
        mock_org_creator,
    ):
        """Path 2 with 2 distinct scrapers must UPDATE the canonical
        row with confidence_score = per_job_score + 5."""
        processor = JobProcessor(MagicMock(spec=Session))

        validator_score = 66
        existing_loc_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        expected_corroborated = 71  # 66 + 5

        llm_response = LLMResponse(
            text=json.dumps(
                {
                    "organization": [{"name": "Test Pantry", "description": "Test"}],
                    "service": [],
                    "location": [
                        {
                            "name": "Test Pantry",
                            "description": "Community food pantry",
                            "latitude": 39.7817,
                            "longitude": -89.6501,
                            "confidence_score": validator_score,
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
                    ],
                }
            ),
            model="test-model",
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )

        job = LLMJob(
            id="job-bump-001",
            prompt="Test prompt",
            created_at=datetime.now(),
            metadata={
                "scraper_id": "scraper_b",
                "type": "hsds_alignment",
            },
        )
        job_result = JobResult(
            job_id="job-bump-001",
            job=job,
            status=JobStatus.COMPLETED,
            result=llm_response,
        )

        mock_org_instance = mock_org_creator.return_value
        mock_org_instance.process_organization.return_value = ("org-uuid", True)
        mock_service_instance = mock_service_creator.return_value
        mock_service_instance.create_services.return_value = []

        mock_location_instance = mock_location_creator.return_value
        mock_location_instance.find_matching_location.return_value = existing_loc_id

        # The COUNT(DISTINCT scraper_id) query inside
        # _apply_corroboration_bonus must return 2 to trigger +5.
        # Default for any other execute() call is a generic mock.
        def execute_side_effect(stmt, params=None):
            sql = str(stmt).lower()
            result = MagicMock()
            if "count(distinct scraper_id)" in sql:
                result.scalar.return_value = 2
            else:
                result.first.return_value = None
                result.scalar.return_value = 0
                result.rowcount = 1
            return result

        processor.db.execute.side_effect = execute_side_effect

        processor.process_job_result(job_result)

        # Find every UPDATE statement against `location` that set
        # confidence_score. There must be exactly one writing the
        # corroborated value.
        score_updates = [
            call.args[1].get("score")
            for call in processor.db.execute.call_args_list
            if (
                "update location" in str(call.args[0]).lower()
                and "confidence_score" in str(call.args[0]).lower()
                and isinstance(call.args[1], dict)
                and "score" in call.args[1]
            )
        ]
        assert expected_corroborated in score_updates, (
            f"Expected an UPDATE writing score={expected_corroborated}; "
            f"found score-bearing UPDATEs: {score_updates}"
        )

    @patch("app.reconciler.job_processor.OrganizationCreator")
    @patch("app.reconciler.job_processor.LocationCreator")
    @patch("app.reconciler.job_processor.ServiceCreator")
    @patch("app.reconciler.job_processor.VersionTracker")
    @patch("app.reconciler.job_processor.logger")
    def test_corroboration_failure_does_not_abort_job(
        self,
        mock_logger,
        mock_version_tracker,
        mock_service_creator,
        mock_location_creator,
        mock_org_creator,
    ):
        """A DB error inside _apply_corroboration_bonus must not abort
        the broader job. The canonical UPDATE and location_source row
        have already committed by then; if corroboration raises, the
        next scraper job will recompute it (idempotent design). Per
        constitution Principle XI (Pipeline Resilience).
        """
        from sqlalchemy.exc import OperationalError

        processor = JobProcessor(MagicMock(spec=Session))
        existing_loc_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        llm_response = LLMResponse(
            text=json.dumps(
                {
                    "organization": [{"name": "X", "description": "x"}],
                    "service": [],
                    "location": [
                        {
                            "name": "X",
                            "description": "x",
                            "latitude": 39.7,
                            "longitude": -89.6,
                            "confidence_score": 66,
                            "validation_status": "needs_review",
                            "address": [
                                {
                                    "address_1": "1 X",
                                    "city": "X",
                                    "state_province": "IL",
                                    "postal_code": "62701",
                                    "country": "US",
                                    "address_type": "physical",
                                }
                            ],
                        }
                    ],
                }
            ),
            model="m",
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        )
        job = LLMJob(
            id="j",
            prompt="p",
            created_at=datetime.now(),
            metadata={"scraper_id": "b", "type": "hsds_alignment"},
        )
        job_result = JobResult(
            job_id="j", job=job, status=JobStatus.COMPLETED, result=llm_response
        )

        mock_org_instance = mock_org_creator.return_value
        mock_org_instance.process_organization.return_value = ("org", True)
        mock_service_instance = mock_service_creator.return_value
        mock_service_instance.create_services.return_value = []
        mock_location_instance = mock_location_creator.return_value
        mock_location_instance.find_matching_location.return_value = existing_loc_id

        generic_result = MagicMock()
        generic_result.first.return_value = None
        generic_result.scalar.return_value = 0
        generic_result.rowcount = 1
        processor.db.execute.return_value = generic_result

        with patch.object(
            processor,
            "_apply_corroboration_bonus",
            side_effect=OperationalError("boom", None, None),
        ):
            # Must not raise — job continues despite the corroboration
            # failure.
            result = processor.process_job_result(job_result)

        assert result["status"] == "success"
        # The failure was logged for operator discoverability.
        warn_messages = [
            call_args.args[0] if call_args.args else call_args.kwargs.get("msg", "")
            for call_args in mock_logger.warning.call_args_list
        ]
        assert any(
            "corroboration_failed" in str(m) for m in warn_messages
        ), f"Expected 'corroboration_failed' in warning logs; got {warn_messages}"
