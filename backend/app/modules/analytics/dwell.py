"""Per-person zone dwell — how long each named person spends in each zone.

This is the "indoor geofencing" computation: for a time window, attribute every
tracked person's presence to the zones they were in and sum the time. It is the
temporal companion to ``occupancy.py`` (which is a live headcount snapshot).

Kept free of DB/async so it can be unit-tested in isolation; the async DB wrapper
is ``service.get_zone_dwell``.

Model (identical zone↔camera binding to occupancy, so the two agree):
  * A **zone** is a polygon (fractional 0..1) on a floor plan.
  * A **camera** has a marker point on the floor plan; it "belongs to" a zone
    when its marker lies inside the zone polygon.
  * A **track** is one person on one camera for ``[started_at, ended_at]``. That
    interval IS the person's dwell in every zone the camera sits in.

"Named" person = a track carrying a face identity (``emp_id`` from the FaceTrack
feed). Anonymous tracks have no ``emp_id`` and are ignored here — dwell answers
"which *employee* was where, and for how long"; anonymous headcount is the
occupancy panel's job.

A person seen by two cameras that both sit in the same zone, or re-acquired under
a new tracker id, contributes multiple tracks to that (person, zone) pair — they
are summed as ``seconds`` with ``sessions`` counting the fragments. Overlapping
fragments (same instant, two cameras) can marginally over-count; gaps where the
tracker briefly loses the person under-count. This is the same honest
approximation occupancy makes, stated plainly rather than hidden.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable

from app.modules.floor_plans.zones_math import point_in_polygon


def camera_zone_index(
    floor_plans: Iterable[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Map each camera id -> the list of zones its marker falls inside.

    ``floor_plans`` items: ``{"id", "name", "zones": [{"id","name","polygon":
    [{"x","y"}]}], "markers": [{"camera_id","x","y"}]}`` — same shape occupancy
    consumes. A camera can belong to several zones (overlapping polygons); each
    zone ref is ``{floor_plan_id, floor_plan_name, zone_id, zone_name}``.
    """
    index: dict[str, list[dict[str, Any]]] = {}
    for fp in floor_plans:
        markers: dict[str, tuple[float, float]] = {}
        for m in fp.get("markers") or []:
            cam_id = m.get("camera_id")
            if cam_id is not None:
                markers[str(cam_id)] = (float(m.get("x", 0.0)), float(m.get("y", 0.0)))

        for z in fp.get("zones") or []:
            polygon = [(float(p["x"]), float(p["y"])) for p in (z.get("polygon") or [])]
            if len(polygon) < 3:
                continue  # not a valid area
            ref = {
                "floor_plan_id": str(fp["id"]),
                "floor_plan_name": fp.get("name"),
                "zone_id": str(z.get("id")),
                "zone_name": z.get("name", "Zone"),
            }
            for cam, pt in markers.items():
                if point_in_polygon(pt, polygon):
                    index.setdefault(cam, []).append(ref)
    return index


def clip_interval(
    start: datetime, end: datetime, lo: datetime, hi: datetime
) -> tuple[datetime, datetime] | None:
    """Intersect ``[start, end]`` with the window ``[lo, hi]``.

    Returns the clipped ``(start, end)`` or ``None`` if they don't overlap (or the
    overlap is empty). ``end`` before ``start`` (bad data) yields ``None``.
    """
    s = max(start, lo)
    e = min(end, hi)
    if e <= s:
        return None
    return (s, e)


