"""Camera service layer.

Why this exists as a separate module from `router.py`:
  - The router handles HTTP concerns (auth, status codes, request parsing)
  - The service handles business logic (DB writes coordinated with MediaMTX)
  - This split lets the same logic be reused from background tasks
    (health check, ONVIF bulk-add) without going through HTTP.

Sync semantics:
  - On create: write to DB first (canonical state), then sync to MediaMTX.
    If MediaMTX sync fails we DO NOT roll back the DB — the camera exists,
    just isn't streaming yet. The user sees the camera with status=ERROR
    and the next health check or manual retry will re-sync.
  - On update: same — DB first, then MediaMTX.
  - On delete: MediaMTX first (best-effort), then DB. The user-visible
    contract is "after delete, the camera is gone from VisionTrack",
    so DB delete must succeed.
"""

import re
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.modules.cameras.mediamtx_client import MediaMTXClient
from app.modules.cameras.models import Camera, CameraStatus
from app.modules.cameras.schemas import CameraCalibration, CameraCreate, CameraUpdate
from app.modules.floor_plans.models import FloorPlan
from app.modules.sites.models import Site

log = get_logger("cameras.service")


# MediaMTX path names must be safe: letters, digits, dash, underscore.
# We strip everything else and prefix with "cam-".
_PATH_SAFE = re.compile(r"[^a-zA-Z0-9_-]")


def _derive_mediamtx_path(camera_id: UUID) -> str:
    """Stable, URL-safe path derived from the camera's UUID."""
    short = str(camera_id).replace("-", "")[:12]
    return f"cam-{short}"


def derive_h264_sibling_path(mediamtx_path: str) -> str:
    """Name of the H.264-transcoded sibling for a given camera path."""
    return f"{mediamtx_path}-h264"


def needs_browser_transcode(codec: str | None) -> bool:
    """True if the source codec is one that browsers can't reliably play.

    H.265/HEVC: Safari supports, Chrome and Firefox do not. We always
    transcode H.265 to H.264 for the browser-facing HLS stream.
    H.264: every modern browser plays this natively, no transcode needed.
    Unknown codec: don't transcode yet; wait for codec detection.
    """
    return codec == "H265"


async def ensure_browser_path(db: AsyncSession, camera: Camera) -> bool:
    """If the camera needs transcoding, ensure the -h264 sibling exists.

    Called when an H.265 codec is first detected and on backend boot
    during the sync_all_cameras_to_mediamtx pass. Idempotent.

    Returns True if a sibling was created/patched, False if not needed
    or if MediaMTX rejected the request.
    """
    if not needs_browser_transcode(camera.codec):
        return False

    client = MediaMTXClient()
    sibling = derive_h264_sibling_path(camera.mediamtx_path)
    ok = await client.add_transcode_path(
        sibling_name=sibling,
        source_path=camera.mediamtx_path,
    )
    if not ok:
        log.warning(
            "camera.transcode_provision_failed",
            camera_id=str(camera.id),
            sibling=sibling,
        )
    return ok


def _sanitize_path_override(value: str) -> str:
    cleaned = _PATH_SAFE.sub("", value).strip("-_")
    if not cleaned:
        raise ValueError("path name resolves to empty after sanitization")
    return cleaned[:120]


async def _load_site_in_tenant(db: AsyncSession, site_id: UUID, tenant_id: UUID) -> Site:
    result = await db.execute(
        select(Site).where(Site.id == site_id, Site.tenant_id == tenant_id)
    )
    site = result.scalar_one_or_none()
    if site is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Site not found or does not belong to this tenant",
        )
    if not site.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot add a camera to an inactive site",
        )
    return site


