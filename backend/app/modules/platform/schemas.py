"""Pydantic schemas for the platform (cross-tenant) module."""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class PlatformTenant(BaseModel):
    id: UUID
    name: str
    subdomain: str
    external_company_id: str | None = None
    is_active: bool
    employee_count: int = 0
    camera_count: int = 0


class PlatformTenantList(BaseModel):
    total: int
    rows: list[PlatformTenant]
