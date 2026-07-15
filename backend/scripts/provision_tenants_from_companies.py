"""Backfill: provision a dedicated tenant for every reflected FaceTrack company.

Multi-tenant Phase 1. Runs inside VisionTrack (reads the already-synced
``companies`` table — no FaceTrack access needed) and creates a tenant per
company via ``tenants.provisioning.provision_tenant_for_company``. Idempotent.

    docker exec vt-backend python -m scripts.provision_tenants_from_companies
"""
import asyncio

import app.core.models  # noqa: F401 -- register every ORM model
from sqlalchemy import select

from app.core.db import AsyncSessionLocal
from app.modules.companies.models import Company
from app.modules.tenants.provisioning import provision_tenant_for_company


async def main() -> None:
    async with AsyncSessionLocal() as db:
        companies = (await db.execute(
            select(Company).where(Company.external_id.is_not(None))
        )).scalars().all()

        created = skipped = 0
        for c in companies:
            tenant, was_created = await provision_tenant_for_company(
                db, external_company_id=c.external_id, name=c.name,
                admin_username=c.admin_username,
            )
            if was_created:
                created += 1
                print(f"  + tenant '{tenant.name}' (subdomain={tenant.subdomain}) "
                      f"for company {c.external_id}")
            else:
                skipped += 1
        await db.commit()
        print(f"provisioned {created} tenant(s), {skipped} already existed")


if __name__ == "__main__":
    asyncio.run(main())
