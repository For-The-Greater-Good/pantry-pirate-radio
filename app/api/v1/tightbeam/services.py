# ruff: noqa: S608
# (Dynamic WHERE clauses use hardcoded column names; all user values are parameterized.)
"""Tightbeam service layer — search, update, soft-delete, restore, history.

All writes are append-only. Human corrections create new location_source rows.
Soft-deletes create rejected validation_status records. Every mutation is
recorded in the change_audit table with full provenance.
"""

from uuid import uuid4

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    AuditEntry,
    CallerIdentity,
    HistoryResponse,
    LocationDetail,
    LocationResult,
    LocationUpdateResponse,
    MutationResponse,
    SearchResponse,
    SourceRecord,
)

logger = structlog.get_logger(__name__)


class TightbeamService:
    """Service layer for Tightbeam location management."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

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
    # Update (append-only)
    # ------------------------------------------------------------------

    async def update_location(
        self,
        location_id: str,
        name: str | None = None,
        address_1: str | None = None,
        city: str | None = None,
        state: str | None = None,
        postal_code: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        phone: str | None = None,
        email: str | None = None,
        website: str | None = None,
        description: str | None = None,
        caller: CallerIdentity | None = None,
        caller_context: dict | None = None,
    ) -> LocationUpdateResponse:
        """Create an append-only human correction for a location.

        Creates a new location_source row with scraper_id='human_update' and
        confidence_score=100. Updates the canonical location record. Records
        everything in change_audit.
        """
        # Verify location exists
        check_sql = text(
            "SELECT id, name, latitude, longitude, description, url "
            "FROM location WHERE id = :id"
        )
        result = await self.session.execute(check_sql, {"id": location_id})
        existing = result.fetchone()
        if not existing:
            return None  # type: ignore[return-value]

        # Build previous/new values for audit
        previous_values: dict = {}
        new_values: dict = {}
        changed_fields: list[str] = []

        field_map = {
            "name": (name, existing.name),
            "latitude": (latitude, existing.latitude),
            "longitude": (longitude, existing.longitude),
            "description": (description, existing.description),
            "website": (website, existing.url),
        }

        for field, (new_val, old_val) in field_map.items():
            if new_val is not None:
                changed_fields.append(field)
                previous_values[field] = old_val
                new_values[field] = new_val

        # Address fields require a separate lookup
        addr_sql = text(
            "SELECT address_1, city, state_province, postal_code "
            "FROM address WHERE location_id = :id AND address_type = 'physical' "
            "LIMIT 1"
        )
        addr_result = await self.session.execute(addr_sql, {"id": location_id})
        addr_row = addr_result.fetchone()

        addr_fields = {
            "address_1": (address_1, addr_row.address_1 if addr_row else None),
            "city": (city, addr_row.city if addr_row else None),
            "state": (state, addr_row.state_province if addr_row else None),
            "postal_code": (
                postal_code,
                addr_row.postal_code if addr_row else None,
            ),
        }
        for field, (new_val, old_val) in addr_fields.items():
            if new_val is not None:
                changed_fields.append(field)
                previous_values[field] = old_val
                new_values[field] = new_val

        # Phone requires lookup too
        if phone is not None:
            phone_sql = text("SELECT number FROM phone WHERE location_id = :id LIMIT 1")
            phone_result = await self.session.execute(phone_sql, {"id": location_id})
            phone_row = phone_result.fetchone()
            changed_fields.append("phone")
            previous_values["phone"] = phone_row.number if phone_row else None
            new_values["phone"] = phone

        if email is not None:
            changed_fields.append("email")
            new_values["email"] = email

        # 1. Create new location_source row (append-only)
        source_id = str(uuid4())
        insert_source = text(
            """
            INSERT INTO location_source
                (id, location_id, scraper_id, name, description, latitude, longitude,
                 source_type, confidence_score, validation_status, updated_by, created_at, updated_at)
            VALUES
                (:id, :location_id, 'human_update', :name, :description,
                 :latitude, :longitude, 'human_update', 100, 'verified',
                 :updated_by, NOW(), NOW())
            """
        )
        src_name = name or existing.name
        src_lat = latitude if latitude is not None else float(existing.latitude)
        src_lon = longitude if longitude is not None else float(existing.longitude)
        await self.session.execute(
            insert_source,
            {
                "id": source_id,
                "location_id": location_id,
                "name": src_name,
                "description": description or existing.description,
                "latitude": src_lat,
                "longitude": src_lon,
                "updated_by": caller.api_key_name if caller else None,
            },
        )

        # 2. Update canonical location
        update_parts: list[str] = []
        update_params: dict = {"id": location_id}

        if name is not None:
            update_parts.append("name = :name")
            update_params["name"] = name
        if latitude is not None:
            update_parts.append("latitude = :latitude")
            update_params["latitude"] = latitude
        if longitude is not None:
            update_parts.append("longitude = :longitude")
            update_params["longitude"] = longitude
        if description is not None:
            update_parts.append("description = :description")
            update_params["description"] = description
        if website is not None:
            update_parts.append("url = :website")
            update_params["website"] = website

        if update_parts:
            # update_parts contains hardcoded column names; values are parameterized
            loc_update = f"UPDATE location SET {', '.join(update_parts)} WHERE id = :id"  # nosec B608
            await self.session.execute(text(loc_update), update_params)

        # Update address if any address fields changed
        addr_update_parts: list[str] = []
        addr_update_params: dict = {"location_id": location_id}
        if address_1 is not None:
            addr_update_parts.append("address_1 = :address_1")
            addr_update_params["address_1"] = address_1
        if city is not None:
            addr_update_parts.append("city = :city")
            addr_update_params["city"] = city
        if state is not None:
            addr_update_parts.append("state_province = :state")
            addr_update_params["state"] = state
        if postal_code is not None:
            addr_update_parts.append("postal_code = :postal_code")
            addr_update_params["postal_code"] = postal_code

        if addr_update_parts:
            addr_update = f"UPDATE address SET {', '.join(addr_update_parts)} WHERE location_id = :location_id AND address_type = 'physical'"  # nosec B608
            await self.session.execute(text(addr_update), addr_update_params)

        # Update phone if changed
        if phone is not None:
            await self.session.execute(
                text(
                    "UPDATE phone SET number = :phone WHERE location_id = :location_id"
                ),
                {"phone": phone, "location_id": location_id},
            )

        # 3. Record audit entry
        audit_id = str(uuid4())
        merged_context = caller_context or {}
        if caller and caller.caller_context:
            merged_context.update(caller.caller_context)

        import json

        audit_sql = text(
            """
            INSERT INTO change_audit
                (id, location_id, action, changed_fields, previous_values,
                 new_values, api_key_id, api_key_name, source_ip, user_agent,
                 caller_context)
            VALUES
                (:id, :location_id, 'update', :changed_fields, :previous_values,
                 :new_values, :api_key_id, :api_key_name, :source_ip, :user_agent,
                 :caller_context)
            """
        )
        await self.session.execute(
            audit_sql,
            {
                "id": audit_id,
                "location_id": location_id,
                "changed_fields": json.dumps(changed_fields),
                "previous_values": json.dumps(previous_values),
                "new_values": json.dumps(new_values),
                "api_key_id": caller.api_key_id if caller else None,
                "api_key_name": caller.api_key_name if caller else None,
                "source_ip": caller.source_ip if caller else None,
                "user_agent": caller.user_agent if caller else None,
                "caller_context": (
                    json.dumps(merged_context) if merged_context else None
                ),
            },
        )

        await self.session.commit()

        logger.info(
            "tightbeam_location_updated",
            location_id=location_id,
            changed_fields=changed_fields,
            source_id=source_id,
            audit_id=audit_id,
        )

        return LocationUpdateResponse(
            location_id=location_id,
            source_id=source_id,
            audit_id=audit_id,
        )

    # ------------------------------------------------------------------
    # Soft-delete
    # ------------------------------------------------------------------

    async def soft_delete(
        self,
        location_id: str,
        reason: str | None = None,
        caller: CallerIdentity | None = None,
        caller_context: dict | None = None,
    ) -> MutationResponse | None:
        """Soft-delete a location by setting validation_status to 'rejected'."""
        check = await self.session.execute(
            text("SELECT id, name FROM location WHERE id = :id"),
            {"id": location_id},
        )
        existing = check.fetchone()
        if not existing:
            return None

        # Update canonical location
        await self.session.execute(
            text("UPDATE location SET validation_status = 'rejected' WHERE id = :id"),
            {"id": location_id},
        )

        # Create source record for the deletion
        source_id = str(uuid4())
        await self.session.execute(
            text(
                """
                INSERT INTO location_source
                    (id, location_id, scraper_id, name, description, latitude, longitude,
                     source_type, confidence_score, validation_status, updated_by)
                VALUES
                    (:id, :location_id, 'human_update', :name, :reason, 0, 0,
                     'human_update', 0, 'rejected', :updated_by)
                """
            ),
            {
                "id": source_id,
                "location_id": location_id,
                "name": existing.name or "deleted",
                "reason": reason,
                "updated_by": caller.api_key_name if caller else None,
            },
        )

        # Audit
        import json

        audit_id = str(uuid4())
        merged_context = caller_context or {}
        if caller and caller.caller_context:
            merged_context.update(caller.caller_context)

        await self.session.execute(
            text(
                """
                INSERT INTO change_audit
                    (id, location_id, action, changed_fields, previous_values,
                     new_values, api_key_id, api_key_name, source_ip, user_agent,
                     caller_context)
                VALUES
                    (:id, :location_id, 'soft_delete', :changed_fields,
                     :previous_values, :new_values,
                     :api_key_id, :api_key_name, :source_ip, :user_agent,
                     :caller_context)
                """
            ),
            {
                "id": audit_id,
                "location_id": location_id,
                "changed_fields": json.dumps(["validation_status"]),
                "previous_values": json.dumps({"validation_status": None}),
                "new_values": json.dumps(
                    {"validation_status": "rejected", "reason": reason}
                ),
                "api_key_id": caller.api_key_id if caller else None,
                "api_key_name": caller.api_key_name if caller else None,
                "source_ip": caller.source_ip if caller else None,
                "user_agent": caller.user_agent if caller else None,
                "caller_context": (
                    json.dumps(merged_context) if merged_context else None
                ),
            },
        )

        await self.session.commit()

        logger.info(
            "tightbeam_location_soft_deleted",
            location_id=location_id,
            reason=reason,
            audit_id=audit_id,
        )

        return MutationResponse(
            location_id=location_id,
            audit_id=audit_id,
            message="Location soft-deleted successfully",
        )

    # ------------------------------------------------------------------
    # Restore
    # ------------------------------------------------------------------

    async def restore(
        self,
        location_id: str,
        reason: str | None = None,
        caller: CallerIdentity | None = None,
        caller_context: dict | None = None,
    ) -> MutationResponse | None:
        """Restore a soft-deleted location by setting validation_status to 'verified'."""
        check = await self.session.execute(
            text("SELECT id, name FROM location WHERE id = :id"),
            {"id": location_id},
        )
        existing = check.fetchone()
        if not existing:
            return None

        await self.session.execute(
            text("UPDATE location SET validation_status = 'verified' WHERE id = :id"),
            {"id": location_id},
        )

        # Create source record for the restore
        source_id = str(uuid4())
        await self.session.execute(
            text(
                """
                INSERT INTO location_source
                    (id, location_id, scraper_id, name, description, latitude, longitude,
                     source_type, confidence_score, validation_status, updated_by)
                VALUES
                    (:id, :location_id, 'human_update', :name, :reason, 0, 0,
                     'human_update', 100, 'verified', :updated_by)
                """
            ),
            {
                "id": source_id,
                "location_id": location_id,
                "name": existing.name or "restored",
                "reason": reason,
                "updated_by": caller.api_key_name if caller else None,
            },
        )

        # Audit
        import json

        audit_id = str(uuid4())
        merged_context = caller_context or {}
        if caller and caller.caller_context:
            merged_context.update(caller.caller_context)

        await self.session.execute(
            text(
                """
                INSERT INTO change_audit
                    (id, location_id, action, changed_fields, previous_values,
                     new_values, api_key_id, api_key_name, source_ip, user_agent,
                     caller_context)
                VALUES
                    (:id, :location_id, 'restore', :changed_fields,
                     :previous_values, :new_values,
                     :api_key_id, :api_key_name, :source_ip, :user_agent,
                     :caller_context)
                """
            ),
            {
                "id": audit_id,
                "location_id": location_id,
                "changed_fields": json.dumps(["validation_status"]),
                "previous_values": json.dumps({"validation_status": "rejected"}),
                "new_values": json.dumps(
                    {"validation_status": "verified", "reason": reason}
                ),
                "api_key_id": caller.api_key_id if caller else None,
                "api_key_name": caller.api_key_name if caller else None,
                "source_ip": caller.source_ip if caller else None,
                "user_agent": caller.user_agent if caller else None,
                "caller_context": (
                    json.dumps(merged_context) if merged_context else None
                ),
            },
        )

        await self.session.commit()

        logger.info(
            "tightbeam_location_restored",
            location_id=location_id,
            reason=reason,
            audit_id=audit_id,
        )

        return MutationResponse(
            location_id=location_id,
            audit_id=audit_id,
            message="Location restored successfully",
        )

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
