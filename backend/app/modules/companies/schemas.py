"""Pydantic schemas for the companies module."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    external_id: str | None = None
    name: str
    admin_username: str | None = None
    status: str | None = None
    source: str
    is_active: bool
    synced_at: datetime | None = None
    employee_count: int = 0


class CompanyListResponse(BaseModel):
    total: int
    rows: list[CompanyRead]


class CompanyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    admin_username: str | None = Field(None, max_length=255)
    status: str | None = Field(None, max_length=64)
    is_active: bool = True


class CompanyUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    admin_username: str | None = Field(None, max_length=255)
    status: str | None = Field(None, max_length=64)
    is_active: bool | None = None
