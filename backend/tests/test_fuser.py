"""Pure-logic tests for the MV3DT fuser's linking + union-find.

No DB — exercises the spatial/appearance link decision and clustering in
isolation. The end-to-end fusion is verified against the running stack.
"""

from datetime import datetime, timedelta, UTC
from uuid import uuid4

import app.core.models  # noqa: F401  -- registers every ORM model (Site, etc.)
from app.modules.mv3dt.fuser import MultiViewFuser, _Candidate, _UnionFind
from app.modules.tracks.models import Track

T0 = datetime(2026, 6, 10, 12, 0, 0, tzinfo=UTC)


def _track(person_id=None, start=T0, end=None):
    return Track(
        id=uuid4(),
        tenant_id=uuid4(),
        camera_id=uuid4(),
        tracker_id=1,
        started_at=start,
        ended_at=end or (start + timedelta(seconds=5)),
        person_id=person_id,
    )


def _cand(track, pts):
    # pts: list of (offset_seconds, world_x, world_y)
    return _Candidate(
        track,
        [(track.started_at + timedelta(seconds=o), x, y, track.camera_id) for o, x, y in pts],
    )


def test_unionfind_groups():
    uf = _UnionFind()
    for k in ("a", "b", "c", "d"):
        uf.find(k)
    uf.union("a", "b")
    uf.union("b", "c")
    groups = [sorted(g) for g in uf.groups().values()]
    assert sorted(groups, key=len, reverse=True)[0] == ["a", "b", "c"]
    assert ["d"] in groups


def test_span_gap():
    a = _track(start=T0, end=T0 + timedelta(seconds=5))
    b = _track(start=T0 + timedelta(seconds=8), end=T0 + timedelta(seconds=12))
    assert MultiViewFuser._span_gap(a, b) == 3.0  # 8 - 5
    assert MultiViewFuser._span_gap(a, a) == 0.0  # overlapping


def test_spatial_link_when_coincident():
    f = MultiViewFuser()
    a = _cand(_track(), [(0, 0.50, 0.50), (1, 0.51, 0.50)])
    b = _cand(_track(), [(0, 0.51, 0.50), (1, 0.52, 0.51)])  # same place, same time
    assert f._should_link(a, b) is True


def test_no_spatial_link_when_far():
    f = MultiViewFuser()
    a = _cand(_track(), [(0, 0.10, 0.10)])
    b = _cand(_track(), [(0, 0.90, 0.90)])  # far apart
    assert f._should_link(a, b) is False


def test_appearance_link_same_person_small_gap():
    f = MultiViewFuser()
    pid = uuid4()
    # Spatially far, but same identity and adjacent in time -> link.
    a = _cand(_track(person_id=pid, start=T0, end=T0 + timedelta(seconds=5)),
              [(0, 0.10, 0.10)])
    b = _cand(_track(person_id=pid, start=T0 + timedelta(seconds=8),
                     end=T0 + timedelta(seconds=12)),
              [(0, 0.90, 0.90)])
    assert f._should_link(a, b) is True


def test_no_link_different_person_far():
    f = MultiViewFuser()
    a = _cand(_track(person_id=uuid4()), [(0, 0.10, 0.10)])
    b = _cand(_track(person_id=uuid4()), [(0, 0.90, 0.90)])
    assert f._should_link(a, b) is False
