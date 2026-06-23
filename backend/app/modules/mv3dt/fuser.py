"""MV3DT Phase A — multi-view fuser.

Stitches per-camera `tracks` into site-wide `global_tracks` using floor-plan
world positions (from BEV calibration, persisted on track_points) plus the
appearance identity the matcher assigns (`tracks.person_id`).

Runtime model
-------------
A background asyncio sweep started/stopped from app.main lifespan, mirroring
PersonMatcher / the embedding consumer. Every MV3DT_INTERVAL_SECONDS, per
tenant, it fuses *completed, unassigned* tracks within a recent window:

  1. Candidate tracks: global_track_id IS NULL, ended (settled), on a
     BEV-calibrated camera, ended within the look-back window.
  2. Load each candidate's world-coord point series.
  3. Within a floor plan, union two tracks when EITHER:
       - spatial: their world points coincide in space + time
         (avg distance < MV3DT_WORLD_EPS over time-overlapping samples), OR
       - appearance: same non-null person_id and time spans within
         MV3DT_LINK_GAP_SECONDS.
  4. Each union-find cluster -> one GlobalTrack; set tracks.global_track_id;
     emit fused GlobalTrackPoints (world positions averaged across the
     cameras seeing the person at each time bucket).

Why "completed" tracks: a finished track's full world trajectory is known, so
fusion is one-shot and idempotent — each track is assigned to a global track
exactly once. Live merge/extension is a later refinement (see docs/MV3DT.md).
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timedelta, UTC
from uuid import UUID

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import AsyncSessionLocal
from app.core.logging import get_logger
from app.modules.cameras.models import Camera
from app.modules.mv3dt.models import GlobalTrack, GlobalTrackPoint
from app.modules.tenants.models import Tenant
from app.modules.tracks.models import Track, TrackPoint

log = get_logger("mv3dt.fuser")


class _UnionFind:
    """Tiny union-find over hashable ids."""

    def __init__(self) -> None:
        self._parent: dict = {}

    def find(self, x):
        p = self._parent.setdefault(x, x)
        while p != x:
            self._parent[x] = self._parent.setdefault(p, p)
            x, p = p, self._parent[p]
        return x

    def union(self, a, b) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[ra] = rb

    def groups(self) -> dict:
        out: dict = defaultdict(list)
        for x in list(self._parent.keys()):
            out[self.find(x)].append(x)
        return out


class _Candidate:
    """A completed track plus its world-point series within the window."""

    __slots__ = ("track", "pts")

    def __init__(self, track: Track, pts: list[tuple[datetime, float, float, UUID]]):
        self.track = track
        self.pts = pts  # (ts, world_x, world_y, camera_id), time-ordered


class MultiViewFuser:
    def __init__(self) -> None:
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="mv3dt-fuser")
        log.info(
            "fuser.started",
            interval_s=settings.MV3DT_INTERVAL_SECONDS,
            eps=settings.MV3DT_WORLD_EPS,
        )

    async def stop(self) -> None:
        log.info("fuser.stopping")
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        log.info("fuser.stopped")

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                for tid in await self._fetch_tenant_ids():
                    await self._fuse_tenant(tid)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("fuser.sweep_failed", error=str(e))
            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=settings.MV3DT_INTERVAL_SECONDS
                )
            except asyncio.TimeoutError:
                pass

    async def _fetch_tenant_ids(self) -> list[UUID]:
        async with AsyncSessionLocal() as db:
            return [r[0] for r in (await db.execute(select(Tenant.id))).all()]

    async def _fuse_tenant(self, tenant_id: UUID) -> None:
        async with AsyncSessionLocal() as db:
            try:
                created = await self._fuse(db, tenant_id)
                if created:
                    await db.commit()
                    log.info(
                        "fuser.tenant_done",
                        tenant_id=str(tenant_id),
                        global_tracks=created,
                    )
                else:
                    await db.rollback()
            except Exception:
                await db.rollback()
                raise

    async def _fuse(self, db: AsyncSession, tenant_id: UUID) -> int:
        now = datetime.now(tz=UTC)
        window_start = now - timedelta(seconds=settings.MV3DT_WINDOW_SECONDS)
        settle_before = now - timedelta(seconds=settings.MV3DT_SETTLE_SECONDS)

        # camera_id -> floor_plan_id for BEV-calibrated cameras in this tenant.
        cam_plan = await self._calibrated_cameras(db, tenant_id)
        if not cam_plan:
            return 0

        # Candidate completed, unassigned tracks on calibrated cameras.
        tracks = (
            await db.execute(
                select(Track).where(
                    Track.tenant_id == tenant_id,
                    Track.global_track_id.is_(None),
                    Track.ended_at.is_not(None),
                    Track.ended_at < settle_before,
                    Track.ended_at >= window_start,
                    Track.camera_id.in_(list(cam_plan.keys())),
                )
            )
        ).scalars().all()
        if len(tracks) < 1:
            return 0

        # Load world-point series per candidate; drop those without world data.
        candidates: list[_Candidate] = []
        for tr in tracks:
            pts = (
                await db.execute(
                    select(
                        TrackPoint.ts,
                        TrackPoint.world_x,
                        TrackPoint.world_y,
                        TrackPoint.camera_id,
                    )
                    .where(
                        TrackPoint.track_id == tr.id,
                        TrackPoint.world_x.is_not(None),
                    )
                    .order_by(TrackPoint.ts)
                )
            ).all()
            if pts:
                candidates.append(
                    _Candidate(tr, [(p.ts, p.world_x, p.world_y, p.camera_id) for p in pts])
                )
        if not candidates:
            return 0

        created = 0
        # Fuse within each floor plan independently.
        by_plan: dict[UUID, list[_Candidate]] = defaultdict(list)
        for c in candidates:
            by_plan[cam_plan[c.track.camera_id]].append(c)

        for floor_plan_id, group in by_plan.items():
            uf = _UnionFind()
            for c in group:
                uf.find(c.track.id)  # ensure singletons are represented
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    if self._should_link(group[i], group[j]):
                        uf.union(group[i].track.id, group[j].track.id)

            by_id = {c.track.id: c for c in group}
            for member_ids in uf.groups().values():
                members = [by_id[mid] for mid in member_ids]
                await self._materialize(db, tenant_id, floor_plan_id, members)
                created += 1
        return created

    async def _calibrated_cameras(
        self, db: AsyncSession, tenant_id: UUID
    ) -> dict[UUID, UUID]:
        rows = (
            await db.execute(
                select(Camera.id, Camera.calibration).where(
                    Camera.tenant_id == tenant_id
                )
            )
        ).all()
        out: dict[UUID, UUID] = {}
        for cam_id, calibration in rows:
            if isinstance(calibration, dict):
                fp = calibration.get("floor_plan_id")
                h = calibration.get("homography")
                if fp and isinstance(h, list) and len(h) == 9:
                    try:
                        out[cam_id] = UUID(str(fp))
                    except (ValueError, AttributeError):
                        continue
        return out

    def _should_link(self, a: _Candidate, b: _Candidate) -> bool:
        # Appearance: same identity, time spans close together.
        pa, pb = a.track.person_id, b.track.person_id
        if pa is not None and pb is not None and pa == pb:
            gap = self._span_gap(a.track, b.track)
            if gap <= settings.MV3DT_LINK_GAP_SECONDS:
                return True
        # Spatial: world positions coincide in space + time across cameras.
        bucket = timedelta(milliseconds=settings.MV3DT_FUSE_BUCKET_MS)
        overlaps: list[float] = []
        for ts_a, xa, ya, _ in a.pts:
            for ts_b, xb, yb, _ in b.pts:
                if abs((ts_a - ts_b).total_seconds()) <= bucket.total_seconds():
                    overlaps.append(((xa - xb) ** 2 + (ya - yb) ** 2) ** 0.5)
        if overlaps:
            avg = sum(overlaps) / len(overlaps)
            if avg < settings.MV3DT_WORLD_EPS:
                return True
        return False

    @staticmethod
    def _span_gap(a: Track, b: Track) -> float:
        """Seconds between the two tracks' time spans (0 if they overlap)."""
        a0, a1 = a.started_at, a.ended_at or a.started_at
        b0, b1 = b.started_at, b.ended_at or b.started_at
        if a1 < b0:
            return (b0 - a1).total_seconds()
        if b1 < a0:
            return (a0 - b1).total_seconds()
        return 0.0

    async def _materialize(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        floor_plan_id: UUID,
        members: list[_Candidate],
    ) -> None:
        starts = [m.track.started_at for m in members]
        ends = [m.track.ended_at for m in members]
        person_ids = {m.track.person_id for m in members if m.track.person_id}
        gt = GlobalTrack(
            tenant_id=tenant_id,
            floor_plan_id=floor_plan_id,
            person_id=next(iter(person_ids)) if len(person_ids) == 1 else None,
            started_at=min(starts),
            ended_at=None if any(e is None for e in ends) else max(ends),
        )
        db.add(gt)
        await db.flush()  # assign gt.id

        # Link the per-camera fragments.
        await db.execute(
            update(Track)
            .where(
                Track.id.in_([m.track.id for m in members]),
                Track.tenant_id == tenant_id,
            )
            .values(global_track_id=gt.id)
        )

        # Fuse world points: average across cameras per time bucket.
        bucket_ms = settings.MV3DT_FUSE_BUCKET_MS
        buckets: dict[int, list[tuple[float, float, UUID]]] = defaultdict(list)
        for m in members:
            for ts, x, y, cam in m.pts:
                key = int(ts.timestamp() * 1000) // bucket_ms
                buckets[key].append((x, y, cam))
        for key, vals in buckets.items():
            n = len(vals)
            avg_x = sum(v[0] for v in vals) / n
            avg_y = sum(v[1] for v in vals) / n
            ts = datetime.fromtimestamp((key * bucket_ms) / 1000.0, tz=UTC)
            db.add(
                GlobalTrackPoint(
                    ts=ts,
                    global_track_id=gt.id,
                    tenant_id=tenant_id,
                    world_x=avg_x,
                    world_y=avg_y,
                    contributing_camera_id=vals[0][2] if n == 1 else None,
                    confidence=float(min(n, 3)) / 3.0,  # more cameras => more sure
                )
            )


# Module-level singleton (matches matcher.py / consumer.py shape).
fuser = MultiViewFuser()
