"""Pydantic schemas for the platform (cross-tenant) module."""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class PlatformTenant(BaseModel):
    id: UUID
    name: str
    subdomain: str
    external_company_id: str | None = None
    plan: str
    timezone: str
    recording_retention_days: int
    is_active: bool
    max_cameras: int = 0
    employee_count: int = 0
    camera_count: int = 0
    user_count: int = 0


class PlatformTenantList(BaseModel):
    total: int
    rows: list[PlatformTenant]


class PlatformTenantUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=255)
    is_active: bool | None = None
    plan: str | None = Field(None, max_length=50)
    timezone: str | None = Field(None, max_length=64)
    recording_retention_days: int | None = Field(None, ge=1, le=3650)
    # Per-tenant camera quota (0 = unlimited), stored in tenant.settings.
    max_cameras: int | None = Field(None, ge=0, le=100000)
