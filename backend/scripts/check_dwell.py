"""Integration check for per-person zone dwell (indoor geofencing).

Seeds a self-contained scenario (one tenant, a floor plan with two zones, two
cameras placed inside them, and a handful of tracks + face identities) into the
configured database, then calls ``analytics.service.get_zone_dwell`` and asserts
the aggregated dwell is what we expect.

Run inside the backend image against a throwaway DB, e.g.:

    POSTGRES_HOST=localhost POSTGRES_PORT=5533 python -m scripts.check_dwell

Exits non-zero on the first failed assertion. Idempotent-ish: it creates a fresh
tenant (random subdomain) each run, so re-running never collides.
"""
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import delete

import app.core.models  # noqa: F401 -- registers every ORM model (relationships)
from app.core.db import AsyncSessionLocal
from app.modules.analytics.service import get_zone_dwell
from app.modules.cameras.models import Camera
from app.modules.floor_plans.models import FloorPlan
from app.modules.persons.models import PersonIdentity
from app.modules.sites.models import Site
from app.modules.tenants.models import Tenant
from app.modules.tracks.models import Track

UTC = timezone.utc

# Two side-by-side zones on a unit floor plan; a camera marker inside each.
ZONES = [
    {"id": str(uuid4()), "name": "Sales",
     "polygon": [{"x": 0.0, "y": 0.0}, {"x": 0.5, "y": 0.0},
                 {"x": 0.5, "y": 1.0}, {"x": 0.0, "y": 1.0}], "rules": []},
    {"id": str(uuid4()), "name": "Production",
     "polygon": [{"x": 0.5, "y": 0.0}, {"x": 1.0, "y": 0.0},
                 {"x": 1.0, "y": 1.0}, {"x": 0.5, "y": 1.0}], "rules": []},
]


def _assert(cond, msg):
    if not cond:
        print(f"  ✗ {msg}")
        raise SystemExit(1)
    print(f"  ✓ {msg}")


