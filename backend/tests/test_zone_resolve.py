"""Pure-logic tests for desk-level zone attribution via homography.

Exercises foot-point projection and the position-vs-marker resolution in
isolation (no DB). The DB path is covered in scripts/check_dwell.py.
"""
from app.modules.analytics.zone_resolve import (
    camera_plan_zones,
    homographies_by_camera,
    project_foot,
    resolve_track_zone_refs,
)

# A homography that maps 1000x1000 source pixels to 0..1 floor-plan fractions
# (i.e. divide by 1000). Row-major 3x3.
H_SCALE = [0.001, 0.0, 0.0, 0.0, 0.001, 0.0, 0.0, 0.0, 1.0]

# One camera ("cam") covering two desks: left half = Desk A, right half = Desk B.
FLOOR_PLANS = [{
    "id": "fp", "name": "Office",
    "zones": [
        {"id": "deskA", "name": "Desk A",
         "polygon": [{"x": 0.0, "y": 0.0}, {"x": 0.5, "y": 0.0},
                     {"x": 0.5, "y": 1.0}, {"x": 0.0, "y": 1.0}]},
        {"id": "deskB", "name": "Desk B",
         "polygon": [{"x": 0.5, "y": 0.0}, {"x": 1.0, "y": 0.0},
                     {"x": 1.0, "y": 1.0}, {"x": 0.5, "y": 1.0}]},
    ],
    # Marker sits in Desk A -> marker mode would attribute EVERYONE to Desk A.
    "markers": [{"camera_id": "cam", "x": 0.25, "y": 0.5}],
}]


def test_project_foot_dict_and_list_agree():
    dict_bbox = {"x1": 400, "y1": 700, "x2": 600, "y2": 900}
    list_bbox = [400, 700, 600, 900]
    # foot = ((400+600)/2, 900) = (500, 900) -> /1000 -> (0.5, 0.9)
    for bbox in (dict_bbox, list_bbox):
        pt = project_foot(H_SCALE, bbox)
        assert pt is not None
        assert abs(pt[0] - 0.5) < 1e-9 and abs(pt[1] - 0.9) < 1e-9


def test_project_foot_rejects_bad_input():
    assert project_foot([1, 2, 3], {"x1": 0, "y1": 0, "x2": 1, "y2": 1}) is None  # wrong len
    assert project_foot(H_SCALE, None) is None
    assert project_foot(H_SCALE, {"x1": 0}) is None  # missing keys
    # Degenerate w -> None (last row projects to 0).
    assert project_foot([1, 0, 0, 0, 1, 0, 0, 0, 0], [10, 10, 20, 20]) is None


def test_camera_plan_zones_indexes_camera_to_plan_zones():
    idx = camera_plan_zones(FLOOR_PLANS)
    assert "cam" in idx
    (fp_id, fp_name, zones) = idx["cam"][0]
    assert fp_id == "fp" and fp_name == "Office"
    assert sorted(z[0] for z in zones) == ["deskA", "deskB"]


def _marker_zones():
    # Desk A contains the camera marker (0.25, 0.5); Desk B does not.
    return {"cam": [{"floor_plan_id": "fp", "floor_plan_name": "Office",
                     "zone_id": "deskA", "zone_name": "Desk A"}]}


def test_position_mode_distinguishes_desks_in_one_camera():
    plan_zones = camera_plan_zones(FLOOR_PLANS)
    H = {"cam": H_SCALE}
    marker = _marker_zones()

    # Person on the LEFT (foot ~x=0.25) -> Desk A
    left = resolve_track_zone_refs("cam", [200, 700, 300, 900], H, marker, plan_zones)
    assert [r["zone_id"] for r in left] == ["deskA"]

    # Person on the RIGHT (foot ~x=0.75) -> Desk B, NOT Desk A (the marker zone).
    right = resolve_track_zone_refs("cam", [700, 700, 800, 900], H, marker, plan_zones)
    assert [r["zone_id"] for r in right] == ["deskB"]


def test_marker_fallback_when_no_homography():
    plan_zones = camera_plan_zones(FLOOR_PLANS)
    # No homography for the camera -> coarse marker mode (everyone in Desk A).
    refs = resolve_track_zone_refs("cam", [700, 700, 800, 900], {}, _marker_zones(), plan_zones)
    assert [r["zone_id"] for r in refs] == ["deskA"]


def test_position_mode_off_plan_point_falls_back_to_marker():
    plan_zones = camera_plan_zones(FLOOR_PLANS)
    H = {"cam": H_SCALE}
    # Foot at px 5000 -> fractional x=5.0, outside [0,1] -> fall back to marker.
    refs = resolve_track_zone_refs("cam", [4900, 700, 5100, 900], H, _marker_zones(), plan_zones)
    assert [r["zone_id"] for r in refs] == ["deskA"]


def test_position_mode_in_no_zone_returns_empty():
    # A plan whose only zone is a small box in the corner; a foot-point elsewhere
    # is in NO zone -> precise empty (person is between desks / in an aisle).
    fps = [{"id": "fp", "name": "F",
            "zones": [{"id": "z", "name": "Corner",
                       "polygon": [{"x": 0.0, "y": 0.0}, {"x": 0.1, "y": 0.0},
                                   {"x": 0.1, "y": 0.1}, {"x": 0.0, "y": 0.1}]}],
            "markers": [{"camera_id": "cam", "x": 0.05, "y": 0.05}]}]
    plan_zones = camera_plan_zones(fps)
    marker = {"cam": [{"floor_plan_id": "fp", "floor_plan_name": "F",
                       "zone_id": "z", "zone_name": "Corner"}]}
    # foot at (0.5, 0.9) -> not in the corner box -> []
    refs = resolve_track_zone_refs("cam", [400, 700, 600, 900], {"cam": H_SCALE}, marker, plan_zones)
    assert refs == []


def test_homographies_by_camera_extracts_valid_only():
    rows = [
        ("cam1", {"homography": H_SCALE}),
        ("cam2", {"homography": [1, 2, 3]}),   # wrong length -> skipped
        ("cam3", {}),                          # no homography -> skipped
        ("cam4", None),                        # no calibration -> skipped
    ]
    out = homographies_by_camera(rows)
    assert list(out.keys()) == ["cam1"]
    assert out["cam1"] == H_SCALE
