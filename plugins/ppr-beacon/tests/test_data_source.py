"""Tests for database query quality gate enforcement.

Constitution Principle 4: Data Quality Gate.
These tests verify the quality gate SQL string and config defaults
without requiring a database connection.
"""

import pytest
from app.config import BeaconConfig


class TestQualityGateConfig:
    """Verify quality gate configuration."""

    def test_default_min_confidence_is_93(self):
        config = BeaconConfig()
        assert config.min_confidence == 93

    def test_dsn_format(self):
        config = BeaconConfig()
        assert config.dsn.startswith("postgresql://")


class TestQualityGateSQL:
    """Verify the quality gate SQL constant is correct."""

    def test_quality_gate_string(self):
        # Import the constant directly from the module text to avoid psycopg2 dep
        import ast
        from pathlib import Path

        source = (Path(__file__).parent.parent / "app" / "data_source.py").read_text()
        # Find the _QUALITY_GATE assignment
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "_QUALITY_GATE":
                        # Evaluate the constant string
                        gate = ast.literal_eval(node.value)
                        assert "verified_by" in gate
                        assert "confidence_score" in gate
                        assert "'admin'" in gate
                        assert "'source'" in gate
                        assert "%s" in gate
                        return
        pytest.fail("_QUALITY_GATE constant not found in data_source.py")

    def test_get_location_detail_has_quality_gate(self):
        """Verify get_location_detail SQL includes quality gate (C1 fix)."""
        from pathlib import Path

        source = (Path(__file__).parent.parent / "app" / "data_source.py").read_text()
        # Find the get_location_detail function and verify it has the quality gate
        in_func = False
        for line in source.split("\n"):
            if "def get_location_detail" in line:
                in_func = True
            if in_func and "_QUALITY_GATE" in line:
                return  # Found it
            if in_func and line.startswith("def ") and "get_location_detail" not in line:
                break
        pytest.fail("get_location_detail does not include _QUALITY_GATE")
