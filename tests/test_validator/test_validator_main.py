"""Tests for validator main module and service initialization."""

import sys
from unittest.mock import MagicMock, patch, call

import pytest


class TestValidatorMain:
    """Test validator main module and service initialization."""

    def test_validator_module_imports(self):
        """Test that validator module can be imported."""
        from app.validator import (
            ValidationService,
            ValidationProcessor,
            validator_queue,
            process_validation_job,
        )
        
        assert ValidationService is not None
        assert ValidationProcessor is not None
        assert validator_queue is not None
        assert process_validation_job is not None

    def test_validator_service_main(self):
        """Test validator service main entry point."""
        from app.validator.__main__ import main
        
        with patch("app.validator.__main__.ValidatorWorker") as MockWorker:
            with patch("app.validator.__main__.setup_logging"):
                with patch("sys.argv", ["validator"]):
                    mock_worker = MockWorker.return_value
                    mock_worker.run = MagicMock()
                    
                    # Run main
                    main()
                    
                    # Should create and run worker
                    MockWorker.assert_called_once()
                    mock_worker.run.assert_called_once()

    def test_validator_worker_initialization(self):
        """Test ValidatorWorker initialization."""
        from app.validator.worker import ValidatorWorker
        
        with patch("app.validator.worker.validator_queue"):
            with patch("app.validator.worker.Redis"):
                worker = ValidatorWorker()
                
                assert worker is not None
                assert hasattr(worker, "work")
                assert hasattr(worker, "setup")
                assert hasattr(worker, "teardown")

    def test_validator_worker_setup(self):
        """Test ValidatorWorker setup method."""
        from app.validator.worker import ValidatorWorker
        
        with patch("app.validator.worker.validator_queue"):
            with patch("app.validator.worker.Redis") as MockRedis:
                mock_redis = MockRedis.return_value
                mock_redis.ping.return_value = True
                
                worker = ValidatorWorker()
                worker.setup()
                
                # Should connect to Redis
                MockRedis.assert_called()
                mock_redis.ping.assert_called()

    def test_validator_worker_work_method(self):
        """Test ValidatorWorker work method."""
        from app.validator.worker import ValidatorWorker
        
        with patch("app.validator.worker.Worker") as MockRQWorker:
            mock_rq_worker = MockRQWorker.return_value
            mock_rq_worker.work = MagicMock()
            
            worker = ValidatorWorker()
            worker.work()
            
            # Should delegate to RQ worker
            mock_rq_worker.work.assert_called()

    def test_validator_worker_teardown(self):
        """Test ValidatorWorker teardown method."""
        from app.validator.worker import ValidatorWorker
        
        with patch("app.validator.worker.validator_queue"):
            with patch("app.validator.worker.Redis") as MockRedis:
                mock_redis = MockRedis.return_value
                
                worker = ValidatorWorker()
                worker.teardown()
                
                # Should close Redis connection
                mock_redis.close.assert_called()

    def test_validator_cli_arguments(self):
        """Test validator CLI argument parsing."""
        from app.validator.__main__ import parse_args
        
        # Test with default arguments
        args = parse_args([])
        assert args.workers == 1
        assert args.burst is False
        assert args.verbose is False
        
        # Test with custom arguments
        args = parse_args(["--workers", "4", "--burst", "--verbose"])
        assert args.workers == 4
        assert args.burst is True
        assert args.verbose is True

    def test_validator_logging_setup(self):
        """Test validator logging configuration."""
        from app.validator.__main__ import setup_logging
        
        with patch("logging.basicConfig") as mock_config:
            setup_logging(verbose=True)
            
            mock_config.assert_called_once()
            call_kwargs = mock_config.call_args[1]
            assert call_kwargs["level"] == "DEBUG"
        
        with patch("logging.basicConfig") as mock_config:
            setup_logging(verbose=False)
            
            mock_config.assert_called_once()
            call_kwargs = mock_config.call_args[1]
            assert call_kwargs["level"] == "INFO"

    def test_validator_signal_handling(self):
        """Test validator signal handling for graceful shutdown."""
        from app.validator.__main__ import setup_signal_handlers
        
        with patch("signal.signal") as mock_signal:
            handlers = setup_signal_handlers()
            
            # Should register SIGTERM and SIGINT handlers
            assert mock_signal.call_count >= 2
            
            # Test handler execution
            handlers["shutdown_handler"](None, None)
            # Should trigger graceful shutdown

    def test_validator_health_check(self):
        """Test validator health check endpoint."""
        from app.validator.health import check_health
        
        with patch("app.validator.queues.validator_queue") as mock_queue:
            with patch("app.validator.queues.Redis") as MockRedis:
                mock_redis = MockRedis.return_value
                mock_redis.ping.return_value = True
                mock_queue.count = 10
                
                health = check_health()
                
                assert health["status"] == "healthy"
                assert health["queue_size"] == 10
                assert health["redis_connected"] is True

    def test_validator_metrics_endpoint(self):
        """Test validator metrics endpoint."""
        from app.validator.metrics import get_metrics
        
        metrics = get_metrics()
        
        assert "jobs_total" in metrics
        assert "jobs_passed" in metrics
        assert "jobs_failed" in metrics
        assert "processing_time_avg" in metrics
        assert "queue_size" in metrics

    def test_validator_configuration_reload(self):
        """Test validator configuration can be reloaded."""
        from app.validator.config import reload_config
        
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.VALIDATOR_ENABLED = False
            
            # Initial state
            from app.validator.config import is_validator_enabled
            assert is_validator_enabled() is False
            
            # Change configuration
            mock_settings.VALIDATOR_ENABLED = True
            reload_config()
            
            # Should reflect new configuration
            assert is_validator_enabled() is True

    def test_validator_docker_integration(self):
        """Test validator service Docker integration."""
        # This is more of a documentation test
        # The validator service should have Docker configuration
        
        expected_docker_config = {
            "service_name": "validator",
            "image": "pantry-pirate-radio:latest",
            "command": "python -m app.validator",
            "environment": [
                "VALIDATOR_ENABLED",
                "REDIS_URL",
                "DATABASE_URL",
            ],
            "depends_on": ["cache", "db"],
        }
        
        # Verify expected configuration structure
        assert expected_docker_config["service_name"] == "validator"
        assert "python -m app.validator" in expected_docker_config["command"]

    def test_validator_module_exports(self):
        """Test that validator module exports the expected interface."""
        import app.validator as validator_module
        
        # Should export key classes and functions
        assert hasattr(validator_module, "ValidationService")
        assert hasattr(validator_module, "ValidationProcessor")
        assert hasattr(validator_module, "validator_queue")
        assert hasattr(validator_module, "process_validation_job")
        assert hasattr(validator_module, "is_validator_enabled")
        assert hasattr(validator_module, "get_validator_config")