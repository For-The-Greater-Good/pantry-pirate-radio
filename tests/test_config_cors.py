"""Tests for CORS configuration validation."""

from app.core.config import Settings


class TestCorsConfiguration:
    """Test CORS origins configuration."""

    def test_cors_origins_wildcard_replacement(self):
        """Test that wildcard CORS origins are replaced with specific origins."""
        # Create settings with wildcard CORS origins
        settings = Settings(cors_origins=["*"])

        # The validator should replace wildcard with specific origins
        expected_origins = [
            "http://localhost",
            "http://localhost:8000",
            "http://localhost:3000",
        ]

        assert settings.cors_origins == expected_origins

    def test_cors_origins_specific_unchanged(self):
        """Test that specific CORS origins are unchanged."""
        specific_origins = ["https://example.com", "https://app.example.com"]
        settings = Settings(cors_origins=specific_origins)

        # Should remain unchanged
        assert settings.cors_origins == specific_origins

    def test_cors_origins_empty_unchanged(self):
        """Test that empty CORS origins list is unchanged."""
        settings = Settings(cors_origins=[])
        assert settings.cors_origins == []

    def test_cors_origins_single_specific_unchanged(self):
        """Test that single specific origin is unchanged."""
        settings = Settings(cors_origins=["https://production.example.com"])
        assert settings.cors_origins == ["https://production.example.com"]
