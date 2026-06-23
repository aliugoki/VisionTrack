"""Floor Plans — REST endpoints.

  GET    /floor-plans                  list (optional site_id filter)
  POST   /floor-plans                  upload (multipart/form-data)
  GET    /floor-plans/{id}             metadata
  PATCH  /floor-plans/{id}             update name/description
  DELETE /floor-plans/{id}             delete (cascades to MinIO)
  GET    /floor-plans/{id}/image       stream the displayable image
  GET    /floor-plans/{id}/original    stream the original upload
"""

from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from minio.error import S3Error
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import RequirePermission
from app.core.logging import get_logger
from app.core.permissions import (
    FLOOR_PLAN_CREATE,
    FLOOR_PLAN_DELETE,
    FLOOR_PLAN_READ,
    FLOOR_PLAN_UPDATE,
    ZONE_UPDATE,
)
from app.modules.floor_plans import service, storage
from app.modules.floor_plans.schemas import (
    FloorPlanMarkersUpdate,
    FloorPlanRead,
    FloorPlanUpdate,
    ZonesUpdate,
)
from app.modules.floor_plans.service import SiteNotInTenant

log = get_logger("floor_plans.router")

router = APIRouter(prefix="/floor-plans", tags=["floor-plans"])


@router.get("", response_model=list[FloorPlanRead])
async def list_floor_plans(
    site_id: UUID | None = Query(default=None, description="Filter to one site"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(RequirePermission(FLOOR_PLAN_READ)),
):
    plans = await service.list_plans(
        db, tenant_id=current_user.tenant_id, site_id=site_id
    )
    return [FloorPlanRead.model_validate(p) for p in plans]


@router.post(
    "",
    response_model=FloorPlanRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_floor_plan(
    site_id: UUID = Form(...),
    name: str = Form(..., min_length=1, max_length=120),
    description: str | None = Form(default=None, max_length=500),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(RequirePermission(FLOOR_PLAN_CREATE)),
):
    """Multipart upload: site_id + name + (optional description) + file.

    Files >50 MB are rejected with 413. Unsupported file types return 400.
    """
    # Read fully into memory — 50 MB cap makes this safe. For larger
    # uploads we'd switch to streaming-to-temp-file.
    content = await file.read()

    try:
        plan = await service.create_plan(
            db,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            site_id=site_id,
            name=name,
            description=description,
            filename=file.filename or "untitled",
            content_type=file.content_type or "application/octet-stream",
            content=content,
        )
    except SiteNotInTenant as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Site {e} is not in this tenant",
        )
    except ValueError as e:
        # Storage rejected the upload (size / format / unreadable image)
        msg = str(e)
        sc = (
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
            if "exceeds" in msg
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=sc, detail=msg)
    except S3Error as e:
        log.error("floor_plans.s3_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Storage backend unavailable",
        )

    await db.commit()
    return FloorPlanRead.model_validate(plan)


@router.get("/{plan_id}", response_model=FloorPlanRead)
async def get_floor_plan(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(RequirePermission(FLOOR_PLAN_READ)),
):
    plan = await service.get_plan(db, current_user.tenant_id, plan_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Floor plan not found"
        )
    return FloorPlanRead.model_validate(plan)


@router.patch("/{plan_id}", response_model=FloorPlanRead)
async def update_floor_plan(
    plan_id: UUID,
    payload: FloorPlanUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(RequirePermission(FLOOR_PLAN_UPDATE)),
):
    plan = await service.update_plan(
        db, current_user.tenant_id, plan_id, payload
    )
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Floor plan not found"
        )
    await db.commit()
    return FloorPlanRead.model_validate(plan)


@router.patch("/{plan_id}/markers", response_model=FloorPlanRead)
async def update_floor_plan_markers(
    plan_id: UUID,
    payload: FloorPlanMarkersUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(RequirePermission(FLOOR_PLAN_UPDATE)),
):
    """Replace the markers array. Whole-set update (operator saves the
    full editor state at once)."""
    markers_data = [m.model_dump() for m in payload.markers]
    try:
        plan = await service.update_markers(
            db, current_user.tenant_id, plan_id, markers_data
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Floor plan not found"
        )
    await db.commit()
    return FloorPlanRead.model_validate(plan)


@router.put("/{plan_id}/zones", response_model=FloorPlanRead)
async def update_floor_plan_zones(
    plan_id: UUID,
    payload: ZonesUpdate,
    db: AsyncSession = Depends(get_db),
    # ZONE_UPDATE covers create/edit/delete in the atomic-replace model:
    # the operator saves the full zone set including additions, edits, and
    # deletions in one call. We use ZONE_UPDATE rather than splitting into
    # ZONE_CREATE/DELETE because the editor's mental model is "save my work",
    # not "POST one zone at a time". Tenant Admin has all three; the
    # Supervisor role (Step 5 seed update) has all three; everyone else can
    # only read.
    current_user=Depends(RequirePermission(ZONE_UPDATE)),
):
    """Replace the zones array on a floor plan.

    Atomic-replace: the editor PUTs the full list at once. Empty list
    is a valid body — clears all zones from this plan.
    """
    zones_data = [z.model_dump() for z in payload.zones]
    plan = await service.update_zones(
        db, current_user.tenant_id, plan_id, zones_data
    )
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Floor plan not found"
        )
    await db.commit()
    return FloorPlanRead.model_validate(plan)


@router.delete(
    "/{plan_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_floor_plan(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(RequirePermission(FLOOR_PLAN_DELETE)),
):
    deleted = await service.delete_plan(db, current_user.tenant_id, plan_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Floor plan not found"
        )
    await db.commit()


@router.get("/{plan_id}/image")
async def get_floor_plan_image(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(RequirePermission(FLOOR_PLAN_READ)),
):
    """Stream the displayable image (PNG for PDFs, original for PNG/JPG/SVG)."""
    plan = await service.get_plan(db, current_user.tenant_id, plan_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Floor plan not found"
        )

    key = service.viewable_storage_key(plan)
    return _stream_object(key)


@router.get("/{plan_id}/original")
async def get_floor_plan_original(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(RequirePermission(FLOOR_PLAN_READ)),
):
    """Stream the original uploaded file (e.g. the source PDF)."""
    plan = await service.get_plan(db, current_user.tenant_id, plan_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Floor plan not found"
        )
    return _stream_object(
        plan.storage_key_original,
        download_name=plan.original_filename,
    )


def _stream_object(
    storage_key: str, download_name: str | None = None
) -> StreamingResponse:
    """Open the MinIO object and wrap it in a FastAPI StreamingResponse."""
    try:
        obj, length, content_type = storage.open_for_streaming(storage_key)
    except S3Error as e:
        log.warning("floor_plans.stream_failed", key=storage_key, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not available",
        )

    def iterator():
        try:
            yield from obj.stream(amt=64 * 1024)
        finally:
            obj.close()
            obj.release_conn()

    headers = {}
    if length:
        headers["Content-Length"] = str(length)
    # Cache for an hour. Plans don't change content after upload.
    headers["Cache-Control"] = "private, max-age=3600"
    if download_name:
        headers["Content-Disposition"] = f'inline; filename="{download_name}"'

    return StreamingResponse(
        iterator(), media_type=content_type, headers=headers
    )
