"""Type definitions for HSDS data structures.

This module re-exports types from type_defs for backward compatibility.
"""

from app.llm.hsds_aligner.type_defs import (
    AddressDict,
    HSDSDataDict,
    LocationDict,
    OrganizationDict,
    ServiceDict,
)
from app.llm.hsds_aligner.type_defs import (
    AlignmentOutputDict as AlignmentResultDict,
)

__all__ = [
    "AddressDict",
    "AlignmentResultDict",
    "HSDSDataDict",
    "LocationDict",
    "OrganizationDict",
    "ServiceDict",
]
