"""Floor Plans — Pydantic schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


# Allowed storage formats (matches what we accept on upload)
StorageFormat = Literal["png", "jpg", "svg", "pdf"]


class FloorPlanMarker(BaseModel):
    """A single camera placement on a floor plan.

    Coordinates are fractional (0.0..1.0) relative to the plan's
    width_px / height_px so they survive image-resize on the frontend.

    Coverage cone (optional — set when operator enables it for a marker):
      cone_angle_deg  — field-of-view horizontal sweep. 90° is typical
        for fixed wide-angle CCTV. Range 1..360 (360 = full circle).
      cone_range  — fractional radius from the marker, relative to the
        plan's width. 0.15 ≈ a reasonable indoor reach. Range 0..1.
      cone_rotation_deg  — which direction the camera points, in degrees
        clockwise from "east" (positive x-axis). 0..359.

    A marker with cone fields set to None renders without a cone.
    """
    id: UUID = Field(default_factory=uuid4)
    camera_id: UUID
    # Fractional position. 0,0 = top-left of the source image.
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    # Optional display label; UI falls back to camera.name when None.
    label: str | None = Field(default=None, max_length=120)

    # Coverage-cone visualization. All-or-nothing: either all three are
    # None (no cone shown), or all three are set. UI handles enable/disable
    # by toggling the trio together.
    cone_angle_deg: float | None = Field(default=None, ge=1.0, le=360.0)
    cone_range: float | None = Field(default=None, ge=0.0, le=1.0)
    cone_rotation_deg: float | None = Field(default=None, ge=0.0, lt=360.0)

    @field_validator("x", "y")
    @classmethod
    def _clamp_fractional(cls, v: float) -> float:
        # Defensive — Field's ge/le already enforce, but rounding errors
        # in the frontend may emit 1.0000001. Clamp to be safe.
        return max(0.0, min(1.0, float(v)))


class FloorPlanMarkersUpdate(BaseModel):
    """Body of PATCH /floor-plans/{id}/markers — replace the full set."""
    markers: list[FloorPlanMarker]


class FloorPlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    site_id: UUID
    uploaded_by_user_id: UUID | None
    name: str
    description: str | None
    original_filename: str
    original_content_type: str
    original_size_bytes: int
    format: StorageFormat
    width_px: int
    height_px: int
    markers: list[FloorPlanMarker] = Field(default_factory=list)
    zones: list["Zone"] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class FloorPlanUpdate(BaseModel):
    """Patchable fields. The image itself isn't editable — delete + re-upload."""
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)


# -- Zones (Step 5) ----------------------------------------------------------
# A zone is a polygon drawn on a floor plan with one or more alert rules
# attached. Polygons are stored as fractional coordinates (0..1 relative to
# the plan's width_px / height_px) so they scale correctly at any viewer
# size — same convention as FloorPlanMarker.
#
# Atomicity: the editor PUTs the full list of zones at once, matching the
# marker editing UX. No partial updates for now (KISS; promote to per-zone
# endpoints later if needed).

ZoneRuleKind = Literal["occupancy_max", "occupancy_min", "dwell", "entry"]
ZoneRuleSeverity = Literal["info", "warning", "critical"]
ZoneRuleChannel = Literal["in_app", "email", "whatsapp"]
ScheduleMode = Literal["always", "scheduled"]


class ZonePoint(BaseModel):
    """One vertex of a zone polygon. Fractional 0..1 relative to plan size."""
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)

    @field_validator("x", "y")
    @classmethod
    def _clamp(cls, v: float) -> float:
        return max(0.0, min(1.0, float(v)))


class ZoneRuleSchedule(BaseModel):
    """When a rule is active.

    'always': fires at any time of day, any day of week.
    'scheduled': fires only during start_time..end_time on specified days.
      Times are HH:MM 24-hour strings. Days are 0=Monday..6=Sunday (ISO).
      An end_time earlier than start_time is interpreted as crossing midnight.
    """
    mode: ScheduleMode = "always"
    start_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    end_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    days: list[int] = Field(default_factory=list)

    @field_validator("start_time", "end_time")
    @classmethod
    def _valid_hhmm(cls, v: str | None) -> str | None:
        # Pattern already ensures "DD:DD" shape; here we verify the
        # hour and minute fall in real-clock ranges.
        if v is None:
            return v
        h, m = v.split(":")
        if not (0 <= int(h) <= 23 and 0 <= int(m) <= 59):
            raise ValueError(f"invalid HH:MM time: {v}")
        return v

    @field_validator("days")
    @classmethod
    def _valid_days(cls, v: list[int]) -> list[int]:
        for d in v:
            if d < 0 or d > 6:
                raise ValueError("day must be 0..6 (0=Mon, 6=Sun)")
        # Dedup + sort for stable serialization
        return sorted(set(v))


class ZoneRule(BaseModel):
    """One alert rule attached to a zone.

    Semantics by kind:
      occupancy_max — fire when count(people in zone) > threshold for hold_time_s
      occupancy_min — fire when count(people in zone) < threshold for hold_time_s
                       (useful for "warehouse should never be empty during shift")
      dwell         — fire when ANY single person remains in zone for > threshold
                       (threshold is seconds in this kind; hold_time_s ignored)
      entry         — fire on each transition: someone crossing into the zone
                       (used together with schedule for "after-hours entry")
    """
    id: UUID = Field(default_factory=uuid4)
    kind: ZoneRuleKind
    threshold: float = Field(gt=0)
    # Sustained for this long before firing. Ignored for 'entry' (edge-triggered).
    hold_time_s: int = Field(default=0, ge=0, le=86400)
    schedule: ZoneRuleSchedule = Field(default_factory=ZoneRuleSchedule)
    severity: ZoneRuleSeverity = "warning"
    channels: list[ZoneRuleChannel] = Field(default_factory=lambda: ["in_app"])
    enabled: bool = True
    # Optional human-readable label (e.g. "Off-hours entry"). Falls back to
    # auto-generated name based on kind + threshold if None.
    label: str | None = Field(default=None, max_length=120)


class Zone(BaseModel):
    """A polygon drawn on a floor plan, with attached alert rules."""
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=120)
    # Hex color used for outline + tinted fill. Must be 6-digit hex.
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    # Polygon points (min 3 to be a real polygon, max 64 to bound the
    # evaluation cost — a 64-gon is more than enough for any floor shape).
    polygon: list[ZonePoint] = Field(min_length=3, max_length=64)
    rules: list[ZoneRule] = Field(default_factory=list, max_length=10)


class ZonesUpdate(BaseModel):
    """Body of PUT /floor-plans/{id}/zones — replaces the full zone set."""
    zones: list[Zone]


# Resolve the forward-reference now that Zone is defined
FloorPlanRead.model_rebuild()
