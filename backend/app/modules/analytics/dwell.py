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

from datetime import datetime
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
    cam_zones: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Sum per-(person, zone) dwell over the given tracks.

    Each track dict: ``{"camera_id", "emp_id", "name", "start": datetime,
    "end": datetime, "present": bool}`` where ``start``/``end`` are already
    clipped to the query window and ``present`` marks a still-active track. Tracks
    without an ``emp_id`` (anonymous) or whose camera is in no zone are skipped.

    Returns one row per (emp_id, zone) with ``seconds`` (float), ``sessions``,
    ``first_seen``, ``last_seen``, ``present`` (any fragment still active), and
    the zone/floor-plan labels. Rows are sorted by ``seconds`` descending.
    """
    agg: dict[tuple[str, str], dict[str, Any]] = {}
    for t in tracks:
        emp_id = t.get("emp_id")
        if not emp_id:
            continue  # anonymous — not a named employee
        zones = cam_zones.get(str(t["camera_id"]))
        if not zones:
            continue  # camera sits in no zone
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