async def create_camera(
    db: AsyncSession,
    tenant_id: UUID,
    payload: CameraCreate,
) -> Camera:
    """Create a camera and register it with MediaMTX."""
    await _load_site_in_tenant(db, payload.site_id, tenant_id)

    # Enforce unique name within tenant *before* attempting MediaMTX sync,
    # so a duplicate name doesn't leave an orphan path on MediaMTX.
    dup = await db.execute(
        select(Camera).where(
            Camera.tenant_id == tenant_id, Camera.name == payload.name
        )
    )
    if dup.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A camera with this name already exists in your tenant",
        )

    camera_id = uuid4()
    camera = Camera(
        id=camera_id,
        tenant_id=tenant_id,
        site_id=payload.site_id,
        name=payload.name,
        description=payload.description,
        rtsp_url=payload.rtsp_url,
        mediamtx_path=_derive_mediamtx_path(camera_id),
        status=CameraStatus.PENDING.value,
        is_recording=payload.is_recording,
    )
    db.add(camera)
    await db.flush()

    # Best-effort MediaMTX sync. Failure is logged but not raised — the
    # camera exists in our DB and the next health check / manual retry
    # will re-sync.
    client = MediaMTXClient()
    ok = await client.add_path(
        camera.mediamtx_path, camera.rtsp_url, record=camera.is_recording
    )
    if not ok:
        camera.status = CameraStatus.ERROR.value
        await db.flush()
        log.warning("camera.created_but_mediamtx_failed", camera_id=str(camera.id))

    # Load server-defaulted columns (id/created_at/updated_at) in the async
    # context so response serialization doesn't lazy-load and raise MissingGreenlet.
    await db.refresh(camera)
    return camera


async def update_camera(
    db: AsyncSession,
    tenant_id: UUID,
    camera_id: UUID,
    payload: CameraUpdate,
) -> Camera:
    camera = await _load_camera(db, camera_id, tenant_id)

    source_changed = False
    if payload.name is not None:
        if payload.name != camera.name:
            dup = await db.execute(
                select(Camera).where(
                    Camera.tenant_id == tenant_id,
                    Camera.name == payload.name,
                    Camera.id != camera_id,
                )
            )
            if dup.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A camera with this name already exists in your tenant",
                )
        camera.name = payload.name

    if payload.description is not None:
        camera.description = payload.description

    if payload.rtsp_url is not None and payload.rtsp_url != camera.rtsp_url:
        camera.rtsp_url = payload.rtsp_url
        source_changed = True

    if payload.is_recording is not None and payload.is_recording != camera.is_recording:
        camera.is_recording = payload.is_recording
        source_changed = True

    if payload.calibration is not None:
        camera.calibration = payload.calibration

    await db.flush()

    if source_changed:
        client = MediaMTXClient()
        ok = await client.patch_path(
            camera.mediamtx_path, camera.rtsp_url, record=camera.is_recording
        )
        if not ok:
            camera.status = CameraStatus.ERROR.value
            await db.flush()

    # Load the server-computed `updated_at` (onupdate=now()) within the async
    # context — otherwise Pydantic serializing the response triggers a lazy
    # reload outside the greenlet and raises MissingGreenlet.
    await db.refresh(camera)
    return camera


