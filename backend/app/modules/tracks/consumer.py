"""Redis Streams → TimescaleDB persistence + Socket.IO live broadcast.

Reads from two streams produced by the AI worker:

  vt:tracks:<tenant_id>            — per-frame detections at 10 fps
  vt:track_lifecycle:<tenant_id>   — track started/ended events

Two background tasks per tenant: one for each stream. The tenant list
is discovered on every iteration so newly created tenants are picked
up without a restart.

Persistence rules:
  - Track LIFECYCLE events always create/update the `tracks` row
    (these are sparse — 1 per track start/end, not per frame)
  - Track FRAME events are sampled at TRACK_POINT_STORE_FPS (default 2)
    before insertion into `track_points`. The full 10 fps still flows
    out via Socket.IO for live overlays.
  - All events are broadcast via Socket.IO at full rate, regardless of
    whether they were persisted.

Failure model:
  - Redis disconnect: backoff and retry, the stream cursor is preserved
    server-side so we resume where we left off (`$` becomes the last
    delivered ID).
  - DB write fails: log and continue. We drop the frame rather than
    block the consumer — a brief storage gap is preferable to falling
    further behind.

Consumer group: we use a single named consumer per tenant per stream so
horizontal scaling (multiple backend replicas) requires only changing
the consumer name to something instance-unique.
"""

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import redis.asyncio as redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import AsyncSessionLocal
from app.core.logging import get_logger
from app.modules.cameras.models import Camera
from app.modules.realtime.socketio_app import broadcast_to_tenant
from app.modules.tenants.models import Tenant
from app.modules.tracks.models import Track, TrackPoint

log = get_logger("tracks.consumer")


# Tunables. These can be moved into Settings later; keeping them as
# module constants for now since they're internal implementation details.
TRACK_POINT_STORE_FPS = float(os.getenv("TRACK_POINT_STORE_FPS", "2.0"))
CONSUMER_GROUP = "vt-backend-consumers"
CONSUMER_NAME = os.getenv("HOSTNAME", "backend-1")  # docker container hostname
BLOCK_MS = 1000  # XREADGROUP block timeout
READ_COUNT = 100  # max events per read


