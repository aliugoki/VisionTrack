"""Pydantic schemas for the tenants module."""

from datetime import datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _validate_timezone(v: str) -> str:
    """Round-trip the value through ZoneInfo to ensure it's a real IANA
    timezone name. Catches typos ('Asia/Karchi'), and rejects abbreviations
    like 'PKT' (not unique globally, ambiguous)."""
    try:
        ZoneInfo(v)
    except ZoneInfoNotFoundError as e:
        raise ValueError(f"unknown timezone: {v}") from e
    return v


class TenantBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    subdomain: str = Field(..., min_length=2, max_length=63, pattern=r"^[a-z0-9-]+$")


class TenantCreate(TenantBase):
    plan: str = "trial"
    # Common Gulf + Pakistan defaults for quick tenant onboarding.
    timezone: str = Field(default="UTC", max_length=64)

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        return _validate_timezone(v)


class TenantUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=255)
    timezone: str | None = Field(None, max_length=64)
    settings: dict[str, Any] | None = None
    is_active: bool | None = None
    recording_retention_days: int | None = Field(None, ge=1, le=3650)
    use_deepstream: bool | None = None

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return _validate_timezone(v)


class TenantRead(TenantBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plan: str
    is_active: bool
    timezone: str
    recording_retention_days: int
    use_deepstream: bool
    settings: dict[str, Any]
    created_at: datetime
    updated_at: datetime
