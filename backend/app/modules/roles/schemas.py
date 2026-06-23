"""Pydantic schemas for the roles module."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.permissions import ALL_PERMISSIONS


class RoleBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    description: str | None = None
    permissions: list[str] = Field(default_factory=list)

    @field_validator("permissions")
    @classmethod
    def validate_permission_keys(cls, v: list[str]) -> list[str]:
        unknown = set(v) - ALL_PERMISSIONS
        if unknown:
            raise ValueError(f"Unknown permissions: {sorted(unknown)}")
        return sorted(set(v))


class RoleCreate(RoleBase):
    pass


class RoleUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=100)
    description: str | None = None
    permissions: list[str] | None = None

    @field_validator("permissions")
    @classmethod
    def validate_permission_keys(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        unknown = set(v) - ALL_PERMISSIONS
        if unknown:
            raise ValueError(f"Unknown permissions: {sorted(unknown)}")
        return sorted(set(v))


class RoleRead(RoleBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    is_system: bool
    created_at: datetime
    updated_at: datetime


class PermissionCatalogItem(BaseModel):
    key: str
    group: str
    label: str
