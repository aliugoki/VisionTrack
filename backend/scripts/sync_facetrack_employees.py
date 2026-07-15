"""Sync the employee roster from FaceTrack into VisionTrack.

FaceTrack (the face-recognition system) owns the roster in its ``user_data``
table. VisionTrack's ``employees`` table is a synced copy so the dashboard can
show and filter by employee. ``emp_id`` is the shared key the face-identity
bridge stamps onto ``person_identities``, so a synced employee links to their
tracked identity.

Because the two databases live on different networks, run this where both are
reachable (e.g. a ``--network host`` container):

    FACETRACK_DATABASE_URL=postgresql://postgres:PW@localhost:5432/facial_recognition_db \
    VT_DATABASE_URL=postgresql://visiontrack:visiontrack@localhost:15432/visiontrack \
    python -m scripts.sync_facetrack_employees

Idempotent: upserts on (tenant_id, emp_id). Target tenant = ``VT_TENANT_ID`` or,
if unset, the oldest tenant in VisionTrack (fine for a single-tenant install).
"""
import os
import sys
import uuid
from datetime import datetime, timezone

import psycopg2


def main() -> None:
    ft_url = os.environ.get("FACETRACK_DATABASE_URL")
    vt_url = os.environ.get("VT_DATABASE_URL")
    if not ft_url or not vt_url:
        sys.exit("set FACETRACK_DATABASE_URL and VT_DATABASE_URL")

    ft = psycopg2.connect(ft_url)
    vt = psycopg2.connect(vt_url)
    vc = vt.cursor()

    tenant = os.environ.get("VT_TENANT_ID")
    if not tenant:
        vc.execute("SELECT id FROM tenants ORDER BY created_at LIMIT 1")
        row = vc.fetchone()
        if not row:
            sys.exit("no tenant in VisionTrack — seed one first")
        tenant = str(row[0])

    fc = ft.cursor()
    fc.execute(
        "SELECT emp_id, first_name, last_name, company_id, image_path FROM user_data"
    )
    rows = fc.fetchall()

    now = datetime.now(timezone.utc)
    n = 0
    for emp_id, first_name, last_name, company_id, image_path in rows:
        if not emp_id:
            continue
        vc.execute(
            """
            INSERT INTO employees
              (id, tenant_id, emp_id, first_name, last_name,
               external_company_id, image_path, source, synced_at, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'facetrack', %s, now())
            ON CONFLICT (tenant_id, emp_id) DO UPDATE SET
              first_name = EXCLUDED.first_name,
              last_name = EXCLUDED.last_name,
              external_company_id = EXCLUDED.external_company_id,
              image_path = EXCLUDED.image_path,
              synced_at = EXCLUDED.synced_at
            """,
            (str(uuid.uuid4()), tenant, str(emp_id), first_name, last_name,
             company_id, image_path, now),
        )
        n += 1

    vt.commit()
    print(f"synced {n} employees from FaceTrack into VisionTrack tenant {tenant}")
    ft.close()
    vt.close()


if __name__ == "__main__":
    main()
