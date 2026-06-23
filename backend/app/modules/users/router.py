"""User HTTP routes.

Includes a /me endpoint that any authenticated user can call, plus
permission-gated CRUD on /users.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.db import get_db
from app.core.deps import RequirePermission, get_current_user
from app.core.permissions import (
    USER_CREATE,
    USER_DELETE,
    USER_READ,
    USER_UPDATE,
)
from app.core.security import hash_password, verify_password
from app.modules.roles.models import Role
from app.modules.users.models import User
from app.modules.users.schemas import (
    UserCreate,
    UserPasswordUpdate,
    UserRead,
    UserUpdate,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead)
async def read_me(current_user: User = Depends(get_current_user)) -> User:
    """Current user's profile, including assigned roles."""
    return current_user


@router.put("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_my_password(
    payload: UserPasswordUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = Depends(get_current_user),
) -> None:
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    current_user.password_hash = hash_password(payload.new_password)
    await db.flush()


@router.get("", response_model=list[UserRead])
async def list_users(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = Depends(RequirePermission(USER_READ)),
) -> list[User]:
    result = await db.execute(
        select(User)
        .where(User.tenant_id == current_user.tenant_id)
        .options(selectinload(User.roles))
        .order_by(User.full_name)
    )
    return list(result.scalars().all())


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = Depends(RequirePermission(USER_CREATE)),
) -> User:
    # Email uniqueness within the tenant
    existing = await db.execute(
        select(User).where(
            User.tenant_id == current_user.tenant_id,
            User.email == payload.email.lower(),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists in your tenant",
        )

    # Validate that all requested roles belong to this tenant
    roles: list[Role] = []
    if payload.role_ids:
        result = await db.execute(
            select(Role).where(
                Role.id.in_(payload.role_ids),
                Role.tenant_id == current_user.tenant_id,
            )
        )
        roles = list(result.scalars().all())
        if len(roles) != len(set(payload.role_ids)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="One or more role_ids are invalid for this tenant",
            )

    user = User(
        tenant_id=current_user.tenant_id,
        email=payload.email.lower(),
        full_name=payload.full_name,
        locale=payload.locale,
        is_active=payload.is_active,
        password_hash=hash_password(payload.password),
        roles=roles,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user, attribute_names=["roles"])
    return user


@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = Depends(RequirePermission(USER_READ)),
) -> User:
    return await _load_user(db, user_id, current_user.tenant_id)


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: UUID,
    payload: UserUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = Depends(RequirePermission(USER_UPDATE)),
) -> User:
    user = await _load_user(db, user_id, current_user.tenant_id)

    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.locale is not None:
        user.locale = payload.locale
    if payload.is_active is not None:
        user.is_active = payload.is_active

    if payload.role_ids is not None:
        result = await db.execute(
            select(Role).where(
                Role.id.in_(payload.role_ids),
                Role.tenant_id == current_user.tenant_id,
            )
        )
        roles = list(result.scalars().all())
        if len(roles) != len(set(payload.role_ids)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="One or more role_ids are invalid for this tenant",
            )
        user.roles = roles

    await db.flush()
    await db.refresh(user, attribute_names=["roles"])
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = Depends(RequirePermission(USER_DELETE)),
) -> None:
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account",
        )
    user = await _load_user(db, user_id, current_user.tenant_id)
    await db.delete(user)


async def _load_user(db: AsyncSession, user_id: UUID, tenant_id: UUID) -> User:
    result = await db.execute(
        select(User)
        .where(User.id == user_id, User.tenant_id == tenant_id)
        .options(selectinload(User.roles))
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return user
