"""Service layer for analytics queries.

Time-bucket strategy:
  We use PostgreSQL's built-in `date_trunc()` for time-series aggregation.
  This works on any PostgreSQL installation (TimescaleDB not required).

  For our data volumes (<1M alerts, <10M track_points per tenant) the
  performance difference vs TimescaleDB's `time_bucket()` is negligible
  given our existing indexes on (tenant_id, fired_at) and
  (tenant_id, ts DESC). If we later need finer than hourly granularity
  or much larger volumes, switching to TimescaleDB is a single function
  rename here.

Tenant safety:
  Every query filters on tenant_id from the JWT. No cross-tenant reads
  are possible from this layer.

Date range semantics:
  - `started_after` is the inclusive lower bound
  - `started_before` is the exclusive upper bound
  - Callers pass a half-open interval [from, to)
"""

from __future__ import annotations

from datetime import datetime, timedelta, UTC
from typing import Literal
from uuid import UUID

from sqlalchemy import and_, distinct, func, or_, select, text, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from zoneinfo import ZoneInfo

from app.modules.alerts.models import Alert
from app.modules.analytics.attendance import attendance_from_dwell
from app.modules.analytics.heatmap import hour_of_day_heatmap
from app.modules.analytics.zone_report import zone_rollup_from_dwell
from app.modules.tenants.models import Tenant
from app.modules.analytics.dwell import (
    accumulate_dwell,
    build_person_timeline,
    camera_zone_index,
    clip_interval,
    track_zone_intervals,
    union_seconds,
    zone_durations_from_intervals,
)
from app.modules.analytics.occupancy import zones_occupancy_from_tracks
from app.modules.analytics.zone_resolve import (
    camera_plan_zones,
    homographies_by_camera,
    point_zone_refs,
    resolve_track_zone_refs,
)
from app.modules.cameras.models import Camera
from app.modules.floor_plans.models import FloorPlan
from app.modules.persons.models import PersonIdentity
from app.modules.recordings.models import Recording
from app.modules.tracks.models import Track, TrackPoint


# Supported bucket sizes — keep this list short. The bucket name maps
# directly to a date_trunc precision.
BUCKET_PRECISION: dict[str, str] = {
    "hour": "hour",
    "day": "day",
}


async def get_overview(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    started_after: datetime,
    started_before: datetime,
) -> dict:
    """Aggregate the 4-7 KPI tiles in a single round-trip per source table.

    Returns a dict matching OverviewKPIs schema.
    """
    # Alerts aggregate
    alerts_q = select(
        func.count().label("total"),
        func.count().filter(Alert.status == "active").label("active"),
        func.count().filter(Alert.severity == "critical").label("critical"),
        func.count(distinct(Alert.zone_id)).label("distinct_zones"),
    ).where(
        Alert.tenant_id == tenant_id,
        Alert.fired_at >= started_after,
        Alert.fired_at < started_before,
    )
    alerts_row = (await db.execute(alerts_q)).one()

    # Distinct persons tracked = distinct (camera_id, tracker_id) pairs.
    # tracker_id alone isn't unique across cameras (each camera resets
    # its tracker numbering). The combo is what represents a unique
    # tracked person in the absence of cross-camera ReID (Phase 3+).
    persons_q = select(
        func.count(distinct(tuple_(TrackPoint.camera_id, TrackPoint.tracker_id)))
    ).where(
        TrackPoint.tenant_id == tenant_id,
        TrackPoint.ts >= started_after,
        TrackPoint.ts < started_before,
    )
    persons = (await db.execute(persons_q)).scalar_one() or 0

    # Recordings aggregate
    rec_q = select(
        func.count().label("count"),
        func.coalesce(func.sum(Recording.size_bytes), 0).label("size_bytes"),
    ).where(
        Recording.tenant_id == tenant_id,
        Recording.started_at >= started_after,
        Recording.started_at < started_before,
    )
    rec_row = (await db.execute(rec_q)).one()

    return {
        "alerts_total": int(alerts_row.total or 0),
        "alerts_active": int(alerts_row.active or 0),
        "alerts_critical": int(alerts_row.critical or 0),
        "distinct_zones_with_alerts": int(alerts_row.distinct_zones or 0),
        "distinct_persons_tracked": int(persons),
        "recordings_count": int(rec_row.count or 0),
        "recordings_size_bytes": int(rec_row.size_bytes or 0),
    }


