"""Unit tests for the per-zone rollup + its CSV (pure)."""
import csv
import io
from datetime import datetime, timezone

from app.modules.analytics.export import zone_rollup_csv
from app.modules.analytics.zone_report import zone_rollup_from_dwell

T = datetime(2026, 7, 15, 9, 0, 0, tzinfo=timezone.utc)


def _row(emp_id, zone_id, zone_name, seconds, present=False):
    return {
        "emp_id": emp_id, "zone_id": zone_id, "zone_name": zone_name,
        "floor_plan_id": "fp", "floor_plan_name": "Ground",
        "seconds": seconds, "present": present,
        "first_seen": T, "last_seen": T,
    }


def test_zone_rollup():
    rows = [
        _row("E1", "sales", "Sales", 1800, present=True),
        _row("E2", "sales", "Sales", 1200),
        _row("E3", "prod", "Production", 600),
    ]
    roll = zone_rollup_from_dwell(rows)
    # Busiest first: Sales (3000s) then Production (600s).
    assert [z["zone_name"] for z in roll] == ["Sales", "Production"]
    sales, prod = roll
    assert sales["total_seconds"] == 3000
    assert sales["people_count"] == 2
    assert sales["avg_seconds"] == 1500
    assert sales["present_count"] == 1
    assert prod["people_count"] == 1
    assert prod["avg_seconds"] == 600


def test_zone_rollup_empty():
    assert zone_rollup_from_dwell([]) == []


def test_zone_rollup_csv():
    rows = [_row("E1", "sales", "Sales", 1800), _row("E2", "sales", "Sales", 1200)]
    data = {"rows": zone_rollup_from_dwell(rows)}
    parsed = list(csv.reader(io.StringIO(zone_rollup_csv(data))))
    assert parsed[0] == ["zone_id", "zone", "floor_plan", "total_seconds", "total",
                         "people", "avg_seconds", "avg", "present"]
    assert parsed[1][1] == "Sales"
    assert parsed[1][3] == "3000" and parsed[1][5] == "2"
    assert parsed[1][6] == "1500" and parsed[1][7] == "0:25:00"  # avg 25m
