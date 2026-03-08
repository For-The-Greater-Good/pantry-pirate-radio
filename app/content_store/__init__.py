"""Content store module for deduplicating scraped content.

S3ContentStoreBackend is imported lazily to avoid pulling in boto3 when
only the file-based backend is needed (e.g. local Docker containers).
"""

from app.content_store.backend import ContentStoreBackend, FileContentStoreBackend
from app.content_store.store import ContentStore

__all__ = [
    "ContentStore",
    "ContentStoreBackend",
    "FileContentStoreBackend",
    "S3ContentStoreBackend",
]


def __getattr__(name: str):
    if name == "S3ContentStoreBackend":
        from app.content_store.backend_s3 import S3ContentStoreBackend

        return S3ContentStoreBackend
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
