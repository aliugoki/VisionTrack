"""Pydantic schemas for the analytics module."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class OverviewKPIs(BaseModel):
    """Top-of-dashboard headline KPIs.

    All counts are scoped to the current tenant + date range.
    """
    alerts_total: int
    alerts_active: int
    alerts_critical: int
    distinct_zones_with_alerts: int
    distinct_persons_tracked: int  # distinct (camera_id, tracker_id) pairs
    recordings_count: int
    recordings_size_bytes: int


class TimeseriesPoint(BaseModel):
    """One bucket of a time-series response.

    `bucket_start` is the inclusive lower bound of the bucket, in UTC.
    A 1-day bucket whose `bucket_start` is `2026-06-05T00:00:00Z` covers
    `[2026-06-05T00:00Z, 2026-06-06T00:00Z)`.
    """
    bucket_start: datetime
    count: int


class TimeseriesResponse(BaseModel):
    bucket: str  # "hour" | "day"
    points: list[TimeseriesPoint]


class BreakdownItem(BaseModel):
    """One bar of a breakdown bar-chart."""
    label: str
    count: int


class AlertsBreakdownResponse(BaseModel):
    """Three slices of the alerts data, returned together so the
    dashboard does ONE round-trip instead of three for the breakdown
    panel. Each slice is sorted by count desc, top 10 only."""
    by_severity: list[BreakdownItem]
    by_zone: list[BreakdownItem]
    by_rule: list[BreakdownItem]



class PersonsSummary(BaseModel):
    """Identity-level stats from the persons table.

    Distinct from OverviewKPIs.distinct_persons_tracked, which counts
    (camera_id, tracker_id) pairs at the track level. These fields
    count cross-camera identities — populated once the matcher
    attributes tracks to persons.
    """
    total_identities: int
    active_last_24h: int
    new_today: int
    avg_appearances: float
