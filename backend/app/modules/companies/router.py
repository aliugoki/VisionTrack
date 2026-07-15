"""Companies HTTP routes.

  GET    /companies            list (reflected from FaceTrack + native)
  POST   /companies            create a VisionTrack-native company
  PATCH  /companies/{id}       update
  DELETE /companies/{id}       delete

Gated with tenant:read / tenant:update (companies are org-level admin data).
"""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import RequirePermission
from app.core.permissions import TENANT_READ, TENANT_UPDATE
from app.modules.companies.schemas import (
    CompanyCreate,
    CompanyListResponse,
    CompanyRead,
    CompanyUpdate,
)
from app.modules.companies.service import (
    create_company,
    delete_company,
    list_companies,
    update_company,
)
from app.modules.users.models import User

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("", response_model=CompanyListResponse)
async def list_companies_endpoint(
    current_user: User = Depends(RequirePermission(TENANT_READ)),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
) -> CompanyListResponse:
    data = await list_companies(db, tenant_id=current_user.tenant_id)
    return CompanyListResponse(**data)


@router.post("", response_model=CompanyRead, status_code=status.HTTP_201_CREATED)
async def create_company_endpoint(
    payload: CompanyCreate,
    current_user: User = Depends(RequirePermission(TENANT_UPDATE)),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
) -> CompanyRead:
    company = await create_company(db, tenant_id=current_user.tenant_id, payload=payload)
    return CompanyRead.model_validate(company)


@router.patch("/{company_id}", response_model=CompanyRead)
async def update_company_endpoint(
    company_id: UUID,
    payload: CompanyUpdate,
    current_user: User = Depends(RequirePermission(TENANT_UPDATE)),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
) -> CompanyRead:
    company = await update_company(
        db, tenant_id=current_user.tenant_id, company_id=company_id, payload=payload)
    return CompanyRead.model_validate(company)


@router.delete("/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_company_endpoint(
    company_id: UUID,
    current_user: User = Depends(RequirePermission(TENANT_UPDATE)),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
):
    await delete_company(db, tenant_id=current_user.tenant_id, company_id=company_id)
