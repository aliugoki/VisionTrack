"""Reusable FastAPI dependencies.

These are the building blocks every protected route uses:

- `get_current_user` — decodes the JWT, loads the user, validates state
- `get_current_tenant_id` — extracts tenant from token for query scoping
- `RequirePermission` — declarative permission check
- `RequireAnyPermission` — allows access if user has at least one
- `RequireAllPermissions` — requires every listed permission
"""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.db import get_db
from app.core.security import decode_token


# We declare the OAuth2 scheme here so the OpenAPI docs render a login form.
# The actual login endpoint lives in app.modules.auth.router.
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_PREFIX}/auth/login",
    auto_error=True,
)


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Decode the JWT and load the User from the database.

    Imported lazily to avoid circular imports — User model imports from
    Base which is in core.db, but we don't want core.deps to import
    a specific module's models at module load time.
    """
    from app.modules.users.models import User

    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_token(token)
        if payload.get("typ") != "access":
            raise credentials_exc
        user_id_str = payload.get("sub")
        if not user_id_str:
            raise credentials_exc
        user_id = UUID(user_id_str)
    except (JWTError, ValueError):
        raise credentials_exc

    result = await db.execute(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.roles))
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exc
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    return user


async def get_current_tenant_id(
    token: Annotated[str, Depends(oauth2_scheme)],
) -> UUID:
    """Extract tenant ID from token without loading the user.

    Useful for high-frequency endpoints where we just need to scope a query.
    """
    try:
        payload = decode_token(token)
        return UUID(payload["tid"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid tenant context",
        )


def _collect_user_permissions(user) -> set[str]:
    """Flatten all permissions across a user's roles."""
    perms: set[str] = set()
    for role in user.roles:
        perms.update(role.permissions or [])
    return perms


class RequirePermission:
    """Dependency factory: require a single permission to access a route.

    Usage:
        @router.post("/cameras", dependencies=[Depends(RequirePermission(CAMERA_CREATE))])
    """

    def __init__(self, permission: str):
        self.permission = permission

    async def __call__(
        self,
        current_user=Depends(get_current_user),
    ):
        if self.permission not in _collect_user_permissions(current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {self.permission}",
            )
        return current_user


class RequireAnyPermission:
    """Allow access if the user has at least one of the listed permissions."""

    def __init__(self, *permissions: str):
        self.permissions = set(permissions)

    async def __call__(self, current_user=Depends(get_current_user)):
        user_perms = _collect_user_permissions(current_user)
        if not (self.permissions & user_perms):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of: {', '.join(sorted(self.permissions))}",
            )
        return current_user


class RequireAllPermissions:
    """Require every listed permission to access the route."""

    def __init__(self, *permissions: str):
        self.permissions = set(permissions)

    async def __call__(self, current_user=Depends(get_current_user)):
        user_perms = _collect_user_permissions(current_user)
        missing = self.permissions - user_perms
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permissions: {', '.join(sorted(missing))}",
            )
        return current_user
