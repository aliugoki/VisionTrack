"""Per-zone rollup derived from zone dwell.

Turns the per-(employee, zone) dwell rows into one row per zone: total
person-time spent there over the window, how many distinct employees passed
through, the average time per person, and how many are present right now. Pure
(no DB/async) — unit-tested; the async wrapper is ``service.get_zone_rollup``.
"""
from __future__ import annotations

from typing import Any, Iterable


def zone_rollup_from_dwell(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate dwell rows into one record per zone, busiest first.

    Each output row: ``zone_id``, ``zone_name``, ``floor_plan_id``,
    ``floor_plan_name``, ``total_seconds`` (summed across employees),
    ``people_count`` (distinct employees), ``avg_seconds`` (total / people), and
    ``present_count`` (employees currently in the zone).
    """
    agg: dict[str, dict[str, Any]] = {}
    for r in rows:
        zid = r["zone_id"]
        z = agg.get(zid)
        if z is None:
            agg[zid] = {
                "zone_id": zid,
                "zone_name": r.get("zone_name", "Zone"),
                "floor_plan_id": r.get("floor_plan_id"),
                "floor_plan_name": r.get("floor_plan_name"),
                "total_seconds": float(r.get("seconds", 0.0)),
                "people": {r.get("emp_id")},
                "present_count": 1 if r.get("present") else 0,
            }
        else:
            z["total_seconds"] += float(r.get("seconds", 0.0))
            z["people"].add(r.get("emp_id"))
            if r.get("present"):
                z["present_count"] += 1

    out: list[dict[str, Any]] = []
    for z in agg.values():
        n = len(z["people"])
        out.append({
            "zone_id": z["zone_id"],
            "zone_name": z["zone_name"],
            "floor_plan_id": z["floor_plan_id"],
            "floor_plan_name": z["floor_plan_name"],
            "total_seconds": z["total_seconds"],
            "people_count": n,
            "avg_seconds": z["total_seconds"] / n if n else 0.0,
            "present_count": z["present_count"],
        })
    return sorted(out, key=lambda x: x["total_seconds"], reverse=True)
