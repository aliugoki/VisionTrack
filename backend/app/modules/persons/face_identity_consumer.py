"""Redis Streams -> Person identity overlay (face-recognition feed).

A separate face-recognition pipeline publishes recognized identities to one
stream per tenant:

  vt:face:identities:<tenant_id>

Each message has fields:
  camera_id        (UUID string)        VisionTrack camera the face was seen on
  emp_id           (string)             external employee id
  name             (string)             display name (may be empty)
  score            (float as string)    match confidence
  bbox             (JSON [left,top,width,height] in source pixels)
  captured_at_ms   (int as string)

Why correlate instead of trust a track_id: the face pipeline runs its OWN
DeepStream tracker, so its track ids don't match VisionTrack's. We bind a face
event to a VisionTrack track by camera + bbox IoU within a small time window,
then label that track's Person. Face labels are an overlay and never feed the
ReID matcher.

Mirrors app.modules.persons.consumer (EmbeddingConsumer) for the supervisor /
discovery / consumer-group / ack scaffolding.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from uuid import UUID

import redis.asyncio as redis
from redis.exceptions import ResponseError
from sqlalchemy import and_, select

from app.core.config import settings
from app.core.db import AsyncSessionLocal
from app.core.logging import get_logger
from app.modules.persons.models import PersonIdentity
from app.modules.tenants.models import Tenant
from app.modules.tracks.models import Track, TrackPoint

log = get_logger("persons.face_identity_consumer")

CONSUMER_GROUP = "vt-backend-consumers"
CONSUMER_NAME = os.getenv("HOSTNAME", "backend-1")
BLOCK_MS = 1000
READ_COUNT = 100


def _iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    """IoU of two xyxy boxes."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


