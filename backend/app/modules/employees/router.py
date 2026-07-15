"""Employees HTTP routes.

  GET /employees   the tenant's employee roster (imported from FaceTrack)
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import RequirePermission
from app.core.permissions import EMPLOYEE_READ
from app.modules.employees.schemas import EmployeeListResponse
from app.modules.employees.service import list_employees
from app.modules.users.models import User

router = APIRouter(prefix="/employees", tags=["employees"])


@router.get("", response_model=EmployeeListResponse)
async def list_employees_endpoint(
    search: str | None = Query(None),
    current_user: User = Depends(RequirePermission(EMPLOYEE_READ)),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
) -> EmployeeListResponse:
    """The employee roster for the tenant (synced from FaceTrack)."""
    data = await list_employees(db, tenant_id=current_user.tenant_id, search=search)
    return EmployeeListResponse(**data)
