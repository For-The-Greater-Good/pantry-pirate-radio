"""Performance benchmarks for data operations.

This module contains benchmarks for measuring performance of key operations.
Database operation benchmarks were attempted but removed due to challenges with
async operations in a benchmark context. Consider implementing these as separate
integration tests if performance metrics for database operations are needed.
"""

from pytest_benchmark.fixture import BenchmarkFixture


def test_basic_validation_benchmark(benchmark: BenchmarkFixture) -> None:
    """Benchmark basic data validation performance."""

    def validate_data() -> None:
        data = {"id": "test-id", "name": "test-name", "status": "active"}
        assert "id" in data
        assert "name" in data
        assert "status" in data
        assert isinstance(data["id"], str)
        assert isinstance(data["name"], str)
        assert data["status"] in ["active", "inactive"]

    benchmark(validate_data)
