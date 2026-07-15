"""Analytics HTTP routes.

  GET /analytics/overview              KPIs for the date range
  GET /analytics/alerts/timeseries     Alert counts per time bucket
  GET /analytics/alerts/breakdown      Top severities / zones / rules
  GET /analytics/people/timeseries     Distinct persons tracked per bucket

All endpoints require analytics:read permission. Date range is a
half-open interval [from, to). If `to` is omitted, NOW() is used.

bucket parameter is "hour" or "day". For ranges >48h, callers should
prefer "day" to keep response size reasonable; ranges <=48h prefer
"hour" for resolution. Frontend auto-picks based on range span.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import RequirePermission
from app.core.permissions import ANALYTICS_READ
from app.modules.analytics import service
from app.modules.analytics.export import (
    attendance_csv,
    dwell_csv,
    heatmap_csv,
    timeline_csv,
    zone_rollup_csv,
)
from app.modules.analytics.schemas import (
    AlertsBreakdownResponse,
    AttendanceResponse,
    OccupancyHeatmapResponse,
    OverviewKPIs,
    PersonsSummary,
    PersonTimelineResponse,
    TimeseriesResponse,
    ZoneDwellResponse,
    ZoneOccupancyResponse,
    ZoneRollupResponse,
)
from app.modules.analytics.service import (
    get_alerts_breakdown,
    get_alerts_timeseries,
    get_attendance,
    get_occupancy_heatmap,
    get_overview,
    get_people_timeseries,
    get_person_timeline,
    get_zone_dwell,
    get_zone_occupancy,
    get_zone_rollup,
)
from app.modules.users.models import User


router = APIRouter(prefix="/analytics", tags=["analytics"])


def _resolve_range(
    from_: datetime | None, to_: datetime | None
) -> tuple[datetime, datetime]:
    """Resolve nullable params into a sane half-open interval.

    Defaults:
      - `to_` defaults to NOW (UTC)
      - `from_` defaults to 7 days before `to_`
    Both are returned tz-aware UTC.
    """
    end = to_ or datetime.now(timezone.utc)
    start = from_ or (end - timedelta(days=7))
    # Normalize to UTC if naive (shouldn't happen with query parsing but safe)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return start, end


@router.get("/overview", response_model=OverviewKPIs)
async def overview_endpoint(
    from_: datetime | None = Query(None, alias="from"),
    to_: datetime | None = Query(None, alias="to"),
    current_user: User = Depends(RequirePermission(ANALYTICS_READ)),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
) -> OverviewKPIs:
    start, end = _resolve_range(from_, to_)
    data = await get_overview(
        db,
        tenant_id=current_user.tenant_id,
        started_after=start,
        started_before=end,
    )
    return OverviewKPIs(**data)


@router.get("/zones/occupancy", response_model=ZoneOccupancyResponse)
async def zones_occupancy_endpoint(
    window: int = Query(
        60, ge=5, le=600,
        description="seconds; a track counts as present if seen within this window",
    ),
    current_user: User = Depends(RequirePermission(ANALYTICS_READ)),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
) -> ZoneOccupancyResponse:
    """Live per-zone headcount (known vs unknown) across all floor plans."""
    data = await get_zone_occupancy(
        db, tenant_id=current_user.tenant_id, active_window_sec=window
    )
    return ZoneOccupancyResponse(**data)


@router.get("/zones/dwell", response_model=ZoneDwellResponse)
async def zones_dwell_endpoint(
    from_: datetime | None = Query(None, alias="from"),
    to_: datetime | None = Query(None, alias="to"),
    window: int = Query(
        60, ge=5, le=600,
        description="seconds; a person counts as 'here now' if seen within this window",
    ),
    min_seconds: int = Query(
        0, ge=0,
        description="drop (person, zone) rows below this many seconds of dwell",
    ),
    emp_id: str | None = Query(None, description="filter to one employee"),
    zone_id: str | None = Query(None, description="filter to one zone"),
    current_user: User = Depends(RequirePermission(ANALYTICS_READ)),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
) -> ZoneDwellResponse:
    """Per-employee time-in-zone over a window (indoor geofencing).

    Which named person was in which department/desk, for how long, and who is
    there right now. Defaults to today (start of the current UTC day → now).
    Optional ``emp_id`` / ``zone_id`` filters narrow the report.
    """
    end = to_ or datetime.now(timezone.utc)
    start = from_ or end.replace(hour=0, minute=0, second=0, microsecond=0)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    data = await get_zone_dwell(
        db,
        tenant_id=current_user.tenant_id,
        started_after=start,
        started_before=end,
        active_window_sec=window,
        min_seconds=min_seconds,
        emp_id=emp_id,
        zone_id=zone_id,
    )
    return ZoneDwellResponse(**data)


@router.get("/persons/{emp_id}/timeline", response_model=PersonTimelineResponse)
async def person_timeline_endpoint(
    emp_id: str,
    from_: datetime | None = Query(None, alias="from"),
    to_: datetime | None = Query(None, alias="to"),
    window: int = Query(
        60, ge=5, le=600,
        description="seconds; a visit is 'here now' if the person was seen within this",
    ),
    merge_gap: int = Query(
        60, ge=0, le=3600,
        description="seconds; same-zone fragments closer than this merge into one visit",
    ),
    current_user: User = Depends(RequirePermission(ANALYTICS_READ)),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
) -> PersonTimelineResponse:
    """Where was this employee today — their zone visits in chronological order.

    Defaults to today (start of the current UTC day -> now).
    """
    end = to_ or datetime.now(timezone.utc)
    start = from_ or end.replace(hour=0, minute=0, second=0, microsecond=0)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    data = await get_person_timeline(
        db,
        tenant_id=current_user.tenant_id,
        emp_id=emp_id,
        started_after=start,
        started_before=end,
        active_window_sec=window,
        merge_gap_seconds=merge_gap,
    )
    return PersonTimelineResponse(**data)


def _daily_range(
    from_: datetime | None, to_: datetime | None
) -> tuple[datetime, datetime]:
    """Resolve nullable from/to into a today-default UTC interval (start of the
    current day -> now), matching the dwell/timeline endpoints."""
    end = to_ or datetime.now(timezone.utc)
    start = from_ or end.replace(hour=0, minute=0, second=0, microsecond=0)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return start, end


def _csv_response(text: str, filename: str) -> Response:
    return Response(
        content=text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _safe_filename(part: str) -> str:
    cleaned = "".join(c if (c.isalnum() or c in "-_") else "_" for c in part)
    return cleaned[:40] or "export"


@router.get("/zones/dwell.csv")
async def zones_dwell_csv(
    from_: datetime | None = Query(None, alias="from"),
    to_: datetime | None = Query(None, alias="to"),
    window: int = Query(60, ge=5, le=600),
    min_seconds: int = Query(0, ge=0),
    emp_id: str | None = Query(None),
    zone_id: str | None = Query(None),
    current_user: User = Depends(RequirePermission(ANALYTICS_READ)),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
) -> Response:
    """Download per-employee zone dwell for the day as CSV (with optional filters)."""
    start, end = _daily_range(from_, to_)
    data = await get_zone_dwell(
        db, tenant_id=current_user.tenant_id,
        started_after=start, started_before=end,
        active_window_sec=window, min_seconds=min_seconds,
        emp_id=emp_id, zone_id=zone_id,
    )
    return _csv_response(dwell_csv(data), f"zone-dwell-{start.date()}.csv")


@router.get("/zones/rollup", response_model=ZoneRollupResponse)
async def zones_rollup_endpoint(
    from_: datetime | None = Query(None, alias="from"),
    to_: datetime | None = Query(None, alias="to"),
    window: int = Query(60, ge=5, le=600),
    min_seconds: int = Query(0, ge=0),
    emp_id: str | None = Query(None),
    zone_id: str | None = Query(None),
    current_user: User = Depends(RequirePermission(ANALYTICS_READ)),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
) -> ZoneRollupResponse:
    """Per-zone rollup: total person-time, distinct people, avg, present."""
    start, end = _daily_range(from_, to_)
    data = await get_zone_rollup(
        db, tenant_id=current_user.tenant_id,
        started_after=start, started_before=end,
        active_window_sec=window, min_seconds=min_seconds,
        emp_id=emp_id, zone_id=zone_id,
    )
    return ZoneRollupResponse(**data)


@router.get("/zones/rollup.csv")
async def zones_rollup_csv(
    from_: datetime | None = Query(None, alias="from"),
    to_: datetime | None = Query(None, alias="to"),
    window: int = Query(60, ge=5, le=600),
    min_seconds: int = Query(0, ge=0),
    emp_id: str | None = Query(None),
    zone_id: str | None = Query(None),
    current_user: User = Depends(RequirePermission(ANALYTICS_READ)),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
) -> Response:
    """Download the per-zone rollup as CSV."""
    start, end = _daily_range(from_, to_)
    data = await get_zone_rollup(
        db, tenant_id=current_user.tenant_id,
        started_after=start, started_before=end,
        active_window_sec=window, min_seconds=min_seconds,
        emp_id=emp_id, zone_id=zone_id,
    )
    return _csv_response(zone_rollup_csv(data), f"zone-rollup-{start.date()}.csv")


@router.get("/zones/heatmap", response_model=OccupancyHeatmapResponse)
async def zones_heatmap_endpoint(
    from_: datetime | None = Query(None, alias="from"),
    to_: datetime | None = Query(None, alias="to"),
    window: int = Query(60, ge=5, le=600),
    emp_id: str | None = Query(None),
    zone_id: str | None = Query(None),
    current_user: User = Depends(RequirePermission(ANALYTICS_READ)),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
) -> OccupancyHeatmapResponse:
    """Hour-of-day occupancy heatmap — per zone, person-time + people per hour."""
    start, end = _daily_range(from_, to_)
    data = await get_occupancy_heatmap(
        db, tenant_id=current_user.tenant_id,
        started_after=start, started_before=end,
        active_window_sec=window, emp_id=emp_id, zone_id=zone_id,
    )
    return OccupancyHeatmapResponse(**data)


@router.get("/zones/heatmap.csv")
async def zones_heatmap_csv(
    from_: datetime | None = Query(None, alias="from"),
    to_: datetime | None = Query(None, alias="to"),
    window: int = Query(60, ge=5, le=600),
    emp_id: str | None = Query(None),
    zone_id: str | None = Query(None),
    current_user: User = Depends(RequirePermission(ANALYTICS_READ)),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
) -> Response:
    """Download the hour-of-day occupancy heatmap as CSV."""
    start, end = _daily_range(from_, to_)
    data = await get_occupancy_heatmap(
        db, tenant_id=current_user.tenant_id,
        started_after=start, started_before=end,
        active_window_sec=window, emp_id=emp_id, zone_id=zone_id,
    )
    return _csv_response(heatmap_csv(data), f"occupancy-heatmap-{start.date()}.csv")


@router.get("/attendance", response_model=AttendanceResponse)
async def attendance_endpoint(
    from_: datetime | None = Query(None, alias="from"),
    to_: datetime | None = Query(None, alias="to"),
    window: int = Query(60, ge=5, le=600),
    min_seconds: int = Query(0, ge=0),
    emp_id: str | None = Query(None),
    zone_id: str | None = Query(None),
    current_user: User = Depends(RequirePermission(ANALYTICS_READ)),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
) -> AttendanceResponse:
    """Per-employee attendance (arrival / departure / on-site span / tracked)."""
    start, end = _daily_range(from_, to_)
    data = await get_attendance(
        db, tenant_id=current_user.tenant_id,
        started_after=start, started_before=end,
        active_window_sec=window, min_seconds=min_seconds,
        emp_id=emp_id, zone_id=zone_id,
    )
    return AttendanceResponse(**data)


@router.get("/attendance.csv")
async def attendance_csv_endpoint(
    from_: datetime | None = Query(None, alias="from"),
    to_: datetime | None = Query(None, alias="to"),
    window: int = Query(60, ge=5, le=600),
    min_seconds: int = Query(0, ge=0),
    emp_id: str | None = Query(None),
    zone_id: str | None = Query(None),
    current_user: User = Depends(RequirePermission(ANALYTICS_READ)),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
) -> Response:
    """Download per-employee attendance for the range as CSV."""
    start, end = _daily_range(from_, to_)
    data = await get_attendance(
        db, tenant_id=current_user.tenant_id,
        started_after=start, started_before=end,
        active_window_sec=window, min_seconds=min_seconds,
        emp_id=emp_id, zone_id=zone_id,
    )
    return _csv_response(attendance_csv(data), f"attendance-{start.date()}.csv")


@router.get("/persons/{emp_id}/timeline.csv")
async def person_timeline_csv(
    emp_id: str,
    from_: datetime | None = Query(None, alias="from"),
    to_: datetime | None = Query(None, alias="to"),
    window: int = Query(60, ge=5, le=600),
    merge_gap: int = Query(60, ge=0, le=3600),
    current_user: User = Depends(RequirePermission(ANALYTICS_READ)),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
) -> Response:
    """Download one employee's zone-visit timeline for the day as CSV."""
    start, end = _daily_range(from_, to_)
    data = await get_person_timeline(
        db, tenant_id=current_user.tenant_id, emp_id=emp_id,
        started_after=start, started_before=end,
        active_window_sec=window, merge_gap_seconds=merge_gap,
    )
    fname = f"timeline-{_safe_filename(emp_id)}-{start.date()}.csv"
    return _csv_response(timeline_csv(data), fname)


