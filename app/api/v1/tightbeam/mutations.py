# ruff: noqa: S608
"""Tightbeam mutation service — update, soft-delete, restore.

Human corrections create new location_source rows for provenance.
The canonical location, address, and phone tables are updated in place.
Every mutation is recorded in the change_audit table with full provenance.
"""

import json
from uuid import uuid4

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    CallerIdentity,
    LocationUpdateResponse,
    MutationResponse,
)

logger = structlog.get_logger(__name__)


async def _record_audit(
    session: AsyncSession,
    location_id: str,
    action: str,
    changed_fields: list[str],
    previous_values: dict,
    new_values: dict,
    caller: CallerIdentity | None,
    caller_context: dict | None,
) -> str:
    """Insert an audit row into change_audit and return the audit_id."""
    audit_id = str(uuid4())
    merged_context = caller_context or {}
    if caller and caller.caller_context:
        merged_context.update(caller.caller_context)

    await session.execute(
        text(
            """
            INSERT INTO change_audit
                (id, location_id, action, changed_fields, previous_values,
                 new_values, api_key_id, api_key_name, source_ip, user_agent,
                 caller_context)
            VALUES
                (:id, :location_id, :action, :changed_fields, :previous_values,
                 :new_values, :api_key_id, :api_key_name, :source_ip, :user_agent,
                 :caller_context)
            """
        ),
        {
            "id": audit_id,
            "location_id": location_id,
            "action": action,
            "changed_fields": json.dumps(changed_fields),
            "previous_values": json.dumps(previous_values),
            "new_values": json.dumps(new_values),
            "api_key_id": caller.api_key_id if caller else None,
            "api_key_name": caller.api_key_name if caller else None,
            "source_ip": caller.source_ip if caller else None,
            "user_agent": caller.user_agent if caller else None,
            "caller_context": (json.dumps(merged_context) if merged_context else None),
        },
    )
    return audit_id


class TightbeamMutationService:
    """Mutation operations for Tightbeam location management."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

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
        # location_source.latitude is NOT NULL; use 0 sentinel when no value available
        src_lat = (
            latitude
            if latitude is not None
            else (float(existing.latitude) if existing.latitude is not None else 0)
        )
        src_lon = (
            longitude
            if longitude is not None
            else (float(existing.longitude) if existing.longitude is not None else 0)
        )
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
        audit_id = await _record_audit(
            self.session,
            location_id,
            "update",
            changed_fields,
            previous_values,
            new_values,
            caller,
            caller_context,
        )

        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            logger.error(
                "tightbeam_update_failed",
                location_id=location_id,
                exc_info=True,
            )
            raise

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
            text("SELECT id, name, latitude, longitude FROM location WHERE id = :id"),
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

        # Create source record for the deletion — use existing coords for provenance
        source_id = str(uuid4())
        src_lat = float(existing.latitude) if existing.latitude is not None else 0
        src_lon = float(existing.longitude) if existing.longitude is not None else 0
        await self.session.execute(
            text(
                """
                INSERT INTO location_source
                    (id, location_id, scraper_id, name, description, latitude, longitude,
                     source_type, confidence_score, validation_status, updated_by)
                VALUES
                    (:id, :location_id, 'human_update', :name, :reason, :latitude, :longitude,
                     'human_update', 0, 'rejected', :updated_by)
                """
            ),
            {
                "id": source_id,
                "location_id": location_id,
                "name": existing.name or "deleted",
                "reason": reason,
                "latitude": src_lat,
                "longitude": src_lon,
                "updated_by": caller.api_key_name if caller else None,
            },
        )

        # Audit
        audit_id = await _record_audit(
            self.session,
            location_id,
            "soft_delete",
            ["validation_status"],
            {"validation_status": None},
            {"validation_status": "rejected", "reason": reason},
            caller,
            caller_context,
        )

        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            logger.error(
                "tightbeam_soft_delete_failed",
                location_id=location_id,
                exc_info=True,
            )
            raise

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
            text("SELECT id, name, latitude, longitude FROM location WHERE id = :id"),
            {"id": location_id},
        )
        existing = check.fetchone()
        if not existing:
            return None

        await self.session.execute(
            text("UPDATE location SET validation_status = 'verified' WHERE id = :id"),
            {"id": location_id},
        )

        # Create source record for the restore — use existing coords for provenance
        source_id = str(uuid4())
        src_lat = float(existing.latitude) if existing.latitude is not None else 0
        src_lon = float(existing.longitude) if existing.longitude is not None else 0
        await self.session.execute(
            text(
                """
                INSERT INTO location_source
                    (id, location_id, scraper_id, name, description, latitude, longitude,
                     source_type, confidence_score, validation_status, updated_by)
                VALUES
                    (:id, :location_id, 'human_update', :name, :reason, :latitude, :longitude,
                     'human_update', 100, 'verified', :updated_by)
                """
            ),
            {
                "id": source_id,
                "location_id": location_id,
                "name": existing.name or "restored",
                "reason": reason,
                "latitude": src_lat,
                "longitude": src_lon,
                "updated_by": caller.api_key_name if caller else None,
            },
        )

        # Audit
        audit_id = await _record_audit(
            self.session,
            location_id,
            "restore",
            ["validation_status"],
            {"validation_status": "rejected"},
            {"validation_status": "verified", "reason": reason},
            caller,
            caller_context,
        )

        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            logger.error(
                "tightbeam_restore_failed",
                location_id=location_id,
                exc_info=True,
            )
            raise

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
