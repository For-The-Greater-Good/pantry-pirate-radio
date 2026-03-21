# ruff: noqa: S608
# (Dynamic WHERE clauses use hardcoded column names; all user values are parameterized.)
"""Tightbeam service layer — search, get location detail, and audit history.

Human corrections create new location_source rows for provenance.
The canonical location, address, and phone tables are updated in place.
Every mutation is recorded in the change_audit table with full provenance.

Mutation methods (update, soft-delete, restore) live in ``mutations.py``.
"""

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    AuditEntry,
    HistoryResponse,
    LocationDetail,
    LocationResult,
    SearchResponse,
    SourceRecord,
)
from .mutations import TightbeamMutationService  # noqa: F401 — re-export

logger = structlog.get_logger(__name__)


class TightbeamService(TightbeamMutationService):
    """Service layer for Tightbeam location management.

    Inherits mutation methods from TightbeamMutationService.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search(
        self,
        q: str | None = None,
        name: str | None = None,
        address: str | None = None,
        city: str | None = None,
        state: str | None = None,
        zip_code: str | None = None,
        phone: str | None = None,
        email: str | None = None,
        website: str | None = None,
        include_rejected: bool = False,
        limit: int = 20,
        offset: int = 0,
    ) -> SearchResponse:
        """Multi-field search across locations."""
        conditions: list[str] = []
        params: dict = {"limit": limit, "offset": offset}

        if not include_rejected:
            conditions.append(
                "(l.validation_status != 'rejected' OR l.validation_status IS NULL)"
            )

        if q:
            conditions.append(
                "(l.name ILIKE :q OR o.name ILIKE :q "
                "OR a.address_1 ILIKE :q OR a.city ILIKE :q)"
            )
            params["q"] = f"%{q}%"

        if name:
            conditions.append("l.name ILIKE :name")
            params["name"] = f"%{name}%"

        if address:
            conditions.append("a.address_1 ILIKE :address")
            params["address"] = f"%{address}%"

        if city:
            conditions.append("a.city ILIKE :city")
            params["city"] = f"%{city}%"

        if state:
            conditions.append("a.state_province ILIKE :state")
            params["state"] = f"%{state}%"

        if zip_code:
            conditions.append("a.postal_code = :zip_code")
            params["zip_code"] = zip_code

        if phone:
            conditions.append("p.number ILIKE :phone")
            params["phone"] = f"%{phone}%"

        if email:
            conditions.append("o.email ILIKE :email")
            params["email"] = f"%{email}%"

        if website:
            conditions.append("(l.url ILIKE :website OR o.website ILIKE :website)")
            params["website"] = f"%{website}%"

        where_clause = " AND ".join(conditions) if conditions else "TRUE"

        # where_clause is built from hardcoded column names; values are parameterized
        count_sql = text(
            f"SELECT COUNT(DISTINCT l.id) FROM location l LEFT JOIN organization o ON l.organization_id = o.id LEFT JOIN address a ON a.location_id = l.id AND a.address_type = 'physical' LEFT JOIN phone p ON p.location_id = l.id WHERE {where_clause}"  # nosec B608
        )
        count_result = await self.session.execute(count_sql, params)
        total = count_result.scalar() or 0

        query_sql = text(
            f"SELECT DISTINCT ON (l.id) l.id, l.name, o.name AS organization_name, a.address_1, a.city, a.state_province AS state, a.postal_code, l.latitude, l.longitude, p.number AS phone, o.email, l.url AS website, l.description, l.confidence_score, l.validation_status FROM location l LEFT JOIN organization o ON l.organization_id = o.id LEFT JOIN address a ON a.location_id = l.id AND a.address_type = 'physical' LEFT JOIN phone p ON p.location_id = l.id WHERE {where_clause} ORDER BY l.id LIMIT :limit OFFSET :offset"  # nosec B608
        )
        result = await self.session.execute(query_sql, params)
        rows = result.fetchall()

        results = [
            LocationResult(
                id=row.id,
                name=row.name,
                organization_name=row.organization_name,
                address_1=row.address_1,
                city=row.city,
                state=row.state,
                postal_code=row.postal_code,
                latitude=float(row.latitude) if row.latitude else None,
                longitude=float(row.longitude) if row.longitude else None,
                phone=row.phone,
                email=row.email,
                website=row.website,
                description=row.description,
                confidence_score=row.confidence_score,
                validation_status=row.validation_status,
            )
            for row in rows
        ]

        return SearchResponse(results=results, total=total, limit=limit, offset=offset)

    # ------------------------------------------------------------------
    # Get location detail
    # ------------------------------------------------------------------

    async def get_location(self, location_id: str) -> LocationDetail | None:
        """Get a location with all its source records."""
        loc_sql = text(
            """
            SELECT DISTINCT ON (l.id)
                l.id, l.name,
                o.name AS organization_name,
                a.address_1, a.city,
                a.state_province AS state, a.postal_code,
                l.latitude, l.longitude,
                p.number AS phone, o.email,
                l.url AS website, l.description,
                l.confidence_score, l.validation_status
            FROM location l
            LEFT JOIN organization o ON l.organization_id = o.id
            LEFT JOIN address a ON a.location_id = l.id AND a.address_type = 'physical'
            LEFT JOIN phone p ON p.location_id = l.id
            WHERE l.id = :location_id
            ORDER BY l.id
            """
        )
        result = await self.session.execute(loc_sql, {"location_id": location_id})
        row = result.fetchone()
        if not row:
            return None

        location = LocationResult(
            id=row.id,
            name=row.name,
            organization_name=row.organization_name,
            address_1=row.address_1,
            city=row.city,
            state=row.state,
            postal_code=row.postal_code,
            latitude=float(row.latitude) if row.latitude else None,
            longitude=float(row.longitude) if row.longitude else None,
            phone=row.phone,
            email=row.email,
            website=row.website,
            description=row.description,
            confidence_score=row.confidence_score,
            validation_status=row.validation_status,
        )

        src_sql = text(
            """
            SELECT id, scraper_id, name, description, latitude, longitude,
                   source_type, confidence_score, validation_status,
                   updated_by, created_at, updated_at
            FROM location_source
            WHERE location_id = :location_id
            ORDER BY created_at DESC
            """
        )
        src_result = await self.session.execute(src_sql, {"location_id": location_id})
        sources = [
            SourceRecord(
                id=s.id,
                scraper_id=s.scraper_id,
                name=s.name,
                description=s.description,
                latitude=float(s.latitude) if s.latitude else None,
                longitude=float(s.longitude) if s.longitude else None,
                source_type=s.source_type,
                confidence_score=s.confidence_score,
                validation_status=s.validation_status,
                updated_by=s.updated_by,
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
            for s in src_result.fetchall()
        ]

        return LocationDetail(location=location, sources=sources)

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    async def get_history(
        self,
        location_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> HistoryResponse | None:
        """Get the audit trail for a location."""
        check = await self.session.execute(
            text("SELECT id FROM location WHERE id = :id"),
            {"id": location_id},
        )
        if not check.fetchone():
            return None

        count_sql = text(
            "SELECT COUNT(*) FROM change_audit WHERE location_id = :location_id"
        )
        count_result = await self.session.execute(
            count_sql, {"location_id": location_id}
        )
        total = count_result.scalar() or 0

        query_sql = text(
            """
            SELECT id, location_id, action, changed_fields, previous_values,
                   new_values, api_key_id, api_key_name, source_ip, user_agent,
                   caller_context, created_at
            FROM change_audit
            WHERE location_id = :location_id
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
            """
        )
        result = await self.session.execute(
            query_sql,
            {"location_id": location_id, "limit": limit, "offset": offset},
        )

        entries = [
            AuditEntry(
                id=row.id,
                location_id=row.location_id,
                action=row.action,
                changed_fields=row.changed_fields,
                previous_values=row.previous_values,
                new_values=row.new_values,
                api_key_id=row.api_key_id,
                api_key_name=row.api_key_name,
                source_ip=row.source_ip,
                user_agent=row.user_agent,
                caller_context=row.caller_context,
                created_at=row.created_at,
            )
            for row in result.fetchall()
        ]

        return HistoryResponse(
            location_id=location_id,
            entries=entries,
            total=total,
        )
