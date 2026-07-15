"""Cross-tenant leakage test suite (multi-tenant Phase 5).

Proves that one tenant cannot see or modify another tenant's data across the API.
Runs against a live server (default http://localhost:18000). Logs in as two
different company admins and a platform admin, then probes cross-tenant access.

    python scripts/check_tenant_isolation.py [BASE_URL]

Exits non-zero on the first failed assertion (a real isolation leak).
"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:18000") + "/api/v1"

# Provisioned per-company admins (Phase 1) + the platform admin.
A_EMAIL = "admin@metaxperts.visiontrack.local"
B_EMAIL = "admin@sabri-solutions.visiontrack.local"
PLATFORM_EMAIL = "admin@visiontrack.io"
PW = "ChangeMe123!"


def req(method, path, token=None, body=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw


def login(email):
    st, d = req("POST", "/auth/login", body={"email": email, "password": PW})
    assert st == 200, f"login {email} -> {st} {d}"
    return d["access_token"]


PASS = 0


def check(cond, msg):
    global PASS
    if not cond:
        print(f"  ✗ LEAK: {msg}")
        sys.exit(1)
    PASS += 1
    print(f"  ✓ {msg}")


def main():
    a = login(A_EMAIL)      # MetaXperts admin
    b = login(B_EMAIL)      # Sabri admin
    p = login(PLATFORM_EMAIL)
    print("logged in: A=MetaXperts, B=Sabri, P=platform")

    # A's own tenant + a site to create a resource in.
    _, a_tenant = req("GET", "/tenants/me", a)
    _, sites = req("GET", "/sites", a)
    a_site = (sites[0]["id"] if isinstance(sites, list) and sites else None)
    check(a_site is not None, "A has a site to create resources in")

    # A creates a camera in its own tenant (unique name so re-runs never collide).
    cam_name = f"ISO-TEST-CAM-{os.urandom(3).hex()}"
    st, cam = req("POST", "/cameras", a, {
        "name": cam_name, "site_id": a_site, "rtsp_url": "rtsp://127.0.0.1/isotest",
    })
    check(st == 201, f"A creates a camera (201, got {st})")
    cam_id = cam["id"]

    print("\n[cross-tenant read]")
    st, _ = req("GET", f"/cameras/{cam_id}", b)
    check(st == 404, f"B cannot GET A's camera by id (404, got {st})")
    _, b_cams = req("GET", "/cameras", b)
    b_ids = [c["id"] for c in (b_cams or [])] if isinstance(b_cams, list) else []
    check(cam_id not in b_ids, "A's camera is NOT in B's camera list")

    print("\n[cross-tenant write]")
    st, _ = req("PATCH", f"/cameras/{cam_id}", b, {"name": "HACKED"})
    check(st == 404, f"B cannot PATCH A's camera (404, got {st})")
    st, _ = req("DELETE", f"/cameras/{cam_id}", b)
    check(st == 404, f"B cannot DELETE A's camera (404, got {st})")
    # confirm A's camera survived B's attempts
    st, cam2 = req("GET", f"/cameras/{cam_id}", a)
    check(st == 200 and cam2["name"] == cam_name, "A's camera is untouched by B")

    print("\n[list scoping]")
    _, a_emps = req("GET", "/employees", a)
    _, b_emps = req("GET", "/employees", b)
    # NB: FaceTrack emp_ids are per-company numbers that repeat across companies,
    # so overlapping emp_id VALUES are expected and are not a leak — the rows are
    # still tenant-scoped (the camera by-id test above proves the mechanism).
    check(a_emps["total"] > 0 and b_emps["total"] > 0, "both tenants have their own employees")
    check(a_emps["total"] != b_emps["total"], "A and B see different-sized employee rosters (scoped)")
    _, a_users = req("GET", "/users", a)
    a_user_emails = {u["email"] for u in a_users}
    check(B_EMAIL not in a_user_emails, "A's user list does NOT include B's admin")

    print("\n[platform access control]")
    st, _ = req("GET", "/platform/tenants", a)
    check(st == 403, f"tenant admin A blocked from /platform/tenants (403, got {st})")
    st, _ = req("POST", f"/platform/tenants/{a_tenant['id']}/enter", b)
    check(st == 403, f"tenant admin B cannot enter tenants (403, got {st})")

    # cleanup
    req("DELETE", f"/cameras/{cam_id}", a)

    print(f"\n✅ NO CROSS-TENANT LEAKS — {PASS} isolation checks passed")


if __name__ == "__main__":
    main()
