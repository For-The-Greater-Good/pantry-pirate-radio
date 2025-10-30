"""Tests for FoodFinder.us scraper."""

import json
import zlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.geographic import GridPoint
from app.scraper.foodfinder_us_scraper import Foodfinder_UsScraper


@pytest.fixture(name="scraper")
def fixture_scraper() -> Foodfinder_UsScraper:
    """Create test scraper instance."""
    return Foodfinder_UsScraper()


@pytest.fixture(name="mock_location")
def fixture_mock_location() -> dict[str, Any]:
    """Create mock location data from FoodFinder API."""
    return {
        "id": "61793",
        "name": "Alliance for Positive Change - Midtown Central Location",
        "latitude": 40.7501422,
        "longitude": -73.9868341,
        "operating_days": '{"monday":{"checked":true,"hours":[{"hoursFrom":"09:00","hoursTo":"17:00"}]}}',
        "operating_hours": "",
        "address1": "64 W 35th St.",
        "address2": "3rd Floor",
        "city": "New York",
        "county": "New York County",
        "state": "NY",
        "zip_code": "10001",
        "phone_number": "212-645-0875",
        "email": "questions@alliance.nyc",
        "url": "www.alliance.nyc",
        "serviceArea": "Open To All",
        "requirements": "Photo ID is Required.",
        "services1": "Food Pantry, Emergency Food Pantry, & Shelter.",
        "languages": "English Speaking. Translation Services are available.",
    }


@pytest.fixture(name="encrypted_response")
def fixture_encrypted_response() -> tuple[bytes, str]:
    """Create mock encrypted response.

    Returns:
        Tuple of (encrypted_data, timestamp)
    """
    # Create sample JSON data
    sample_data = [
        {
            "id": "12345",
            "name": "Test Pantry",
            "latitude": 40.7,
            "longitude": -73.9,
        }
    ]
    json_data = json.dumps(sample_data).encode("utf-8")

    # Compress with zlib
    compressed = zlib.compress(json_data)

    # For testing, we'll use a simple password and encrypt
    # This simulates the real encrypted response
    timestamp = "1234567890"

    # Import encryption modules
    import hashlib

    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.padding import PKCS7

    # Create password from MD5(timestamp)
    password_hash = hashlib.md5(timestamp.encode()).hexdigest()
    password = password_hash.encode("utf-8")

    # Create salt
    salt = b"testsalt"

    # Derive key and IV
    def evp_bytes_to_key(
        pwd: bytes, slt: bytes, key_len: int = 32, iv_len: int = 16
    ) -> tuple[bytes, bytes]:
        derived = b""
        prev = b""
        while len(derived) < key_len + iv_len:
            prev = hashlib.md5(prev + pwd + slt).digest()
            derived += prev
        return derived[:key_len], derived[key_len : key_len + iv_len]

    key, iv = evp_bytes_to_key(password, salt)

    # Add PKCS7 padding
    padder = PKCS7(128).padder()
    padded_data = padder.update(compressed) + padder.finalize()

    # Encrypt
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded_data) + encryptor.finalize()

    # Create OpenSSL format: "Salted__" + salt + ciphertext
    encrypted_data = b"Salted__" + salt + ciphertext

    return encrypted_data, timestamp


def test_get_api_headers(scraper: Foodfinder_UsScraper) -> None:
    """Test API headers generation."""
    headers = scraper.get_api_headers()

    assert "Accept" in headers
    assert "Referer" in headers
    assert "Origin" in headers
    assert "User-Agent" in headers
    assert headers["Origin"] == scraper.web_url
    assert headers["Referer"] == f"{scraper.web_url}/"


def test_evp_bytes_to_key(scraper: Foodfinder_UsScraper) -> None:
    """Test EVP_BytesToKey derivation."""
    password = b"test_password"
    salt = b"testsalt"

    key, iv = scraper.evp_bytes_to_key(password, salt, key_len=32, iv_len=16)

    assert len(key) == 32
    assert len(iv) == 16
    assert isinstance(key, bytes)
    assert isinstance(iv, bytes)


def test_decrypt_response(
    scraper: Foodfinder_UsScraper, encrypted_response: tuple[bytes, str]
) -> None:
    """Test response decryption."""
    encrypted_data, timestamp = encrypted_response

    decrypted = scraper.decrypt_response(encrypted_data, timestamp)

    # Should be valid JSON
    data = json.loads(decrypted)
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["id"] == "12345"
    assert data[0]["name"] == "Test Pantry"


def test_decrypt_response_invalid_format(scraper: Foodfinder_UsScraper) -> None:
    """Test decryption with invalid format."""
    # Data that doesn't start with "Salted__"
    invalid_data = b"Invalid data"

    with pytest.raises(ValueError, match="Invalid encrypted format"):
        scraper.decrypt_response(invalid_data, "1234567890")


