"""Simple import tests for database modules to boost coverage."""

import pytest


def test_database_init_import():
    """Test database __init__ module can be imported."""
    import app.database

    assert app.database is not None


def test_database_base_import():
    """Test database base module can be imported."""
    import app.database.base

    assert app.database.base is not None


def test_database_models_import():
    """Test database models can be imported."""
    from app.database.models import (
        OrganizationModel,
        LocationModel,
        ServiceModel,
        ServiceAtLocationModel,
        AddressModel,
    )

    assert OrganizationModel is not None
    assert LocationModel is not None
    assert ServiceModel is not None
    assert ServiceAtLocationModel is not None
    assert AddressModel is not None


def test_database_repositories_import():
    """Test database repositories can be imported."""
    from app.database.repositories import (
        OrganizationRepository,
        LocationRepository,
        ServiceRepository,
        ServiceAtLocationRepository,
        AddressRepository,
    )

    assert OrganizationRepository is not None
    assert LocationRepository is not None
    assert ServiceRepository is not None
    assert ServiceAtLocationRepository is not None
    assert AddressRepository is not None


def test_database_geo_utils_import():
    """Test geo utils can be imported."""
    import app.database.geo_utils

    assert app.database.geo_utils is not None


def test_models_hsds_query_import():
    """Test HSDS query models can be imported."""
    import app.models.hsds.query

    assert app.models.hsds.query is not None


def test_models_hsds_response_import():
    """Test HSDS response models can be imported."""
    import app.models.hsds.response

    assert app.models.hsds.response is not None
