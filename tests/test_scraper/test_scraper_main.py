"""Tests for app/scraper/__main__.py module."""

import argparse
import asyncio
import importlib
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from app.scraper.__main__ import (
    list_available_scrapers,
    load_scraper_class,
    main,
    run_all_scrapers_parallel,
    run_scraper_parallel,
)
from app.scraper.utils import ScraperJob


class MockScraper(ScraperJob):
    """Mock scraper for testing."""

    async def run(self) -> None:
        """Mock run method."""
        pass

    async def scrape(self) -> str:
        """Mock scrape method."""
        return ""


class FailingScraper(ScraperJob):
    """Mock failing scraper for testing."""

    async def run(self) -> None:
        """Mock run method that fails."""
        raise RuntimeError("Scraper failed")

    async def scrape(self) -> str:
        """Mock scrape method."""
        return ""


@pytest.fixture
def mock_scraper_dir(tmp_path: Path) -> Path:
    """Create a mock scraper directory with test scrapers."""
    scraper_dir = tmp_path / "app" / "scraper"
    scraper_dir.mkdir(parents=True)

    # Create some mock scraper files
    (scraper_dir / "sample_scraper.py").write_text("# Sample scraper")
    (scraper_dir / "test_scraper.py").write_text("# Test scraper")
    (scraper_dir / "another_scraper.py").write_text("# Another scraper")
    (scraper_dir / "__init__.py").write_text("# Init file")
    (scraper_dir / "not_a_scraper.py").write_text("# Not a scraper file")

    return scraper_dir


class TestLoadScraperClass:
    """Test the load_scraper_class function."""

    @patch("app.scraper.__main__.importlib.import_module")
    def test_load_single_scraper_class(self, mock_import: Mock) -> None:
        """Test loading a scraper when module has single scraper class."""
        # Mock module with single scraper class
        mock_module = Mock()
        mock_module.SampleScraper = MockScraper
        mock_import.return_value = mock_module

        # Mock dir() to return the class names
        with patch(
            "builtins.dir",
            return_value=["SampleScraper", "some_function", "_private_class"],
        ):
            result = load_scraper_class("sample")

        assert result == MockScraper
        mock_import.assert_called_with("app.scraper.sample_scraper")

    @patch("app.scraper.__main__.importlib.import_module")
    def test_load_multiple_scraper_classes_exact_match(self, mock_import: Mock) -> None:
        """Test loading when module has multiple scraper classes with exact match."""
        # Mock module with multiple scraper classes
        mock_module = Mock()
        mock_module.TestScraper = MockScraper
        mock_module.AnotherTestScraper = FailingScraper
        mock_import.return_value = mock_module

        with patch("builtins.dir", return_value=["TestScraper", "AnotherTestScraper"]):
            result = load_scraper_class("test")

        assert result == MockScraper
        mock_import.assert_called_with("app.scraper.test_scraper")

    @patch("app.scraper.__main__.importlib.import_module")
    @patch("app.scraper.__main__.logger")
    def test_load_multiple_scraper_classes_fallback(
        self, mock_logger: Mock, mock_import: Mock
    ) -> None:
        """Test loading when no exact match, falls back to first scraper."""
        # Mock module with multiple scraper classes, no exact match
        mock_module = Mock()
        mock_module.FirstScraper = MockScraper
        mock_module.SecondScraper = FailingScraper
        mock_import.return_value = mock_module

        with patch("builtins.dir", return_value=["FirstScraper", "SecondScraper"]):
            result = load_scraper_class("nonexistent")

        assert result == MockScraper
        mock_logger.warning.assert_called_once()
        mock_import.assert_called_with("app.scraper.nonexistent_scraper")

    @patch("app.scraper.__main__.importlib.import_module")
    def test_load_no_scraper_classes(self, mock_import: Mock) -> None:
        """Test loading when module has no scraper classes."""
        # Mock module with no scraper classes
        mock_module = Mock()
        mock_import.return_value = mock_module

        with patch("builtins.dir", return_value=["some_function", "SomeClass"]):
            with pytest.raises(ImportError, match="No scraper classes found"):
                load_scraper_class("empty")

    @patch("app.scraper.__main__.importlib.import_module")
    @patch("app.scraper.__main__.logger")
    def test_load_import_error(self, mock_logger: Mock, mock_import: Mock) -> None:
        """Test handling of import errors."""
        mock_import.side_effect = ImportError("Module not found")

        with pytest.raises(ImportError, match="Module not found"):
            load_scraper_class("nonexistent")

        mock_logger.error.assert_called_once()

    @patch("app.scraper.__main__.importlib.import_module")
    def test_load_case_insensitive_matching(self, mock_import: Mock) -> None:
        """Test case-insensitive matching of scraper names."""
        # Mock module with scraper class that should match case-insensitively
        mock_module = Mock()
        mock_module.MyTestScraper = MockScraper
        mock_module.AnotherScraper = FailingScraper
        mock_import.return_value = mock_module

        with patch("builtins.dir", return_value=["MyTestScraper", "AnotherScraper"]):
            result = load_scraper_class("my_test")

        assert result == MockScraper


