"""Base database model configuration."""

from sqlalchemy import MetaData
from sqlalchemy.orm import declarative_base

# Create metadata with naming convention for foreign keys
metadata = MetaData(
    naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(column_0_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)

# Create base class for all models
Base = declarative_base(metadata=metadata)
