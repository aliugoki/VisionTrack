"""Live Wall preset CRUD service.

Cross-cuts the Camera table to validate that every camera_id in a
preset's tiles belongs to the same tenant.
"""

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.modules.cameras.models import Camera
from app.modules.live_wall.models import WallPreset
from app.modules.live_wall.schemas import WallPresetCreate, WallPresetUpdate

log = get_logger("live_wall.service")


class PresetNameConflict(Exception):
    """Raised when a preset name is already taken in this tenant."""


class CameraNotInTenant(Exception):
    """A tile referenced a camera that doesn't belong to this tenant."""

    def __init__(self, camera_id: UUID):
        self.camera_id = camera_id
        super().__init__(f"Camera {camera_id} not found in tenant")


async def list_presets(db: AsyncSession, tenant_id: UUID) -> list[WallPreset]:
    result = await db.execute(
        select(WallPreset)
        .where(WallPreset.tenant_id == tenant_id)
        .order_by(WallPreset.name)
    )
    return list(result.scalars().all())


async def get_preset(
    db: AsyncSession, tenant_id: UUID, preset_id: UUID
) -> WallPreset | None:
    result = await db.execute(
        select(WallPreset).where(
            WallPreset.id == preset_id,
            WallPreset.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def create_preset(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    payload: WallPresetCreate,
) -> WallPreset:
    await _validate_camera_refs(db, tenant_id, payload.tiles)

    # If marking this as default, unset any other default first.
    if payload.is_default:
        await _clear_other_defaults(db, tenant_id, exclude_id=None)

    preset = WallPreset(
        tenant_id=tenant_id,
        created_by_user_id=user_id,
        name=payload.name,
        description=payload.description,
        rows=payload.rows,
        cols=payload.cols,
        tiles=[str(t) if t is not None else None for t in payload.tiles],
        is_default=payload.is_default,
    )
    db.add(preset)
    try:
        await db.flush()
    except IntegrityError as e:
        await db.rollback()
        if "uq_wall_presets_tenant_name" in str(e.orig):
            raise PresetNameConflict(payload.name) from e
        raise
    await db.refresh(preset)
    log.info("preset.created", preset_id=str(preset.id), name=preset.name)
    return preset


async def update_preset(
    db: AsyncSession,
    tenant_id: UUID,
    preset_id: UUID,
    payload: WallPresetUpdate,
) -> WallPreset | None:
    preset = await get_preset(db, tenant_id, preset_id)
    if preset is None:
        return None

    data = payload.model_dump(exclude_unset=True)

    # If tiles is in the update, validate camera ownership
    if "tiles" in data:
        await _validate_camera_refs(db, tenant_id, data["tiles"])
        data["tiles"] = [str(t) if t is not None else None for t in data["tiles"]]

    # If switching to default, clear other defaults first
    if data.get("is_default") is True:
        await _clear_other_defaults(db, tenant_id, exclude_id=preset.id)

    # Validate the (rows, cols) combination if either changes
    new_rows = data.get("rows", preset.rows)
    new_cols = data.get("cols", preset.cols)
    if (new_rows, new_cols) not in {(1, 1), (2, 2), (3, 3), (4, 4)}:
        raise ValueError(f"Unsupported grid {new_rows}x{new_cols}")

    # If tiles wasn't provided but rows/cols changed, resize tiles
    if "tiles" not in data and ("rows" in data or "cols" in data):
        new_size = new_rows * new_cols
        old_tiles = preset.tiles or []
        if len(old_tiles) < new_size:
            data["tiles"] = old_tiles + [None] * (new_size - len(old_tiles))
        else:
            data["tiles"] = old_tiles[:new_size]

    for k, v in data.items():
        setattr(preset, k, v)

    try:
        await db.flush()
    except IntegrityError as e:
        await db.rollback()
        if "uq_wall_presets_tenant_name" in str(e.orig):
            raise PresetNameConflict(data.get("name", preset.name)) from e
        raise
    await db.refresh(preset)
    log.info("preset.updated", preset_id=str(preset.id))
    return preset


async def delete_preset(
    db: AsyncSession, tenant_id: UUID, preset_id: UUID
) -> bool:
    preset = await get_preset(db, tenant_id, preset_id)
    if preset is None:
        return False
    await db.delete(preset)
    await db.flush()
    log.info("preset.deleted", preset_id=str(preset_id))
    return True


# -- helpers ------------------------------------------------------------------

async def _validate_camera_refs(
    db: AsyncSession, tenant_id: UUID, tiles: list
) -> None:
    """Ensure every non-null camera_id in tiles belongs to this tenant."""
    camera_ids = {UUID(str(t)) for t in tiles if t is not None}
    if not camera_ids:
        return

    result = await db.execute(
        select(Camera.id)
        .where(Camera.tenant_id == tenant_id)
        .where(Camera.id.in_(camera_ids))
    )
    found = {row[0] for row in result.all()}
    missing = camera_ids - found
    if missing:
        raise CameraNotInTenant(next(iter(missing)))


async def _clear_other_defaults(
    db: AsyncSession, tenant_id: UUID, exclude_id: UUID | None
) -> None:
    """Demote any existing default preset before promoting a new one."""
    stmt = (
        update(WallPreset)
        .where(WallPreset.tenant_id == tenant_id)
        .where(WallPreset.is_default.is_(True))
        .values(is_default=False)
    )
    if exclude_id is not None:
        stmt = stmt.where(WallPreset.id != exclude_id)
    await db.execute(stmt)