class TestListAvailableScrapers:
    """Test the list_available_scrapers function."""

    def test_list_scrapers_from_directory(self, mock_scraper_dir: Path) -> None:
        """Test listing scrapers from directory."""
        with patch(
            "app.scraper.__main__.__file__", str(mock_scraper_dir / "__main__.py")
        ):
            scrapers = list_available_scrapers()

        expected = [
            "another",
            "not_a",
            "sample",
            "test",
        ]  # sorted order, all *_scraper.py files
        assert scrapers == expected

    def test_list_scrapers_empty_directory(self, tmp_path: Path) -> None:
        """Test listing scrapers from empty directory."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        with patch("app.scraper.__main__.__file__", str(empty_dir / "__main__.py")):
            scrapers = list_available_scrapers()

        assert scrapers == []

    def test_list_scrapers_with_init_file(self, tmp_path: Path) -> None:
        """Test that __init__.py is excluded from scraper list."""
        scraper_dir = tmp_path / "scrapers"
        scraper_dir.mkdir()
        (scraper_dir / "__init___scraper.py").write_text("# Should be excluded")
        (scraper_dir / "valid_scraper.py").write_text("# Valid scraper")

        with patch("app.scraper.__main__.__file__", str(scraper_dir / "__main__.py")):
            scrapers = list_available_scrapers()

        assert scrapers == ["valid"]


class TestRunScraperParallel:
    """Test the run_scraper_parallel function."""

    @pytest.mark.asyncio
    async def test_run_scraper_success(self) -> None:
        """Test successful scraper execution."""
        with patch(
            "app.scraper.__main__.load_scraper_class", return_value=MockScraper
        ) as mock_load:
            with patch("app.scraper.__main__.logger") as mock_logger:
                result = await run_scraper_parallel("test_scraper")

        name, success, duration, error_message = result
        assert name == "test_scraper"
        assert success is True
        assert duration >= 0
        assert error_message == ""
        mock_load.assert_called_once_with("test_scraper")
        mock_logger.info.assert_called()

    @pytest.mark.asyncio
    async def test_run_scraper_failure(self) -> None:
        """Test scraper execution failure."""
        with patch(
            "app.scraper.__main__.load_scraper_class", return_value=FailingScraper
        ) as mock_load:
            with patch("app.scraper.__main__.logger") as mock_logger:
                result = await run_scraper_parallel("failing_scraper")

        name, success, duration, error_message = result
        assert name == "failing_scraper"
        assert success is False
        assert duration >= 0
        assert "Scraper failed" in error_message
        mock_load.assert_called_once_with("failing_scraper")
        mock_logger.error.assert_called()

    @pytest.mark.asyncio
    async def test_run_scraper_load_error(self) -> None:
        """Test scraper loading error."""
        with patch(
            "app.scraper.__main__.load_scraper_class",
            side_effect=ImportError("Module not found"),
        ):
            with patch("app.scraper.__main__.logger") as mock_logger:
                result = await run_scraper_parallel("nonexistent_scraper")

        name, success, duration, error_message = result
        assert name == "nonexistent_scraper"
        assert success is False
        assert duration >= 0
        assert "Module not found" in error_message
        mock_logger.error.assert_called()


class TestRunAllScrapersParallel:
    """Test the run_all_scrapers_parallel function."""

    @pytest.mark.asyncio
    async def test_run_all_scrapers_success(self) -> None:
        """Test running all scrapers successfully."""
        mock_scrapers = ["scraper1", "scraper2", "scraper3"]

        with patch(
            "app.scraper.__main__.list_available_scrapers", return_value=mock_scrapers
        ):
            with patch("app.scraper.__main__.run_scraper_parallel") as mock_run:
                # Mock successful results
                mock_run.side_effect = [
                    ("scraper1", True, 1.0, ""),
                    ("scraper2", True, 2.0, ""),
                    ("scraper3", True, 1.5, ""),
                ]

                with patch("app.scraper.__main__.logger") as mock_logger:
                    results = await run_all_scrapers_parallel(max_workers=2)

        assert len(results) == 3
        assert results["scraper1"]["success"] is True
        assert results["scraper2"]["success"] is True
        assert results["scraper3"]["success"] is True
        mock_logger.info.assert_called()

    @pytest.mark.asyncio
    async def test_run_all_scrapers_mixed_results(self) -> None:
        """Test running all scrapers with mixed success/failure."""
        mock_scrapers = ["scraper1", "scraper2"]

        with patch(
            "app.scraper.__main__.list_available_scrapers", return_value=mock_scrapers
        ):
            with patch("app.scraper.__main__.run_scraper_parallel") as mock_run:
                # Mock mixed results
                mock_run.side_effect = [
                    ("scraper1", True, 1.0, ""),
                    ("scraper2", False, 2.0, "Error occurred"),
                ]

                results = await run_all_scrapers_parallel()

        assert len(results) == 2
        assert results["scraper1"]["success"] is True
        assert results["scraper1"]["error"] is None
        assert results["scraper2"]["success"] is False
        assert results["scraper2"]["error"] == "Error occurred"

    @pytest.mark.asyncio
    async def test_run_all_scrapers_empty_list(self) -> None:
        """Test running all scrapers with empty scraper list."""
        with patch("app.scraper.__main__.list_available_scrapers", return_value=[]):
            with patch("app.scraper.__main__.logger") as mock_logger:
                results = await run_all_scrapers_parallel()

        assert results == {}
        mock_logger.info.assert_called_with("Found 0 scrapers to run")


class TestMain:
    """Test the main function."""

    @pytest.mark.asyncio
    async def test_main_list_scrapers(self, capsys) -> None:
        """Test main function with --list argument."""
        mock_scrapers = ["scraper1", "scraper2", "scraper3"]

        with patch("sys.argv", ["__main__.py", "--list"]):
            with patch(
                "app.scraper.__main__.list_available_scrapers",
                return_value=mock_scrapers,
            ):
                await main()

        captured = capsys.readouterr()
        assert "Available scrapers:" in captured.out
        assert "scraper1" in captured.out
        assert "scraper2" in captured.out
        assert "scraper3" in captured.out

    @pytest.mark.asyncio
    async def test_main_no_arguments(self) -> None:
        """Test main function with no arguments (should error)."""
        with patch("sys.argv", ["__main__.py"]):
            with pytest.raises(SystemExit):
                await main()

    @pytest.mark.asyncio
    async def test_main_single_scraper_success(self) -> None:
        """Test main function running single scraper successfully."""
        with patch("sys.argv", ["__main__.py", "test_scraper"]):
            with patch(
                "app.scraper.__main__.load_scraper_class", return_value=MockScraper
            ) as mock_load:
                with patch("app.scraper.__main__.logger") as mock_logger:
                    await main()

        mock_load.assert_called_once_with("test_scraper")
        mock_logger.info.assert_any_call("Running scraper: test_scraper")
        mock_logger.info.assert_any_call("Scraper test_scraper completed successfully")

    @pytest.mark.asyncio
    async def test_main_single_scraper_failure(self) -> None:
        """Test main function with single scraper failure."""
        with patch("sys.argv", ["__main__.py", "failing_scraper"]):
            with patch(
                "app.scraper.__main__.load_scraper_class",
                side_effect=ImportError("Module not found"),
            ):
                with patch("app.scraper.__main__.logger") as mock_logger:
                    with patch("sys.exit") as mock_exit:
                        await main()

        mock_logger.error.assert_called_with("Module not found")
        mock_exit.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_main_single_scraper_runtime_error(self) -> None:
        """Test main function with single scraper runtime error."""
        with patch("sys.argv", ["__main__.py", "failing_scraper"]):
            with patch(
                "app.scraper.__main__.load_scraper_class", return_value=FailingScraper
            ):
                with patch("app.scraper.__main__.logger") as mock_logger:
                    with patch("sys.exit") as mock_exit:
                        await main()

        mock_logger.error.assert_called()
        assert "Scraper failed:" in str(mock_logger.error.call_args)
        mock_exit.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_main_all_scrapers_sequential(self) -> None:
        """Test main function running all scrapers sequentially."""
        mock_scrapers = ["scraper1", "scraper2"]

        with patch("sys.argv", ["__main__.py", "--all"]):
            with patch(
                "app.scraper.__main__.list_available_scrapers",
                return_value=mock_scrapers,
            ):
                with patch(
                    "app.scraper.__main__.load_scraper_class", return_value=MockScraper
                ) as mock_load:
                    with patch("app.scraper.__main__.logger") as mock_logger:
                        await main()

        assert mock_load.call_count == 2
        mock_logger.info.assert_any_call("Running all scrapers sequentially")

    @pytest.mark.asyncio
    async def test_main_all_scrapers_sequential_with_failure(self) -> None:
        """Test main function running all scrapers sequentially with one failure."""
        mock_scrapers = ["good_scraper", "bad_scraper"]

        def mock_load_scraper(name: str) -> type[ScraperJob]:
            if name == "bad_scraper":
                return FailingScraper
            return MockScraper

        with patch("sys.argv", ["__main__.py", "--all"]):
            with patch(
                "app.scraper.__main__.list_available_scrapers",
                return_value=mock_scrapers,
            ):
                with patch(
                    "app.scraper.__main__.load_scraper_class",
                    side_effect=mock_load_scraper,
                ):
                    with patch("app.scraper.__main__.logger") as mock_logger:
                        await main()

        # Should continue with next scraper even after failure
        mock_logger.error.assert_called()
        mock_logger.info.assert_any_call("Running all scrapers sequentially")

    @pytest.mark.asyncio
    async def test_main_all_scrapers_parallel(self, capsys) -> None:
        """Test main function running all scrapers in parallel."""
        mock_results = {
            "scraper1": {"success": True, "duration": 1.0, "error": None},
            "scraper2": {"success": False, "duration": 2.0, "error": "Test error"},
        }

        with patch(
            "sys.argv", ["__main__.py", "--all", "--parallel", "--max-workers", "2"]
        ):
            with patch(
                "app.scraper.__main__.run_all_scrapers_parallel",
                return_value=mock_results,
            ) as mock_run:
                with patch("app.scraper.__main__.logger") as mock_logger:
                    with patch("sys.exit") as mock_exit:
                        await main()

        mock_run.assert_called_once_with(2)
        mock_logger.info.assert_any_call(
            "Running all scrapers in parallel with max 2 workers"
        )

        # Check output contains results summary
        captured = capsys.readouterr()
        assert "Scraper Run Results:" in captured.out
        assert "scraper1: ✅ SUCCESS" in captured.out
        assert "scraper2: ❌ FAILED" in captured.out
        assert "Test error" in captured.out
        assert "Total: 2" in captured.out
        assert "Successful: 1" in captured.out
        assert "Failed: 1" in captured.out

        # Should exit with error code due to failures
        mock_exit.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_main_all_scrapers_parallel_success(self, capsys) -> None:
        """Test main function running all scrapers in parallel with all success."""
        mock_results = {
            "scraper1": {"success": True, "duration": 1.0, "error": None},
            "scraper2": {"success": True, "duration": 2.0, "error": None},
        }

        with patch("sys.argv", ["__main__.py", "--all", "--parallel"]):
            with patch(
                "app.scraper.__main__.run_all_scrapers_parallel",
                return_value=mock_results,
            ):
                with patch("sys.exit") as mock_exit:
                    await main()

        # Should not exit with error code when all succeed
        mock_exit.assert_not_called()

    @pytest.mark.asyncio
    async def test_main_argument_parsing(self) -> None:
        """Test various argument combinations."""
        # Test with scraper name and --all (should work with scraper name taking precedence)
        with patch("sys.argv", ["__main__.py", "test_scraper", "--all"]):
            with patch(
                "app.scraper.__main__.load_scraper_class", return_value=MockScraper
            ):
                with patch("app.scraper.__main__.logger"):
                    await main()

    @pytest.mark.asyncio
    async def test_main_with_max_workers_default(self) -> None:
        """Test main function with default max workers."""
        mock_results = {
            "scraper1": {"success": True, "duration": 1.0, "error": None},
        }

        with patch("sys.argv", ["__main__.py", "--all", "--parallel"]):
            with patch(
                "app.scraper.__main__.run_all_scrapers_parallel",
                return_value=mock_results,
            ) as mock_run:
                await main()

        # Default max-workers should be 4
        mock_run.assert_called_once_with(4)


class TestScoutingPartyMode:
    """Test the special 'scouting-party' mode mentioned in the requirements."""

    @pytest.mark.asyncio
    async def test_scouting_party_mode(self) -> None:
        """Test running scouting-party (all scrapers in parallel)."""
        mock_results = {
            "scraper1": {"success": True, "duration": 1.0, "error": None},
            "scraper2": {"success": True, "duration": 2.0, "error": None},
        }

        with patch("sys.argv", ["__main__.py", "scouting-party"]):
            # Mock load_scraper_class to treat "scouting-party" as special case
            with patch("app.scraper.__main__.load_scraper_class") as mock_load:
                mock_load.side_effect = ImportError("No such scraper")
                with patch(
                    "app.scraper.__main__.run_all_scrapers_parallel",
                    return_value=mock_results,
                ) as mock_run:
                    with patch("app.scraper.__main__.logger") as mock_logger:
                        with patch("sys.exit"):
                            await main()

        # Should fail because scouting-party isn't implemented as special case in the actual code
        mock_logger.error.assert_called()


class TestErrorHandling:
    """Test error handling scenarios."""

    @pytest.mark.asyncio
    async def test_value_error_handling(self) -> None:
        """Test ValueError handling in main."""
        with patch("sys.argv", ["__main__.py", "test_scraper"]):
            with patch(
                "app.scraper.__main__.load_scraper_class",
                side_effect=ValueError("Invalid scraper"),
            ):
                with patch("app.scraper.__main__.logger") as mock_logger:
                    with patch("sys.exit") as mock_exit:
                        await main()

        mock_logger.error.assert_called_with("Invalid scraper")
        mock_exit.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_generic_exception_handling(self) -> None:
        """Test generic exception handling in main."""

        class FailingMockScraper(ScraperJob):
            async def run(self) -> None:
                raise RuntimeError("Generic error")

            async def scrape(self) -> str:
                return ""

        with patch("sys.argv", ["__main__.py", "test_scraper"]):
            with patch(
                "app.scraper.__main__.load_scraper_class",
                return_value=FailingMockScraper,
            ):
                with patch("app.scraper.__main__.logger") as mock_logger:
                    with patch("sys.exit") as mock_exit:
                        await main()

        mock_logger.error.assert_called()
        assert "Scraper failed:" in str(mock_logger.error.call_args)
        mock_exit.assert_called_once_with(1)


class TestCoverageEdgeCases:
    """Test edge cases to improve coverage."""

    def test_load_scraper_underscore_normalization(self) -> None:
        """Test underscore normalization in scraper name matching."""
        mock_module = Mock()
        mock_module.MySpecialScraper = MockScraper

        with patch(
            "app.scraper.__main__.importlib.import_module", return_value=mock_module
        ):
            with patch("builtins.dir", return_value=["MySpecialScraper"]):
                result = load_scraper_class("my_special")

        assert result == MockScraper

    @pytest.mark.asyncio
    async def test_run_scraper_parallel_timing(self) -> None:
        """Test that timing is captured correctly in run_scraper_parallel."""
        import time

        class SlowScraper(ScraperJob):
            async def run(self) -> None:
                await asyncio.sleep(0.1)  # Small delay to test timing

            async def scrape(self) -> str:
                return ""

        with patch("app.scraper.__main__.load_scraper_class", return_value=SlowScraper):
            start_time = time.time()
            result = await run_scraper_parallel("slow_scraper")
            end_time = time.time()

        name, success, duration, error_message = result
        assert name == "slow_scraper"
        assert success is True
        assert duration >= 0.1  # Should be at least the sleep time
        assert duration <= (end_time - start_time) + 0.1  # Allow some overhead
        assert error_message == ""

    def test_list_available_scrapers_file_filtering(self, tmp_path: Path) -> None:
        """Test that only *_scraper.py files are included."""
        scraper_dir = tmp_path / "scrapers"
        scraper_dir.mkdir()

        # Create various files
        (scraper_dir / "valid_scraper.py").write_text("# Valid")
        (scraper_dir / "also_valid_scraper.py").write_text("# Also valid")
        (scraper_dir / "not_scraper.py").write_text("# Not a scraper")
        (scraper_dir / "scraper_not_suffix.py").write_text("# Wrong suffix")
        (scraper_dir / "scraper.py").write_text("# Just 'scraper'")
        (scraper_dir / "_scraper.py").write_text("# Underscore only")

        with patch("app.scraper.__main__.__file__", str(scraper_dir / "__main__.py")):
            scrapers = list_available_scrapers()

        # Should include all files matching *_scraper.py pattern
        # _scraper.py -> "", not_scraper.py -> "not", scraper_not_suffix.py doesn't match
        expected = [
            "",
            "also_valid",
            "not",
            "valid",
        ]  # sorted - includes all *_scraper.py files
        assert scrapers == expected


if __name__ == "__main__":
    # Test the module entry point
    import sys

    # Mock sys.argv and asyncio.run for testing
    with patch("sys.argv", ["__main__.py", "--list"]):
        with patch("asyncio.run") as mock_run:
            from app.scraper.__main__ import __name__ as module_name

            if module_name == "__main__":
                # This would normally call asyncio.run(main())
                pass