async def get_alerts_timeseries(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    started_after: datetime,
    started_before: datetime,
    bucket: Literal["hour", "day"],
) -> list[dict]:
    """Time-bucketed alert counts.

    Returns rows ordered by bucket_start ASC. Empty buckets ARE in the
    result (count=0) — we want gap-free time-series for charting.

    NOTE: gap-filling done in Python rather than SQL to keep the query
    portable. For <500 buckets this is faster than generate_series JOINs.
    """
    precision = BUCKET_PRECISION[bucket]

    # The actual count query
    q = (
        select(
            func.date_trunc(precision, Alert.fired_at).label("bucket_start"),
            func.count().label("count"),
        )
        .where(
            Alert.tenant_id == tenant_id,
            Alert.fired_at >= started_after,
            Alert.fired_at < started_before,
        )
        .group_by(text("bucket_start"))
        .order_by(text("bucket_start"))
    )
    rows = (await db.execute(q)).all()

    # Build a dense gap-filled series. For the chart to look right with
    # no data, we want consecutive bucket_starts even where count=0.
    return _gapfill(rows, started_after, started_before, bucket)


async def get_people_timeseries(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    started_after: datetime,
    started_before: datetime,
    bucket: Literal["hour", "day"],
) -> list[dict]:
    """Distinct persons tracked per time bucket.

    Distinct (camera_id, tracker_id) per bucket. This approximates
    "how many unique persons were tracked during this hour/day"
    without ReID. The double-counts (same physical person across
    cameras) are intentional — until we have ReID, this is the
    closest honest answer.
    """
    precision = BUCKET_PRECISION[bucket]

    q = (
        select(
            func.date_trunc(precision, TrackPoint.ts).label("bucket_start"),
            func.count(
                distinct(tuple_(TrackPoint.camera_id, TrackPoint.tracker_id))
            ).label("count"),
        )
        .where(
            TrackPoint.tenant_id == tenant_id,
            TrackPoint.ts >= started_after,
            TrackPoint.ts < started_before,
        )
        .group_by(text("bucket_start"))
        .order_by(text("bucket_start"))
    )
    rows = (await db.execute(q)).all()
    return _gapfill(rows, started_after, started_before, bucket)


async def get_alerts_breakdown(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    started_after: datetime,
    started_before: datetime,
) -> dict:
    """Three slices of alerts data in one round-trip.

    Each slice is top-10 by count, descending.
    Returns dict matching AlertsBreakdownResponse schema.
    """
    base_filter = and_(
        Alert.tenant_id == tenant_id,
        Alert.fired_at >= started_after,
        Alert.fired_at < started_before,
    )

    async def _slice(col_label, col) -> list[dict]:
        q = (
            select(col.label("label"), func.count().label("count"))
            .where(base_filter)
            .group_by(col)
            .order_by(func.count().desc())
            .limit(10)
        )
        rows = (await db.execute(q)).all()
        # Some rule_label rows can be NULL — represent as "(unnamed)"
        return [
            {
                "label": (row.label if row.label not in (None, "") else "(unnamed)"),
                "count": int(row.count),
            }
            for row in rows
        ]

    return {
        "by_severity": await _slice("severity", Alert.severity),
        "by_zone": await _slice("zone", Alert.zone_name),
        "by_rule": await _slice("rule", Alert.rule_label),
    }


# ---------------------------------------------------------------------------
# Internal: gap-fill a sparse time-series into a dense one
# ---------------------------------------------------------------------------

