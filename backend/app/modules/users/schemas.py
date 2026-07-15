"""Pydantic schemas for the users module."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.modules.roles.schemas import RoleRead


class UserBase(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=255)
    locale: str = Field("en", pattern=r"^(en|ar)$")
    is_active: bool = True


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=128)
    role_ids: list[UUID] = Field(default_factory=list)


class UserUpdate(BaseModel):
    full_name: str | None = Field(None, min_length=1, max_length=255)
    locale: str | None = Field(None, pattern=r"^(en|ar)$")
    is_active: bool | None = None
    role_ids: list[UUID] | None = None


class UserPasswordUpdate(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=128)


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    # Relax email on OUTPUT: stored service-account emails (e.g. the AI worker's
    # ai-worker@system.local) use reserved domains that EmailStr rejects. Input
    # is still validated via UserCreate.email (EmailStr).
    email: str
    id: UUID
    tenant_id: UUID
    is_superuser: bool
    is_platform_admin: bool = False
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime
    roles: list[RoleRead] = Field(default_factory=list)
