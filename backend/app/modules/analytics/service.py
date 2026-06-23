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

from sqlalchemy import and_, distinct, func, select, text, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.alerts.models import Alert
from app.modules.recordings.models import Recording
from app.modules.tracks.models import TrackPoint


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
