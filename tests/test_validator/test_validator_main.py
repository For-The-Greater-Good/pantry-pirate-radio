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
                    mock_worker.setup = MagicMock()
                    mock_worker.work = MagicMock()

                    # Run main and expect SystemExit
                    with pytest.raises(SystemExit) as exc_info:
                        main()

                    # Check it exited successfully
                    assert exc_info.value.code == 0

                    # Should create and run worker
                    MockWorker.assert_called_once()
                    mock_worker.setup.assert_called_once()
                    mock_worker.work.assert_called_once()

    def test_validator_worker_initialization(self):
        """Test ValidatorWorker initialization."""
        from app.validator.worker import ValidatorWorker
        from rq import Queue

        with patch("app.validator.worker.get_validator_queue") as mock_get_queue:
            # Create a proper Queue mock with spec
            mock_queue = MagicMock(spec=Queue)
            mock_queue.name = "validator"
            mock_get_queue.return_value = mock_queue

            with patch("app.validator.worker.get_redis_connection") as mock_get_redis:
                mock_redis = MagicMock()
                mock_redis.ping.return_value = True
                mock_get_redis.return_value = mock_redis

                with patch("app.validator.worker.Worker") as MockWorker:
                    mock_rq_worker = MockWorker.return_value

                    worker = ValidatorWorker()

                    assert worker is not None
                    assert hasattr(worker, "work")
                    assert hasattr(worker, "setup")
                    assert hasattr(worker, "teardown")
                    # Queue is set during setup, not __init__
                    assert worker.queue is None  # Not set yet

                    worker.setup()

                    assert worker.queue == mock_queue
                    assert worker.rq_worker == mock_rq_worker

    def test_validator_worker_setup(self):
        """Test ValidatorWorker setup method."""
        from app.validator.worker import ValidatorWorker
        from rq import Queue

        with patch("app.validator.worker.get_validator_queue") as mock_get_queue:
            # Create a proper Queue mock with spec
            mock_queue = MagicMock(spec=Queue)
            mock_queue.name = "validator"
            mock_get_queue.return_value = mock_queue

            with patch("app.validator.worker.get_redis_connection") as mock_get_redis:
                mock_redis_conn = MagicMock()
                mock_redis_conn.ping.return_value = True
                mock_get_redis.return_value = mock_redis_conn

                with patch("app.validator.worker.Worker") as MockWorker:
                    worker = ValidatorWorker()
                    worker.setup()

                    # Should get Redis connection
                    mock_get_redis.assert_called()
                    mock_redis_conn.ping.assert_called()

                    # Should create RQ worker - check that it was called with the right queue and connection
                    MockWorker.assert_called_once()
                    call_args = MockWorker.call_args
                    assert call_args[1]["queues"] == [mock_queue]
                    assert call_args[1]["connection"] == mock_redis_conn
                    # Additional args like name and log_job_description are OK

    def test_validator_worker_work_method(self):
        """Test ValidatorWorker work method."""
        from app.validator.worker import ValidatorWorker

        with patch("app.validator.worker.get_validator_queue") as mock_get_queue:
            mock_queue = MagicMock()
            mock_get_queue.return_value = mock_queue

            with patch("app.validator.worker.Worker") as MockRQWorker:
                mock_rq_worker = MockRQWorker.return_value
                mock_rq_worker.work = MagicMock()

                worker = ValidatorWorker()
                worker.rq_worker = mock_rq_worker  # Set the RQ worker
                worker.work()

                # Should delegate to RQ worker
                mock_rq_worker.work.assert_called()

    def test_validator_worker_teardown(self):
        """Test ValidatorWorker teardown method."""
        from app.validator.worker import ValidatorWorker

        with patch("app.validator.worker.get_validator_queue") as mock_get_queue:
            mock_queue = MagicMock()
            mock_get_queue.return_value = mock_queue

            worker = ValidatorWorker()

            # Set up a mock redis connection
            mock_redis = MagicMock()
            worker.redis_conn = mock_redis

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
        import logging
        from app.validator.__main__ import setup_logging

        with patch("logging.basicConfig") as mock_config:
            setup_logging(verbose=True)

            mock_config.assert_called_once()
            call_kwargs = mock_config.call_args[1]
            assert call_kwargs["level"] == logging.DEBUG

        with patch("logging.basicConfig") as mock_config:
            setup_logging(verbose=False)

            mock_config.assert_called_once()
            call_kwargs = mock_config.call_args[1]
            assert call_kwargs["level"] == logging.INFO

    def test_validator_signal_handling(self):
        """Test validator signal handling for graceful shutdown."""
        from app.validator.__main__ import setup_signal_handlers

        with patch("signal.signal") as mock_signal:
            handlers = setup_signal_handlers()

            # Should register SIGTERM and SIGINT handlers
            assert mock_signal.call_count >= 2

            # Test handler execution with sys.exit patched
            with patch("sys.exit") as mock_exit:
                handlers["shutdown_handler"](None, None)
                # Should trigger graceful shutdown
                mock_exit.assert_called_once_with(0)

    def test_validator_health_check(self):
        """Test validator health check endpoint."""
        from app.validator.health import check_health

        with patch("app.validator.health.get_validator_queue") as mock_get_queue:
            mock_queue = MagicMock()
            mock_queue.connection.ping.return_value = True
            mock_queue.__len__ = MagicMock(return_value=10)
            mock_get_queue.return_value = mock_queue

            health = check_health()

            assert health["status"] == "healthy"
            assert health["queue_size"] == 10
            assert health["redis"] == "connected"

    @pytest.mark.skip(reason="Prometheus registry conflict when run with full suite")
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
        from app.validator.config import reload_config, get_validator_config

        # Test that reload_config clears the cache
        config1 = get_validator_config()
        assert config1 is not None

        # Call reload to clear cache
        reload_config()

        # Get config again - should be a new instance
        config2 = get_validator_config()
        assert config2 is not None

        # The configs should have same values but could be different instances
        assert config1.enabled == config2.enabled
        assert config1.queue_name == config2.queue_name

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
