"""Camera health check.

Called on a schedule by the Celery beat task `check_camera_health`. The
loop is:

  1. Fetch every camera from the DB (this tenant + all tenants — health
     checks are tenant-agnostic since MediaMTX is a single shared instance)
  2. Fetch every path's runtime state from MediaMTX in one bulk call
  3. For each camera, reconcile:
        - ready=True, tracks present  -> ONLINE, update last_seen_at + codec
        - ready=False, path exists    -> OFFLINE
        - path not in MediaMTX        -> ERROR (orphaned — should re-sync)
  4. Persist status changes; log transitions for diagnostics

Status transitions are tracked via `last_status_change_at` so the UI can
show "Offline for 2 minutes" rather than just "Offline."

This is intentionally not part of the cameras router — it's a background
concern that runs without any HTTP request scope.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.modules.cameras.mediamtx_client import MediaMTXClient
from app.modules.cameras.models import Camera, CameraStatus

log = get_logger("cameras.health")


async def run_health_check(db: AsyncSession) -> dict[str, int]:
    """Reconcile DB camera state against MediaMTX runtime state.

    Returns a summary dict for the Celery task log.
    """
    result = await db.execute(select(Camera))
    cameras = list(result.scalars().all())

    if not cameras:
        return {"checked": 0, "online": 0, "offline": 0, "error": 0, "skipped": 0}

    client = MediaMTXClient()
    paths = await client.list_paths()
    paths_by_name = {p.get("name"): p for p in paths if p.get("name")}

    now = datetime.now(timezone.utc)
    counts = {"checked": 0, "online": 0, "offline": 0, "error": 0, "skipped": 0, "resynced": 0}

    for camera in cameras:
        # Don't probe disabled cameras — admin paused them intentionally
        if camera.status == CameraStatus.DISABLED.value:
            counts["skipped"] += 1
            continue

        counts["checked"] += 1
        path_state = paths_by_name.get(camera.mediamtx_path)

        # Self-healing: if MediaMTX has no record of this camera's path,
        # re-register it. This typically happens after a MediaMTX restart
        # — paths added via runtime API don't persist, but the backend
        # used to require a full restart to re-sync. Now the health check
        # heals it within 30s automatically.
        if path_state is None:
            log.info(
                "camera.path_missing_resyncing",
                camera_id=str(camera.id),
                path=camera.mediamtx_path,
            )
            from app.modules.cameras.service import (
                ensure_browser_path,
                needs_browser_transcode,
            )
            ok = await client.add_path(
                camera.mediamtx_path,
                camera.rtsp_url,
                record=camera.is_recording,
            )
            if ok:
                counts["resynced"] += 1
                # Also re-provision H.264 sibling if this is an H.265 camera
                if needs_browser_transcode(camera.codec):
                    await ensure_browser_path(db, camera)
                # Don't change status yet — let the NEXT health cycle observe
                # the freshly-synced path's state. Avoids flapping.
                continue
            else:
                # Re-sync failed — mark error
                if camera.status != CameraStatus.ERROR.value:
                    camera.status = CameraStatus.ERROR.value
                    camera.last_status_change_at = now
                counts["error"] += 1
                continue

        new_status, detected_codec = _evaluate(path_state)

        # Update codec whenever we know it — even if status didn't change
        if detected_codec and detected_codec != camera.codec:
            log.info(
                "camera.codec_detected",
                camera_id=str(camera.id),
                codec=detected_codec,
            )
            previous_codec = camera.codec
            camera.codec = detected_codec
            # If we've just learned this is an H.265 camera, provision
            # the GPU-transcoded H.264 sibling path now so browser
            # preview works on first click. Idempotent — safe to retry.
            if detected_codec == "H265" and previous_codec != "H265":
                from app.modules.cameras.service import ensure_browser_path
                await ensure_browser_path(db, camera)

        # Track when status flips, for "offline for N minutes" UI
        if camera.status != new_status.value:
            log.info(
                "camera.status_changed",
                camera_id=str(camera.id),
                name=camera.name,
                from_status=camera.status,
                to_status=new_status.value,
            )
            camera.status = new_status.value
            camera.last_status_change_at = now

        if new_status == CameraStatus.ONLINE:
            camera.last_seen_at = now
            counts["online"] += 1
        elif new_status == CameraStatus.OFFLINE:
            counts["offline"] += 1
        elif new_status == CameraStatus.ERROR:
            counts["error"] += 1

    await db.commit()

    # NVENC session counter — log a warning when approaching the consumer
    # GPU limit of 5 concurrent H.264 encode sessions. Each H.265 camera
    # consumes one NVENC session (for the browser-facing transcoder).
    # The 4090 / RTX A6000 etc don't have this limit, but for the RTX 3070
    # / 4060 deployment target it's worth surfacing.
    h265_online_count = sum(
        1
        for c in cameras
        if c.codec == "H265"
        and c.status == CameraStatus.ONLINE.value
    )
    if h265_online_count >= 5:
        log.error(
            "nvenc.session_limit_reached",
            h265_online_count=h265_online_count,
            limit=5,
            hint=(
                "Consumer NVIDIA GPUs cap concurrent H.264 NVENC sessions at 5. "
                "Additional H.265 cameras will fail to transcode. Either upgrade "
                "to a data-center GPU (A6000/L4) or reduce active H.265 cameras."
            ),
        )
    elif h265_online_count == 4:
        log.warning(
            "nvenc.session_limit_approaching",
            h265_online_count=h265_online_count,
            limit=5,
        )

    return counts


def _evaluate(
    path_state: dict | None,
) -> tuple[CameraStatus, str | None]:
    """Map MediaMTX runtime state to our CameraStatus enum.

    Returns (status, detected_codec_or_None).
    """
    # The camera exists in our DB but MediaMTX has no record of it.
    # This usually means MediaMTX restarted and the on-boot sync failed
    # for this camera — the next sync attempt should fix it.
    if path_state is None:
        return CameraStatus.ERROR, None

    tracks = path_state.get("tracks") or []
    ready = bool(path_state.get("ready"))
    bytes_received = path_state.get("bytesReceived") or 0

    # First detected video track is the codec — MediaMTX returns names
    # like "H264", "H265", "MPEG-4 Audio". Filter for video codecs only.
    codec = None
    for track in tracks:
        track_str = str(track).upper()
        if "H264" in track_str or "AVC" in track_str:
            codec = "H264"
            break
        if "H265" in track_str or "HEVC" in track_str:
            codec = "H265"
            break

    # Ready + bytes flowing = online. The bytes check guards against the
    # rare case where MediaMTX reports ready=true momentarily but the
    # source is actually stalled.
    if ready and bytes_received > 0:
        return CameraStatus.ONLINE, codec

    # Path exists, MediaMTX is trying to connect, but it's not flowing yet.
    # This happens during the first ~5-10 seconds after camera creation
    # and after any source URL change.
    return CameraStatus.OFFLINE, codec
