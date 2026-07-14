"""Attendance summary derived from zone dwell.

Rolls the per-(employee, zone) dwell rows up to one attendance record per
employee: when they first appeared (arrival), when they were last seen
(departure), the gross on-site span between the two, the total time actually
tracked inside zones, and how many distinct zones they touched. Pure (no
DB/async) so it can be unit-tested; the async wrapper is ``service.get_attendance``.

Note ``tracked_seconds`` sums per-zone dwell, so with overlapping zones it can
exceed ``span_seconds``; ``span_seconds`` is the wall-clock arrival→departure
window. Both are useful: span for "how long on site", tracked for "how long
actually in a monitored zone".
"""
from __future__ import annotations

from typing import Any, Iterable


def attendance_from_dwell(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate dwell rows (from ``get_zone_dwell``) into per-employee attendance.

    Returns one row per employee, sorted by arrival, with ``emp_id``, ``name``,
    ``arrival``, ``departure``, ``span_seconds``, ``tracked_seconds``,
    ``zones_count`` and ``present``.
    """
    agg: dict[str, dict[str, Any]] = {}
    for r in rows:
        emp_id = r.get("emp_id")
        if not emp_id:
            continue
        e = agg.get(emp_id)
        if e is None:
            agg[emp_id] = {
                "emp_id": emp_id,
                "name": r.get("name"),
                "arrival": r["first_seen"],
                "departure": r["last_seen"],
                "tracked_seconds": float(r.get("seconds", 0.0)),
                "zones": {r["zone_id"]},
                "present": bool(r.get("present")),
            }
        else:
            e["arrival"] = min(e["arrival"], r["first_seen"])
            e["departure"] = max(e["departure"], r["last_seen"])
            e["tracked_seconds"] += float(r.get("seconds", 0.0))
            e["zones"].add(r["zone_id"])
            e["present"] = e["present"] or bool(r.get("present"))
            if r.get("name") and not e.get("name"):
                e["name"] = r["name"]

    out: list[dict[str, Any]] = []
    for e in agg.values():
        span = (e["departure"] - e["arrival"]).total_seconds()
        out.append({
            "emp_id": e["emp_id"],
            "name": e["name"],
            "arrival": e["arrival"],
            "departure": e["departure"],
            "span_seconds": max(0.0, span),
            "tracked_seconds": e["tracked_seconds"],
            "zones_count": len(e["zones"]),
            "present": e["present"],
        })
    return sorted(out, key=lambda x: x["arrival"])
