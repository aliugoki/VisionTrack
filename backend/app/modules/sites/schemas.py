"""Pydantic schemas for the sites module."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SiteBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    address: str | None = Field(None, max_length=500)
    timezone: str = Field("Asia/Karachi", max_length=64)


class SiteCreate(SiteBase):
    pass


class SiteUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=255)
    address: str | None = Field(None, max_length=500)
    timezone: str | None = Field(None, max_length=64)
    is_active: bool | None = None


class SiteRead(SiteBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    is_active: bool
    # See models.py — column is `attributes` not `metadata` to avoid
    # shadowing SQLAlchemy Base.metadata. Field exposed as `attributes`
    # in the API too for consistency.
    attributes: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    camera_count: int = 0
