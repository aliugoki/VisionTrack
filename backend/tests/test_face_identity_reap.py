"""Unit tests for FaceIdentityConsumer._reap_undesired.

When a tenant's FaceTrack feed is toggled off, the discovery loop drops it from
the desired set and _reap_undesired must cancel + remove exactly that tenant's
consume task(s), leaving others running. Pure dict/cancel logic — no event loop,
Redis, or DB (we call the method with a stand-in `self` and fake tasks).
"""
from app.modules.persons.face_identity_consumer import FaceIdentityConsumer


class _FakeTask:
    def __init__(self):
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


class _Holder:
    """Minimal stand-in carrying just the `_tasks` attribute the method uses."""
    def __init__(self, tasks):
        self._tasks = tasks


def test_reap_cancels_and_removes_only_undesired():
    keep, drop = _FakeTask(), _FakeTask()
    h = _Holder({"face-identity:keep": keep, "face-identity:drop": drop})
    FaceIdentityConsumer._reap_undesired(h, {"face-identity:keep"})
    assert "face-identity:drop" not in h._tasks   # removed
    assert drop.cancelled is True                 # cancelled
    assert h._tasks == {"face-identity:keep": keep}
    assert keep.cancelled is False                # survivor untouched


def test_reap_is_a_noop_when_everything_is_desired():
    t = _FakeTask()
    h = _Holder({"k": t})
    FaceIdentityConsumer._reap_undesired(h, {"k"})
    assert h._tasks == {"k": t}
    assert t.cancelled is False


def test_reap_removes_all_when_none_desired():
    t1, t2 = _FakeTask(), _FakeTask()
    h = _Holder({"a": t1, "b": t2})
    FaceIdentityConsumer._reap_undesired(h, set())
    assert h._tasks == {}
    assert t1.cancelled and t2.cancelled


def test_reap_reaps_company_bridge_task_when_tenant_disabled():
    # A disabled tenant has both its native and company-keyed streams reaped.
    native, bridge, other = _FakeTask(), _FakeTask(), _FakeTask()
    h = _Holder({
        "face-identity:T1": native,
        "face-identity:company:C1": bridge,
        "face-identity:T2": other,
    })
    FaceIdentityConsumer._reap_undesired(h, {"face-identity:T2"})
    assert set(h._tasks) == {"face-identity:T2"}
    assert native.cancelled and bridge.cancelled
    assert other.cancelled is False