def test_create_bbox_around_point(scraper: Foodfinder_UsScraper) -> None:
    """Test bounding box creation."""
    point = GridPoint(name="test", latitude=40.7, longitude=-73.9)

    bbox = scraper.create_bbox_around_point(point)

    assert "min_lat" in bbox
    assert "max_lat" in bbox
    assert "min_lon" in bbox
    assert "max_lon" in bbox
    assert "portal" in bbox
    assert "_time" in bbox

    # Check that bounding box is centered around point
    assert bbox["min_lat"] < point.latitude < bbox["max_lat"]
    assert bbox["min_lon"] < point.longitude < bbox["max_lon"]

    # Check portal value
    assert bbox["portal"] == 0

    # Check timestamp is reasonable (recent)
    import time

    assert abs(bbox["_time"] - int(time.time() * 1000)) < 1000  # Within 1 second


@pytest.mark.asyncio
async def test_search_bbox(
    scraper: Foodfinder_UsScraper, mock_location: dict[str, Any]
) -> None:
    """Test bounding box search."""
    with patch("httpx.AsyncClient") as mock_client:
        # Create mock encrypted response
        json_data = json.dumps([mock_location])
        compressed = zlib.compress(json_data.encode("utf-8"))

        # Encrypt it (simplified for test)
        import hashlib

        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives.padding import PKCS7

        timestamp = "1234567890"
        password_hash = hashlib.md5(timestamp.encode()).hexdigest()
        password = password_hash.encode("utf-8")
        salt = b"testsalt"

        def evp_bytes_to_key(
            pwd: bytes, slt: bytes, key_len: int = 32, iv_len: int = 16
        ) -> tuple[bytes, bytes]:
            derived = b""
            prev = b""
            while len(derived) < key_len + iv_len:
                prev = hashlib.md5(prev + pwd + slt).digest()
                derived += prev
            return derived[:key_len], derived[key_len : key_len + iv_len]

        key, iv = evp_bytes_to_key(password, salt)

        padder = PKCS7(128).padder()
        padded_data = padder.update(compressed) + padder.finalize()

        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(padded_data) + encryptor.finalize()

        encrypted_data = b"Salted__" + salt + ciphertext

        # Mock HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = encrypted_data
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response
        )

        bbox = {"min_lat": 40.0, "max_lat": 41.0, "min_lon": -74.0, "max_lon": -73.0, "portal": 0, "_time": int(timestamp)}

        results = await scraper.search_bbox(bbox)

        assert len(results) == 1
        assert results[0]["id"] == "61793"
        assert results[0]["name"] == "Alliance for Positive Change - Midtown Central Location"


@pytest.mark.asyncio
async def test_search_bbox_error(scraper: Foodfinder_UsScraper) -> None:
    """Test bounding box search error handling."""
    with patch("httpx.AsyncClient") as mock_client:
        # Mock failed HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response
        )

        bbox = {"min_lat": 40.0, "max_lat": 41.0, "min_lon": -74.0, "max_lon": -73.0, "portal": 0, "_time": 1234567890}

        results = await scraper.search_bbox(bbox)

        assert len(results) == 0


@pytest.mark.asyncio
async def test_process_batch(
    scraper: Foodfinder_UsScraper, mock_location: dict[str, Any]
) -> None:
    """Test batch processing."""
    coordinates = [GridPoint(name="test", latitude=40.7, longitude=-73.9)]

    # Mock search_bbox
    scraper.search_bbox = AsyncMock(return_value=[mock_location])

    await scraper.process_batch(coordinates)

    assert scraper.total_locations == 1
    assert len(scraper.unique_locations) == 1
    assert "61793" in scraper.unique_locations
    assert "61793" in scraper.location_data


@pytest.mark.asyncio
async def test_process_batch_with_duplicates(
    scraper: Foodfinder_UsScraper, mock_location: dict[str, Any]
) -> None:
    """Test batch processing with duplicate locations."""
    coordinates = [
        GridPoint(name="test1", latitude=40.7, longitude=-73.9),
        GridPoint(name="test2", latitude=40.8, longitude=-73.8),
    ]

    # Both coordinates return the same location
    scraper.search_bbox = AsyncMock(return_value=[mock_location])

    await scraper.process_batch(coordinates)

    # Should only count once
    assert scraper.total_locations == 1
    assert len(scraper.unique_locations) == 1


@pytest.mark.asyncio
async def test_process_batch_error_handling(scraper: Foodfinder_UsScraper) -> None:
    """Test batch processing error handling."""
    coordinates = [GridPoint(name="test", latitude=40.7, longitude=-73.9)]

    # Mock search_bbox to raise exception
    scraper.search_bbox = AsyncMock(side_effect=Exception("API Error"))

    # Should not raise exception
    await scraper.process_batch(coordinates)

    assert scraper.total_locations == 0
    assert len(scraper.unique_locations) == 0