@router.get("/alerts/timeseries", response_model=TimeseriesResponse)
async def alerts_timeseries_endpoint(
    bucket: Literal["hour", "day"] = Query("day"),
    from_: datetime | None = Query(None, alias="from"),
    to_: datetime | None = Query(None, alias="to"),
    current_user: User = Depends(RequirePermission(ANALYTICS_READ)),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
) -> TimeseriesResponse:
    start, end = _resolve_range(from_, to_)
    points = await get_alerts_timeseries(
        db,
        tenant_id=current_user.tenant_id,
        started_after=start,
        started_before=end,
        bucket=bucket,
    )
    return TimeseriesResponse(bucket=bucket, points=points)


@router.get("/people/timeseries", response_model=TimeseriesResponse)
async def people_timeseries_endpoint(
    bucket: Literal["hour", "day"] = Query("day"),
    from_: datetime | None = Query(None, alias="from"),
    to_: datetime | None = Query(None, alias="to"),
    current_user: User = Depends(RequirePermission(ANALYTICS_READ)),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
) -> TimeseriesResponse:
    start, end = _resolve_range(from_, to_)
    points = await get_people_timeseries(
        db,
        tenant_id=current_user.tenant_id,
        started_after=start,
        started_before=end,
        bucket=bucket,
    )
    return TimeseriesResponse(bucket=bucket, points=points)


@router.get("/alerts/breakdown", response_model=AlertsBreakdownResponse)
async def alerts_breakdown_endpoint(
    from_: datetime | None = Query(None, alias="from"),
    to_: datetime | None = Query(None, alias="to"),
    current_user: User = Depends(RequirePermission(ANALYTICS_READ)),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
) -> AlertsBreakdownResponse:
    start, end = _resolve_range(from_, to_)
    data = await get_alerts_breakdown(
        db,
        tenant_id=current_user.tenant_id,
        started_after=start,
        started_before=end,
    )
    return AlertsBreakdownResponse(**data)



@router.get("/persons/summary", response_model=PersonsSummary)
async def persons_summary_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(RequirePermission(ANALYTICS_READ)),
):
    """Identity-level stats from the persons table.

    Complementary to /analytics/overview's distinct_persons_tracked
    (which counts tracker_ids). This one counts cross-camera identities.
    Returns zeroes until the matcher (P2.5) creates Person rows.
    """
    summary = await service.get_persons_summary(
        db, tenant_id=current_user.tenant_id
    )
    return PersonsSummary(**summary)