async def main() -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    async with AsyncSessionLocal() as db:
        tenant = Tenant(name="Dwell Test Co", subdomain=f"dwell-{uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()

        site = Site(tenant_id=tenant.id, name="HQ")
        db.add(site)
        await db.flush()

        cam_sales = Camera(tenant_id=tenant.id, site_id=site.id, name="Sales Cam",
                           rtsp_url="rtsp://x/sales", mediamtx_path=f"s-{uuid4().hex[:6]}")
        cam_prod = Camera(tenant_id=tenant.id, site_id=site.id, name="Prod Cam",
                          rtsp_url="rtsp://x/prod", mediamtx_path=f"p-{uuid4().hex[:6]}")
        db.add_all([cam_sales, cam_prod])
        await db.flush()

        markers = [
            {"camera_id": str(cam_sales.id), "x": 0.25, "y": 0.5},   # in Sales
            {"camera_id": str(cam_prod.id), "x": 0.75, "y": 0.5},    # in Production
        ]
        fp = FloorPlan(
            tenant_id=tenant.id, site_id=site.id, name="Ground Floor",
            original_filename="fp.png", original_content_type="image/png",
            original_size_bytes=1, format="png", width_px=1000, height_px=1000,
            storage_key_original="k", markers=markers, zones=ZONES,
        )
        db.add(fp)
        await db.flush()

        def mk_track(cam, started, ended, updated):
            t = Track(tenant_id=tenant.id, camera_id=cam.id, tracker_id=1,
                      started_at=started, ended_at=ended,
                      first_bbox={}, last_bbox={}, point_count=1)
            db.add(t)
            return t

        # Ali in Sales: a closed 30-min track + an open 19m30s track (present now).
        t1 = mk_track(cam_sales, now - timedelta(minutes=90), now - timedelta(minutes=60), None)
        t2 = mk_track(cam_sales, now - timedelta(minutes=20), None, now - timedelta(seconds=30))
        # Sara in Production: a closed 40-min track.
        t3 = mk_track(cam_prod, now - timedelta(minutes=45), now - timedelta(minutes=5), None)
        # Anonymous person in Sales — no identity, must be ignored.
        t4 = mk_track(cam_sales, now - timedelta(minutes=30), now - timedelta(minutes=10), None)
        await db.flush()

        # updated_at is server-managed (onupdate=now); force our test values so the
        # "present" check and open-track dwell are deterministic.
        from sqlalchemy import update
        await db.execute(update(Track).where(Track.id == t2.id).values(
            updated_at=now - timedelta(seconds=30)))

        def ident(track, cam, emp_id, name, votes):
            db.add(PersonIdentity(tenant_id=tenant.id, track_id=track.id, camera_id=cam.id,
                                  emp_id=emp_id, name=name, votes=votes, confidence=0.9,
                                  source="face"))

        ident(t1, cam_sales, "E1", "Ali", 5)
        ident(t2, cam_sales, "E1", "Ali", 5)
        ident(t3, cam_prod, "E2", "Sara", 3)
        await db.commit()

        # ---- Exercise the service over a wide window (no clipping of our tracks).
        data = await get_zone_dwell(
            db, tenant_id=tenant.id,
            started_after=now - timedelta(hours=3),
            started_before=now + timedelta(hours=1),
            active_window_sec=60,
        )
        rows = data["rows"]
        print(f"\nget_zone_dwell returned {len(rows)} row(s):")
        for r in rows:
            print(f"  {r['name']:<6} {r['zone_name']:<12} "
                  f"{int(r['seconds'])//60}m{int(r['seconds'])%60:02d}s "
                  f"sessions={r['sessions']} present={r['present']}")

        print("\nAssertions:")
        _assert(len(rows) == 2, "exactly 2 (person, zone) rows (anonymous excluded)")

        by = {(r["emp_id"], r["zone_name"]): r for r in rows}
        ali = by[("E1", "Sales")]
        sara = by[("E2", "Production")]

        _assert(ali["seconds"] == 30 * 60 + 19 * 60 + 30, "Ali Sales = 30m + 19m30s = 2970s")
        _assert(ali["sessions"] == 2, "Ali has 2 sessions in Sales")
        _assert(ali["present"] is True, "Ali is present now (open track within window)")
        _assert(ali["name"] == "Ali", "Ali's display name carried through")

        _assert(sara["seconds"] == 40 * 60, "Sara Production = 40m = 2400s")
        _assert(sara["sessions"] == 1, "Sara has 1 session")
        _assert(sara["present"] is False, "Sara is not present (track ended)")

        _assert(rows[0]["emp_id"] == "E1", "rows sorted by dwell desc (Ali 2970 > Sara 2400)")

        # min_seconds filter drops Sara (2400 < 2500) but keeps Ali (2970).
        filtered = await get_zone_dwell(
            db, tenant_id=tenant.id,
            started_after=now - timedelta(hours=3),
            started_before=now + timedelta(hours=1),
            min_seconds=2500,
        )
        _assert([r["emp_id"] for r in filtered["rows"]] == ["E1"],
                "min_seconds=2500 keeps only Ali")

        # Window clipping: a 1-hour window [now-70m, now-10m]. Every track is
        # truncated to the window bounds:
        #   Ali T1 (90..60m ago) -> [70m,60m] = 10m
        #   Ali T2 (20m ago..open) -> [20m,10m] = 10m   => Ali Sales 20m, 2 sessions
        #   Sara T3 (45..5m ago)  -> [45m,10m] = 35m
        win_end = now - timedelta(minutes=10)
        clipped = await get_zone_dwell(
            db, tenant_id=tenant.id,
            started_after=win_end - timedelta(hours=1),
            started_before=win_end,
        )
        cby = {(r["emp_id"], r["zone_name"]): r for r in clipped["rows"]}
        _assert(cby[("E1", "Sales")]["seconds"] == 20 * 60, "clipped: Ali Sales = 20m (10m + 10m, both truncated)")
        _assert(cby[("E1", "Sales")]["sessions"] == 2, "clipped: Ali has 2 sessions in window")
        _assert(cby[("E2", "Production")]["seconds"] == 35 * 60, "clipped: Sara truncated to 35m")

        # Cleanup so a shared DB stays tidy (throwaway DBs don't need this).
        await db.execute(delete(PersonIdentity).where(PersonIdentity.tenant_id == tenant.id))
        await db.execute(delete(Track).where(Track.tenant_id == tenant.id))
        await db.execute(delete(FloorPlan).where(FloorPlan.tenant_id == tenant.id))
        await db.execute(delete(Camera).where(Camera.tenant_id == tenant.id))
        await db.execute(delete(Site).where(Site.tenant_id == tenant.id))
        await db.execute(delete(Tenant).where(Tenant.id == tenant.id))
        await db.commit()

    print("\n✅ ALL DWELL INTEGRATION CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