@pytest.mark.asyncio
async def test_process_batch_missing_id(scraper: Foodfinder_UsScraper) -> None:
    """Test handling of locations without ID."""
    coordinates = [GridPoint(name="test", latitude=40.7, longitude=-73.9)]

    # Mock location without ID
    location_no_id = {"name": "Test", "latitude": 40.7}

    scraper.search_bbox = AsyncMock(return_value=[location_no_id])

    await scraper.process_batch(coordinates)

    assert scraper.total_locations == 0
    assert len(scraper.unique_locations) == 0


@pytest.mark.asyncio
async def test_scrape(scraper: Foodfinder_UsScraper) -> None:
    """Test full scrape process."""
    # Mock grid points
    with patch("app.scraper.utils.ScraperUtils.get_us_grid_points") as mock_grid:
        mock_grid.return_value = [GridPoint(name="test", latitude=40.7, longitude=-73.9)]

        # Mock process_batch
        scraper.process_batch = AsyncMock()

        # Mock submit_to_queue
        scraper.submit_to_queue = MagicMock(return_value="test-job-id")

        result = await scraper.scrape()
        data = json.loads(result)

        assert data["total_coordinates"] == 1
        assert "source" in data
        assert data["source"] == scraper.api_url
        assert scraper.process_batch.called


@pytest.mark.asyncio
async def test_scrape_test_mode(scraper: Foodfinder_UsScraper) -> None:
    """Test scrape in test mode."""
    # Create scraper in test mode
    test_scraper = Foodfinder_UsScraper(test_mode=True)

    # Mock grid points (10 points)
    with patch("app.scraper.utils.ScraperUtils.get_us_grid_points") as mock_grid:
        mock_grid.return_value = [
            GridPoint(name=f"test{i}", latitude=40.7 + i * 0.1, longitude=-73.9 + i * 0.1)
            for i in range(10)
        ]

        # Mock process_batch
        test_scraper.process_batch = AsyncMock()

        # Mock submit_to_queue
        test_scraper.submit_to_queue = MagicMock(return_value="test-job-id")

        result = await test_scraper.scrape()
        data = json.loads(result)

        # In test mode, should only process first 5 points
        assert data["total_coordinates"] == 5
        assert test_scraper.process_batch.called


@pytest.mark.asyncio
async def test_scrape_with_submissions(
    scraper: Foodfinder_UsScraper, mock_location: dict[str, Any]
) -> None:
    """Test that scrape submits locations to queue."""
    # Mock grid points
    with patch("app.scraper.utils.ScraperUtils.get_us_grid_points") as mock_grid:
        mock_grid.return_value = [GridPoint(name="test", latitude=40.7, longitude=-73.9)]

        # Mock process_batch to populate location data
        async def mock_process_batch(coordinates):
            # Simulate finding a location
            scraper.location_data["61793"] = mock_location
            scraper.unique_locations.add("61793")
            scraper.total_locations = 1

        scraper.process_batch = AsyncMock(side_effect=mock_process_batch)

        # Mock submit_to_queue
        scraper.submit_to_queue = MagicMock(return_value="test-job-id")

        await scraper.scrape()

        # Verify submission was called
        assert scraper.submit_to_queue.called
        assert scraper.submit_to_queue.call_count == 1

        # Verify data was submitted as JSON
        call_args = scraper.submit_to_queue.call_args
        submitted_data = json.loads(call_args[0][0])
        assert submitted_data["id"] == "61793"


def test_init_default_values(scraper: Foodfinder_UsScraper) -> None:
    """Test scraper initialization with default values."""
    assert scraper.scraper_id == "foodfinder_us"
    assert scraper.api_url == "https://api-v2-prod-dot-foodfinder-183216.uc.r.appspot.com"
    assert scraper.web_url == "https://foodfinder-prod-dot-foodfinder-183216.uc.r.appspot.com"
    assert scraper.batch_size == 25
    assert scraper.request_delay == 0.2
    assert scraper.test_mode is False
    assert scraper.total_locations == 0
    assert len(scraper.unique_locations) == 0
    assert len(scraper.location_data) == 0


def test_init_custom_scraper_id() -> None:
    """Test scraper initialization with custom ID."""
    custom_scraper = Foodfinder_UsScraper(scraper_id="custom_id")
    assert custom_scraper.scraper_id == "custom_id"


def test_init_test_mode() -> None:
    """Test scraper initialization in test mode."""
    test_scraper = Foodfinder_UsScraper(test_mode=True)
    assert test_scraper.test_mode is True
