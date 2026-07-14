# VisionTrack

Enterprise-grade people-tracking platform for factories, warehouses, and facilities. Built on the NVIDIA Metropolis / DeepStream stack for production deployments.

This repository is the **Step 1 scaffold** — a complete, runnable foundation with multi-tenant auth, granular role-based permissions (EN + AR i18n), 13 domain modules stubbed, and Docker orchestration for all required infrastructure (PostgreSQL+TimescaleDB, Redis, MinIO, MediaMTX). The detection pipeline and module business logic are built progressively in Steps 2–13.

---

## Quick start

Prerequisites: Docker Desktop 4.20+ (or Docker Engine 24+) and `make`.

```bash
# Clone, then from the repo root:
make up

# First boot takes ~2 minutes (image pulls + npm install + DB migrations + seeding).
# Watch the logs:
make logs
```

When it's ready:

| Service     | URL                          | Notes                                        |
| ----------- | ---------------------------- | -------------------------------------------- |
| Frontend    | http://localhost:5173        | The operator/admin dashboard                 |
| Backend API | http://localhost:8000/docs   | Swagger UI with the full OpenAPI spec        |
| MinIO       | http://localhost:9001        | S3-compatible object storage console         |
| MediaMTX    | rtsp://localhost:8554        | RTSP ingest point for cameras                |

**First-login credentials** (seeded automatically):

- **Email:** `admin@visiontrack.io`
- **Password:** `ChangeMe123!`

Change these in `backend/.env` before any non-local deployment.

---

## Architecture

Five tiers, designed so the AI pipeline can be swapped (YOLOv8 → DeepStream → MV3DT) without changing the API or frontend.

```
Cameras (RTSP)
   ↓
MediaMTX (ingest + HLS republish + recording)
   ↓
AI Worker (detection + tracking on GPU)         ←─ swappable: YOLOv8 today, DeepStream tomorrow
   ↓
Redis Streams (events bus)
   ↓
FastAPI backend (REST + Socket.IO + Celery)
   ↓
PostgreSQL (entities) + TimescaleDB (tracks) + MinIO (clips)
   ↓
React frontend (live wall, floor plan, alerts, recordings, analytics)
```

The full architecture diagram lives in `docs/architecture.md` (to be written in Step 2).

## Documentation

- [`docs/SPATIAL_ANALYTICS.md`](docs/SPATIAL_ANALYTICS.md) — indoor geofencing &
  reporting: zones, calibration (homography), occupancy / dwell / timeline /
  attendance / zone-rollup, the report route (CSV + printable PDF), filters,
  code map, and how to run the tests.
- [`docs/MV3DT.md`](docs/MV3DT.md) — multi-view 3D tracking / cross-camera fusion.
- [`docs/DEPLOY_BOTH_SYSTEMS.md`](docs/DEPLOY_BOTH_SYSTEMS.md) — deploying
  VisionTrack alongside FaceTrack.

---

## What's in this scaffold

### Backend (`backend/`)

**Fully implemented:**
- Core layer: config (Pydantic Settings), async SQLAlchemy 2.0, JWT auth, structured logging, the **permission registry** with 50+ named permission keys across 13 groups
- Auth module: login (JSON + OAuth2 form for Swagger), refresh, logout, password change
- Tenants module: multi-tenant root entity
- Users module: full CRUD with permission-gated routes, password change, `/me` endpoint
- Roles module: full CRUD + public permission catalog endpoint that the frontend uses to render the permission matrix UI
- First-run seeder: creates demo tenant, four default roles (Tenant Admin / Supervisor / Operator / Viewer), and the superuser
- Alembic migration that creates all four tables + installs the TimescaleDB extension

**Scaffolded (router stubs, ready to be filled in):**
- `sites`, `cameras`, `zones`, `employees`, `tracks`, `events`, `alerts`, `recordings`, `analytics`, `realtime`

### Frontend (`frontend/`)

