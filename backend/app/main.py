"""FastAPI application factory.

This is the entrypoint that uvicorn loads. It:
  - Configures structured logging
  - Sets up CORS for the React frontend
  - Mounts every module's router under /api/v1
  - Mounts the Socket.IO server at /socket.io for live track broadcast
  - Seeds the database on first startup
  - Re-registers cameras with MediaMTX on startup (paths don't persist)
  - Starts the Redis -> TimescaleDB track consumer
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import settings
from app.core.db import AsyncSessionLocal, engine
from app.core.logging import configure_logging, get_logger
# Eagerly load every ORM model so SQLAlchemy mapper relationships resolve
# in every process that imports this module. Required for Alembic and
# any ad-hoc script that uses app.core.db without importing model modules
# transitively.
from app.core import models as _models  # noqa: F401
from app.core.seed import seed_initial_data

# Module routers
from app.modules.alerts.router import router as alerts_router
from app.modules.analytics.router import router as analytics_router
from app.modules.auth.router import router as auth_router
from app.modules.cameras.router import router as cameras_router
from app.modules.companies.router import router as companies_router
from app.modules.employees.router import router as employees_router
from app.modules.events.router import router as events_router
from app.modules.floor_plans.router import router as floor_plans_router
from app.modules.live_wall.router import router as live_wall_router
from app.modules.persons.router import router as persons_router
from app.modules.realtime.router import router as realtime_router
from app.modules.realtime.socketio_app import socket_app
from app.modules.recordings.router import router as recordings_router
from app.modules.roles.router import router as roles_router
from app.modules.sites.router import router as sites_router
from app.modules.tenants.router import router as tenants_router
from app.modules.tracks.consumer import consumer as track_consumer
from app.modules.persons.consumer import consumer as embedding_consumer
from app.modules.persons.face_identity_consumer import consumer as face_identity_consumer
from app.modules.persons.matcher import matcher as person_matcher
from app.modules.mv3dt.fuser import fuser as mv3dt_fuser
from app.modules.tracks.router import router as tracks_router
from app.modules.users.router import router as users_router
from app.modules.zones.router import router as zones_router

configure_logging()
log = get_logger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("app.startup", env=settings.APP_ENV, version="0.1.0")

    # Wait for DB to be ready, then seed
    async with AsyncSessionLocal() as db:
        await db.execute(text("SELECT 1"))
        await seed_initial_data(db)

    # Re-register all cameras with MediaMTX. MediaMTX doesn't persist
    # runtime-added paths across restarts, so this is critical for cameras
    # to stream after a MediaMTX or backend bounce. Best-effort.
    try:
        from app.modules.cameras.service import sync_all_cameras_to_mediamtx
        async with AsyncSessionLocal() as db:
            counts = await sync_all_cameras_to_mediamtx(db)
            await db.commit()
        log.info("app.mediamtx_sync_done", **counts)
    except Exception as e:
        log.warning("app.mediamtx_sync_failed", error=str(e))

    # Start the Redis Streams -> TimescaleDB + Socket.IO consumer. It
    # spawns background tasks per tenant; they run for the lifetime of
    # the process.
    try:
        await track_consumer.start()
    except Exception as e:
        log.warning("app.track_consumer_failed", error=str(e))
    # P2.3 — connect to Milvus + start the embedding consumer. Both are
    # best-effort: if Milvus is unavailable we still run, pgvector writes
    # work fine; the embedding consumer keeps trying.
    try:
        from app.core import milvus as milvus_module
        milvus_module.connect()
    except Exception as e:
        log.warning("app.milvus_connect_failed", error=str(e))

    try:
        await embedding_consumer.start()
    except Exception as e:
        log.warning("app.embedding_consumer_failed", error=str(e))

    # Face identity feed — labels Persons with external (face-recognition)
    # identities correlated by camera + bbox + time. Gated by a flag.
    if settings.FACE_IDENTITY_ENABLED:
        try:
            await face_identity_consumer.start()
        except Exception as e:
            log.warning("app.face_identity_consumer_failed", error=str(e))

    # P2.5 — start the cross-camera matcher. Sweeps unmatched embeddings into
    # Person identities. Gated by a flag so ops/tests can disable it.
    if settings.MATCHER_ENABLED:
        try:
            await person_matcher.start()
        except Exception as e:
            log.warning("app.matcher_failed", error=str(e))

    # MV3DT Phase A — multi-view fuser. Stitches per-camera tracks into
    # site-wide global trajectories. Gated by a flag.
    if settings.MV3DT_ENABLED:
        try:
            await mv3dt_fuser.start()
        except Exception as e:
            log.warning("app.fuser_failed", error=str(e))


    # Start the alerts Redis pub/sub -> Socket.IO bridge. Celery worker
    # publishes fired alerts to vt:alerts:<tenant_id>; this bridge
    # consumes and forwards to connected Socket.IO clients.
    try:
        from app.modules.alerts.realtime_bridge import alerts_realtime_bridge
        await alerts_realtime_bridge.start()
    except Exception as e:
        log.warning("app.alerts_bridge_failed", error=str(e))

    log.info("app.ready")

    yield

    # Stop the consumer first so it doesn't try to use the DB after
    # we tear the engine down.
    try:
        await track_consumer.stop()
    except Exception as e:
        log.warning("app.track_consumer_stop_failed", error=str(e))
    try:
        await embedding_consumer.stop()
    except Exception as e:
        log.warning("app.embedding_consumer_stop_failed", error=str(e))
    try:
        await face_identity_consumer.stop()
    except Exception as e:
        log.warning("app.face_identity_consumer_stop_failed", error=str(e))
    try:
        await person_matcher.stop()
    except Exception as e:
        log.warning("app.matcher_stop_failed", error=str(e))
    try:
        await mv3dt_fuser.stop()
    except Exception as e:
        log.warning("app.fuser_stop_failed", error=str(e))

    try:
        from app.core import milvus as milvus_module
        milvus_module.disconnect()
    except Exception as e:
        log.warning("app.milvus_disconnect_failed", error=str(e))


    try:
        from app.modules.alerts.realtime_bridge import alerts_realtime_bridge
        await alerts_realtime_bridge.stop()
    except Exception as e:
        log.warning("app.alerts_bridge_stop_failed", error=str(e))

    await engine.dispose()
    log.info("app.shutdown")


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description="Enterprise people-tracking platform built on NVIDIA Metropolis (MV3DT).",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.APP_NAME, "env": settings.APP_ENV}


# Mount all module routers under the API prefix
api_prefix = settings.API_V1_PREFIX
for r in (
    auth_router,
    users_router,
    roles_router,
    sites_router,
    tenants_router,
    cameras_router,
    zones_router,
    employees_router,
    companies_router,
    tracks_router,
    events_router,
    alerts_router,
    recordings_router,
    analytics_router,
    realtime_router,
    live_wall_router,
    persons_router,
    floor_plans_router,
):
    app.include_router(r, prefix=api_prefix)


# Mount the Socket.IO ASGI sub-app at /socket.io. The Vite proxy is
# already configured to forward /socket.io traffic (including WS upgrade)
# to the backend on port 8000.
app.mount("/socket.io", socket_app)
