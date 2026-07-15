# Multi-Tenant Isolation per Company — Scope & Plan

Goal: each **FaceTrack company** becomes its own isolated **VisionTrack tenant**
(own cameras, floor plans, zones, tracks, employees, analytics). A user from
Company A sees only Company A; a **platform super-admin** can enter any company.

---

## 1. The good news — ~80% already exists

VisionTrack was built multi-tenant from day one:

- Every domain table carries `tenant_id` (`cameras`, `floor_plans`, `tracks`,
  `track_points`, `persons`, `person_identities`, `employees`, `companies`,
  `alerts`, `recordings`, …).
- Every service query filters on `tenant_id` from the JWT.
- The face-identity Redis bridge is already keyed per tenant
  (`vt:face:identities:<tenant_id>`).
- Roles/permissions are tenant-scoped and seeded per tenant.

So isolation isn't something to *build* — it's something to **populate**
(one tenant per company) and **expose** (platform admin + tenant switching).

## 2. The gap

| # | Gap | Today |
|---|---|---|
| 1 | One tenant per company | 1 tenant holds everything; companies are rows |
| 2 | Company→tenant mapping | no `tenants.external_company_id` |
| 3 | Tenant provisioning | only the seed makes 1 tenant (roles + 1 admin) |
| 4 | Platform super-admin | auth is single-tenant; no cross-tenant role/view |
| 5 | Tenant switching | JWT has a fixed `tid`; no switch |
| 6 | Bridges target the right tenant | employee/company sync + face bridge point at 1 tenant |
| 7 | Camera/pipeline per tenant | cameras + AI-worker events need per-company scoping |

## 3. Target design

```
FaceTrack company (company_id) ──1:1──▶ VisionTrack tenant (external_company_id)
        ├─ employees ───────────────────▶ employees (tenant_id)
        ├─ cameras ─────────────────────▶ cameras (tenant_id)
        └─ recognitions ──Redis──▶ vt:face:identities:<tenant_id> (mapped by company_id)

Platform super-admin ──▶ list tenants ──▶ pick company ──▶ mint tenant-scoped token ──▶ enters tenant
```

- Add `tenants.external_company_id` (unique) — the canonical company↔tenant link.
- The `companies` table becomes the *provisioning source* (one tenant per row);
  the tenants themselves become the companies.

## 4. Auth model (the crux)

**(a) Where do company users' credentials live?**
- **Option A — provisioned local users** (chosen for Phase 1): each company gets a
  VisionTrack admin user at provisioning (self-contained).
- **Option B — SSO/token federation from FaceTrack**: users log into FaceTrack;
  VisionTrack trusts a FaceTrack-issued token (needs a shared token contract).

**(b) Platform super-admin movement — recommended: tenant-switch tokens.** The
platform admin authenticates once, lists tenants, picks one, and the backend
**mints a new JWT scoped to that tenant's `tid`**. Every existing query then just
works (they already filter by `tid`) — no query rewrites, no leakage risk. Avoid
a superuser flag that bypasses the tenant filter.

## 5. Bridges & data (make them tenant-aware)

- **Company sync → tenant provisioning:** upsert a tenant per FaceTrack company
  (by `external_company_id`) + seed roles + admin user.
- **Employee sync:** route each employee to `tenant(external_company_id =
  employee.company_id)`.
- **Face-identity bridge:** FaceTrack publishes per `company_id`; VisionTrack maps
  `company_id → tenant_id`. *(Needs a small FaceTrack-side keying change or a
  mapping VisionTrack owns.)*
- **Cameras & pipeline:** cameras live under their company's tenant; the AI worker
  tags events with the tenant.

## 6. Migration path (no data loss)

1. Add `tenants.external_company_id` (nullable). Keep the demo tenant.
2. Provision a tenant per existing company (backfill).
3. Re-assign already-synced employees to their company's tenant.
4. Demo cameras/floor plans → assign to a company or keep a "Demo" tenant.
5. Flip the syncs to tenant-aware. All additive; reversible.

## 7. Phased plan

| Phase | Deliverable | Status |
|---|---|---|
| **0** | Decisions (auth source, platform model, GPU model) | — |
| **1** | `tenants.external_company_id` + company→tenant provisioning + backfill | **in progress** |
| **2** | Platform super-admin: platform role, `GET /platform/tenants`, tenant-switch token, switcher UI | planned |
| **3** | Tenant-aware bridges: employee sync per tenant, face-identity company→tenant map, cameras per tenant | planned |
| **4** | Lifecycle: auto-provision on new company, suspend, cascade delete, per-tenant settings | planned |
| **5** | Hardening: cross-tenant leakage tests, quotas, audit, docs | planned |

## 8. Key decisions

1. **Auth:** provisioned local users (A) vs SSO from FaceTrack (B). *Phase 1 uses A.*
2. **Platform admin:** confirm tenant-switch-token model.
3. **GPU/pipeline:** one shared AI worker (scoped by tenant) vs per-tenant workers.
4. **Face bridge:** can FaceTrack's publisher key events by `company_id`?
5. **Demo data:** assign to a company vs keep a "Demo" tenant.
6. **Routing:** single app + tenant switcher (recommended) vs subdomain-per-company.

## 9. Recommendation

Do **Phase 1 + 2 first** — provision a tenant per company and add the platform
switch. That delivers real, clickable per-company isolation on top of the tenant
scoping that already exists. Phase 3 then wires the live FaceTrack bridges per
tenant. The one external dependency is **#4 (face-bridge keying)**; everything
else is self-contained in VisionTrack.
