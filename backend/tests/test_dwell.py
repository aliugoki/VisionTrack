"""Pure-logic tests for per-person zone dwell (indoor geofencing).

No DB — exercises the camera->zone index, window clipping, and per-(person, zone)
accumulation in isolation. The end-to-end query is verified against the DB in
scripts/check_dwell.py.
"""
from datetime import datetime, timedelta, timezone

from app.modules.analytics.dwell import (
    accumulate_dwell,
    camera_zone_index,
    clip_interval,
)

T0 = datetime(2026, 7, 15, 9, 0, 0, tzinfo=timezone.utc)

# A unit square zone [0.0,0.5]x[0.0,1.0] (left half) and [0.5,1.0]x[0.0,1.0]
# (right half) on one floor plan, with two cameras: camA marker in the left
# zone, camB in the right.
FLOOR_PLANS = [{
    "id": "fp1",
    "name": "Ground Floor",
    "zones": [
        {"id": "zL", "name": "Sales",
         "polygon": [{"x": 0.0, "y": 0.0}, {"x": 0.5, "y": 0.0},
                     {"x": 0.5, "y": 1.0}, {"x": 0.0, "y": 1.0}]},
        {"id": "zR", "name": "Production",
         "polygon": [{"x": 0.5, "y": 0.0}, {"x": 1.0, "y": 0.0},
                     {"x": 1.0, "y": 1.0}, {"x": 0.5, "y": 1.0}]},
    ],
    "markers": [
        {"camera_id": "camA", "x": 0.25, "y": 0.5},   # inside Sales
        {"camera_id": "camB", "x": 0.75, "y": 0.5},   # inside Production
        {"camera_id": "camC", "x": 0.9, "y": 0.9},    # inside Production too
    ],
}]


def test_camera_zone_index_marker_in_polygon():
    idx = camera_zone_index(FLOOR_PLANS)
    assert [z["zone_id"] for z in idx["camA"]] == ["zL"]
    assert [z["zone_id"] for z in idx["camB"]] == ["zR"]
    assert idx["camA"][0]["zone_name"] == "Sales"
    # camC is also in Production
    assert [z["zone_id"] for z in idx["camC"]] == ["zR"]


def test_camera_zone_index_overlapping_zones():
    # A camera whose marker sits inside two overlapping polygons belongs to both.
    fps = [{
        "id": "fp", "name": "F",
        "zones": [
            {"id": "z1", "name": "A", "polygon": [{"x": 0, "y": 0}, {"x": 1, "y": 0},
                                                  {"x": 1, "y": 1}, {"x": 0, "y": 1}]},
            {"id": "z2", "name": "B", "polygon": [{"x": 0.2, "y": 0.2}, {"x": 0.8, "y": 0.2},
                                                  {"x": 0.8, "y": 0.8}, {"x": 0.2, "y": 0.8}]},
        ],
        "markers": [{"camera_id": "cam", "x": 0.5, "y": 0.5}],
    }]
    idx = camera_zone_index(fps)
    assert sorted(z["zone_id"] for z in idx["cam"]) == ["z1", "z2"]


def test_camera_zone_index_ignores_degenerate_polygon():
    fps = [{"id": "fp", "name": "F",
            "zones": [{"id": "z", "name": "bad", "polygon": [{"x": 0, "y": 0}, {"x": 1, "y": 1}]}],
            "markers": [{"camera_id": "cam", "x": 0.5, "y": 0.5}]}]
    assert camera_zone_index(fps) == {}


def test_clip_interval():
    lo, hi = T0, T0 + timedelta(hours=1)
    # fully inside
    assert clip_interval(T0 + timedelta(minutes=10), T0 + timedelta(minutes=20), lo, hi) == \
        (T0 + timedelta(minutes=10), T0 + timedelta(minutes=20))
    # overhang both ends -> clamped to window
    assert clip_interval(T0 - timedelta(hours=1), T0 + timedelta(hours=2), lo, hi) == (lo, hi)
    # disjoint (before) -> None
    assert clip_interval(T0 - timedelta(hours=2), T0 - timedelta(hours=1), lo, hi) is None
    # inverted / zero-length -> None
    assert clip_interval(T0 + timedelta(minutes=20), T0 + timedelta(minutes=10), lo, hi) is None


def _track(camera_id, emp_id, name, start_off, end_off, present=False):
    return {
        "camera_id": camera_id, "emp_id": emp_id, "name": name,
        "start": T0 + timedelta(minutes=start_off),
        "end": T0 + timedelta(minutes=end_off),
        "present": present,
    }


def test_accumulate_single_person_one_zone():
    idx = camera_zone_index(FLOOR_PLANS)
    rows = accumulate_dwell([_track("camA", "E1", "Ali", 0, 30)], idx)
    assert len(rows) == 1
    r = rows[0]
    assert r["emp_id"] == "E1" and r["name"] == "Ali"
    assert r["zone_id"] == "zL" and r["zone_name"] == "Sales"
    assert r["seconds"] == 30 * 60
    assert r["sessions"] == 1
    assert r["present"] is False


def test_accumulate_sums_fragments_and_span():
    idx = camera_zone_index(FLOOR_PLANS)
    rows = accumulate_dwell([
        _track("camA", "E1", "Ali", 0, 20),            # 20 min in Sales
        _track("camA", "E1", "Ali", 40, 55, present=True),  # +15 min, still here
    ], idx)
    assert len(rows) == 1
    r = rows[0]
    assert r["seconds"] == 35 * 60
    assert r["sessions"] == 2
    assert r["first_seen"] == T0
    assert r["last_seen"] == T0 + timedelta(minutes=55)
    assert r["present"] is True   # any fragment present -> present now


def test_accumulate_skips_anonymous_and_zoneless():
    idx = camera_zone_index(FLOOR_PLANS)
    rows = accumulate_dwell([
        _track("camA", None, None, 0, 30),        # anonymous -> skipped
        _track("camZ", "E1", "Ali", 0, 30),       # camera in no zone -> skipped
    ], idx)
    assert rows == []


def test_accumulate_multi_zone_and_sort_order():
    idx = camera_zone_index(FLOOR_PLANS)
    rows = accumulate_dwell([
        _track("camA", "E1", "Ali", 0, 10),    # Sales, 10 min
        _track("camB", "E2", "Sara", 0, 45),   # Production, 45 min
    ], idx)
    # sorted by seconds desc -> Sara (Production) first
    assert [(r["emp_id"], r["zone_name"], r["seconds"]) for r in rows] == [
        ("E2", "Production", 45 * 60),
        ("E1", "Sales", 10 * 60),
    ]
