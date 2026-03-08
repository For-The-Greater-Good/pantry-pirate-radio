"""Tests for Lambda handler and API-only app."""

import importlib
import os
import sys
from unittest.mock import MagicMock, patch

import pytest


class TestLambdaAppCreation:
    """Lambda app must create without Redis/LLM dependencies."""

    def test_app_creates_without_redis(self):
        """Lambda app should import and create without Redis."""
        with patch.dict(os.environ, {"AWS_LAMBDA_FUNCTION_NAME": "test-fn"}):
            from app.api.lambda_app import app

            assert app is not None
            assert app.title == "Pantry Pirate Radio"

    def test_health_endpoint_returns_healthy(self):
        """Health endpoint works in Lambda mode."""
        with patch.dict(os.environ, {"AWS_LAMBDA_FUNCTION_NAME": "test-fn"}):
            from app.api.lambda_app import app
            from starlette.testclient import TestClient

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/api/v1/health")
            assert response.status_code == 200
            assert response.json()["status"] == "healthy"

    def test_docs_endpoint_exists(self):
        """Docs endpoint should be available."""
        with patch.dict(os.environ, {"AWS_LAMBDA_FUNCTION_NAME": "test-fn"}):
            from app.api.lambda_app import app
            from starlette.testclient import TestClient

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/docs")
            assert response.status_code == 200

    def test_root_redirects_to_docs(self):
        """Root path should redirect to /api/docs."""
        with patch.dict(os.environ, {"AWS_LAMBDA_FUNCTION_NAME": "test-fn"}):
            from app.api.lambda_app import app
            from starlette.testclient import TestClient

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/", follow_redirects=False)
            assert response.status_code == 307
            assert "/api/docs" in response.headers["location"]

    def test_mangum_handler_callable(self):
        """Mangum handler must be callable for Lambda runtime."""
        # Mock mangum since it's not installed in the dev container
        mock_mangum = MagicMock()
        mock_mangum.return_value = MagicMock()
        with patch.dict(sys.modules, {"mangum": MagicMock(Mangum=mock_mangum)}):
            # Force reimport with mangum mocked
            if "app.api.lambda_handler" in sys.modules:
                del sys.modules["app.api.lambda_handler"]
            from app.api.lambda_handler import handler

            assert callable(handler)

    def test_api_metadata_endpoint(self):
        """API metadata endpoint should work."""
        with patch.dict(os.environ, {"AWS_LAMBDA_FUNCTION_NAME": "test-fn"}):
            from app.api.lambda_app import app
            from starlette.testclient import TestClient

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/api/v1/")
            assert response.status_code == 200
            data = response.json()
            assert data["version"] == "3.1.1"
            assert data["implementation"] == "Pantry Pirate Radio HSDS API"


class TestLambdaConditionalEndpoints:
    """Verify Docker-only endpoints are not registered in Lambda mode."""

    def test_redis_health_not_in_lambda_router(self):
        """Redis health endpoint should not exist when Lambda env var is set."""
        with patch.dict(os.environ, {"AWS_LAMBDA_FUNCTION_NAME": "test-fn"}):
            # Need to reload the actual module, not the router object
            import app.api.v1.router as router_module

            importlib.reload(sys.modules["app.api.v1.router"])
            # Re-import after reload
            from app.api.v1.router import router

            routes = [r.path for r in router.routes]
            assert "/health/redis" not in routes
            assert "/health/llm" not in routes
            assert "/metrics" not in routes
            # Data endpoints should still exist
            assert "/health" in routes
            assert "/health/db" in routes


class TestLambdaDatabaseConfig:
    """Lambda database pool sizing."""

    def test_lambda_uses_small_pool_size(self):
        """Lambda should use pool_size=1."""
        with patch.dict(os.environ, {"AWS_LAMBDA_FUNCTION_NAME": "test-fn"}):
            import app.core.db as db_mod

            # Reset module state
            db_mod.engine = None
            db_mod.async_session_factory = None

            # Patch create_async_engine to capture kwargs
            captured = {}

            def fake_engine(url, **kwargs):
                captured.update(kwargs)
                return MagicMock()

            with patch("app.core.db.create_async_engine", side_effect=fake_engine):
                with patch(
                    "app.core.db.os.getenv",
                    side_effect=lambda k, d=None: {
                        "TESTING": None,
                        "AWS_LAMBDA_FUNCTION_NAME": "test-fn",
                    }.get(k, d),
                ):
                    with patch(
                        "app.core.db.os.environ",
                        {
                            "AWS_LAMBDA_FUNCTION_NAME": "test-fn",
                        },
                    ):
                        db_mod._initialize_database()

            assert captured.get("pool_size") == 1
            assert captured.get("max_overflow") == 2
            assert captured.get("pool_pre_ping") is True
            assert captured.get("pool_recycle") == 300

            # Cleanup
            db_mod.engine = None
            db_mod.async_session_factory = None
