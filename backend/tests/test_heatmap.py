"""Unit tests for the hour-of-day occupancy heatmap (pure)."""
import csv
import io
from datetime import datetime, timezone

from app.modules.analytics.export import heatmap_csv
from app.modules.analytics.heatmap import hour_of_day_heatmap

UTC = timezone.utc


def _seg(emp_id, h1, m1, h2, m2, zone_id="z", zone_name="Sales"):
    return {
        "zone_id": zone_id, "zone_name": zone_name,
        "floor_plan_id": "fp", "floor_plan_name": "Ground",
        "emp_id": emp_id,
        "start": datetime(2026, 7, 15, h1, m1, tzinfo=UTC),
        "end": datetime(2026, 7, 15, h2, m2, tzinfo=UTC),
    }


def test_heatmap_splits_at_hour_boundaries():
    presence = [
        _seg("E1", 9, 15, 10, 45),   # 09:15-10:00 (45m) + 10:00-10:45 (45m)
        _seg("E2", 9, 30, 9, 50),    # 20m in hour 9
    ]
    rows = hour_of_day_heatmap(presence, UTC)
    assert len(rows) == 1
    cells = {c["hour"]: c for c in rows[0]["cells"]}
    assert len(rows[0]["cells"]) == 24
    assert cells[9]["seconds"] == 45 * 60 + 20 * 60  # 3900
    assert cells[9]["people"] == 2
    assert cells[10]["seconds"] == 45 * 60
    assert cells[10]["people"] == 1
    assert cells[8]["seconds"] == 0 and cells[8]["people"] == 0
    assert rows[0]["total_seconds"] == 45 * 60 + 20 * 60 + 45 * 60


def test_heatmap_two_zones_busiest_first():
    presence = [
        _seg("E1", 9, 0, 9, 30, zone_id="a", zone_name="A"),   # 30m
        _seg("E2", 9, 0, 11, 0, zone_id="b", zone_name="B"),   # 120m
    ]
    rows = hour_of_day_heatmap(presence, UTC)
    assert [r["zone_name"] for r in rows] == ["B", "A"]


def test_heatmap_ignores_zero_length():
    presence = [_seg("E1", 9, 0, 9, 0)]
    assert hour_of_day_heatmap(presence, UTC) == []


def test_heatmap_empty():
    assert hour_of_day_heatmap([], UTC) == []


def test_heatmap_csv():
    presence = [_seg("E1", 9, 0, 9, 30), _seg("E2", 10, 0, 10, 30)]
    data = {"zones": hour_of_day_heatmap(presence, UTC)}
    parsed = list(csv.reader(io.StringIO(heatmap_csv(data))))
    header = parsed[0]
    assert header[0] == "zone" and header[2] == "00:00" and header[25] == "23:00"
    assert header[-1] == "total_min"
    # hour 09 column (index 2 + 9 = 11) = 30 min; hour 10 (index 12) = 30 min
    assert parsed[1][11] == "30"
    assert parsed[1][12] == "30"
    assert parsed[1][-1] == "60"
