"""Tests for reconciler handling of rejected locations."""

import json
import uuid
import pytest
from unittest.mock import Mock, patch, call
from app.reconciler.job_processor import JobProcessor
from app.llm.queue.models import JobResult, JobStatus
from app.llm.queue.job import LLMJob
from app.llm.providers.types import LLMResponse


class TestReconcilerRejectionHandling:
    """Test reconciler properly handles rejected locations."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        db = Mock()
        db.execute = Mock()
        db.commit = Mock()
        db.rollback = Mock()
        db.scalar = Mock()
        return db

    @pytest.fixture
    def job_result_with_rejected_locations(self):
        """Create job result with both accepted and rejected locations."""
        job = Mock(spec=LLMJob)
        job.id = "test-job-123"
        job.type = "validator"
        job.metadata = {"scraper_id": "test-scraper"}  # Add missing metadata attribute
        job.data = {
            "organization": {
                "name": "Test Organization",
                "confidence_score": 50,
                "validation_status": "needs_review",
            },
            "locations": [
                {
                    "name": "Good Location",
                    "latitude": 40.7128,
                    "longitude": -74.0060,
                    "confidence_score": 85,
                    "validation_status": "verified",
                    "validation_notes": {"source": "arcgis"},
                },
                {
                    "name": "Rejected Location 1",
                    "latitude": 0.0,
                    "longitude": 0.0,
                    "confidence_score": 5,
                    "validation_status": "rejected",
                    "validation_notes": {"rejection_reason": "Invalid 0,0 coordinates"},
                },
                {
                    "name": "Borderline Location",
                    "latitude": 40.7,
                    "longitude": -74.0,
                    "confidence_score": 10,  # Exactly at threshold
                    "validation_status": "needs_review",
                    "validation_notes": {},
                },
                {
                    "name": "Rejected Location 2",
                    "latitude": None,
                    "longitude": None,
                    "confidence_score": 0,
                    "validation_status": "rejected",
                    "validation_notes": {
                        "rejection_reason": "Missing coordinates after enrichment"
                    },
                },
            ],
            "services": [],
        }

        job_result = Mock(spec=JobResult)
        job_result.job_id = "test-job-123"
        job_result.job = job
        job_result.status = JobStatus.COMPLETED

        # Convert to HSDS format for result.text
        hsds_data = {
            "organization": [job.data["organization"]],
            "location": job.data["locations"],
            "service": job.data["services"],
        }

        result = Mock(spec=LLMResponse)
        result.text = json.dumps(hsds_data)
        job_result.result = result

        return job_result

    def test_reconciler_skips_rejected_status_locations(
        self, mock_db, job_result_with_rejected_locations
    ):
        """Test reconciler skips locations with validation_status='rejected'."""
        processor = JobProcessor(db=mock_db)

        # Mock the creator classes
        with patch(
            "app.reconciler.job_processor.OrganizationCreator"
        ) as MockOrgCreator, patch(
            "app.reconciler.job_processor.LocationCreator"
        ) as MockLocCreator, patch(
            "app.reconciler.job_processor.ServiceCreator"
        ) as MockSvcCreator, patch(
            "app.reconciler.job_processor.VersionTracker"
        ) as MockVersionTracker:

            # Setup mocks
            mock_org_creator = Mock()
            MockOrgCreator.return_value = mock_org_creator
            mock_org_creator.process_organization.return_value = (
                str(uuid.uuid4()),
                False,
            )

            mock_loc_creator = Mock()
            MockLocCreator.return_value = mock_loc_creator
            # Return a new UUID string for each call (accept any arguments)
            mock_loc_creator.create_location.side_effect = lambda *args, **kwargs: str(
                uuid.uuid4()
            )
            # Mock find_matching_location to return None (no match found)
            mock_loc_creator.find_matching_location.return_value = None

            mock_svc_creator = Mock()
            MockSvcCreator.return_value = mock_svc_creator

            mock_version_tracker = Mock()
            MockVersionTracker.return_value = mock_version_tracker

            # Process the job
            result = processor.process_job_result(job_result_with_rejected_locations)

            # Verify location creator was NOT called for rejected locations
            # Should only be called for "Good Location" and "Borderline Location" (score=10, not rejected)
            assert mock_loc_creator.create_location.call_count == 2

            # Check the locations that were created
            created_location_names = []
            for call_obj in mock_loc_creator.create_location.call_args_list:
                # The first argument is the location name
                if call_obj.args and len(call_obj.args) > 0:
                    created_location_names.append(call_obj.args[0])

            # Should NOT include rejected locations
            assert "Good Location" in created_location_names
            assert "Borderline Location" in created_location_names
            assert "Rejected Location 1" not in created_location_names
            assert "Rejected Location 2" not in created_location_names

    def test_reconciler_skips_low_confidence_score_locations(self, mock_db):
        """Test reconciler skips locations marked as rejected by validator."""
        processor = JobProcessor(db=mock_db)

        # Create job with locations that have been marked by validator
        job = Mock(spec=LLMJob)
        job.metadata = {"scraper_id": "test-scraper"}  # Add missing metadata attribute
        job.data = {
            "locations": [
                {
                    "name": "Score 9 Location",
                    "latitude": 40.7,
                    "longitude": -74.0,
                    "confidence_score": 9,
                    "validation_status": "rejected",  # Validator marked as rejected
                },
                {
                    "name": "Score 10 Location",
                    "latitude": 40.7,
                    "longitude": -74.0,
                    "confidence_score": 10,
                    "validation_status": "needs_review",  # Not rejected by validator
                },
                {
                    "name": "Score 11 Location",
                    "latitude": 40.7,
                    "longitude": -74.0,
                    "confidence_score": 11,
                    "validation_status": "verified",  # Not rejected by validator
                },
            ]
        }

        job_result = Mock(spec=JobResult)
        job_result.job_id = "test-job"
        job_result.job = job
        job_result.status = JobStatus.COMPLETED

        # Convert to HSDS format for result.text
        hsds_data = {
            "organization": [],
            "location": job.data["locations"],
            "service": [],
        }
        result = Mock(spec=LLMResponse)
        result.text = json.dumps(hsds_data)
        job_result.result = result

        with patch(
            "app.reconciler.job_processor.OrganizationCreator"
        ) as MockOrgCreator, patch(
            "app.reconciler.job_processor.LocationCreator"
        ) as MockLocCreator, patch(
            "app.reconciler.job_processor.ServiceCreator"
        ) as MockSvcCreator, patch(
            "app.reconciler.job_processor.VersionTracker"
        ) as MockVersionTracker:

            # Setup organization creator mock
            mock_org_creator = Mock()
            MockOrgCreator.return_value = mock_org_creator
            mock_org_creator.process_organization.return_value = (
                str(uuid.uuid4()),
                False,
            )

            # Setup location creator mock
            mock_loc_creator = Mock()
            MockLocCreator.return_value = mock_loc_creator
            # Return a new UUID string for each call (accept any arguments)
            mock_loc_creator.create_location.side_effect = lambda *args, **kwargs: str(
                uuid.uuid4()
            )
            # Mock find_matching_location to return None (no match found)
            mock_loc_creator.find_matching_location.return_value = None

            # Setup service creator mock
            mock_svc_creator = Mock()
            MockSvcCreator.return_value = mock_svc_creator

            # Setup version tracker mock
            mock_version_tracker = Mock()
            MockVersionTracker.return_value = mock_version_tracker

            # Process the job
            result = processor.process_job_result(job_result)

            # Should skip only the location marked as rejected
            assert mock_loc_creator.create_location.call_count == 2

            created_names = [
                (
                    call_args.args[0]
                    if call_args.args and len(call_args.args) > 0
                    else None
                )
                for call_args in mock_loc_creator.create_location.call_args_list
            ]

            assert "Score 9 Location" not in created_names  # Rejected
            assert (
                "Score 10 Location" in created_names
                or "Score 11 Location" in created_names
            )

    def test_rejection_is_logged_with_details(
        self, mock_db, job_result_with_rejected_locations, caplog
    ):
        """Test rejected locations are logged with details."""
        processor = JobProcessor(db=mock_db)

        with patch(
            "app.reconciler.job_processor.OrganizationCreator"
        ) as MockOrgCreator, patch(
            "app.reconciler.job_processor.LocationCreator"
        ) as MockLocCreator, patch(
            "app.reconciler.job_processor.ServiceCreator"
        ) as MockSvcCreator, patch(
            "app.reconciler.job_processor.VersionTracker"
        ) as MockVersionTracker:

            # Setup mocks to return proper values
            mock_org_creator = Mock()
            MockOrgCreator.return_value = mock_org_creator
            mock_org_creator.process_organization.return_value = (
                str(uuid.uuid4()),
                False,
            )

            mock_loc_creator = Mock()
            MockLocCreator.return_value = mock_loc_creator
            mock_loc_creator.create_location.side_effect = lambda *args, **kwargs: str(
                uuid.uuid4()
            )
            mock_loc_creator.find_matching_location.return_value = None

            MockSvcCreator.return_value = Mock()
            MockVersionTracker.return_value = Mock()

            # Process with debug logging
            import logging

            with caplog.at_level(logging.INFO):
                processor.process_job_result(job_result_with_rejected_locations)

            # Check that rejections were logged
            rejection_logs = [
                r for r in caplog.records if "rejected" in r.message.lower()
            ]
            assert len(rejection_logs) >= 2  # At least 2 rejected locations

            # Check log contains location names
            log_messages = " ".join([r.message for r in rejection_logs])
            assert (
                "Rejected Location 1" in log_messages
                or "confidence score 5" in log_messages
            )
            assert (
                "Rejected Location 2" in log_messages
                or "confidence score 0" in log_messages
            )

    def test_rejected_locations_not_in_database(
        self, mock_db, job_result_with_rejected_locations
    ):
        """Test rejected locations are not created in database."""
        processor = JobProcessor(db=mock_db)

        # Track database operations
        created_locations = []

        def mock_create_location(*args, **kwargs):
            # First arg is the name
            if args:
                created_locations.append({"name": args[0]})
            elif kwargs:
                created_locations.append(kwargs)
            return str(uuid.uuid4())

        with patch(
            "app.reconciler.job_processor.OrganizationCreator"
        ) as MockOrgCreator, patch(
            "app.reconciler.job_processor.LocationCreator"
        ) as MockLocCreator, patch(
            "app.reconciler.job_processor.ServiceCreator"
        ) as MockSvcCreator, patch(
            "app.reconciler.job_processor.VersionTracker"
        ) as MockVersionTracker:

            # Setup organization creator mock
            mock_org_creator = Mock()
            MockOrgCreator.return_value = mock_org_creator
            mock_org_creator.process_organization.return_value = (
                str(uuid.uuid4()),
                False,
            )

            mock_loc_creator = Mock()
            MockLocCreator.return_value = mock_loc_creator
            mock_loc_creator.create_location.side_effect = mock_create_location
            mock_loc_creator.find_matching_location.return_value = None

            # Setup other mocks
            MockSvcCreator.return_value = Mock()
            MockVersionTracker.return_value = Mock()

            # Process the job
            processor.process_job_result(job_result_with_rejected_locations)

            # Verify no rejected locations were created
            created_names = [loc.get("name") for loc in created_locations]
            assert "Rejected Location 1" not in created_names
            assert "Rejected Location 2" not in created_names

            # Verify only non-rejected locations were created
            assert len(created_locations) == 2  # Good and Borderline locations only

    def test_rejection_with_custom_threshold(self, mock_db):
        """Test reconciler only respects validation_status, not thresholds."""
        processor = JobProcessor(db=mock_db)

        # Reconciler doesn't use thresholds - only validation_status matters
        job = Mock(spec=LLMJob)
        job.metadata = {"scraper_id": "test-scraper"}  # Add missing metadata attribute
        job.data = {
            "locations": [
                {
                    "name": "Low Score but Not Rejected",
                    "latitude": 40.7,
                    "longitude": -74.0,
                    "confidence_score": 5,  # Very low score
                    "validation_status": "needs_review",  # But not rejected
                },
                {
                    "name": "High Score but Rejected",
                    "latitude": 40.7,
                    "longitude": -74.0,
                    "confidence_score": 95,  # Very high score
                    "validation_status": "rejected",  # But marked as rejected
                },
            ]
        }

        job_result = Mock(spec=JobResult)
        job_result.job_id = "test-job"
        job_result.job = job
        job_result.status = JobStatus.COMPLETED

        # Convert to HSDS format for result.text
        hsds_data = {
            "organization": [],
            "location": job.data["locations"],
            "service": [],
        }
        result = Mock(spec=LLMResponse)
        result.text = json.dumps(hsds_data)
        job_result.result = result

        with patch(
            "app.reconciler.job_processor.OrganizationCreator"
        ) as MockOrgCreator, patch(
            "app.reconciler.job_processor.LocationCreator"
        ) as MockLocCreator, patch(
            "app.reconciler.job_processor.ServiceCreator"
        ) as MockSvcCreator, patch(
            "app.reconciler.job_processor.VersionTracker"
        ) as MockVersionTracker:

            # Setup organization creator mock
            mock_org_creator = Mock()
            MockOrgCreator.return_value = mock_org_creator
            mock_org_creator.process_organization.return_value = (
                str(uuid.uuid4()),
                False,
            )

            # Setup location creator mock
            mock_loc_creator = Mock()
            MockLocCreator.return_value = mock_loc_creator
            # Return a new UUID string for each call (accept any arguments)
            mock_loc_creator.create_location.side_effect = lambda *args, **kwargs: str(
                uuid.uuid4()
            )
            # Mock find_matching_location to return None (no match found)
            mock_loc_creator.find_matching_location.return_value = None

            # Setup service creator mock
            mock_svc_creator = Mock()
            MockSvcCreator.return_value = mock_svc_creator

            # Setup version tracker mock
            mock_version_tracker = Mock()
            MockVersionTracker.return_value = mock_version_tracker

            # Process the job
            processor.process_job_result(job_result)

            # Only validation_status matters - so low score not rejected should be created
            assert mock_loc_creator.create_location.call_count == 1

            # Only the non-rejected location should be created (despite low score)
            created_names = [
                (
                    call_args.args[0]
                    if call_args.args and len(call_args.args) > 0
                    else None
                )
                for call_args in mock_loc_creator.create_location.call_args_list
            ]
            assert "Low Score but Not Rejected" in created_names
            assert "High Score but Rejected" not in created_names


class TestLocationCreatorRejection:
    """Test LocationCreator handles rejection properly."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        db = Mock()
        db.execute = Mock()
        db.commit = Mock()
        db.scalar = Mock()
        return db

    def test_location_creator_early_return_for_rejected(self, mock_db):
        """Test LocationCreator returns early for rejected locations."""
        from app.reconciler.location_creator import LocationCreator

        creator = LocationCreator(db=mock_db)

        # Try to create a rejected location
        with patch.object(creator.logger, "info") as mock_log:
            result = creator.create_location(
                name="Rejected Location",
                description="Test location",
                latitude=0.0,
                longitude=0.0,
                metadata={},
                confidence_score=5,
                validation_status="rejected",
                validation_notes={"rejection_reason": "Test data detected"},
            )

            # Should return None for rejected locations
            assert result is None

            # Check that it logged the skip
            mock_log.assert_called_with("Skipping rejected location: Rejected Location")
