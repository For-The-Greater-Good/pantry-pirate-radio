"""Tests for HSDS types imports."""

from app.llm.hsds_aligner.hsds_types import (
    AddressDict,
    AlignmentResultDict,
    HSDSDataDict,
    LocationDict,
    OrganizationDict,
    ServiceDict,
)


def test_imports_available():
    """Test that all expected types are importable."""
    # Verify types can be imported and are available
    assert AddressDict is not None
    assert AlignmentResultDict is not None
    assert HSDSDataDict is not None
    assert LocationDict is not None
    assert OrganizationDict is not None
    assert ServiceDict is not None


def test_all_exports():
    """Test __all__ exports."""
    from app.llm.hsds_aligner import hsds_types

    expected_exports = [
        "AddressDict",
        "AlignmentResultDict",
        "HSDSDataDict",
        "LocationDict",
        "OrganizationDict",
        "ServiceDict",
    ]

    assert hasattr(hsds_types, "__all__")
    assert all(item in hsds_types.__all__ for item in expected_exports)
