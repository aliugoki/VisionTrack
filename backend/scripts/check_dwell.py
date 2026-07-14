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
from app.modules.analytics.export import dwell_csv, timeline_csv
from app.modules.analytics.service import get_person_timeline, get_zone_dwell
from app.modules.cameras.models import Camera
from app.modules.floor_plans.models import FloorPlan
from app.modules.persons.models import PersonIdentity
from app.modules.sites.models import Site
from app.modules.tenants.models import Tenant
from app.modules.tracks.models import Track, TrackPoint

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

        # ---- "Where was Ali today" timeline. Ali has two Sales tracks 40m apart
        # (T1 90..60m ago, T2 20m ago..open) -> two visits at the default 60s gap.
        wide_from = now - timedelta(hours=3)
        wide_to = now + timedelta(hours=1)
        tl = await get_person_timeline(
            db, tenant_id=tenant.id, emp_id="E1",
            started_after=wide_from, started_before=wide_to,
        )
        print("\nAli timeline:")
        for s in tl["segments"]:
            print(f"  {s['zone_name']:<10} {int(s['seconds'])//60}m present={s['present']}")
        _assert(tl["name"] == "Ali", "timeline resolves the employee name")
        _assert([s["zone_name"] for s in tl["segments"]] == ["Sales", "Sales"],
                "Ali's day = two Sales visits (40m apart, not merged)")
        _assert(tl["segments"][0]["seconds"] == 30 * 60, "first Sales visit = 30m")
        _assert(tl["segments"][0]["present"] is False, "first visit not present")
        _assert(tl["segments"][1]["present"] is True, "second (open) visit is present")
        _assert(tl["segments"][0]["start"] < tl["segments"][1]["start"],
                "timeline is chronological")

        # With a 60-min merge tolerance the 40m gap closes -> one visit spanning
        # 90m..~now, sessions=2.
        merged = await get_person_timeline(
            db, tenant_id=tenant.id, emp_id="E1",
            started_after=wide_from, started_before=wide_to,
            merge_gap_seconds=3600,
        )
        _assert(len(merged["segments"]) == 1, "merge_gap=1h collapses to one Sales visit")
        _assert(merged["segments"][0]["sessions"] == 2, "merged visit records 2 sessions")

        # ---- CSV export smoke: format the real service output.
        dcsv = dwell_csv(data)
        tcsv = timeline_csv(tl)
        print("\nCSV export:")
        print("  dwell header:", dcsv.splitlines()[0])
        _assert(dcsv.splitlines()[0].startswith("employee_id,employee_name,"),
                "dwell CSV has the expected header")
        _assert("Ali" in dcsv and "0:49:30" in dcsv, "dwell CSV contains Ali 0:49:30")
        _assert(len(dcsv.splitlines()) == 3, "dwell CSV = header + 2 employees")
        _assert(tcsv.splitlines()[0].startswith("employee_id,employee_name,sequence,"),
                "timeline CSV has the expected header")
        _assert(len(tcsv.splitlines()) == 3 and "Sales" in tcsv,
                "timeline CSV = header + Ali's 2 Sales visits")

        # ---- Reporting filters (emp_id / zone_id).
        sales_zone = next(r["zone_id"] for r in data["rows"] if r["zone_name"] == "Sales")
        by_emp = await get_zone_dwell(
            db, tenant_id=tenant.id,
            started_after=now - timedelta(hours=3), started_before=now + timedelta(hours=1),
            emp_id="E1")
        _assert({r["emp_id"] for r in by_emp["rows"]} == {"E1"}, "emp_id filter returns only Ali")
        by_zone = await get_zone_dwell(
            db, tenant_id=tenant.id,
            started_after=now - timedelta(hours=3), started_before=now + timedelta(hours=1),
            zone_id=sales_zone)
        _assert({r["zone_name"] for r in by_zone["rows"]} == {"Sales"},
                "zone_id filter returns only Sales")
        both = await get_zone_dwell(
            db, tenant_id=tenant.id,
            started_after=now - timedelta(hours=3), started_before=now + timedelta(hours=1),
            emp_id="E2", zone_id=sales_zone)
        _assert(both["rows"] == [], "emp_id=Sara + zone=Sales -> empty (Sara is in Production)")

        # ---- Desk-level precision: ONE calibrated camera covering two desks.
        # A homography mapping 1000x1000 px -> 0..1 fractions; two people at
        # different x land in different desk polygons (marker mode would lump both
        # into Desk A, where the camera marker sits).
        H_SCALE = [0.001, 0.0, 0.0, 0.0, 0.001, 0.0, 0.0, 0.0, 1.0]
        t2 = Tenant(name="Desk Test Co", subdomain=f"desk-{uuid4().hex[:8]}")
        db.add(t2)
        await db.flush()
        s2 = Site(tenant_id=t2.id, name="Office")
        db.add(s2)
        await db.flush()
        dcam = Camera(tenant_id=t2.id, site_id=s2.id, name="Desk Cam",
                      rtsp_url="rtsp://x/desk", mediamtx_path=f"d-{uuid4().hex[:6]}",
                      calibration={"homography": H_SCALE})
        db.add(dcam)
        await db.flush()
        desk_zones = [
            {"id": str(uuid4()), "name": "Desk A", "rules": [],
             "polygon": [{"x": 0.0, "y": 0.0}, {"x": 0.5, "y": 0.0},
                         {"x": 0.5, "y": 1.0}, {"x": 0.0, "y": 1.0}]},
            {"id": str(uuid4()), "name": "Desk B", "rules": [],
             "polygon": [{"x": 0.5, "y": 0.0}, {"x": 1.0, "y": 0.0},
                         {"x": 1.0, "y": 1.0}, {"x": 0.5, "y": 1.0}]},
        ]
        fp2 = FloorPlan(
            tenant_id=t2.id, site_id=s2.id, name="Office Floor",
            original_filename="o.png", original_content_type="image/png",
            original_size_bytes=1, format="png", width_px=1000, height_px=1000,
            storage_key_original="k",
            markers=[{"camera_id": str(dcam.id), "x": 0.25, "y": 0.5}],  # marker in Desk A
            zones=desk_zones)
        db.add(fp2)
        await db.flush()

        def desk_track(bbox):
            t = Track(tenant_id=t2.id, camera_id=dcam.id, tracker_id=1,
                      started_at=now - timedelta(minutes=10), ended_at=None,
                      first_bbox=bbox, last_bbox=bbox, point_count=1)
            db.add(t)
            return t
        # Zed sits on the LEFT (foot x~0.25 -> Desk A); Yan on the RIGHT (x~0.75 -> Desk B).
        z_tr = desk_track({"x1": 200, "y1": 700, "x2": 300, "y2": 900})
        y_tr = desk_track({"x1": 700, "y1": 700, "x2": 800, "y2": 900})
        await db.flush()
        for tr in (z_tr, y_tr):
            await db.execute(update(Track).where(Track.id == tr.id).values(
                updated_at=now - timedelta(seconds=30)))
        db.add(PersonIdentity(tenant_id=t2.id, track_id=z_tr.id, camera_id=dcam.id,
                              emp_id="E9", name="Zed", votes=5, confidence=0.9, source="face"))
        db.add(PersonIdentity(tenant_id=t2.id, track_id=y_tr.id, camera_id=dcam.id,
                              emp_id="E8", name="Yan", votes=5, confidence=0.9, source="face"))
        await db.commit()

        desk = await get_zone_dwell(
            db, tenant_id=t2.id,
            started_after=now - timedelta(hours=1), started_before=now + timedelta(hours=1),
        )
        dmap = {(r["emp_id"], r["zone_name"]) for r in desk["rows"]}
        print("\nDesk-level (one calibrated camera, two desks):")
        for r in desk["rows"]:
            print(f"  {r['name']:<5} -> {r['zone_name']}")
        _assert(("E9", "Desk A") in dmap, "Zed (left) attributed to Desk A")
        _assert(("E8", "Desk B") in dmap, "Yan (right) attributed to Desk B")
        _assert(("E9", "Desk B") not in dmap and ("E8", "Desk A") not in dmap,
                "same camera, different desks — not lumped by camera marker")

        for tbl in (PersonIdentity, Track, FloorPlan, Camera, Site):
            await db.execute(delete(tbl).where(tbl.tenant_id == t2.id))
        await db.execute(delete(Tenant).where(Tenant.id == t2.id))
        await db.commit()

        # ---- Per-track-point time-weighting: ONE track that MOVES Desk A -> Desk B.
        # track_points carry world_x/world_y (projected at ingest). last_bbox points
        # at Desk B, so whole-track attribution would say "all Desk B" — per-point
        # weighting must instead split the time 50/50.
        t3 = Tenant(name="Move Test Co", subdomain=f"move-{uuid4().hex[:8]}")
        db.add(t3)
        await db.flush()
        s3 = Site(tenant_id=t3.id, name="Office")
        db.add(s3)
        await db.flush()
        mcam = Camera(tenant_id=t3.id, site_id=s3.id, name="Move Cam",
                      rtsp_url="rtsp://x/move", mediamtx_path=f"m-{uuid4().hex[:6]}",
                      calibration={"homography": H_SCALE})
        db.add(mcam)
        await db.flush()
        move_zones = [
            {"id": str(uuid4()), "name": "Desk A", "rules": [],
             "polygon": [{"x": 0.0, "y": 0.0}, {"x": 0.5, "y": 0.0},
                         {"x": 0.5, "y": 1.0}, {"x": 0.0, "y": 1.0}]},
            {"id": str(uuid4()), "name": "Desk B", "rules": [],
             "polygon": [{"x": 0.5, "y": 0.0}, {"x": 1.0, "y": 0.0},
                         {"x": 1.0, "y": 1.0}, {"x": 0.5, "y": 1.0}]},
        ]
        fp3 = FloorPlan(
            tenant_id=t3.id, site_id=s3.id, name="Move Floor",
            original_filename="m.png", original_content_type="image/png",
            original_size_bytes=1, format="png", width_px=1000, height_px=1000,
            storage_key_original="k",
            markers=[{"camera_id": str(mcam.id), "x": 0.25, "y": 0.5}],
            zones=move_zones)
        db.add(fp3)
        await db.flush()
        # Closed 20-min track; last_bbox foot-point -> Desk B (right).
        mtr = Track(tenant_id=t3.id, camera_id=mcam.id, tracker_id=1,
                    started_at=now - timedelta(minutes=20), ended_at=now,
                    first_bbox={"x1": 200, "y1": 700, "x2": 300, "y2": 900},
                    last_bbox={"x1": 700, "y1": 700, "x2": 800, "y2": 900}, point_count=4)
        db.add(mtr)
        await db.flush()
        # world_x: 0.25 (Desk A) for the first half, 0.75 (Desk B) for the second.
        samples = [(20, 0.25), (15, 0.25), (10, 0.75), (5, 0.75)]
        for mins_ago, wx in samples:
            db.add(TrackPoint(
                ts=now - timedelta(minutes=mins_ago), track_id=mtr.id,
                tenant_id=t3.id, camera_id=mcam.id, tracker_id=1,
                bbox_x1=0, bbox_y1=0, bbox_x2=10, bbox_y2=10, confidence=0.9,
                world_x=wx, world_y=0.5))
        db.add(PersonIdentity(tenant_id=t3.id, track_id=mtr.id, camera_id=mcam.id,
                              emp_id="E7", name="Mo", votes=5, confidence=0.9, source="face"))
        await db.commit()

        mv = await get_zone_dwell(
            db, tenant_id=t3.id,
            started_after=now - timedelta(hours=1), started_before=now + timedelta(hours=1))
        mrows = {r["zone_name"]: r for r in mv["rows"]}
        print("\nPer-track-point weighting (one track A -> B):")
        for r in mv["rows"]:
            print(f"  Mo {r['zone_name']}: {int(r['seconds'])//60}m (sessions={r['sessions']})")
        _assert(set(mrows) == {"Desk A", "Desk B"}, "moving track split across BOTH desks")
        _assert(mrows["Desk A"]["seconds"] == 10 * 60, "Desk A = 10m (first half)")
        _assert(mrows["Desk B"]["seconds"] == 10 * 60, "Desk B = 10m (second half, not the whole 20m)")
        _assert(mrows["Desk A"]["sessions"] == 1 and mrows["Desk B"]["sessions"] == 1,
                "one session per desk (not per point)")

        mtl = await get_person_timeline(
            db, tenant_id=t3.id, emp_id="E7",
            started_after=now - timedelta(hours=1), started_before=now + timedelta(hours=1))
        print("Timeline:", [(s["zone_name"], f"{int(s['seconds'])//60}m") for s in mtl["segments"]])
        _assert([s["zone_name"] for s in mtl["segments"]] == ["Desk A", "Desk B"],
                "timeline shows the move: Desk A then Desk B")

        for tbl in (PersonIdentity, TrackPoint, Track, FloorPlan, Camera, Site):
            await db.execute(delete(tbl).where(tbl.tenant_id == t3.id))
        await db.execute(delete(Tenant).where(Tenant.id == t3.id))
        await db.commit()

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
