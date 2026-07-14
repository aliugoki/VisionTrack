"""Pydantic schemas for the analytics module."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


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


class KnownPerson(BaseModel):
    """A recognized employee currently present in a zone."""
    emp_id: str
    name: str | None = None


class ZoneOccupancy(BaseModel):
    """Live headcount for one zone, split known vs unknown.

    total = active tracks on the cameras whose markers fall in the zone.
    known = those correlated to a face identity (an employee); unknown = the rest.
    """
    floor_plan_id: str
    floor_plan_name: str | None = None
    zone_id: str
    zone_name: str
    camera_ids: list[str]
    total: int
    known: int
    unknown: int
    known_people: list[KnownPerson]


class ZoneOccupancyResponse(BaseModel):
    as_of: datetime            # server time this snapshot was computed
    active_window_sec: int     # a track counts as "present" if seen within this window
    zones: list[ZoneOccupancy]


class ZoneDwellRow(BaseModel):
    """How long one named employee spent in one zone over the window.

    ``seconds`` is summed across all of that person's tracks on the zone's
    cameras, clipped to the query window. ``sessions`` counts the track fragments
    (re-acquisitions / multiple cameras). ``present`` is true if any of those
    tracks is still active — i.e. the person is in the zone *right now*.
    """
    emp_id: str
    name: str | None = None
    floor_plan_id: str
    floor_plan_name: str | None = None
    zone_id: str
    zone_name: str
    seconds: float
    sessions: int
    first_seen: datetime
    last_seen: datetime
    present: bool


class ZoneDwellResponse(BaseModel):
    as_of: datetime            # server time this was computed
    from_: datetime = Field(alias="from")   # window lower bound (inclusive)
    to: datetime               # window upper bound (exclusive)
    active_window_sec: int     # a track counts as "present now" if seen within this
    rows: list[ZoneDwellRow]

    model_config = {"populate_by_name": True}


class TimelineSegment(BaseModel):
    """One zone visit in an employee's day — a contiguous stay in a zone.

    ``sessions`` counts the track fragments merged into this visit; ``present``
    is true if the person is still in the zone right now.
    """
    zone_id: str
    zone_name: str
    floor_plan_id: str
    floor_plan_name: str | None = None
    start: datetime
    end: datetime
    seconds: float
    sessions: int
    present: bool


class PersonTimelineResponse(BaseModel):
    """"Where was this employee today" — their zone visits in chronological order."""
    emp_id: str
    name: str | None = None
    as_of: datetime
    from_: datetime = Field(alias="from")
    to: datetime
    total_seconds: float
    segments: list[TimelineSegment]

    model_config = {"populate_by_name": True}
