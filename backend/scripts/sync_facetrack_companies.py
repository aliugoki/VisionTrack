"""Sync companies from FaceTrack into VisionTrack.

Reflects FaceTrack's ``companies`` (company_id, company_name, admin_username,
status) into VisionTrack's ``companies`` table. Secrets (password hashes,
session tokens, api keys) are deliberately NOT copied. Idempotent: upserts on
(tenant_id, external_id).

Run where both DBs are reachable (e.g. --network host):

    FACETRACK_DATABASE_URL=postgresql://postgres:PW@localhost:5432/facial_recognition_db \
    VT_DATABASE_URL=postgresql://visiontrack:PW@localhost:15432/visiontrack \
    python -m scripts.sync_facetrack_companies
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
    fc.execute("SELECT company_id, company_name, admin_username, status FROM companies")
    rows = fc.fetchall()

    now = datetime.now(timezone.utc)
    n = 0
    for company_id, company_name, admin_username, status in rows:
        if not company_id:
            continue
        vc.execute(
            """
            INSERT INTO companies
              (id, tenant_id, external_id, name, admin_username, status,
               source, is_active, synced_at, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, 'facetrack', true, %s, now(), now())
            ON CONFLICT (tenant_id, external_id) DO UPDATE SET
              name = EXCLUDED.name,
              admin_username = EXCLUDED.admin_username,
              status = EXCLUDED.status,
              synced_at = EXCLUDED.synced_at,
              updated_at = now()
            """,
            (str(uuid.uuid4()), tenant, str(company_id),
             company_name or str(company_id), admin_username, status, now),
        )
        n += 1

    vt.commit()
    print(f"synced {n} companies from FaceTrack into VisionTrack tenant {tenant}")
    ft.close()
    vt.close()


if __name__ == "__main__":
    main()
