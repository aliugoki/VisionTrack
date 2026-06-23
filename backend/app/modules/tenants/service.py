"""Tenant service — read + update current tenant.

Multi-tenant safety:
  All operations key off `current_user.tenant_id` from the JWT. The
  router never accepts a tenant_id parameter from clients. This is
  by design: the only tenant a user can ever touch is their own.

  System-level tenant operations (creating new tenants, suspending
  others) are routed through SYSTEM_TENANT_MANAGE-gated admin
  endpoints, NOT exposed here.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.modules.tenants.models import Tenant
from app.modules.tenants.schemas import TenantUpdate


log = get_logger("tenants.service")


async def get_tenant(db: AsyncSession, tenant_id: UUID) -> Tenant | None:
    """Load a tenant by ID. Returns None if not found."""
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    return result.scalar_one_or_none()


async def update_tenant(
    db: AsyncSession, tenant: Tenant, payload: TenantUpdate
) -> Tenant:
    """Apply partial update to a tenant. Only sets fields that were
    explicitly provided (None values are no-ops).

    Validation already happened in the Pydantic schema (timezone,
    name length, etc.) — this layer is pure assignment + commit.
    """
    changed_fields: list[str] = []

    if payload.name is not None and payload.name != tenant.name:
        tenant.name = payload.name
        changed_fields.append("name")
    if payload.timezone is not None and payload.timezone != tenant.timezone:
        tenant.timezone = payload.timezone
        changed_fields.append("timezone")
    if payload.settings is not None:
        # Merge into existing settings rather than replace, so a partial
        # PATCH doesn't accidentally clobber other keys.
        merged = dict(tenant.settings or {})
        merged.update(payload.settings)
        tenant.settings = merged
        changed_fields.append("settings")
    if payload.is_active is not None and payload.is_active != tenant.is_active:
        tenant.is_active = payload.is_active
        changed_fields.append("is_active")
    if (
        payload.recording_retention_days is not None
        and payload.recording_retention_days != tenant.recording_retention_days
    ):
        tenant.recording_retention_days = payload.recording_retention_days
        changed_fields.append("recording_retention_days")

    if not changed_fields:
        log.info("tenant.update_noop", tenant_id=str(tenant.id))
        return tenant

    try:
        await db.flush()
        await db.refresh(tenant)
    except IntegrityError as e:
        # Future-proofing: when we add subdomain edits (probably never),
        # uniqueness violations would surface here.
        await db.rollback()
        raise

    log.info(
        "tenant.updated",
        tenant_id=str(tenant.id),
        fields=changed_fields,
    )
    return tenant
