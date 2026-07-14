"""CSV rendering for the daily per-employee zone reports.

Pure string builders (no DB/async) so they can be unit-tested: they take the
dicts returned by ``service.get_zone_dwell`` / ``get_person_timeline`` and emit
CSV. HR/payroll ingest CSV directly; timestamps are ISO-8601 (UTC) and durations
are given both in seconds and H:MM:SS.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any


def _hms(seconds: Any) -> str:
    """Seconds -> ``H:MM:SS`` (e.g. 2970 -> ``0:49:30``)."""
    s = int(round(max(0.0, float(seconds))))
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def _iso(dt: Any) -> str:
    return dt.isoformat() if isinstance(dt, datetime) else ""


def _safe(v: Any) -> str:
    """Stringify a cell, guarding against spreadsheet formula injection.

    A field a spreadsheet would evaluate (starts with = + - @) is prefixed with a
    single quote so Excel/Sheets treat it as text, not a formula.
    """
    s = "" if v is None else str(v)
    if s[:1] in ("=", "+", "-", "@"):
        s = "'" + s
    return s


def dwell_csv(data: dict) -> str:
    """CSV of ``get_zone_dwell`` output: one row per (employee, zone)."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "employee_id", "employee_name", "floor_plan", "zone",
        "seconds", "time", "visits", "first_seen", "last_seen", "present",
    ])
    for r in data.get("rows", []):
        w.writerow([
            _safe(r.get("emp_id")), _safe(r.get("name")),
            _safe(r.get("floor_plan_name")), _safe(r.get("zone_name")),
            int(round(r.get("seconds", 0))), _hms(r.get("seconds", 0)),
            r.get("sessions", 0),
            _iso(r.get("first_seen")), _iso(r.get("last_seen")),
            "yes" if r.get("present") else "no",
        ])
    return buf.getvalue()


def timeline_csv(data: dict) -> str:
    """CSV of ``get_person_timeline`` output: one row per zone visit, in order."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "employee_id", "employee_name", "sequence", "floor_plan", "zone",
        "start", "end", "seconds", "time", "visits", "present",
    ])
    emp = data.get("emp_id")
    name = data.get("name")
    for i, s in enumerate(data.get("segments", []), start=1):
        w.writerow([
            _safe(emp), _safe(name), i,
            _safe(s.get("floor_plan_name")), _safe(s.get("zone_name")),
            _iso(s.get("start")), _iso(s.get("end")),
            int(round(s.get("seconds", 0))), _hms(s.get("seconds", 0)),
            s.get("sessions", 0),
            "yes" if s.get("present") else "no",
        ])
    return buf.getvalue()
