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

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import RequirePermission
from app.core.permissions import ANALYTICS_READ
from app.modules.analytics import service
from app.modules.analytics.schemas import (
    AlertsBreakdownResponse,
    OverviewKPIs,
    PersonsSummary,
    TimeseriesResponse,
)
from app.modules.analytics.service import (
    get_alerts_breakdown,
    get_alerts_timeseries,
    get_overview,
    get_people_timeseries,
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
