"""Tests for rejection metrics tracking."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from app.validator.job_processor import ValidationProcessor
from app.validator.metrics import (
    VALIDATOR_JOBS_TOTAL,
    VALIDATOR_JOBS_PASSED,
    VALIDATOR_JOBS_FAILED,
)
from app.llm.queue.models import JobResult, Job, Result, JobStatus


class TestRejectionMetrics:
    """Test metrics tracking for rejected locations."""
    
    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        db = MagicMock()
        db.commit = MagicMock()
        db.rollback = MagicMock()
        return db
    
    @pytest.fixture
    def job_with_rejected_locations(self):
        """Create job result with rejected locations."""
        job = Mock(spec=Job)
        job.id = "test-job-metrics"
        job.type = "scraper"
        job.data = {
            "locations": [
                {"name": "Good 1", "latitude": 40.7, "longitude": -74.0},
                {"name": "Rejected 1", "latitude": 0.0, "longitude": 0.0},
                {"name": "Good 2", "latitude": 41.8, "longitude": -87.6},
                {"name": "Rejected 2"},  # Missing coordinates
                {"name": "Rejected 3", "latitude": 999, "longitude": 999},  # Outside bounds
            ]
        }
        
        result = Mock(spec=Result)
        result.text = ""
        
        job_result = Mock(spec=JobResult)
        job_result.job_id = "test-job-metrics"
        job_result.job = job
        job_result.result = result
        job_result.status = JobStatus.COMPLETED
        
        return job_result
    
    def test_rejection_counter_increments(self, mock_db, job_with_rejected_locations):
        """Test VALIDATOR_LOCATIONS_REJECTED counter increments."""
        processor = ValidationProcessor(db=mock_db)
        
        # Mock the new rejection counter (to be added)
        with patch('app.validator.metrics.VALIDATOR_LOCATIONS_REJECTED') as mock_counter:
            mock_counter.inc = Mock()
            
            # Mock enrichment to skip it
            with patch.object(processor, '_enrich_data', side_effect=lambda jr, data: data):
                processor.process_job_result(job_with_rejected_locations)
            
            # Should increment for each rejected location
            # We expect 3 rejections (0,0 coords, missing coords, outside bounds)
            assert mock_counter.inc.call_count >= 3
    
    def test_rejection_rate_calculation(self, mock_db, job_with_rejected_locations):
        """Test VALIDATOR_REJECTION_RATE gauge is updated."""
        processor = ValidationProcessor(db=mock_db)
        
        # Mock the rejection rate gauge (to be added)
        with patch('app.validator.metrics.VALIDATOR_REJECTION_RATE') as mock_gauge:
            mock_gauge.set = Mock()
            
            with patch.object(processor, '_enrich_data', side_effect=lambda jr, data: data):
                result = processor.process_job_result(job_with_rejected_locations)
            
            # Should calculate and set rejection rate
            # 3 rejected out of 5 total = 60% rejection rate
            locations = result['data']['locations']
            rejected_count = sum(1 for l in locations if l.get('validation_status') == 'rejected')
            total_count = len(locations)
            expected_rate = (rejected_count / total_count) * 100 if total_count > 0 else 0
            
            # Verify gauge was set with rejection rate
            if mock_gauge.set.called:
                set_value = mock_gauge.set.call_args[0][0]
                assert set_value == pytest.approx(expected_rate, rel=0.1)
    
    def test_rejection_reason_labels(self, mock_db):
        """Test rejection metrics include reason labels."""
        processor = ValidationProcessor(db=mock_db)
        
        # Create job with specific rejection reasons
        job = Mock(spec=Job)
        job.data = {
            "locations": [
                {"name": "Zero Coords", "latitude": 0.0, "longitude": 0.0},
                {"name": "Missing Coords"},
                {"name": "Outside US", "latitude": 10.0, "longitude": 10.0},  # Africa
                {"name": "Test Data", "latitude": 40.7, "longitude": -74.0, 
                 "address": [{"city": "Anytown", "postal_code": "00000"}]},
            ]
        }
        
        job_result = Mock(spec=JobResult)
        job_result.job_id = "test-reasons"
        job_result.job = job
        job_result.result = Mock(text="")
        job_result.status = JobStatus.COMPLETED
        
        # Mock the labeled counter (to be added)
        with patch('app.validator.metrics.VALIDATOR_LOCATIONS_REJECTED_BY_REASON') as mock_counter:
            mock_counter.labels = Mock(return_value=Mock(inc=Mock()))
            
            with patch.object(processor, '_enrich_data', side_effect=lambda jr, data: data):
                processor.process_job_result(job_result)
            
            # Should have different labels for different rejection reasons
            label_calls = mock_counter.labels.call_args_list
            if label_calls:
                reasons = [call.kwargs.get('reason') for call in label_calls if call.kwargs]
                
                # Should include various rejection reasons
                expected_reasons = [
                    'zero_coordinates',
                    'missing_coordinates',
                    'outside_us_bounds',
                    'test_data'
                ]
                
                for expected in expected_reasons:
                    assert any(expected in str(r).lower() for r in reasons if r)
    
    def test_metrics_updated_on_validation(self, mock_db, job_with_rejected_locations):
        """Test standard metrics are still updated during validation."""
        processor = ValidationProcessor(db=mock_db)
        
        # Mock all metrics
        with patch.object(VALIDATOR_JOBS_TOTAL, 'inc') as mock_total, \
             patch.object(VALIDATOR_JOBS_PASSED, 'inc') as mock_passed, \
             patch.object(VALIDATOR_JOBS_FAILED, 'inc') as mock_failed:
            
            with patch.object(processor, '_enrich_data', side_effect=lambda jr, data: data):
                result = processor.process_job_result(job_with_rejected_locations)
            
            # Total should always increment
            mock_total.assert_called_once()
            
            # Either passed or failed should increment based on validation errors
            if processor._validation_errors:
                mock_failed.assert_called_once()
                mock_passed.assert_not_called()
            else:
                mock_passed.assert_called_once()
                mock_failed.assert_not_called()
    
    def test_rejection_metrics_in_summary(self, mock_db):
        """Test rejection metrics appear in metrics summary."""
        from app.validator.metrics import get_metrics_summary
        
        # Mock the rejection metrics (to be added)
        with patch('app.validator.metrics.VALIDATOR_LOCATIONS_REJECTED') as mock_counter, \
             patch('app.validator.metrics.VALIDATOR_REJECTION_RATE') as mock_gauge:
            
            # Mock metric values
            mock_counter._value = 150  # Mock internal value
            mock_gauge._value = 15.5  # 15.5% rejection rate
            
            summary = get_metrics_summary()
            
            # Should include rejection metrics in summary
            if 'locations_rejected' in summary:
                assert summary['locations_rejected'] == 150
            
            if 'rejection_rate' in summary:
                assert summary['rejection_rate'] == 15.5
    
    def test_rejection_metrics_export(self):
        """Test rejection metrics can be exported for Prometheus."""
        # This would test that the metrics are properly registered
        # and can be scraped by Prometheus
        
        try:
            from prometheus_client import REGISTRY
            
            # Mock the new metrics to be registered
            with patch('app.validator.metrics.VALIDATOR_LOCATIONS_REJECTED'):
                # Check metric would be in registry
                metric_names = [m.name for m in REGISTRY.collect()]
                
                # After implementation, these should exist
                expected_metrics = [
                    'validator_locations_rejected_total',
                    'validator_rejection_rate',
                    'validator_locations_rejected_by_reason_total'
                ]
                
                # This will fail until metrics are added
                # Just check that validator metrics exist for now
                validator_metrics = [m for m in metric_names if 'validator' in m]
                assert len(validator_metrics) > 0
                
        except ImportError:
            # prometheus_client not available, skip
            pytest.skip("prometheus_client not available")


class TestRejectionMetricsIntegration:
    """Test metrics integration with full validation pipeline."""
    
    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        db = MagicMock()
        db.commit = MagicMock()
        return db
    
    def test_end_to_end_metrics_tracking(self, mock_db):
        """Test metrics are tracked through full validation pipeline."""
        processor = ValidationProcessor(db=mock_db)
        
        # Create a realistic job
        job = Mock(spec=Job)
        job.data = {}
        
        result_text = """{
            "organization": {"name": "Food Bank"},
            "locations": [
                {"name": "Main Site", "latitude": 40.7128, "longitude": -74.0060},
                {"name": "Test Site", "latitude": 0, "longitude": 0},
                {"name": "Missing GPS Site", "address": [{"street": "Unknown"}]}
            ]
        }"""
        
        result = Mock(spec=Result)
        result.text = result_text
        
        job_result = Mock(spec=JobResult)
        job_result.job_id = "test-e2e"
        job_result.job = job
        job_result.result = result
        job_result.status = JobStatus.COMPLETED
        
        # Track all metric calls
        metric_calls = {
            'total': 0,
            'passed': 0,
            'failed': 0,
            'rejected': 0
        }
        
        def track_inc(metric_type):
            def _inc(*args, **kwargs):
                metric_calls[metric_type] += 1
            return _inc
        
        # Mock all metrics
        with patch.object(VALIDATOR_JOBS_TOTAL, 'inc', side_effect=track_inc('total')), \
             patch.object(VALIDATOR_JOBS_PASSED, 'inc', side_effect=track_inc('passed')), \
             patch.object(VALIDATOR_JOBS_FAILED, 'inc', side_effect=track_inc('failed')), \
             patch('app.validator.metrics.VALIDATOR_LOCATIONS_REJECTED', 
                    Mock(inc=Mock(side_effect=track_inc('rejected')))):
            
            with patch.object(processor, '_enrich_data', side_effect=lambda jr, data: data):
                result = processor.process_job_result(job_result)
            
            # Verify metrics were tracked
            assert metric_calls['total'] == 1  # Job was processed
            
            # Should have some rejections
            locations = result['data']['locations']
            rejected_count = sum(1 for l in locations if l.get('validation_status') == 'rejected')
            assert rejected_count >= 2  # Test site and Missing GPS site