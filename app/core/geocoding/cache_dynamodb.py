"""DynamoDB geocoding cache backend for AWS deployment.

Uses the DynamoDB table provisioned by DatabaseStack._create_geocoding_cache_table
with schema: PK=address, latitude, longitude, provider, cached_at, ttl.
"""

import json
import time
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class DynamoDBGeocodingCache:
    """DynamoDB-backed geocoding cache.

    Uses lazy boto3 client initialization (same pattern as backend_s3.py).

    Args:
        table_name: DynamoDB table name
        region_name: AWS region (optional, uses default credential chain)
    """

    def __init__(self, table_name: str, region_name: Optional[str] = None) -> None:
        self._table_name = table_name
        self._region_name = region_name
        self._client: Any = None

    def _get_client(self) -> Any:
        """Get or create DynamoDB client (lazy init)."""
        if self._client is None:
            try:
                import boto3
            except ImportError as e:
                raise ImportError(
                    "boto3 is required for DynamoDBGeocodingCache. "
                    "Install it with: pip install boto3"
                ) from e

            kwargs: dict = {}
            if self._region_name:
                kwargs["region_name"] = self._region_name
            self._client = boto3.client("dynamodb", **kwargs)
        return self._client

    def get(self, cache_key: str) -> Optional[dict]:
        """Retrieve a cached geocoding result from DynamoDB.

        Args:
            cache_key: Cache key (used as partition key ``address``)

        Returns:
            Dict with 'lat' and 'lon' keys, or None
        """
        try:
            client = self._get_client()
            response = client.get_item(
                TableName=self._table_name,
                Key={"address": {"S": cache_key}},
            )
            item = response.get("Item")
            if not item:
                return None

            # Check TTL (DynamoDB TTL cleanup is eventually consistent)
            ttl_val = item.get("ttl", {}).get("N")
            if ttl_val and int(ttl_val) < int(time.time()):
                return None

            result: dict = {}
            if "latitude" in item:
                result["lat"] = float(item["latitude"]["N"])
            if "longitude" in item:
                result["lon"] = float(item["longitude"]["N"])

            # Include any extra data stored as JSON
            if "data" in item:
                try:
                    extra = json.loads(item["data"]["S"])
                    result.update(extra)
                except json.JSONDecodeError as e:
                    logger.warning(
                        "DynamoDB geocoding cache data corruption",
                        cache_key=cache_key,
                        error=str(e),
                    )

            if "lat" in result and "lon" in result:
                return result
            return None

        except json.JSONDecodeError as e:
            logger.warning(
                "DynamoDB geocoding cache data parsing error on get",
                cache_key=cache_key,
                error=str(e),
            )
            return None
        except Exception as e:
            logger.error(
                "DynamoDB geocoding cache infrastructure error on get",
                cache_key=cache_key,
                error=str(e),
            )
            return None

    def set(self, cache_key: str, data: dict, ttl: int) -> None:
        """Store a geocoding result in DynamoDB.

        Args:
            cache_key: Cache key (used as partition key ``address``)
            data: Dict with at least 'lat' and 'lon' keys
            ttl: Time-to-live in seconds (converted to Unix timestamp)
        """
        try:
            client = self._get_client()
            now = int(time.time())
            ttl_timestamp = now + ttl

            # Extract provider from cache key if present
            provider = ""
            parts = cache_key.split(":")
            if len(parts) >= 2:
                provider = parts[1]

            item: dict = {
                "address": {"S": cache_key},
                "ttl": {"N": str(ttl_timestamp)},
                "cached_at": {"N": str(now)},
            }

            if "lat" in data:
                item["latitude"] = {"N": str(data["lat"])}
            if "lon" in data:
                item["longitude"] = {"N": str(data["lon"])}
            if provider:
                item["provider"] = {"S": provider}

            # Store any extra keys beyond lat/lon as JSON blob
            extra = {k: v for k, v in data.items() if k not in ("lat", "lon")}
            if extra:
                item["data"] = {"S": json.dumps(extra)}

            client.put_item(TableName=self._table_name, Item=item)

        except json.JSONDecodeError as e:
            logger.warning(
                "DynamoDB geocoding cache data serialization error on set",
                cache_key=cache_key,
                error=str(e),
            )
        except Exception as e:
            logger.error(
                "DynamoDB geocoding cache infrastructure error on set",
                cache_key=cache_key,
                error=str(e),
            )
