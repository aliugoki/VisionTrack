"""Pure-logic tests for per-person zone dwell (indoor geofencing).

No DB — exercises the camera->zone index, window clipping, and per-(person, zone)
accumulation in isolation. The end-to-end query is verified against the DB in
scripts/check_dwell.py.
"""
from datetime import datetime, timedelta, timezone

from app.modules.analytics.dwell import (
    accumulate_dwell,
    build_person_timeline,
    camera_zone_index,
    clip_interval,
    track_zone_intervals,
    zone_durations_from_intervals,
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


# --------------------------------------------------------------------------- #
# build_person_timeline — "where was X today"
# --------------------------------------------------------------------------- #

def _seg(zone_id, zone_name, start_off, end_off, present=False):
    return {
        "zone_id": zone_id, "zone_name": zone_name,
        "floor_plan_id": "fp1", "floor_plan_name": "Ground Floor",
        "start": T0 + timedelta(minutes=start_off),
        "end": T0 + timedelta(minutes=end_off),
        "present": present,
    }


def test_timeline_orders_chronologically_across_zones():
    # Sales 0-45, Production 45-90, Sales 90-120 -> three visits, Sales twice.
    tl = build_person_timeline([
        _seg("zR", "Production", 45, 90),
        _seg("zL", "Sales", 0, 45),
        _seg("zL", "Sales", 90, 120, present=True),
    ])
    assert [(v["zone_name"], v["seconds"], v["present"]) for v in tl] == [
        ("Sales", 45 * 60, False),
        ("Production", 45 * 60, False),
        ("Sales", 30 * 60, True),
    ]


def test_timeline_merges_same_zone_fragments_within_gap():
    # Two Sales fragments 30s apart (tracker drop) merge into one visit.
    tl = build_person_timeline([
        _seg("zL", "Sales", 0, 10),
        _seg("zL", "Sales", 10.5, 20),   # 30s gap
    ], merge_gap_seconds=60)
    assert len(tl) == 1
    assert tl[0]["seconds"] == 20 * 60
    assert tl[0]["sessions"] == 2


def test_timeline_keeps_same_zone_return_as_separate_visit():
    # Left Sales for 40 min then came back -> two Sales visits (gap > tolerance).
    tl = build_person_timeline([
        _seg("zL", "Sales", 0, 20),
        _seg("zL", "Sales", 60, 75),
    ], merge_gap_seconds=60)
    assert [(v["zone_name"], v["seconds"]) for v in tl] == [
        ("Sales", 20 * 60),
        ("Sales", 15 * 60),
    ]


def test_timeline_merges_overlapping_fragments():
    # Overlapping tracks (two cameras, same zone) merge to the union span.
    tl = build_person_timeline([
        _seg("zL", "Sales", 0, 30),
        _seg("zL", "Sales", 20, 45),
    ])
    assert len(tl) == 1
    assert tl[0]["start"] == T0
    assert tl[0]["end"] == T0 + timedelta(minutes=45)
    assert tl[0]["seconds"] == 45 * 60


def test_timeline_empty():
    assert build_person_timeline([]) == []


# --------------------------------------------------------------------------- #
# track_zone_intervals — per-track-point time-weighting
# --------------------------------------------------------------------------- #

def _refA():
    return {"zone_id": "zL", "zone_name": "Sales", "floor_plan_id": "fp1",
            "floor_plan_name": "Ground Floor"}


def _refB():
    return {"zone_id": "zR", "zone_name": "Production", "floor_plan_id": "fp1",
            "floor_plan_name": "Ground Floor"}


def _samp(min_off, refs):
    return (T0 + timedelta(minutes=min_off), refs)


def test_intervals_single_zone_spans_segment():
    # Three samples all in Sales at t=2,4,6; segment [0,10] -> one interval [0,10]
    # (head extends to seg_start, tail to seg_end via forward-fill).
    pts = [_samp(2, [_refA()]), _samp(4, [_refA()]), _samp(6, [_refA()])]
    ivs = track_zone_intervals(pts, T0, T0 + timedelta(minutes=10))
    assert len(ivs) == 1
    assert ivs[0]["zone_name"] == "Sales"
    assert ivs[0]["start"] == T0 and ivs[0]["end"] == T0 + timedelta(minutes=10)


def test_intervals_move_A_to_B_splits_time():
    # Sales until minute 5, then Production. Segment [0,10].
    # Forward-fill: A owns [0,5) then [5, ...] is B -> A:[0,5], B:[5,10].
    pts = [_samp(0, [_refA()]), _samp(5, [_refB()])]
    ivs = track_zone_intervals(pts, T0, T0 + timedelta(minutes=10))
    assert [(i["zone_name"], i["start"], i["end"]) for i in ivs] == [
        ("Sales", T0, T0 + timedelta(minutes=5)),
        ("Production", T0 + timedelta(minutes=5), T0 + timedelta(minutes=10)),
    ]


def test_intervals_return_visit_separates():
    # A -> B -> A: three intervals, Sales appears twice.
    pts = [_samp(0, [_refA()]), _samp(3, [_refB()]), _samp(6, [_refA()])]
    ivs = track_zone_intervals(pts, T0, T0 + timedelta(minutes=9))
    assert [i["zone_name"] for i in ivs] == ["Sales", "Production", "Sales"]


def test_intervals_off_zone_samples_contribute_nothing():
    # Middle sample is in no zone (aisle) -> that time is unattributed.
    pts = [_samp(0, [_refA()]), _samp(4, []), _samp(8, [_refA()])]
    ivs = track_zone_intervals(pts, T0, T0 + timedelta(minutes=12))
    # Two Sales intervals: [0,4] and [8,12]; the [4,8] aisle gap is dropped.
    assert [(i["start"], i["end"]) for i in ivs] == [
        (T0, T0 + timedelta(minutes=4)),
        (T0 + timedelta(minutes=8), T0 + timedelta(minutes=12)),
    ]


def test_intervals_empty_points():
    assert track_zone_intervals([], T0, T0 + timedelta(minutes=5)) == []


def test_zone_durations_from_intervals_sums_per_zone():
    ivs = track_zone_intervals(
        [_samp(0, [_refA()]), _samp(3, [_refB()]), _samp(6, [_refA()])],
        T0, T0 + timedelta(minutes=9))
    zd = {z["ref"]["zone_name"]: z for z in zone_durations_from_intervals(ivs)}
    # Sales = [0,3] + [6,9] = 6 min; Production = [3,6] = 3 min.
    assert zd["Sales"]["seconds"] == 6 * 60
    assert zd["Production"]["seconds"] == 3 * 60
    assert zd["Sales"]["first"] == T0
    assert zd["Sales"]["last"] == T0 + timedelta(minutes=9)


def test_accumulate_dwell_consumes_zone_durations():
    # A single moving track -> two zones via zone_durations; one session each.
    ivs = track_zone_intervals(
        [_samp(0, [_refA()]), _samp(5, [_refB()])], T0, T0 + timedelta(minutes=10))
    track = {"emp_id": "E1", "name": "Ali", "present": True,
             "zone_durations": zone_durations_from_intervals(ivs)}
    rows = {r["zone_name"]: r for r in accumulate_dwell([track])}
    assert rows["Sales"]["seconds"] == 5 * 60 and rows["Sales"]["sessions"] == 1
    assert rows["Production"]["seconds"] == 5 * 60 and rows["Production"]["sessions"] == 1
    assert rows["Production"]["present"] is True
