"""Unit tests for the attendance rollup + its CSV (pure)."""
import csv
import io
from datetime import datetime, timedelta, timezone

from app.modules.analytics.attendance import attendance_from_dwell
from app.modules.analytics.export import attendance_csv

T = datetime(2026, 7, 15, 9, 0, 0, tzinfo=timezone.utc)


def _row(emp_id, name, zone_id, first_off, last_off, seconds, present=False):
    return {
        "emp_id": emp_id, "name": name, "zone_id": zone_id,
        "first_seen": T + timedelta(minutes=first_off),
        "last_seen": T + timedelta(minutes=last_off),
        "seconds": seconds, "present": present,
    }


def test_attendance_rollup():
    rows = [
        _row("E1", "Ali", "sales", 0, 30, 1800),
        _row("E1", "Ali", "prod", 40, 50, 600, present=True),
        _row("E2", "Sara", "sales", 10, 45, 2100),
    ]
    att = attendance_from_dwell(rows)
    # Sorted by arrival: Ali (09:00) then Sara (09:10).
    assert [a["emp_id"] for a in att] == ["E1", "E2"]
    ali, sara = att
    assert ali["arrival"] == T
    assert ali["departure"] == T + timedelta(minutes=50)
    assert ali["span_seconds"] == 50 * 60
    assert ali["tracked_seconds"] == 1800 + 600
    assert ali["zones_count"] == 2
    assert ali["present"] is True
    assert sara["span_seconds"] == 35 * 60
    assert sara["tracked_seconds"] == 2100
    assert sara["zones_count"] == 1
    assert sara["present"] is False


def test_attendance_skips_anonymous_rows():
    rows = [_row(None, None, "z", 0, 10, 600), _row("E1", "Ali", "z", 0, 10, 600)]
    att = attendance_from_dwell(rows)
    assert [a["emp_id"] for a in att] == ["E1"]


def test_attendance_empty():
    assert attendance_from_dwell([]) == []


def test_attendance_csv():
    rows = [
        _row("E1", "Ali", "sales", 0, 30, 1800),
        _row("E1", "Ali", "prod", 40, 50, 600),
    ]
    data = {"rows": attendance_from_dwell(rows)}
    parsed = list(csv.reader(io.StringIO(attendance_csv(data))))
    assert parsed[0] == ["employee_id", "employee_name", "arrival", "departure",
                         "span_seconds", "span", "tracked_seconds", "tracked",
                         "zones", "present"]
    assert parsed[1][0] == "E1"
    assert parsed[1][4] == "3000" and parsed[1][5] == "0:50:00"  # span 50m
    assert parsed[1][6] == "2400" and parsed[1][7] == "0:40:00"  # tracked 40m
    assert parsed[1][8] == "2"
