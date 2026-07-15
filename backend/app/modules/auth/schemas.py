"""Pydantic schemas for the auth module."""

from pydantic import BaseModel


class LoginRequest(BaseModel):
    # `str`, not EmailStr: auth matches the stored email + password, and stored
    # emails may use reserved domains (e.g. provisioned admin@<sub>.visiontrack.local
    # or the ai-worker service account) that EmailStr rejects.
    email: str
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
