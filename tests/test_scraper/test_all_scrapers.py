"""Comprehensive tests for all scrapers (framework and private)."""

import pytest

from app.scraper.__main__ import list_available_scrapers, load_scraper_class
from app.scraper.utils import ScraperJob


@pytest.fixture
def available_scrapers() -> list[str]:
    """Get list of all available scrapers.

    Returns:
        List of scraper names (framework + private if available)
    """
    return list_available_scrapers()


def test_scrapers_discovered(available_scrapers: list[str]) -> None:
    """Test that at least the framework sample scraper is discovered.

    Args:
        available_scrapers: List of available scrapers
    """
    assert len(available_scrapers) > 0, "No scrapers discovered"
    assert "sample" in available_scrapers, "Framework sample scraper not found"


def test_framework_scrapers_present(available_scrapers: list[str]) -> None:
    """Test that framework scrapers are present.

    Args:
        available_scrapers: List of available scrapers
    """
    # Framework scrapers should always be present
    framework_scrapers = [
        s for s in available_scrapers if not s.startswith("scrapers.")
    ]
    assert (
        len(framework_scrapers) >= 1
    ), "No framework scrapers found (expected at least 'sample')"
    assert "sample" in framework_scrapers, "Sample scraper not in framework scrapers"


def test_private_scrapers_optional(available_scrapers: list[str]) -> None:
    """Test that private scrapers are optional (may or may not be present).

    Args:
        available_scrapers: List of available scrapers
    """
    private_scrapers = [s for s in available_scrapers if s.startswith("scrapers.")]

    # Private scrapers are optional - just log what we found
    print(f"\nFound {len(private_scrapers)} private scrapers:")
    for scraper in private_scrapers:
        print(f"  - {scraper}")

    if len(private_scrapers) == 0:
        print(
            "  (No private scrapers available - this is OK for CI without credentials)"
        )


@pytest.mark.parametrize("scraper_name", list_available_scrapers())
def test_scraper_can_be_loaded(scraper_name: str) -> None:
    """Test that each discovered scraper can be loaded.

    Args:
        scraper_name: Name of scraper to test
    """
    scraper_class = load_scraper_class(scraper_name)
    assert scraper_class is not None, f"Failed to load {scraper_name}"
    assert issubclass(
        scraper_class, ScraperJob
    ), f"{scraper_name} is not a ScraperJob subclass"


@pytest.mark.parametrize("scraper_name", list_available_scrapers())
def test_scraper_can_be_instantiated(scraper_name: str) -> None:
    """Test that each scraper can be instantiated.

    Args:
        scraper_name: Name of scraper to test
    """
    scraper_class = load_scraper_class(scraper_name)
    scraper = scraper_class(scraper_id=scraper_name)

    assert scraper is not None, f"Failed to instantiate {scraper_name}"
    assert isinstance(
        scraper, ScraperJob
    ), f"{scraper_name} is not a ScraperJob instance"
    assert scraper.scraper_id == scraper_name, f"Scraper ID mismatch for {scraper_name}"


@pytest.mark.parametrize("scraper_name", list_available_scrapers())
def test_scraper_has_required_methods(scraper_name: str) -> None:
    """Test that each scraper has required ScraperJob methods.

    Args:
        scraper_name: Name of scraper to test
    """
    scraper_class = load_scraper_class(scraper_name)
    scraper = scraper_class(scraper_id=scraper_name)

    # Check for required methods
    assert hasattr(scraper, "scrape"), f"{scraper_name} missing scrape() method"
    assert hasattr(scraper, "run"), f"{scraper_name} missing run() method"
    assert hasattr(
        scraper, "submit_to_queue"
    ), f"{scraper_name} missing submit_to_queue() method"

    # Check that scrape is async
    import inspect

    assert inspect.iscoroutinefunction(
        scraper.scrape
    ), f"{scraper_name}.scrape() must be async"
    assert inspect.iscoroutinefunction(
        scraper.run
    ), f"{scraper_name}.run() must be async"


def test_scraper_naming_conventions(available_scrapers: list[str]) -> None:
    """Test that scrapers follow naming conventions.

    Args:
        available_scrapers: List of available scrapers
    """
    for scraper_name in available_scrapers:
        # Framework scrapers should not have dots
        if not scraper_name.startswith("scrapers."):
            assert (
                "." not in scraper_name
            ), f"Framework scraper {scraper_name} should not contain dots"

        # Private scrapers should have scrapers. prefix
        else:
            assert scraper_name.startswith(
                "scrapers."
            ), f"Private scraper {scraper_name} should start with 'scrapers.'"
            # Name after prefix should not be empty
            name_part = scraper_name.split(".", 1)[1]
            assert len(name_part) > 0, f"Private scraper {scraper_name} has empty name"


def test_sample_scraper_is_framework(available_scrapers: list[str]) -> None:
    """Test that sample scraper is in framework (not private).

    Args:
        available_scrapers: List of available scrapers
    """
    assert "sample" in available_scrapers, "Sample scraper not found"
    assert (
        "scrapers.sample" not in available_scrapers
    ), "Sample scraper should be in framework, not private"
