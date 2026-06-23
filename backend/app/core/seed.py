"""First-run database seeding.

Called from main.py's lifespan. Idempotent — safe to run on every boot.

Creates:
  1. The default tenant (configured via env vars)
  2. The four default roles for that tenant
  3. The first superuser, assigned the Tenant Admin role
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.permissions import DEFAULT_ROLES
from app.core.security import hash_password
from app.modules.roles.models import Role
from app.modules.sites.models import Site
from app.modules.tenants.models import Tenant
from app.modules.users.models import User

log = get_logger("seed")


async def seed_initial_data(db: AsyncSession) -> None:
    tenant = await _ensure_tenant(db)
    admin_role = await _ensure_default_roles(db, tenant.id)
    await _ensure_superuser(db, tenant.id, admin_role)
    await _ensure_default_site(db, tenant.id)
    await db.commit()


async def _ensure_tenant(db: AsyncSession) -> Tenant:
    result = await db.execute(
        select(Tenant).where(Tenant.subdomain == settings.FIRST_TENANT_SUBDOMAIN)
    )
    tenant = result.scalar_one_or_none()
    if tenant is None:
        tenant = Tenant(
            name=settings.FIRST_TENANT_NAME,
            subdomain=settings.FIRST_TENANT_SUBDOMAIN,
            plan="trial",
        )
        db.add(tenant)
        await db.flush()
        log.info("seed.tenant_created", name=tenant.name, subdomain=tenant.subdomain)
    return tenant


async def _ensure_default_roles(db: AsyncSession, tenant_id) -> Role:
    """Seed the four default roles. Returns the Tenant Admin role."""
    admin_role = None
    for role_def in DEFAULT_ROLES:
        result = await db.execute(
            select(Role).where(
                Role.tenant_id == tenant_id,
                Role.name == role_def["name"],
            )
        )
        role = result.scalar_one_or_none()
        if role is None:
            role = Role(
                tenant_id=tenant_id,
                name=role_def["name"],
                description=role_def["description"],
                permissions=role_def["permissions"],
                is_system=role_def["is_system"],
            )
            db.add(role)
            await db.flush()
            log.info("seed.role_created", name=role.name)
        if role.name == "Tenant Admin":
            admin_role = role

    assert admin_role is not None, "Tenant Admin role must exist after seeding"
    return admin_role


async def _ensure_superuser(db: AsyncSession, tenant_id, admin_role: Role) -> None:
    email = settings.FIRST_SUPERUSER_EMAIL.lower()
    result = await db.execute(
        select(User).where(User.tenant_id == tenant_id, User.email == email)
    )
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            tenant_id=tenant_id,
            email=email,
            full_name="VisionTrack Administrator",
            locale="en",
            is_active=True,
            is_superuser=True,
            password_hash=hash_password(settings.FIRST_SUPERUSER_PASSWORD),
            roles=[admin_role],
        )
        db.add(user)
        await db.flush()
        log.info("seed.superuser_created", email=email)


async def _ensure_default_site(db: AsyncSession, tenant_id) -> None:
    """Seed one default site so cameras can be added immediately."""
    result = await db.execute(
        select(Site).where(Site.tenant_id == tenant_id)
    )
    if result.scalar_one_or_none() is not None:
        return
    site = Site(
        tenant_id=tenant_id,
        name="Main Site",
        address=None,
        timezone="Asia/Karachi",
    )
    db.add(site)
    await db.flush()
    log.info("seed.site_created", name=site.name)