class FaceIdentityConsumer:
    """One task per tenant, reading vt:face:identities:<tenant_id>."""

    def __init__(self) -> None:
        self._redis: redis.Redis | None = None
        self._stop = asyncio.Event()
        self._tasks: dict[str, asyncio.Task] = {}

    async def start(self) -> None:
        self._redis = redis.from_url(
            settings.REDIS_URL, encoding="utf-8", decode_responses=True
        )
        await self._redis.ping()
        log.info("face_identity.connected", redis_url=settings.REDIS_URL)
        self._tasks["__discovery"] = asyncio.create_task(
            self._discovery_loop(), name="face-identity-discovery"
        )

    async def stop(self) -> None:
        log.info("face_identity.stopping")
        self._stop.set()
        for t in self._tasks.values():
            t.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
        log.info("face_identity.stopped")

    async def _discovery_loop(self) -> None:
        while not self._stop.is_set():
            try:
                # Only tenants with facetrack_feed_enabled=true are consumed.
                desired: set[str] = set()
                for tid, external_company_id in await self._fetch_tenants():
                    # Native per-tenant stream.
                    key = f"face-identity:{tid}"
                    desired.add(key)
                    self._ensure_task(key, self._consume_stream(tid))
                    # Company-keyed stream: FaceTrack publishes by company_id (which
                    # it has); we route those events into the mapped tenant. This is
                    # the cross-system bridge for multi-tenant (Phase 3).
                    if external_company_id:
                        ckey = f"face-identity:company:{external_company_id}"
                        desired.add(ckey)
                        self._ensure_task(
                            ckey,
                            self._consume_stream(tid, stream_suffix=external_company_id),
                        )
                # Reap tasks for tenants that have since been disabled (or deleted)
                # — the flag can flip between discovery passes, so stop consuming.
                self._reap_undesired(desired)
            except Exception as e:
                log.warning("face_identity.discovery_failed", error=str(e))
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=30.0)
            except asyncio.TimeoutError:
                pass

    def _reap_undesired(self, desired: set[str]) -> None:
        for key in [k for k in self._tasks if k not in desired]:
            task = self._tasks.pop(key)
            task.cancel()
            log.info("face_identity.reaped", key=key)

    def _ensure_task(self, key: str, coro) -> None:
        existing = self._tasks.get(key)
        if existing is not None and not existing.done():
            return
        if existing is not None and existing.done() and not existing.cancelled():
            exc = existing.exception()
            if exc is not None:
                log.warning("face_identity.task_died_respawning", key=key, error=str(exc))
        self._tasks[key] = asyncio.create_task(coro, name=key)

    async def _fetch_tenants(self) -> list[tuple[UUID, str | None]]:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Tenant.id, Tenant.external_company_id).where(
                    Tenant.facetrack_feed_enabled.is_(True)
                )
            )
            return [(row[0], row[1]) for row in result.all()]

    async def _ensure_consumer_group(self, stream_key: str) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.xgroup_create(
                name=stream_key, groupname=CONSUMER_GROUP, id="0", mkstream=True
            )
            log.info("face_identity.group_created", stream=stream_key)
        except ResponseError as e:
            if "BUSYGROUP" not in str(e):
                log.warning("face_identity.group_create_failed", error=str(e))

    async def _consume_stream(self, tenant_id: UUID, stream_suffix=None) -> None:
        # stream_suffix lets one tenant consume both its own stream and its
        # company-keyed stream (Phase 3); events always route to `tenant_id`.
        suffix = stream_suffix if stream_suffix is not None else tenant_id
        stream_key = f"{settings.FACE_IDENTITY_STREAM_PREFIX}:{suffix}"
        await self._ensure_consumer_group(stream_key)
        log.info("face_identity.starting", tenant_id=str(tenant_id), stream=stream_key)

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
                log.warning("face_identity.read_failed", tenant_id=str(tenant_id), error=str(e))
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
                        await self._handle_identity(tenant_id, fields)
                        ids_to_ack.append(entry_id)
                    except Exception as e:
                        log.warning(
                            "face_identity.handle_failed",
                            tenant_id=str(tenant_id), entry_id=entry_id, error=str(e),
                        )
                if ids_to_ack:
                    try:
                        await self._redis.xack(stream_key, CONSUMER_GROUP, *ids_to_ack)
                    except Exception as e:
                        log.warning("face_identity.ack_failed", error=str(e))

    async def _handle_identity(self, tenant_id: UUID, fields: dict[str, str]) -> None:
        try:
            camera_id = UUID(fields["camera_id"])
            emp_id = str(fields["emp_id"])
            name = fields.get("name") or None
            score = float(fields.get("score", "0") or 0.0)
            l, t, w, h = json.loads(fields["bbox"])
            captured_at = datetime.fromtimestamp(
                int(fields["captured_at_ms"]) / 1000.0, tz=timezone.utc
            )
        except (KeyError, ValueError, TypeError) as e:
            # Bad payload — ack (don't redeliver forever).
            log.warning("face_identity.decode_failed", error=str(e), fields=str(fields)[:200])
            return

        event_box = (float(l), float(t), float(l) + float(w), float(t) + float(h))

        async with AsyncSessionLocal() as db:
            try:
                track_id, person_id = await self._correlate(
                    db, tenant_id, camera_id, captured_at, event_box
                )
                if track_id is None:
                    # No overlapping track in the window — nothing to label.
                    log.debug("face_identity.no_correlation", emp_id=emp_id)
                    return
                await self._upsert_identity(
                    db, tenant_id, person_id, track_id, camera_id, emp_id, name, score
                )
                await db.commit()
            except Exception:
                await db.rollback()
                raise

    async def _correlate(self, db, tenant_id, camera_id, captured_at, event_box):
        """Return (track_id, person_id) of the best-overlapping track, or (None, None)."""
        window = timedelta(milliseconds=settings.FACE_ID_CORRELATION_WINDOW_MS)
        rows = (
            await db.execute(
                select(
                    TrackPoint.track_id,
                    TrackPoint.bbox_x1, TrackPoint.bbox_y1,
                    TrackPoint.bbox_x2, TrackPoint.bbox_y2,
                )
                .where(
                    and_(
                        TrackPoint.tenant_id == tenant_id,
                        TrackPoint.camera_id == camera_id,
                        TrackPoint.ts >= captured_at - window,
                        TrackPoint.ts <= captured_at + window,
                    )
                )
                .limit(settings.FACE_ID_CANDIDATE_LIMIT)
            )
        ).all()

        best_track, best_iou = None, settings.FACE_ID_MIN_IOU
        for tid, x1, y1, x2, y2 in rows:
            iou = _iou(event_box, (x1, y1, x2, y2))
            if iou >= best_iou:
                best_iou, best_track = iou, tid
        if best_track is None:
            return None, None

        person_id = (
            await db.execute(select(Track.person_id).where(Track.id == best_track))
        ).scalar_one_or_none()
        return best_track, person_id

    async def _upsert_identity(
        self, db, tenant_id, person_id, track_id, camera_id, emp_id, name, score
    ):
        now = datetime.now(timezone.utc)
        # Dedupe key: by person when known, else by the correlated track.
        if person_id is not None:
            cond = and_(
                PersonIdentity.tenant_id == tenant_id,
                PersonIdentity.person_id == person_id,
                PersonIdentity.emp_id == emp_id,
            )
        else:
            cond = and_(
                PersonIdentity.tenant_id == tenant_id,
                PersonIdentity.person_id.is_(None),
                PersonIdentity.track_id == track_id,
                PersonIdentity.emp_id == emp_id,
            )
        existing = (await db.execute(select(PersonIdentity).where(cond))).scalar_one_or_none()

        if existing is None:
            db.add(PersonIdentity(
                tenant_id=tenant_id, person_id=person_id, track_id=track_id,
                camera_id=camera_id, emp_id=emp_id, name=name, source="face",
                confidence=score, votes=1, first_labeled_at=now, last_labeled_at=now,
            ))
        else:
            # Running mean confidence + vote count; backfill person_id if resolved.
            existing.confidence = (existing.confidence * existing.votes + score) / (existing.votes + 1)
            existing.votes += 1
            existing.last_labeled_at = now
            existing.track_id = track_id
            if name and not existing.name:
                existing.name = name
            if person_id is not None and existing.person_id is None:
                existing.person_id = person_id


# Module-level singleton (matches consumer.py / matcher shape).
consumer = FaceIdentityConsumer()
