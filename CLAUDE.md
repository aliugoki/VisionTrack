# VisionTrack — Claude Code Project Context

## What this is
Enterprise multi-tenant CCTV people-tracking SaaS. Pakistan + Gulf market focus
under TaxJar.pk branding.

## Architecture (high level)
- Frontend: React 18 + Vite + TS + Tailwind. Path aliases use `@/shared/*`,
  `@/modules/<name>/`, `@/layouts/`. Premium SaaS aesthetic (TaxJar green
  #2E9456, Plus Jakarta Sans / Inter).
- Backend: FastAPI + SQLAlchemy 2 async + Alembic. Modular under
  `backend/app/modules/<name>/{router,schemas,service,models}.py`.
- DB: PostgreSQL 16 + pgvector 0.7.2 (no TimescaleDB extension despite the
  image tag). Migrations via Alembic; head currently 0014.
- Streaming infra: MediaMTX (HLS + RTSP), Redis (streams + pubsub), MinIO
  (recordings), Milvus 2.4.13 + etcd (embedding vector store).
- AI workers: two of them.
  - `ai-worker` (P1): legacy, stable, currently emitting track events via
    Socket.IO. Up 24+ hours.
  - `ai-worker-ds` (P2): DeepStream 7.1 pipeline (pgie + tracker → fakesink
    in P2.2 baseline). SGIE + probe + embedding extraction deferred to P2.3b
    due to pyds metadata-dispatch segfault (documented in
    ~/visiontrack-checkpoints/p2-3-deferred/README.md).

## Auth
- JWT-based, tenant-scoped via current_user.tenant_id on every query.
- Permission constants in `backend/app/core/permissions.py` and
  `frontend/src/shared/lib/permissions.ts` (TRACK_READ, CAMERA_READ, etc).
- Seeded admin user is admin@visiontrack.io (dev password ChangeMe123!,
  per docker-compose.yml first-login note).

## Tenant constant
Current single tenant UUID: 4ae93489-babb-4e8e-a476-c64f9bc8f64b

## Camera constant
Head Office HEVC camera UUID: 8a0b2ad4-7173-45e0-8f35-88a940ff460e
mediamtx_path: cam-8a0b2ad47173

## Frontend conventions
- React Query for server state. Hooks live in `<module>/api.ts`.
- Shared components in `frontend/src/shared/components/`: Card, Button
  (variant/size), Input, Badge (tone: neutral/success/warning/danger/primary),
  Spinner, Dialog, Select.
- i18n: `frontend/src/shared/i18n/locales/{en,ar}.json`. EVERY UI string goes
  in both files. Arabic uses RTL-aware spacing classes (me-/ms-, rotate-180
  on chevrons).
- Routes registered in `frontend/src/App.tsx`. Nav items in
  `frontend/src/layouts/AppLayout.tsx` under one of: Monitoring,
  Configuration, Administration groups.
- Permission-gate every nav item that surfaces data.
- Date display uses `Intl.DateTimeFormat(i18n.language === 'ar' ? 'ar-EG' :
  'en-US', ...)`.

## Backend conventions
- Every router endpoint requires `current_user=Depends(RequirePermission(<P>))`.
- Every query filters by `tenant_id == current_user.tenant_id`.
- Schemas mirror models with `model_config = ConfigDict(from_attributes=True)`.
- Migrations only via Alembic — never manual DDL.
- Tests use pytest-asyncio.

## Docker
- All services in `docker-compose.yml`. Use `docker compose` (v2), not
  `docker-compose`.
- Frontend dev runs with Vite HMR on :5173 (mounts host src).
- Backend reloads with --reload flag.
- AI worker images are large (26 GB for ai-worker-ds). Avoid rebuilding
  unless necessary; image rebuild today caused a libstdc++ ABI regression.

## Today's known-good state (2026-06-09 EOD)
Persons UI, CameraActivityPanel, and Analytics "Cross-camera identities"
section are live and working. ai-worker-ds is on the P2-3a-stable code
(no SGIE/probe; backend P2.3 infra running but reading empty stream).

## DON'T do
- Don't propose schema changes that bypass Alembic.
- Don't add Python/JS dependencies without flagging — every dep adds image
  rebuild time.
- Don't suggest tearing down Docker volumes; data lives there.
- Don't break tenant scoping (every query must include tenant_id).
- Don't change brand colors or typography without asking.
- Don't add unrequested files. If a one-file solution exists, prefer it.

## Working style
- Direct, concise, results-oriented. No preamble.
- When making changes, run typecheck/build verification before claiming
  done.
- Reference Pakistani business context where relevant (PKR currency, +92
  phones, FBR/PRA/NTN, CNIC format).
- Checkpoints go to ~/visiontrack-checkpoints/ (vt-db-*.dump +
  vt-code-*.tar.gz).