**Fully implemented:**
- Vite + React 18 + TypeScript + TailwindCSS with a refined command-center dark theme
- i18n bootstrap with English and Arabic resources, automatic RTL switching when Arabic is selected
- Auth flow: login page, persistent token store (Zustand + localStorage), axios client with refresh-token interceptor
- Layout shell: sidebar nav (grouped: Monitoring / Configuration / Administration), top bar with language switcher, user pod with logout
- Permission-aware navigation: menu items only appear when the user has the required permission
- Dashboard overview page with stat cards
- Placeholder pages for all 11 module routes (live wall, floor plan, cameras, zones, employees, alerts, recordings, analytics, users, roles, settings)

### Infrastructure (`docker-compose.yml`)

- PostgreSQL 16 + TimescaleDB 2.17 (ready for high-volume track storage)
- Redis 7 (events, cache, Celery broker)
- MinIO + auto-bucket initialization (recordings + snapshots)
- MediaMTX 1.9 (RTSP ingest → HLS + WebRTC + recording)
- Hot-reloading dev containers for backend (uvicorn `--reload`) and frontend (Vite HMR)

---

## Granular permission system

Every protected action in VisionTrack is a string like `camera:create` or `alert:acknowledge`. Roles are bags of these strings, scoped to tenants. The full catalog is in `backend/app/core/permissions.py` and exposed via `GET /api/v1/roles/permissions` so the frontend can render the permission-matrix UI dynamically.

Four default roles are seeded for every new tenant:

| Role          | Purpose                                                       |
| ------------- | ------------------------------------------------------------- |
| Tenant Admin  | Full access to everything in the tenant                       |
| Supervisor    | Operations + reporting + alert management + evacuation        |
| Operator      | Live monitoring + alert acknowledgement + muster confirmation |
| Viewer        | Read-only — reports and analytics                             |

These are `is_system` and cannot be deleted, but their permissions are editable. Tenant Admins can also create entirely custom roles.

**Reserved for Phase 2.5** (evacuation accountability module): the permission keys `evacuation:trigger`, `evacuation:read`, `evacuation:confirm_safe`, `evacuation:generate_report`, and `muster_point:manage` are already in the catalog and granted to the appropriate default roles. The module itself ships after the DeepStream migration.

---

## A note on ONVIF auto-discovery

The Cameras module includes a WS-Discovery probe that finds ONVIF-compliant cameras on the local network. **For discovery to actually find anything, the backend container must be on the same L2 broadcast domain as your cameras** — Docker's default bridge network doesn't carry LAN multicast.

On Linux hosts, the simplest fix is to run the backend with host networking:

```yaml
# docker-compose.override.yml
services:
  backend:
    network_mode: host
```

On macOS / Windows Docker Desktop, host networking has limitations and the cleanest approach is to deploy a small `onvif-probe` sidecar on the host that POSTs results back to the backend. We'll wire that up when the first client needs it.

Manual RTSP URL entry works in any network setup and is the recommended path for the pilot.

---

## Common commands

```bash
make up              # Start the stack
make down            # Stop (preserves volumes)
make logs            # Tail logs
make ps              # Show running services

make migrate         # Run pending migrations
make revision m="..."# Auto-generate a new migration

make shell-backend   # Open a shell in the backend container
make shell-db        # psql into the database

make reset           # DANGER: wipe all volumes
```

---

## Roadmap

| Phase  | Deliverable                                                    | Tracker                    |
| ------ | -------------------------------------------------------------- | -------------------------- |
| 1      | This scaffold + cameras + zones + alerts + recordings + live wall | YOLOv8 + ByteTrack         |
| 2      | DeepStream migration — same product, GPU-accelerated           | NvDCF + ReIdentificationNet |
| 2.5    | Evacuation accountability module                               | (same)                     |
| 3      | Multi-camera ReID handoff → MV3DT for sites with overlap       | Cross-camera fusion        |
| 4      | Multi-tenant SaaS, billing, edge Jetson, alarm panel adapters  | (same)                     |

**Next step:** Step 2 builds the Cameras module — RTSP camera CRUD, MediaMTX integration so each camera becomes browser-viewable via HLS, and the live-camera-card UI.

---

## License

Proprietary — © TaxJar.pk. All rights reserved.