def accumulate_dwell(
    tracks: Iterable[dict[str, Any]],
    cam_zones: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """Sum per-(person, zone) dwell over the given tracks.

    Each track dict: ``{"camera_id", "emp_id", "name", "start": datetime,
    "end": datetime, "present": bool}`` where ``start``/``end`` are already
    clipped to the query window and ``present`` marks a still-active track.

    Zone attribution: if a track carries a pre-resolved ``"zones"`` list (from
    ``zone_resolve.resolve_track_zone_refs`` — position-aware/desk-level), that is
    used; otherwise it falls back to the coarse camera-marker map ``cam_zones``.
    Tracks without an ``emp_id`` (anonymous) or in no zone are skipped.

    Returns one row per (emp_id, zone) with ``seconds`` (float), ``sessions``,
    ``first_seen``, ``last_seen``, ``present`` (any fragment still active), and
    the zone/floor-plan labels. Rows are sorted by ``seconds`` descending.
    """
    agg: dict[tuple[str, str], dict[str, Any]] = {}
    for t in tracks:
        emp_id = t.get("emp_id")
        if not emp_id:
            continue  # anonymous — not a named employee
        zones = t.get("zones")
        if zones is None:
            zones = (cam_zones or {}).get(str(t["camera_id"]))
        if not zones:
            continue  # in no zone
        start: datetime = t["start"]
        end: datetime = t["end"]
        seconds = (end - start).total_seconds()
        if seconds < 0:
            seconds = 0.0
        present = bool(t.get("present"))
        for ref in zones:
            key = (str(emp_id), ref["zone_id"])
            row = agg.get(key)
            if row is None:
                row = {
                    "emp_id": str(emp_id),
                    "name": t.get("name"),
                    "floor_plan_id": ref["floor_plan_id"],
                    "floor_plan_name": ref["floor_plan_name"],
                    "zone_id": ref["zone_id"],
                    "zone_name": ref["zone_name"],
                    "seconds": 0.0,
                    "sessions": 0,
                    "first_seen": start,
                    "last_seen": end,
                    "present": False,
                }
                agg[key] = row
            row["seconds"] += seconds
            row["sessions"] += 1
            row["first_seen"] = min(row["first_seen"], start)
            row["last_seen"] = max(row["last_seen"], end)
            row["present"] = row["present"] or present
            if t.get("name") and not row.get("name"):
                row["name"] = t["name"]

    return sorted(agg.values(), key=lambda r: r["seconds"], reverse=True)


def build_person_timeline(
    segments: Iterable[dict[str, Any]],
    merge_gap_seconds: float = 60.0,
) -> list[dict[str, Any]]:
    """Collapse one person's per-zone presence segments into a chronological
    "where were they" visit list — the timeline behind "where was X today".

    Each input segment: ``{"zone_id", "zone_name", "floor_plan_id",
    "floor_plan_name", "start": datetime, "end": datetime, "present": bool}`` —
    one per (track, zone), already clipped to the query window.

    Two segments in the **same zone** are merged into one visit when the later
    one starts within ``merge_gap_seconds`` of the running visit's end. This
    bridges brief tracker drops / camera hand-offs so a continuous stay reads as
    one visit rather than a dozen fragments, while a genuine departure and return
    to the same zone (a gap larger than the tolerance) stays two visits.

    Merging is per-zone, so moving Sales -> Production -> Sales yields three
    visits (Sales appears twice). Returns visits sorted by ``start``; each carries
    ``seconds`` (end-start), ``sessions`` (fragments merged), and ``present``.
    """
    by_zone: dict[str, list[dict[str, Any]]] = {}
    for s in segments:
        by_zone.setdefault(s["zone_id"], []).append(s)

    visits: list[dict[str, Any]] = []
    gap = timedelta(seconds=merge_gap_seconds)
    for zone_segs in by_zone.values():
        zone_segs.sort(key=lambda s: s["start"])
        cur: dict[str, Any] | None = None
        for s in zone_segs:
            if cur is not None and s["start"] <= cur["end"] + gap:
                cur["end"] = max(cur["end"], s["end"])
                cur["sessions"] += 1
                cur["present"] = cur["present"] or bool(s.get("present"))
            else:
                if cur is not None:
                    visits.append(cur)
                cur = {
                    "zone_id": s["zone_id"],
                    "zone_name": s["zone_name"],
                    "floor_plan_id": s["floor_plan_id"],
                    "floor_plan_name": s.get("floor_plan_name"),
                    "start": s["start"],
                    "end": s["end"],
                    "sessions": 1,
                    "present": bool(s.get("present")),
                }
        if cur is not None:
            visits.append(cur)

    for v in visits:
        v["seconds"] = (v["end"] - v["start"]).total_seconds()
    return sorted(visits, key=lambda v: v["start"])
