"""Sync the employee roster from FaceTrack into VisionTrack — tenant-aware.

Each FaceTrack employee is routed to its company's VisionTrack tenant
(``tenant.external_company_id = user_data.company_id``), so a company's employees
land in that company's isolated tenant (multi-tenant Phase 3). Employees whose
company has no provisioned tenant are skipped. Idempotent; also cleans up
employees left in the wrong tenant by earlier single-tenant syncs.

Secrets are never copied. Run where both DBs are reachable (--network host):

    FACETRACK_DATABASE_URL=postgresql://postgres:PW@localhost:5432/facial_recognition_db \
    VT_DATABASE_URL=postgresql://visiontrack:PW@localhost:15432/visiontrack \
    python -m scripts.sync_facetrack_employees
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

    # company_id -> tenant_id from provisioned tenants.
    vc.execute("SELECT external_company_id, id FROM tenants WHERE external_company_id IS NOT NULL")
    company_to_tenant = {row[0]: row[1] for row in vc.fetchall()}
    if not company_to_tenant:
        sys.exit("no tenants have external_company_id — run provision_tenants_from_companies first")

    fc = ft.cursor()
    fc.execute(
        "SELECT emp_id, first_name, last_name, company_id, image_path FROM user_data"
    )
    rows = fc.fetchall()

    now = datetime.now(timezone.utc)
    synced = skipped = 0
    for emp_id, first_name, last_name, company_id, image_path in rows:
        if not emp_id:
            continue
        tenant = company_to_tenant.get(company_id)
        if tenant is None:
            skipped += 1  # this company has no VisionTrack tenant yet
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
            (str(uuid.uuid4()), str(tenant), str(emp_id), first_name, last_name,
             company_id, image_path, now),
        )
        synced += 1

    # Remove FaceTrack employees stranded in the wrong tenant (e.g. the demo
    # tenant from an earlier single-tenant sync).
    vc.execute(
        """
        DELETE FROM employees e
        WHERE e.source = 'facetrack' AND e.external_company_id IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM tenants t
            WHERE t.id = e.tenant_id AND t.external_company_id = e.external_company_id
          )
        """
    )
    removed = vc.rowcount
    vt.commit()
    print(f"synced {synced} employees across {len(company_to_tenant)} tenants; "
          f"skipped {skipped} (no tenant); removed {removed} mis-assigned")
    ft.close()
    vt.close()


if __name__ == "__main__":
    main()
