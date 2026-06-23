"""Pydantic schemas for the auth module."""

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    # Optional — only needed if the same email exists across multiple tenants.
    # In the pilot (single tenant) this can be omitted.
    tenant_subdomain: str | None = None


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str