async def set_calibration(
    db: AsyncSession,
    tenant_id: UUID,
    camera_id: UUID,
    payload: CameraCalibration,
) -> Camera:
    """Store a camera's Bird's-Eye-View homography in camera.calibration.

    Validates that the referenced floor plan belongs to the same tenant
    (cross-tenant safety) before persisting. Stamps calibrated_at.
    """
    camera = await _load_camera(db, camera_id, tenant_id)

    plan = (
        await db.execute(
            select(FloorPlan.id).where(
                FloorPlan.id == payload.floor_plan_id,
                FloorPlan.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Floor plan not found in your tenant",
        )

    data = payload.model_dump(mode="json")
    data["calibrated_at"] = datetime.now(timezone.utc).isoformat()
    # Preserve any unrelated keys already in calibration (forward-compat).
    merged = dict(camera.calibration or {})
    merged.update(data)
    camera.calibration = merged
    await db.flush()
    # `updated_at` (onupdate=func.now()) is expired by the flush; refresh within
    # the async context so response serialization doesn't trigger a lazy load
    # outside the greenlet (MissingGreenlet).
    await db.refresh(camera)
    log.info(
        "cameras.calibrated",
        camera_id=str(camera_id),
        floor_plan_id=str(payload.floor_plan_id),
    )
    return camera


async def delete_camera(
    db: AsyncSession, tenant_id: UUID, camera_id: UUID
) -> None:
    camera = await _load_camera(db, camera_id, tenant_id)

    # MediaMTX first (best-effort). DB delete is the contractually visible
    # action so it must run even if MediaMTX is unreachable.
    client = MediaMTXClient()
    await client.delete_path(camera.mediamtx_path)

    await db.delete(camera)


async def list_cameras(
    db: AsyncSession,
    tenant_id: UUID,
    site_id: UUID | None = None,
    status_filter: str | None = None,
    search: str | None = None,
) -> list[Camera]:
    stmt = select(Camera).where(Camera.tenant_id == tenant_id)
    if site_id is not None:
        stmt = stmt.where(Camera.site_id == site_id)
    if status_filter:
        stmt = stmt.where(Camera.status == status_filter)
    if search:
        like = f"%{search.lower()}%"
        stmt = stmt.where(func.lower(Camera.name).like(like))
    stmt = stmt.order_by(Camera.name)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_floor_plan_locations_for_tenant(
    db: AsyncSession, tenant_id: UUID
) -> dict[UUID, list[dict]]:
    """Return {camera_id: [{plan_id, plan_name, marker_id, marker_label}, ...]}.

    One query for the whole tenant — used to enrich camera-list responses
    with floor-plan placements so the frontend can show "this camera is
    on 1 floor plan" badges without an N+1.

    Imports FloorPlan locally to avoid a circular import (FloorPlan
    references cameras via marker.camera_id in the model docstring; the
    Python import graph is fine but keep it lazy for safety).
    """
    from app.modules.floor_plans.models import FloorPlan  # local import

    result = await db.execute(
        select(FloorPlan.id, FloorPlan.name, FloorPlan.markers)
        .where(FloorPlan.tenant_id == tenant_id)
    )
    out: dict[UUID, list[dict]] = {}
    for plan_id, plan_name, markers in result.all():
        if not markers:
            continue
        for m in markers:
            try:
                cam_id = UUID(str(m.get("camera_id")))
            except (ValueError, TypeError):
                # Malformed marker in DB — skip rather than crash the list
                continue
            out.setdefault(cam_id, []).append(
                {
                    "plan_id": str(plan_id),
                    "plan_name": plan_name,
                    "marker_id": str(m.get("id")),
                    "marker_label": m.get("label"),
                }
            )
    return out


async def _load_camera(db: AsyncSession, camera_id: UUID, tenant_id: UUID) -> Camera:
    result = await db.execute(
        select(Camera).where(Camera.id == camera_id, Camera.tenant_id == tenant_id)
    )
    camera = result.scalar_one_or_none()
    if camera is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found"
        )
    return camera


async def sync_all_cameras_to_mediamtx(db: AsyncSession) -> dict[str, int]:
    """Re-register every DB camera with MediaMTX on backend startup.

    MediaMTX's runtime-added paths (those created via its API rather than
    its config file) do NOT persist across MediaMTX container restarts.
    On every backend boot we re-push the canonical state from Postgres so
    cameras keep streaming after a MediaMTX restart or compose restart.

    Behavior:
      - For each camera in every tenant, call `add_path` on its
        `mediamtx_path` with the camera's RTSP URL. add_path is
        idempotent in our MediaMTXClient — it tries POST and falls back
        to PATCH if the path already exists.
      - If the camera codec is known to need transcoding (H.265), also
        provision the -h264 sibling path via `ensure_browser_path`.
      - Best-effort: a failure on one camera doesn't abort the loop.
        Failures are logged + counted.

    Returns:
      dict with counts: total, registered, transcoded, failed.

    Called by main.py's lifespan startup. Caller is responsible for
    committing the session (we may update camera.status on failures).
    """
    counts = {"total": 0, "registered": 0, "transcoded": 0, "failed": 0}
    client = MediaMTXClient()
    result = await db.execute(select(Camera))
    cameras = list(result.scalars().all())

    for camera in cameras:
        counts["total"] += 1
        if not camera.mediamtx_path or not camera.rtsp_url:
            log.warning(
                "camera.skip_sync_no_path",
                camera_id=str(camera.id),
                name=camera.name,
            )
            counts["failed"] += 1
            continue
        try:
            ok = await client.add_path(
                camera.mediamtx_path,
                camera.rtsp_url,
                record=camera.is_recording,
            )
        except Exception as e:
            log.warning(
                "camera.sync_exception",
                camera_id=str(camera.id),
                error=str(e),
            )
            counts["failed"] += 1
            continue

        if not ok:
            log.warning(
                "camera.sync_failed",
                camera_id=str(camera.id),
                name=camera.name,
                path=camera.mediamtx_path,
            )
            counts["failed"] += 1
            continue

        counts["registered"] += 1

        # Browser-transcode sibling for H.265 cameras
        try:
            did_transcode = await ensure_browser_path(db, camera)
            if did_transcode:
                counts["transcoded"] += 1
        except Exception as e:
            log.warning(
                "camera.transcode_exception",
                camera_id=str(camera.id),
                error=str(e),
            )

    return counts