def _gapfill(
    rows: list,
    started_after: datetime,
    started_before: datetime,
    bucket: Literal["hour", "day"],
) -> list[dict]:
    """Densify a sparse time-bucket series.

    If the user asked for 7 days and only 3 days have alerts, the chart
    will look misleading (missing days "skip"). We insert count=0
    placeholders for every empty bucket within [started_after, started_before).
    """
    from datetime import timedelta

    # Bucket step
    step = timedelta(hours=1) if bucket == "hour" else timedelta(days=1)

    # Floor the range to bucket boundaries
    def _floor(dt: datetime) -> datetime:
        if bucket == "hour":
            return dt.replace(minute=0, second=0, microsecond=0)
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)

    counts: dict[datetime, int] = {}
    for r in rows:
        # SQLAlchemy returns row.bucket_start as datetime with TZ
        counts[r.bucket_start] = int(r.count)

    cursor = _floor(started_after)
    end = started_before
    out: list[dict] = []
    while cursor < end:
        out.append({
            "bucket_start": cursor,
            "count": counts.get(cursor, 0),
        })
        cursor = cursor + step
        # Safety: cap dense series at ~500 buckets
        if len(out) > 500:
            break

    return out



async def get_persons_summary(
    db: AsyncSession, *, tenant_id: UUID
) -> dict:
    """Compute identity-level stats from the persons table.

    All four metrics in one query — counting separately would round-trip
    four times for what's a tiny aggregation.

    Today is defined in UTC; if we add tenant timezone awareness later,
    this is where it'd plug in.
    """
    from app.modules.persons.models import Person  # local import to avoid cycle

    now = datetime.now(tz=UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    last_24h = now - timedelta(hours=24)

    q = select(
        func.count(Person.id).label("total"),
        func.count(Person.id).filter(Person.last_seen_at > last_24h).label("active"),
        func.count(Person.id).filter(Person.created_at >= today_start).label("new_today"),
        func.coalesce(func.avg(Person.appearance_count), 0.0).label("avg_app"),
    ).where(Person.tenant_id == tenant_id)

    row = (await db.execute(q)).one()
    return {
        "total_identities": int(row.total or 0),
        "active_last_24h": int(row.active or 0),
        "new_today": int(row.new_today or 0),
        "avg_appearances": float(row.avg_app or 0.0),
    }


async def _zone_resolution_context(db: AsyncSession, *, tenant_id: UUID):
    """Everything needed to attribute a track to zones: the tenant's floor plans,
    the camera-marker zone index (coarse fallback), the per-camera plan zones
    (for position mode), and each calibrated camera's homography.

    Returns ``(floor_plans, marker_zones, plan_zones, homographies)``.
    """
    fps = [
        {"id": r.id, "name": r.name, "zones": r.zones, "markers": r.markers}
        for r in (await db.execute(
            select(FloorPlan.id, FloorPlan.name, FloorPlan.zones, FloorPlan.markers)
            .where(FloorPlan.tenant_id == tenant_id)
        )).all()
    ]
    marker_zones = camera_zone_index(fps)
    plan_zones = camera_plan_zones(fps)
    cam_rows = (await db.execute(
        select(Camera.id, Camera.calibration).where(Camera.tenant_id == tenant_id)
    )).all()
    homographies = homographies_by_camera([(r.id, r.calibration) for r in cam_rows])
    return fps, marker_zones, plan_zones, homographies


async def _resolve_tracks_with_zones(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    rows,
    best_by_track: dict,
    best_by_person: dict,
    marker_zones: dict,
    plan_zones: dict,
    homographies: dict,
    started_after: datetime,
    started_before: datetime,
    active_cutoff: datetime,
    only_emp: str | None = None,
) -> list[dict]:
    """Turn Track rows into named-employee presence records with zone attribution.

    For a track on a **calibrated** camera we time-weight per ``track_point``: the
    person's foot-point (``world_x/world_y``, projected at ingest) is tested
    against the zone polygons frame by frame, so a track that *moves* between
    desks splits its time (``"intervals"``). Tracks with no world points fall back
    to whole-track attribution (``"zones"`` + ``start``/``end``) via
    ``resolve_track_zone_refs`` (last-bbox position for calibrated cameras,
    camera-marker otherwise). Anonymous tracks (and, if ``only_emp`` is given,
    other employees) are dropped.

    Each returned dict has ``emp_id``, ``name``, ``present``, ``camera_id`` and
    EITHER ``intervals`` (time-ordered zone visits) OR ``zones`` + ``start`` +
    ``end``.
    """
    # 1) Clip + identity + split calibrated vs not.
    named: list[dict] = []
    calib_meta: dict = {}  # track_id -> {camera_id, seg_start, seg_end}
    for r in rows:
        ident = best_by_track.get(r.id) or (
            best_by_person.get(r.person_id) if r.person_id is not None else None)
        if not ident or not ident[0]:
            continue
        if only_emp is not None and ident[0] != only_emp:
            continue
        raw_end = r.ended_at if r.ended_at is not None else r.updated_at
        clipped = clip_interval(r.started_at, raw_end, started_after, started_before)
        if clipped is None:
            continue
        present = r.ended_at is None and r.updated_at >= active_cutoff
        rec = {
            "track_id": r.id, "camera_id": str(r.camera_id),
            "emp_id": ident[0], "name": ident[1], "present": present,
            "last_bbox": r.last_bbox, "start": clipped[0], "end": clipped[1],
        }
        named.append(rec)
        if str(r.camera_id) in homographies:
            calib_meta[r.id] = {
                "camera_id": str(r.camera_id),
                "seg_start": clipped[0], "seg_end": clipped[1],
            }

    # 2) Per-point intervals for calibrated tracks (one bounded track_points scan).
    intervals_by_track: dict = {}
    if calib_meta:
        pt_rows = (await db.execute(
            select(
                TrackPoint.track_id, TrackPoint.ts,
                TrackPoint.world_x, TrackPoint.world_y,
            ).where(
                TrackPoint.tenant_id == tenant_id,
                TrackPoint.track_id.in_(list(calib_meta.keys())),
                TrackPoint.ts >= started_after,
                TrackPoint.ts < started_before,
                TrackPoint.world_x.is_not(None),
                TrackPoint.world_y.is_not(None),
            ).order_by(TrackPoint.track_id, TrackPoint.ts)
        )).all()
        grouped: dict = {}
        for r in pt_rows:
            grouped.setdefault(r.track_id, []).append(r)
        for tid, pts in grouped.items():
            meta = calib_meta[tid]
            pz = plan_zones.get(meta["camera_id"], [])
            samples = [
                (p.ts, point_zone_refs(float(p.world_x), float(p.world_y), pz))
                for p in pts
            ]
            intervals_by_track[tid] = track_zone_intervals(
                samples, meta["seg_start"], meta["seg_end"])

    # 3) Emit records: per-point where we have world samples, else whole-track.
    #    span_seconds = the track's window-clipped presence (for aisle/idle time).
    out: list[dict] = []
    for rec in named:
        tid = rec["track_id"]
        span = (rec["end"] - rec["start"]).total_seconds()
        if tid in intervals_by_track:
            out.append({
                "emp_id": rec["emp_id"], "name": rec["name"],
                "present": rec["present"], "camera_id": rec["camera_id"],
                "span_seconds": span, "intervals": intervals_by_track[tid],
            })
        else:
            refs = resolve_track_zone_refs(
                rec["camera_id"], rec["last_bbox"], homographies,
                marker_zones, plan_zones)
            out.append({
                "emp_id": rec["emp_id"], "name": rec["name"],
                "present": rec["present"], "camera_id": rec["camera_id"],
                "span_seconds": span, "zones": refs,
                "start": rec["start"], "end": rec["end"],
            })
    return out


async def get_zone_occupancy(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    active_window_sec: int = 60,
) -> dict:
    """Live per-zone headcount, split known vs unknown.

    A track is "present" if it hasn't ended and was updated within
    ``active_window_sec``. It is "known" when it (or its person) carries a face
    identity (``person_identities``) — i.e. the FaceTrack feed named it.

    Zone attribution is desk-level where possible: for a BEV-calibrated camera a
    person is placed by projecting their foot-point into the zone polygons, so
    several desks in one camera's view are counted separately; uncalibrated
    cameras fall back to the camera-marker model. Pure aggregation is in
    ``occupancy.py``.
    """
    now = datetime.now(UTC)
    cutoff = now - timedelta(seconds=active_window_sec)

    active = (await db.execute(
        select(Track.id, Track.camera_id, Track.person_id, Track.last_bbox).where(
            Track.tenant_id == tenant_id,
            Track.ended_at.is_(None),
            Track.updated_at >= cutoff,
        )
    )).all()

    best_by_track, best_by_person = await _best_identity_by_track(
        db, tenant_id=tenant_id,
        track_ids=[r.id for r in active],
        person_ids=[r.person_id for r in active if r.person_id is not None],
    )

    fps, marker_zones, plan_zones, homographies = await _zone_resolution_context(
        db, tenant_id=tenant_id)

    tracks = []
    for r in active:
        ident = best_by_track.get(r.id) or (
            best_by_person.get(r.person_id) if r.person_id is not None else None)
        tracks.append({
            "camera_id": str(r.camera_id),
            "emp_id": ident[0] if ident else None,
            "name": ident[1] if ident else None,
            "zones": resolve_track_zone_refs(
                r.camera_id, r.last_bbox, homographies, marker_zones, plan_zones),
        })

    return {
        "as_of": now,
        "active_window_sec": active_window_sec,
        "zones": zones_occupancy_from_tracks(fps, tracks),
    }


async def _best_identity_by_track(
    db: AsyncSession, *, tenant_id: UUID, track_ids: list, person_ids: list
) -> tuple[dict, dict]:
    """Strongest face identity per track_id and per person_id.

    Returns ``(best_by_track, best_by_person)`` mapping id -> ``(emp_id, name)``.
    "Strongest" = most votes, then confidence, then most recent label — so a
    single stray correlation can't outrank an established identity. Shared by the
    occupancy and dwell paths so both agree on who a track is.
    """
    best_by_track: dict = {}
    best_by_person: dict = {}
    if not (track_ids or person_ids):
        return best_by_track, best_by_person
    conds = []
    if track_ids:
        conds.append(PersonIdentity.track_id.in_(track_ids))
    if person_ids:
        conds.append(PersonIdentity.person_id.in_(person_ids))
    ident_rows = (await db.execute(
        select(
            PersonIdentity.track_id, PersonIdentity.person_id,
            PersonIdentity.emp_id, PersonIdentity.name,
        ).where(PersonIdentity.tenant_id == tenant_id, or_(*conds))
        .order_by(
            PersonIdentity.votes.desc(),
            PersonIdentity.confidence.desc(),
            PersonIdentity.last_labeled_at.desc(),
        )
    )).all()
    for row in ident_rows:
        if row.track_id is not None and row.track_id not in best_by_track:
            best_by_track[row.track_id] = (row.emp_id, row.name)
        if row.person_id is not None and row.person_id not in best_by_person:
            best_by_person[row.person_id] = (row.emp_id, row.name)
    return best_by_track, best_by_person


async def get_zone_dwell(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    started_after: datetime,
    started_before: datetime,
    active_window_sec: int = 60,
    min_seconds: int = 0,
    emp_id: str | None = None,
    zone_id: str | None = None,
) -> dict:
    """Per-named-person time-in-zone over ``[started_after, started_before)``.

    "Indoor geofencing": each track's lifetime on a camera is the person's dwell
    in the zone(s) they were in. We sum per (employee, zone), clipped to the
    window, and flag anyone whose track is still active (``present``) so the UI
    can show "here now". Zone attribution is desk-level for BEV-calibrated cameras
    (foot-point in polygon) and camera-marker otherwise — so a department camera
    gives department dwell and a calibrated multi-desk camera gives per-desk
    dwell. Pure aggregation lives in ``dwell.py``.
    """
    now = datetime.now(UTC)
    active_cutoff = now - timedelta(seconds=active_window_sec)

    # 1) Tracks overlapping the window: started before the window ends AND either
    #    still open or ended after the window starts.
    rows = (await db.execute(
        select(
            Track.id, Track.camera_id, Track.person_id,
            Track.started_at, Track.ended_at, Track.updated_at, Track.last_bbox,
        ).where(
            Track.tenant_id == tenant_id,
            Track.started_at < started_before,
            or_(Track.ended_at.is_(None), Track.ended_at >= started_after),
        )
    )).all()

    # 2) Attach the strongest face identity (by track, else by person).
    track_ids = [r.id for r in rows]
    person_ids = [r.person_id for r in rows if r.person_id is not None]
    best_by_track, best_by_person = await _best_identity_by_track(
        db, tenant_id=tenant_id, track_ids=track_ids, person_ids=person_ids
    )

    # 3) Zone-resolution context (marker fallback + homography for desk-level).
    fps, marker_zones, plan_zones, homographies = await _zone_resolution_context(
        db, tenant_id=tenant_id)

    # 4) Resolve each track to zones — time-weighted per track-point on calibrated
    #    cameras (splits a moving track across desks), whole-track otherwise.
    resolved = await _resolve_tracks_with_zones(
        db, tenant_id=tenant_id, rows=rows,
        best_by_track=best_by_track, best_by_person=best_by_person,
        marker_zones=marker_zones, plan_zones=plan_zones, homographies=homographies,
        started_after=started_after, started_before=started_before,
        active_cutoff=active_cutoff)

    tracks: list[dict] = []
    for rec in resolved:
        if "intervals" in rec:
            tracks.append({
                "emp_id": rec["emp_id"], "name": rec["name"], "present": rec["present"],
                "zone_durations": zone_durations_from_intervals(rec["intervals"]),
            })
        else:
            tracks.append(rec)  # zones + start + end

    dwell_rows = [
        row for row in accumulate_dwell(tracks)
        if row["seconds"] >= min_seconds
        and (emp_id is None or row["emp_id"] == emp_id)
        and (zone_id is None or row["zone_id"] == zone_id)
    ]
    return {
        "as_of": now,
        "from": started_after,
        "to": started_before,
        "active_window_sec": active_window_sec,
        "rows": dwell_rows,
    }


async def _aisle_by_employee(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    started_after: datetime,
    started_before: datetime,
    active_window_sec: int,
    emp_id: str | None = None,
) -> dict:
    """Per-employee **idle/aisle** seconds — time a person's track existed but
    their position was in **no** zone (walking between desks / in an aisle).

    Per track: ``span - covered``, where ``covered`` is the union of the track's
    in-zone intervals. Calibrated cameras (per-track-point) reveal aisle time
    inside a track; whole-track (marker/last-bbox) attribution is fully in-zone so
    it contributes zero. Summed per employee (same non-cross-track model as
    ``tracked_seconds``)."""
    now = datetime.now(UTC)
    active_cutoff = now - timedelta(seconds=active_window_sec)
    rows = (await db.execute(
        select(
            Track.id, Track.camera_id, Track.person_id,
            Track.started_at, Track.ended_at, Track.updated_at, Track.last_bbox,
        ).where(
            Track.tenant_id == tenant_id,
            Track.started_at < started_before,
            or_(Track.ended_at.is_(None), Track.ended_at >= started_after),
        )
    )).all()
    best_by_track, best_by_person = await _best_identity_by_track(
        db, tenant_id=tenant_id,
        track_ids=[r.id for r in rows],
        person_ids=[r.person_id for r in rows if r.person_id is not None],
    )
    _fps, marker_zones, plan_zones, homographies = await _zone_resolution_context(
        db, tenant_id=tenant_id)
    resolved = await _resolve_tracks_with_zones(
        db, tenant_id=tenant_id, rows=rows,
        best_by_track=best_by_track, best_by_person=best_by_person,
        marker_zones=marker_zones, plan_zones=plan_zones, homographies=homographies,
        started_after=started_after, started_before=started_before,
        active_cutoff=active_cutoff, only_emp=emp_id)

    aisle: dict[str, float] = {}
    for rec in resolved:
        span = rec.get("span_seconds", 0.0)
        if "intervals" in rec:
            covered = union_seconds([(iv["start"], iv["end"]) for iv in rec["intervals"]])
        else:
            covered = span if rec.get("zones") else 0.0
        aisle[rec["emp_id"]] = aisle.get(rec["emp_id"], 0.0) + max(0.0, span - covered)
    return aisle


async def get_attendance(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    started_after: datetime,
    started_before: datetime,
    active_window_sec: int = 60,
    min_seconds: int = 0,
    emp_id: str | None = None,
    zone_id: str | None = None,
) -> dict:
    """Per-employee attendance (arrival / departure / on-site span / tracked /
    idle) over the window. Rolls up ``get_zone_dwell`` so it stays consistent,
    and adds per-employee idle/aisle time (tracked but in no zone)."""
    dwell = await get_zone_dwell(
        db, tenant_id=tenant_id,
        started_after=started_after, started_before=started_before,
        active_window_sec=active_window_sec, min_seconds=min_seconds,
        emp_id=emp_id, zone_id=zone_id,
    )
    aisle = await _aisle_by_employee(
        db, tenant_id=tenant_id,
        started_after=started_after, started_before=started_before,
        active_window_sec=active_window_sec, emp_id=emp_id)
    rows = attendance_from_dwell(dwell["rows"])
    for r in rows:
        r["idle_seconds"] = aisle.get(r["emp_id"], 0.0)
    return {
        "as_of": dwell["as_of"],
        "from": dwell["from"],
        "to": dwell["to"],
        "rows": rows,
    }


async def get_zone_rollup(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    started_after: datetime,
    started_before: datetime,
    active_window_sec: int = 60,
    min_seconds: int = 0,
    emp_id: str | None = None,
    zone_id: str | None = None,
) -> dict:
    """Per-zone rollup (total person-time, distinct people, avg, present) over the
    window. Rolls up ``get_zone_dwell`` so it honours the same filters."""
    dwell = await get_zone_dwell(
        db, tenant_id=tenant_id,
        started_after=started_after, started_before=started_before,
        active_window_sec=active_window_sec, min_seconds=min_seconds,
        emp_id=emp_id, zone_id=zone_id,
    )
    return {
        "as_of": dwell["as_of"],
        "from": dwell["from"],
        "to": dwell["to"],
        "rows": zone_rollup_from_dwell(dwell["rows"]),
    }


async def get_occupancy_heatmap(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    started_after: datetime,
    started_before: datetime,
    active_window_sec: int = 60,
    emp_id: str | None = None,
    zone_id: str | None = None,
) -> dict:
    """Hour-of-day occupancy heatmap — per zone, person-time + distinct people in
    each of the 24 hours (tenant-local), aggregated across the range. Uses the
    same track->zone resolution as dwell (so it agrees), then buckets by hour."""
    now = datetime.now(UTC)
    active_cutoff = now - timedelta(seconds=active_window_sec)

    rows = (await db.execute(
        select(
            Track.id, Track.camera_id, Track.person_id,
            Track.started_at, Track.ended_at, Track.updated_at, Track.last_bbox,
        ).where(
            Track.tenant_id == tenant_id,
            Track.started_at < started_before,
            or_(Track.ended_at.is_(None), Track.ended_at >= started_after),
        )
    )).all()

    best_by_track, best_by_person = await _best_identity_by_track(
        db, tenant_id=tenant_id,
        track_ids=[r.id for r in rows],
        person_ids=[r.person_id for r in rows if r.person_id is not None],
    )
    _fps, marker_zones, plan_zones, homographies = await _zone_resolution_context(
        db, tenant_id=tenant_id)
    resolved = await _resolve_tracks_with_zones(
        db, tenant_id=tenant_id, rows=rows,
        best_by_track=best_by_track, best_by_person=best_by_person,
        marker_zones=marker_zones, plan_zones=plan_zones, homographies=homographies,
        started_after=started_after, started_before=started_before,
        active_cutoff=active_cutoff, only_emp=emp_id)

    # Flatten to zone-presence segments.
    presence: list[dict] = []
    for rec in resolved:
        if "intervals" in rec:
            for iv in rec["intervals"]:
                presence.append({**iv, "emp_id": rec["emp_id"]})
        else:
            for ref in rec["zones"]:
                presence.append({
                    "zone_id": ref["zone_id"], "zone_name": ref["zone_name"],
                    "floor_plan_id": ref["floor_plan_id"],
                    "floor_plan_name": ref["floor_plan_name"],
                    "start": rec["start"], "end": rec["end"], "emp_id": rec["emp_id"],
                })
    if zone_id:
        presence = [p for p in presence if p["zone_id"] == zone_id]

    # Tenant timezone for local hour-of-day bucketing (fallback UTC).
    tz_name = (await db.execute(
        select(Tenant.timezone).where(Tenant.id == tenant_id)
    )).scalar_one_or_none() or "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = UTC

    return {
        "as_of": now,
        "from": started_after,
        "to": started_before,
        "timezone": tz_name,
        "zones": hour_of_day_heatmap(presence, tz),
    }


async def get_person_timeline(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    emp_id: str,
    started_after: datetime,
    started_before: datetime,
    active_window_sec: int = 60,
    merge_gap_seconds: float = 60.0,
) -> dict:
    """"Where was this employee today" — a chronological zone-visit timeline.

    Same track->identity->zone pipeline as ``get_zone_dwell``, but for a single
    employee: each of their tracks becomes a per-zone presence segment (clipped
    to the window), then ``build_person_timeline`` merges same-zone fragments
    into visits and orders them by time. Zone attribution is desk-level for
    calibrated cameras (foot-point in polygon), camera-marker otherwise.
    ``total_seconds`` sums the visits (note: if two cameras' zones overlap it can
    exceed wall-clock — it is time-in-zone, not a wall-clock union).
    """
    now = datetime.now(UTC)
    active_cutoff = now - timedelta(seconds=active_window_sec)

    rows = (await db.execute(
        select(
            Track.id, Track.camera_id, Track.person_id,
            Track.started_at, Track.ended_at, Track.updated_at, Track.last_bbox,
        ).where(
            Track.tenant_id == tenant_id,
            Track.started_at < started_before,
            or_(Track.ended_at.is_(None), Track.ended_at >= started_after),
        )
    )).all()

    track_ids = [r.id for r in rows]
    person_ids = [r.person_id for r in rows if r.person_id is not None]
    best_by_track, best_by_person = await _best_identity_by_track(
        db, tenant_id=tenant_id, track_ids=track_ids, person_ids=person_ids
    )

    fps, marker_zones, plan_zones, homographies = await _zone_resolution_context(
        db, tenant_id=tenant_id)

    resolved = await _resolve_tracks_with_zones(
        db, tenant_id=tenant_id, rows=rows,
        best_by_track=best_by_track, best_by_person=best_by_person,
        marker_zones=marker_zones, plan_zones=plan_zones, homographies=homographies,
        started_after=started_after, started_before=started_before,
        active_cutoff=active_cutoff, only_emp=emp_id)

    name: str | None = None
    segments: list[dict] = []
    for rec in resolved:
        if rec["name"]:
            name = rec["name"]
        if "intervals" in rec:
            # Per-point: each interval is already a time-ordered zone visit,
            # reflecting movement within the track.
            for iv in rec["intervals"]:
                segments.append({**iv, "present": rec["present"]})
        else:
            for ref in rec["zones"]:
                segments.append({
                    "zone_id": ref["zone_id"], "zone_name": ref["zone_name"],
                    "floor_plan_id": ref["floor_plan_id"],
                    "floor_plan_name": ref["floor_plan_name"],
                    "start": rec["start"], "end": rec["end"], "present": rec["present"],
                })

    visits = build_person_timeline(segments, merge_gap_seconds=merge_gap_seconds)
    return {
        "emp_id": emp_id,
        "name": name,
        "as_of": now,
        "from": started_after,
        "to": started_before,
        "total_seconds": sum(v["seconds"] for v in visits),
        "segments": visits,
    }
