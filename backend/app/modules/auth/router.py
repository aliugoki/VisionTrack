"""Authentication routes: login, refresh, logout."""

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.db import get_db
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.modules.auth.schemas import LoginRequest, RefreshRequest, TokenPair
from app.modules.tenants.models import Tenant
from app.modules.users.models import User

router = APIRouter(prefix="/auth", tags=["auth"])
log = get_logger("auth")


@router.post("/login", response_model=TokenPair)
async def login_json(
    payload: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenPair:
    """JSON login — the path the React frontend uses."""
    user = await _authenticate(db, payload.email, payload.password, payload.tenant_subdomain)
    return await _issue_tokens(db, user)


@router.post("/login/oauth", response_model=TokenPair, include_in_schema=False)
async def login_oauth_form(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenPair:
    """OAuth2 password-flow login — used by the Swagger UI authorize button."""
    user = await _authenticate(db, form.username, form.password, None)
    return await _issue_tokens(db, user)


@router.post("/refresh", response_model=TokenPair)
async def refresh_tokens(
    payload: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenPair:
    try:
        claims = decode_token(payload.refresh_token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )
    if claims.get("typ") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not a refresh token",
        )

    user_id = UUID(claims["sub"])
    result = await db.execute(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.roles))
    )
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer valid",
        )

    return await _issue_tokens(db, user, touch_last_login=False)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout() -> None:
    """Stateless logout — the frontend just drops the tokens.

    A real production deployment will add a Redis blocklist of revoked
    refresh tokens; we'll wire that up alongside the alerts module.
    """
    return None


# -- internals -----------------------------------------------------------------

async def _authenticate(
    db: AsyncSession,
    email: str,
    password: str,
    tenant_subdomain: str | None,
) -> User:
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password",
    )

    stmt = (
        select(User)
        .where(User.email == email.lower())
        .options(selectinload(User.roles))
    )

    if tenant_subdomain:
        tenant_q = await db.execute(
            select(Tenant).where(Tenant.subdomain == tenant_subdomain.lower())
        )
        tenant = tenant_q.scalar_one_or_none()
        if tenant is None:
            raise invalid
        stmt = stmt.where(User.tenant_id == tenant.id)

    result = await db.execute(stmt)
    users = list(result.scalars().all())

    # If multiple users match (same email across tenants) and no subdomain
    # was given, fail clearly — don't pick one arbitrarily.
    if not users:
        raise invalid
    if len(users) > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Multiple accounts found for this email — please specify your tenant",
        )

    user = users[0]
    if not user.is_active or not verify_password(password, user.password_hash):
        raise invalid

    return user


async def _issue_tokens(
    db: AsyncSession, user: User, touch_last_login: bool = True
) -> TokenPair:
    access = create_access_token(user.id, user.tenant_id)
    refresh = create_refresh_token(user.id, user.tenant_id)

    if touch_last_login:
        user.last_login_at = datetime.now(timezone.utc)
        await db.flush()

    log.info("auth.login", user_id=str(user.id), tenant_id=str(user.tenant_id))
    return TokenPair(access_token=access, refresh_token=refresh)