class TrackConsumer:
    """Top-level supervisor. One instance per backend process.

    Spawns per-stream tasks for every tenant. On every iteration of the
    discovery loop, new tenants get new tasks; dead tasks get respawned.
    """

    def __init__(self) -> None:
        self._redis: redis.Redis | None = None
        self._stop = asyncio.Event()
        self._tasks: dict[str, asyncio.Task] = {}
        # Per-camera storage-rate state for the 2 fps sampler
        self._last_stored_ts_ms: dict[str, int] = {}
        # Per-camera BEV homography cache (value, monotonic load time). Used to
        # project track foot-points to floor-plan world coords at ingest, so the
        # multi-view fuser (MV3DT Phase A) has world positions to work with.
        self._homography_cache: dict[UUID, tuple[list[float] | None, float]] = {}

    async def start(self) -> None:
        self._redis = redis.from_url(
            settings.REDIS_URL, encoding="utf-8", decode_responses=True
        )
        await self._redis.ping()
        log.info("consumer.connected", redis_url=settings.REDIS_URL)

        # Start the discovery loop that creates per-tenant tasks
        self._tasks["__discovery"] = asyncio.create_task(
            self._discovery_loop(), name="tracks-discovery"
        )

    async def stop(self) -> None:
        log.info("consumer.stopping")
        self._stop.set()
        for t in self._tasks.values():
            t.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
        log.info("consumer.stopped")

    async def _discovery_loop(self) -> None:
        """Every 30s, ensure every tenant has its two consumer tasks running."""
        while not self._stop.is_set():
            try:
                tenant_ids = await self._fetch_tenant_ids()
                for tid in tenant_ids:
                    self._ensure_task(
                        f"tracks:{tid}",
                        self._consume_track_stream(tid),
                    )
                    self._ensure_task(
                        f"lifecycle:{tid}",
                        self._consume_lifecycle_stream(tid),
                    )
            except Exception as e:
                log.warning("consumer.discovery_failed", error=str(e))

            try:
                await asyncio.wait_for(self._stop.wait(), timeout=30.0)
            except asyncio.TimeoutError:
                pass

    def _ensure_task(self, key: str, coro) -> None:
        """Idempotent task spawn: if not running or finished, start fresh."""
        existing = self._tasks.get(key)
        if existing is not None and not existing.done():
            return
        if existing is not None and existing.done():
            # Surface any unhandled exception in the dead task
            exc = existing.exception() if not existing.cancelled() else None
            if exc is not None:
                log.warning("consumer.task_died_respawning", key=key, error=str(exc))
        self._tasks[key] = asyncio.create_task(coro, name=key)

    async def _fetch_tenant_ids(self) -> list[UUID]:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Tenant.id))
            return [row[0] for row in result.all()]

    # ------------------------------------------------------------------ tracks

    async def _consume_track_stream(self, tenant_id: UUID) -> None:
        """One per tenant. Reads vt:tracks:<tid>, persists + broadcasts."""
        stream_key = f"{settings.TRACK_STREAM_PREFIX}:{tenant_id}"
        await self._ensure_consumer_group(stream_key)

        log.info("consumer.tracks_starting", tenant_id=str(tenant_id))

        backoff = 1.0
        while not self._stop.is_set():
            try:
                entries = await self._redis.xreadgroup(
                    groupname=CONSUMER_GROUP,
                    consumername=CONSUMER_NAME,
                    streams={stream_key: ">"},
                    count=READ_COUNT,
                    block=BLOCK_MS,
                )
            except Exception as e:
                log.warning(
                    "consumer.tracks_read_failed",
                    tenant_id=str(tenant_id),
                    error=str(e),
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
                continue
            backoff = 1.0

            if not entries:
                continue

            # entries: [(stream_key, [(entry_id, {field: value, ...}), ...])]
            for _, items in entries:
                ids_to_ack: list[str] = []
                for entry_id, fields in items:
                    try:
                        await self._handle_track_event(tenant_id, fields)
                        ids_to_ack.append(entry_id)
                    except Exception as e:
                        log.warning(
                            "consumer.handle_failed",
                            tenant_id=str(tenant_id),
                            entry_id=entry_id,
                            error=str(e),
                        )
                        # Don't ack — let it be re-delivered. With our
                        # consumer group's idle policy that will retry.
                if ids_to_ack:
                    try:
                        await self._redis.xack(stream_key, CONSUMER_GROUP, *ids_to_ack)
                    except Exception as e:
                        log.warning("consumer.ack_failed", error=str(e))

    async def _handle_track_event(
        self, tenant_id: UUID, fields: dict[str, str]
    ) -> None:
        """Process one per-frame event: broadcast + (sampled) persist."""
        camera_id = UUID(fields["camera_id"])
        frame_ts_ms = int(fields["frame_ts_ms"])
        tracks = json.loads(fields["tracks"])

        # Always broadcast at full rate
        await broadcast_to_tenant(
            tenant_id,
            "track_update",
            {
                "type": "track_update",
                "camera_id": str(camera_id),
                "frame_ts_ms": frame_ts_ms,
                "tracks": tracks,
            },
        )

        # Sample for storage. Per-camera rate limit, not global.
        sample_key = str(camera_id)
        min_gap_ms = int(1000.0 / TRACK_POINT_STORE_FPS)
        last_ms = self._last_stored_ts_ms.get(sample_key, 0)
        if frame_ts_ms - last_ms < min_gap_ms:
            return  # too soon, drop this frame
        self._last_stored_ts_ms[sample_key] = frame_ts_ms

        # Persist this frame's points. One commit per frame keeps tx
        # short and avoids holding locks across cameras.
        try:
            async with AsyncSessionLocal() as db:
                await self._persist_track_points(
                    db, tenant_id, camera_id, frame_ts_ms, tracks
                )
                await db.commit()
        except Exception as e:
            log.warning(
                "consumer.persist_failed",
                camera_id=str(camera_id),
                error=str(e),
            )

    async def _persist_track_points(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        camera_id: UUID,
        frame_ts_ms: int,
        tracks: list[dict[str, Any]],
    ) -> None:
        """Upsert the Track row for each tracker_id and insert TrackPoint rows."""
        ts = datetime.fromtimestamp(frame_ts_ms / 1000.0, tz=timezone.utc)

        for t in tracks:
            tracker_id = int(t["track_id"])
            bbox = t["bbox"]
            conf = float(t.get("confidence", 0.0))

            # Look up the open track row (one per (camera, tracker_id) pair
            # while it's active). If none exists, we're getting a frame
            # event without a matching lifecycle event — fine, the
            # lifecycle consumer will catch up; meanwhile we create the
            # track row here so the point has a parent.
            track = await self._get_or_create_track(
                db,
                tenant_id=tenant_id,
                camera_id=camera_id,
                tracker_id=tracker_id,
                bbox=bbox,
                ts=ts,
            )

            # Update last_bbox and bump point count
            track.last_bbox = _bbox_to_dict(bbox)
            track.point_count = (track.point_count or 0) + 1

            # Project the foot-point to floor-plan world coords if the camera is
            # BEV-calibrated. Stored on the point for the multi-view fuser + BEV.
            world_x = world_y = None
            H = await self._camera_homography(db, camera_id)
            if H is not None:
                proj = _project_foot(H, bbox)
                if proj is not None and 0.0 <= proj[0] <= 1.0 and 0.0 <= proj[1] <= 1.0:
                    world_x, world_y = proj

            db.add(
                TrackPoint(
                    ts=ts,
                    track_id=track.id,
                    tenant_id=tenant_id,
                    camera_id=camera_id,
                    tracker_id=tracker_id,
                    bbox_x1=float(bbox[0]),
                    bbox_y1=float(bbox[1]),
                    bbox_x2=float(bbox[2]),
                    bbox_y2=float(bbox[3]),
                    confidence=conf,
                    world_x=world_x,
                    world_y=world_y,
                )
            )

    async def _camera_homography(
        self, db: AsyncSession, camera_id: UUID
    ) -> list[float] | None:
        """Return a camera's BEV homography (9 floats), cached for 60s.

        None if the camera has no calibration. The cache avoids a query per
        persisted point; calibration changes propagate within a minute.
        """
        now = time.monotonic()
        cached = self._homography_cache.get(camera_id)
        if cached is not None and now - cached[1] < 60.0:
            return cached[0]
        calibration = (
            await db.execute(
                select(Camera.calibration).where(Camera.id == camera_id)
            )
        ).scalar_one_or_none()
        homography: list[float] | None = None
        if isinstance(calibration, dict):
            h = calibration.get("homography")
            if isinstance(h, list) and len(h) == 9:
                homography = [float(v) for v in h]
        self._homography_cache[camera_id] = (homography, now)
        return homography

    async def _get_or_create_track(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        camera_id: UUID,
        tracker_id: int,
        bbox: list[float],
        ts: datetime,
    ) -> Track:
        """Find the open track or create a new one.

        Note on point_count:
          A newly-created track has point_count=0 until the first frame
          event arrives and increments it. The lifecycle "started" event
          can race ahead of the frame event by up to 500ms (we sample
          frames at 2 fps), so /tracks/active may briefly return tracks
          with point_count=0. This self-corrects on the next frame.
        """
        result = await db.execute(
            select(Track)
            .where(Track.tenant_id == tenant_id)
            .where(Track.camera_id == camera_id)
            .where(Track.tracker_id == tracker_id)
            .where(Track.ended_at.is_(None))
            .order_by(Track.started_at.desc())
            .limit(1)
        )
        track = result.scalar_one_or_none()
        if track is not None:
            return track

        # New track — create
        track = Track(
            tenant_id=tenant_id,
            camera_id=camera_id,
            tracker_id=tracker_id,
            started_at=ts,
            first_bbox=_bbox_to_dict(bbox),
            last_bbox=_bbox_to_dict(bbox),
            point_count=0,
        )
        db.add(track)
        await db.flush()
        return track

    # ----------------------------------------------------------- lifecycle

    async def _consume_lifecycle_stream(self, tenant_id: UUID) -> None:
        """One per tenant. Reads vt:track_lifecycle:<tid>."""
        stream_key = f"{settings.LIFECYCLE_STREAM_PREFIX}:{tenant_id}"
        await self._ensure_consumer_group(stream_key)

        log.info("consumer.lifecycle_starting", tenant_id=str(tenant_id))

        backoff = 1.0
        while not self._stop.is_set():
            try:
                entries = await self._redis.xreadgroup(
                    groupname=CONSUMER_GROUP,
                    consumername=CONSUMER_NAME,
                    streams={stream_key: ">"},
                    count=READ_COUNT,
                    block=BLOCK_MS,
                )
            except Exception as e:
                log.warning(
                    "consumer.lifecycle_read_failed",
                    tenant_id=str(tenant_id),
                    error=str(e),
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
                continue
            backoff = 1.0

            if not entries:
                continue

            for _, items in entries:
                ids_to_ack: list[str] = []
                for entry_id, fields in items:
                    try:
                        await self._handle_lifecycle_event(tenant_id, fields)
                        ids_to_ack.append(entry_id)
                    except Exception as e:
                        log.warning(
                            "consumer.lifecycle_handle_failed",
                            tenant_id=str(tenant_id),
                            entry_id=entry_id,
                            error=str(e),
                        )
                if ids_to_ack:
                    try:
                        await self._redis.xack(stream_key, CONSUMER_GROUP, *ids_to_ack)
                    except Exception as e:
                        log.warning("consumer.lifecycle_ack_failed", error=str(e))

    async def _handle_lifecycle_event(
        self, tenant_id: UUID, fields: dict[str, str]
    ) -> None:
        """Handle a track started/ended event."""
        camera_id = UUID(fields["camera_id"])
        tracker_id = int(fields["track_id"])
        event = fields["event"]
        ts_ms = int(fields["ts_ms"])
        ts = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)

        # Broadcast first — UI may want to play a sound or animation
        await broadcast_to_tenant(
            tenant_id,
            "track_lifecycle",
            {
                "type": "track_lifecycle",
                "camera_id": str(camera_id),
                "tracker_id": tracker_id,
                "event": event,
                "ts_ms": ts_ms,
            },
        )

        try:
            async with AsyncSessionLocal() as db:
                if event == "started":
                    bbox_str = fields.get("bbox")
                    bbox = json.loads(bbox_str) if bbox_str else [0, 0, 0, 0]
                    # Idempotent create — if the frame consumer already
                    # created it, we just leave it.
                    await self._get_or_create_track(
                        db,
                        tenant_id=tenant_id,
                        camera_id=camera_id,
                        tracker_id=tracker_id,
                        bbox=bbox,
                        ts=ts,
                    )
                elif event == "ended":
                    # Close the most recent open track for this tracker_id
                    result = await db.execute(
                        select(Track)
                        .where(Track.tenant_id == tenant_id)
                        .where(Track.camera_id == camera_id)
                        .where(Track.tracker_id == tracker_id)
                        .where(Track.ended_at.is_(None))
                        .order_by(Track.started_at.desc())
                        .limit(1)
                    )
                    track = result.scalar_one_or_none()
                    if track is not None:
                        track.ended_at = ts
                await db.commit()
        except Exception as e:
            log.warning(
                "consumer.lifecycle_persist_failed",
                camera_id=str(camera_id),
                event=event,
                error=str(e),
            )

    # ---------------------------------------------------- consumer group setup

    async def _ensure_consumer_group(self, stream_key: str) -> None:
        """Create the consumer group if it doesn't exist. Idempotent."""
        try:
            await self._redis.xgroup_create(
                stream_key, CONSUMER_GROUP, id="$", mkstream=True
            )
            log.info("consumer.group_created", stream=stream_key)
        except redis.ResponseError as e:
            if "BUSYGROUP" in str(e):
                pass  # already exists, fine
            else:
                raise


# Module-level singleton, started/stopped from main.py lifespan
consumer = TrackConsumer()


def _bbox_to_dict(bbox: list[float]) -> dict[str, float]:
    """Convert [x1, y1, x2, y2] to dict — JSONB friendlier than raw arrays."""
    return {
        "x1": float(bbox[0]),
        "y1": float(bbox[1]),
        "x2": float(bbox[2]),
        "y2": float(bbox[3]),
    }


def _project_foot(
    homography: list[float], bbox: list[float]
) -> tuple[float, float] | None:
    """Project a bbox foot-point (bottom-center) through a row-major 3x3
    homography to floor-plan fractional coords. None if it maps to infinity.

    Mirrors the frontend's bev/homography.ts so ingest and the live BEV view
    agree on positions.
    """
    fx = (float(bbox[0]) + float(bbox[2])) / 2.0
    fy = float(bbox[3])
    h = homography
    w = h[6] * fx + h[7] * fy + h[8]
    if abs(w) < 1e-9:
        return None
    return ((h[0] * fx + h[1] * fy + h[2]) / w, (h[3] * fx + h[4] * fy + h[5]) / w)
