"""Tenant provisioning — create an isolated VisionTrack tenant for a company.

Multi-tenant Phase 1: given a company (FaceTrack company_id + name), ensure a
dedicated tenant exists with its default roles, a local admin user, and a default
site. Idempotent on ``external_company_id``. Reused by the backfill script and,
later, by auto-provision on company sync (Phase 4).

Auth model: Phase 1 provisions a **local admin user** per tenant (Option A in
docs/MULTI_TENANT_SCOPING.md) with a default password to be rotated.
"""
from __future__ import annotations

import hashlib
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.core.seed import _ensure_default_roles
from app.modules.sites.models import Site
from app.modules.tenants.models import Tenant
from app.modules.users.models import User

# Default admin password for a freshly provisioned tenant — rotate after handover.
DEFAULT_ADMIN_PASSWORD = "ChangeMe123!"


def _slug(name: str | None, ext: str) -> str:
    base = re.sub(r"[^a-z0-9-]+", "-", (name or ext).lower()).strip("-")[:50]
    return base or "company"


async def _unique_subdomain(db: AsyncSession, base: str, ext: str) -> str:
    sub = base
    for attempt in range(20):
        exists = (await db.execute(
            select(Tenant.id).where(Tenant.subdomain == sub)
        )).scalar_one_or_none()
        if not exists:
            return sub
        suffix = hashlib.sha1(f"{ext}-{attempt}".encode()).hexdigest()[:6]
        sub = f"{base[:50]}-{suffix}"
    return f"{base[:40]}-{ext[:8]}"


async def provision_tenant_for_company(
    db: AsyncSession,
    *,
    external_company_id: str,
    name: str | None,
    admin_username: str | None = None,
) -> tuple[Tenant, bool]:
    """Ensure a tenant exists for ``external_company_id``. Returns
    ``(tenant, created)``. Seeds default roles + a local admin user + a site on
    creation. Caller commits."""
    existing = (await db.execute(
        select(Tenant).where(Tenant.external_company_id == external_company_id)
    )).scalar_one_or_none()
    if existing is not None:
        return existing, False

    display = name or external_company_id
    subdomain = await _unique_subdomain(db, _slug(name, external_company_id), external_company_id)

    tenant = Tenant(
        name=display,
        subdomain=subdomain,
        plan="active",
        external_company_id=external_company_id,
    )
    db.add(tenant)
    await db.flush()

    admin_role = await _ensure_default_roles(db, tenant.id)

    email = f"admin@{subdomain}.visiontrack.local"
    db.add(User(
        tenant_id=tenant.id,
        email=email,
        full_name=f"{display} Admin",
        locale="en",
        is_active=True,
        is_superuser=False,   # tenant admin via the Tenant Admin role, not platform
        password_hash=hash_password(DEFAULT_ADMIN_PASSWORD),
        roles=[admin_role],
    ))
    db.add(Site(tenant_id=tenant.id, name="Main Site", timezone="UTC"))
    await db.flush()
    return tenant, True
