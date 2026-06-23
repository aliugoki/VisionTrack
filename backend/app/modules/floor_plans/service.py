"""Floor Plans service layer.

CRUD + orchestration of the storage subsystem.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.modules.floor_plans import storage
from app.modules.floor_plans.models import FloorPlan
from app.modules.floor_plans.schemas import FloorPlanUpdate
from app.modules.sites.models import Site

log = get_logger("floor_plans.service")


class SiteNotInTenant(Exception):
    """Raised when a floor plan upload references a site not in the tenant."""


async def list_plans(
    db: AsyncSession,
    tenant_id: UUID,
    site_id: UUID | None = None,
) -> list[FloorPlan]:
    stmt = (
        select(FloorPlan)
        .where(FloorPlan.tenant_id == tenant_id)
        .order_by(FloorPlan.name)
    )
    if site_id is not None:
        stmt = stmt.where(FloorPlan.site_id == site_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_plan(
    db: AsyncSession, tenant_id: UUID, plan_id: UUID
) -> FloorPlan | None:
    result = await db.execute(
        select(FloorPlan).where(
            FloorPlan.id == plan_id,
            FloorPlan.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def create_plan(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    user_id: UUID,
    site_id: UUID,
    name: str,
    description: str | None,
    filename: str,
    content_type: str,
    content: bytes,
) -> FloorPlan:
    """Create a floor plan from an uploaded file.

    Steps:
      1. Verify the site belongs to the tenant
      2. Generate a new plan UUID
      3. Upload to MinIO + (for PDFs) render PNG
      4. Insert the FloorPlan row with extracted metadata

    Raises:
      SiteNotInTenant — caller maps to 400
      ValueError — caller maps to 400 (unsupported format / too large / unreadable)
      S3Error — caller maps to 502 (storage backend issue)
    """
    # Verify site belongs to tenant
    site_check = await db.execute(
        select(Site.id).where(
            Site.id == site_id, Site.tenant_id == tenant_id
        )
    )
    if site_check.scalar_one_or_none() is None:
        raise SiteNotInTenant(str(site_id))

    # Create the row first to reserve the UUID — this gives us a stable
    # storage prefix even before the bytes land in MinIO. If the storage
    # step fails we rollback the DB tx.
    plan = FloorPlan(
        tenant_id=tenant_id,
        site_id=site_id,
        uploaded_by_user_id=user_id,
        name=name,
        description=description,
        original_filename=filename,
        original_content_type=content_type,
        original_size_bytes=len(content),
        # Placeholders — overwritten after storage step succeeds.
        format="png",
        width_px=0,
        height_px=0,
        storage_key_original="",
        storage_key_rendered=None,
    )
    db.add(plan)
    await db.flush()  # populate plan.id

    # Upload + (for PDFs) render
    result = storage.store_upload(
        tenant_id=tenant_id,
        site_id=site_id,
        plan_id=plan.id,
        filename=filename,
        content_type=content_type,
        content=content,
    )

    # Fill in the real metadata
    plan.format = result.format
    plan.width_px = result.width_px
    plan.height_px = result.height_px
    plan.storage_key_original = result.storage_key_original
    plan.storage_key_rendered = result.storage_key_rendered
    plan.original_size_bytes = result.size_bytes

    await db.flush()
    await db.refresh(plan)
    log.info(
        "floor_plans.created",
        plan_id=str(plan.id),
        fmt=plan.format,
        name=plan.name,
    )
    return plan


async def update_plan(
    db: AsyncSession,
    tenant_id: UUID,
    plan_id: UUID,
    payload: FloorPlanUpdate,
) -> FloorPlan | None:
    plan = await get_plan(db, tenant_id, plan_id)
    if plan is None:
        return None
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(plan, k, v)
    await db.flush()
    await db.refresh(plan)
    return plan


async def update_markers(
    db: AsyncSession,
    tenant_id: UUID,
    plan_id: UUID,
    markers: list[dict],
) -> FloorPlan | None:
    """Replace the markers array.

    Validates that every camera_id referenced by a marker belongs to the
    same tenant — protects against cross-tenant data injection.
    Marker schema itself is validated by Pydantic before reaching here.
    """
    plan = await get_plan(db, tenant_id, plan_id)
    if plan is None:
        return None

    # Validate camera ownership in one query rather than N
    camera_ids = {UUID(str(m["camera_id"])) for m in markers}
    if camera_ids:
        from app.modules.cameras.models import Camera

        result = await db.execute(
            select(Camera.id)
            .where(Camera.tenant_id == tenant_id)
            .where(Camera.id.in_(camera_ids))
        )
        found = {row[0] for row in result.all()}
        missing = camera_ids - found
        if missing:
            raise ValueError(
                f"Camera {next(iter(missing))} is not in this tenant"
            )

    # Stringify UUIDs for JSONB storage — psycopg can't always serialize
    # UUID objects inside dicts inside JSONB column updates.
    # Cone fields are optional; None values are preserved so the frontend
    # can distinguish "cone not set" from "cone set to 0".
    plan.markers = [
        {
            "id": str(m["id"]),
            "camera_id": str(m["camera_id"]),
            "x": float(m["x"]),
            "y": float(m["y"]),
            "label": m.get("label"),
            "cone_angle_deg": (
                float(m["cone_angle_deg"])
                if m.get("cone_angle_deg") is not None
                else None
            ),
            "cone_range": (
                float(m["cone_range"])
                if m.get("cone_range") is not None
                else None
            ),
            "cone_rotation_deg": (
                float(m["cone_rotation_deg"])
                if m.get("cone_rotation_deg") is not None
                else None
            ),
        }
        for m in markers
    ]

    await db.flush()
    await db.refresh(plan)
    log.info(
        "floor_plans.markers_updated",
        plan_id=str(plan_id),
        count=len(markers),
    )
    return plan


async def update_zones(
    db: AsyncSession,
    tenant_id: UUID,
    plan_id: UUID,
    zones: list[dict],
) -> FloorPlan | None:
    """Replace the zones array on a floor plan.

    Same atomic-replace semantics as `update_markers`: the editor PUTs
    the full list at once. Zone schema (polygon points, rule structure,
    color format) is validated by Pydantic before reaching here.

    Stringifies UUIDs at every nesting level so JSONB serialization is
    deterministic and the row survives `db.refresh` without coercion
    surprises.
    """
    plan = await get_plan(db, tenant_id, plan_id)
    if plan is None:
        return None

    def _serialize_rule(r: dict) -> dict:
        sched_in = r.get("schedule") or {}
        return {
            "id": str(r["id"]),
            "kind": r["kind"],
            "threshold": float(r["threshold"]),
            "hold_time_s": int(r.get("hold_time_s", 0)),
            "schedule": {
                "mode": sched_in.get("mode", "always"),
                "start_time": sched_in.get("start_time"),
                "end_time": sched_in.get("end_time"),
                "days": list(sched_in.get("days") or []),
            },
            "severity": r.get("severity", "warning"),
            "channels": list(r.get("channels") or ["in_app"]),
            "enabled": bool(r.get("enabled", True)),
            "label": r.get("label"),
        }

    plan.zones = [
        {
            "id": str(z["id"]),
            "name": z["name"],
            "color": z["color"],
            "polygon": [
                {"x": float(p["x"]), "y": float(p["y"])}
                for p in z["polygon"]
            ],
            "rules": [_serialize_rule(r) for r in (z.get("rules") or [])],
        }
        for z in zones
    ]

    await db.flush()
    await db.refresh(plan)
    log.info(
        "floor_plans.zones_updated",
        plan_id=str(plan_id),
        zones=len(zones),
        rules_total=sum(len(z.get("rules") or []) for z in zones),
    )
    return plan


async def delete_plan(
    db: AsyncSession, tenant_id: UUID, plan_id: UUID
) -> bool:
    plan = await get_plan(db, tenant_id, plan_id)
    if plan is None:
        return False
    # Delete DB row first; storage cleanup is best-effort.
    site_id = plan.site_id
    await db.delete(plan)
    await db.flush()
    storage.delete_plan_files(tenant_id, site_id, plan_id)
    log.info("floor_plans.deleted", plan_id=str(plan_id))
    return True


def viewable_storage_key(plan: FloorPlan) -> str:
    """For PNG/JPG/SVG we serve the original; for PDF we serve the rendered PNG."""
    if plan.format == "pdf" and plan.storage_key_rendered:
        return plan.storage_key_rendered
    return plan.storage_key_original
