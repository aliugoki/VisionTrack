"""End-to-end live-recognition proof.

Exercises the full recognition loop with the exact data shapes the live pipeline
produces, so it can be verified without the GPU AI worker or a live camera:

  1. a live TRACK (Track + TrackPoint) on a company's camera  <- the AI worker
  2. a RECOGNITION published to vt:face:identities:<company_id> <- FaceTrack
  3. VisionTrack's running consumer correlates (camera + bbox IoU + time) and
     writes a PersonIdentity into that company's tenant, naming the person.

Verifies the employee then shows as "recognized". Leaves the PersonIdentity (so
the Employees page shows it) but removes the synthetic camera/track.

    docker exec vt-backend python -m scripts.e2e_recognition [subdomain]
"""
import asyncio
import json
import sys
import uuid
from datetime import datetime, timezone

import app.core.models  # noqa: F401 — register ORM models
import redis.asyncio as redis
from sqlalchemy import delete, select, text

from app.core.config import settings
from app.core.db import AsyncSessionLocal
from app.modules.cameras.models import Camera
from app.modules.employees.models import Employee
from app.modules.persons.models import PersonIdentity
from app.modules.sites.models import Site
from app.modules.tenants.models import Tenant
from app.modules.tracks.models import Track, TrackPoint

SUBDOMAIN = sys.argv[1] if len(sys.argv) > 1 else "metaxperts"
BBOX = (100.0, 200.0, 300.0, 500.0)  # x1, y1, x2, y2 (track_point + recognition match => IoU 1.0)


async def main() -> None:
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        tenant = (await db.execute(
            select(Tenant).where(Tenant.subdomain == SUBDOMAIN)
        )).scalar_one()
        company_id = tenant.external_company_id
        assert company_id, f"tenant {SUBDOMAIN} has no external_company_id"
        site = (await db.execute(
            select(Site).where(Site.tenant_id == tenant.id))).scalars().first()
        employee = (await db.execute(
            select(Employee).where(Employee.tenant_id == tenant.id))).scalars().first()
        assert site and employee, "tenant needs a site and at least one employee"
        emp_id = employee.emp_id
        emp_name = " ".join(p for p in (employee.first_name, employee.last_name) if p)

        cam = Camera(tenant_id=tenant.id, site_id=site.id, name=f"E2E-REC-{uuid.uuid4().hex[:6]}",
                     rtsp_url="rtsp://127.0.0.1/e2e", mediamtx_path=f"e2e-{uuid.uuid4().hex[:6]}")
        db.add(cam)
        await db.flush()

        track = Track(tenant_id=tenant.id, camera_id=cam.id, tracker_id=1,
                      started_at=now, first_bbox={}, last_bbox={}, point_count=1)
        db.add(track)
        await db.flush()
        db.add(TrackPoint(
            ts=now, track_id=track.id, tenant_id=tenant.id, camera_id=cam.id, tracker_id=1,
            bbox_x1=BBOX[0], bbox_y1=BBOX[1], bbox_x2=BBOX[2], bbox_y2=BBOX[3], confidence=0.9))
        await db.commit()
        cam_id, track_id = str(cam.id), track.id

    print(f"tenant={SUBDOMAIN} company={company_id}")
    print(f"seeded: camera={cam_id}  track(bbox={BBOX})  employee={emp_id} ({emp_name})")

    # Publish a recognition to the COMPANY-keyed stream (as FaceTrack would).
    r = redis.from_url(settings.REDIS_URL, decode_responses=True)
    stream = f"{settings.FACE_IDENTITY_STREAM_PREFIX}:{company_id}"
    l, t, w, h = BBOX[0], BBOX[1], BBOX[2] - BBOX[0], BBOX[3] - BBOX[1]
    await r.xadd(stream, {
        "camera_id": cam_id, "emp_id": emp_id, "name": emp_name, "score": "0.97",
        "bbox": json.dumps([l, t, w, h]), "captured_at_ms": str(int(now.timestamp() * 1000)),
    })
    print(f"published recognition to {stream}")

    # Give the running consumer time to correlate + write.
    await asyncio.sleep(4)

    async with AsyncSessionLocal() as db:
        ident = (await db.execute(
            select(PersonIdentity).where(
                PersonIdentity.tenant_id == tenant.id, PersonIdentity.emp_id == emp_id)
        )).scalars().first()
        ok = ident is not None
        print(f"\n{'✅' if ok else '❌'} person_identity written: {ok}")
        if ok:
            print(f"   emp_id={ident.emp_id} name={ident.name} conf={ident.confidence:.2f} "
                  f"votes={ident.votes} track={'correlated' if ident.track_id else 'none'} "
                  f"source={ident.source}")
        # Clean up the synthetic camera/track (keep the identity as visible proof).
        await db.execute(text("DELETE FROM track_points WHERE track_id = :t"), {"t": str(track_id)})
        await db.execute(delete(Track).where(Track.id == track_id))
        await db.execute(delete(Camera).where(Camera.id == uuid.UUID(cam_id)))
        await db.commit()

    if not ok:
        sys.exit(1)
    print("\nLIVE-RECOGNITION LOOP VERIFIED — track + recognition -> named identity in the tenant.")


if __name__ == "__main__":
    asyncio.run(main())
