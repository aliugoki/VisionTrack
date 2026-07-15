"""Employees service — list the roster (sourced from FaceTrack)."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.employees.models import Employee
from app.modules.persons.models import PersonIdentity


async def list_employees(
    db: AsyncSession, *, tenant_id: UUID, search: str | None = None
) -> dict:
    """Return the tenant's employee roster, flagging who has been recognized in
    VisionTrack (an ``emp_id`` present in ``person_identities``)."""
    q = select(Employee).where(Employee.tenant_id == tenant_id)
    if search:
        like = f"%{search.lower()}%"
        from sqlalchemy import func, or_
        q = q.where(or_(
            func.lower(Employee.emp_id).like(like),
            func.lower(func.coalesce(Employee.first_name, "")).like(like),
            func.lower(func.coalesce(Employee.last_name, "")).like(like),
        ))
    q = q.order_by(Employee.first_name, Employee.last_name, Employee.emp_id)
    employees = (await db.execute(q)).scalars().all()

    # Which emp_ids have been recognized in VisionTrack.
    seen = set((await db.execute(
        select(PersonIdentity.emp_id).where(PersonIdentity.tenant_id == tenant_id).distinct()
    )).scalars().all())

    rows = [{
        "id": str(e.id),
        "emp_id": e.emp_id,
        "name": " ".join(p for p in (e.first_name, e.last_name) if p) or e.emp_id,
        "external_company_id": e.external_company_id,
        "source": e.source,
        "synced_at": e.synced_at,
        "seen": e.emp_id in seen,
    } for e in employees]
    return {"total": len(rows), "rows": rows}
