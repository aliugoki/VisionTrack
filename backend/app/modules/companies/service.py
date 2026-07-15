"""Companies service — list + CRUD for the reflected/native company roster."""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.companies.models import Company
from app.modules.companies.schemas import CompanyCreate, CompanyUpdate
from app.modules.employees.models import Employee


async def _employee_counts(db: AsyncSession, tenant_id: UUID) -> dict[str, int]:
    """external_company_id -> number of employees, for the current tenant."""
    rows = (await db.execute(
        select(Employee.external_company_id, func.count())
        .where(Employee.tenant_id == tenant_id)
        .group_by(Employee.external_company_id)
    )).all()
    return {r[0]: r[1] for r in rows if r[0] is not None}


async def list_companies(db: AsyncSession, *, tenant_id: UUID) -> dict:
    companies = (await db.execute(
        select(Company).where(Company.tenant_id == tenant_id).order_by(Company.name)
    )).scalars().all()
    counts = await _employee_counts(db, tenant_id)
    rows = []
    for c in companies:
        data = {
            "id": c.id, "external_id": c.external_id, "name": c.name,
            "admin_username": c.admin_username, "status": c.status,
            "source": c.source, "is_active": c.is_active, "synced_at": c.synced_at,
            "employee_count": counts.get(c.external_id, 0),
        }
        rows.append(data)
    return {"total": len(rows), "rows": rows}


async def _load(db: AsyncSession, tenant_id: UUID, company_id: UUID) -> Company:
    company = (await db.execute(
        select(Company).where(Company.id == company_id, Company.tenant_id == tenant_id)
    )).scalar_one_or_none()
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company


async def create_company(db: AsyncSession, *, tenant_id: UUID, payload: CompanyCreate) -> Company:
    company = Company(
        tenant_id=tenant_id, name=payload.name,
        admin_username=payload.admin_username, status=payload.status,
        is_active=payload.is_active, source="visiontrack",
    )
    db.add(company)
    await db.flush()
    await db.commit()
    await db.refresh(company)
    return company


async def update_company(
    db: AsyncSession, *, tenant_id: UUID, company_id: UUID, payload: CompanyUpdate
) -> Company:
    company = await _load(db, tenant_id, company_id)
    if payload.name is not None:
        company.name = payload.name
    if payload.admin_username is not None:
        company.admin_username = payload.admin_username
    if payload.status is not None:
        company.status = payload.status
    if payload.is_active is not None:
        company.is_active = payload.is_active
    await db.flush()
    await db.commit()
    await db.refresh(company)
    return company


async def delete_company(db: AsyncSession, *, tenant_id: UUID, company_id: UUID) -> None:
    company = await _load(db, tenant_id, company_id)
    await db.delete(company)
    await db.commit()
